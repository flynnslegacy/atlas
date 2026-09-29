"""L'entretien du Core depuis la page : la version, le redémarrage (la marque, puis l'arrêt), et
la mise à jour, sur de vrais dépôts git temporaires (une origine locale : aucun réseau)."""

import asyncio
import os
import subprocess
from pathlib import Path

import pytest

from atlas_core import entretien as module
from atlas_core.entretien import (
    DEJA_A_JOUR,
    ECHEC_INSTALLATION,
    ECHEC_RECUPERATION,
    OCCUPE,
    Entretien,
    marque,
)
from atlas_core.protocole_web import CoreEnCours, FinCore

REUSSIT = ("sh", "-c", "echo installé > installe")
RATE = ("sh", "-c", "echo 'uv : paquet introuvable' >&2; exit 2")


def lente(dossier) -> tuple[str, ...]:
    """Une installation qui lance un sous-processus et l'attend, comme make lance uv."""
    return ("sh", "-c", f"sleep 30 & echo $! > {dossier}/pid; wait")


def mort(fichier_pid) -> bool:
    try:
        os.kill(int(fichier_pid.read_text()), 0)
    except ProcessLookupError:
        return True
    return False


@pytest.fixture(autouse=True)
def _git_isole(monkeypatch):
    # Ni la configuration git de David, ni la signature de ses commits.
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for cle, valeur in {"NAME": "Test", "EMAIL": "test@example.com"}.items():
        monkeypatch.setenv(f"GIT_AUTHOR_{cle}", valeur)
        monkeypatch.setenv(f"GIT_COMMITTER_{cle}", valeur)
    monkeypatch.setattr(module, "DELAI_ARRET_S", 0)


def git(dossier, *args) -> str:
    r = subprocess.run(["git", *args], cwd=dossier, capture_output=True, text=True, check=True)
    return r.stdout.strip()


class Depots:
    """Une origine, le dépôt du Core qui la suit sur `main`, et un autre clone qui pousse."""

    def __init__(self, racine):
        self.origine, self.core, self.autre = (racine / n for n in ("origine", "core", "autre"))
        git(racine, "init", "-q", "--bare", "-b", "main", str(self.origine))
        git(racine, "clone", "-q", str(self.origine), str(self.autre))
        (self.autre / "LISEZMOI.md").write_text("Atlas\n")
        git(self.autre, "add", "LISEZMOI.md")
        git(self.autre, "commit", "-q", "-m", "Premier")
        git(self.autre, "push", "-q", "origin", "HEAD:main")
        git(racine, "clone", "-q", str(self.origine), str(self.core))

    def pousser(self, *titres: str) -> None:
        for titre in titres:
            git(self.autre, "commit", "-q", "--allow-empty", "-m", titre)
        git(self.autre, "push", "-q", "origin", "HEAD:main")


@pytest.fixture
def depots(tmp_path) -> Depots:
    return Depots(tmp_path)


class Temoins:
    def __init__(self) -> None:
        self.publies: list = []
        self.arrets = 0

    def arreter(self) -> None:
        self.arrets += 1


@pytest.fixture
def temoins() -> Temoins:
    return Temoins()


def entretien(depots, temoins, installer=REUSSIT, delais=(30, 30)) -> Entretien:
    return Entretien(
        temoins.publies.append,
        depots.core,
        installer=installer,
        delais=delais,
        arreter=temoins.arreter,
    )


async def test_la_version_qui_tourne(depots, temoins):
    etat = await entretien(depots, temoins).etat()
    assert etat.version == git(depots.core, "rev-parse", "--short", "HEAD")
    assert etat.date == git(depots.core, "log", "-1", "--format=%cs")
    assert (etat.occupe, etat.mise_a_jour_possible, etat.raison) == (False, True, "")


async def test_hors_d_un_depot_git_la_version_est_inconnue(tmp_path, temoins):
    etat = await Entretien(temoins.publies.append, tmp_path, arreter=temoins.arreter).etat()
    assert (etat.version, etat.date, etat.mise_a_jour_possible) == ("inconnue", "", False)
    assert etat.raison.endswith("mets-le à jour au Terminal.")


async def test_redemarrer_laisse_la_marque_puis_arrete_le_core(depots, temoins):
    e = entretien(depots, temoins)
    assert e.demander_redemarrage() is None
    assert temoins.publies == [CoreEnCours(etape="redemarrage", texte="Redémarrage du Core…")]
    assert marque(depots.core).exists()
    await asyncio.sleep(0.01)
    assert temoins.arrets == 1
    assert e.demander_redemarrage() == FinCore(ok=False, texte=OCCUPE)
    assert await e.demander_mise_a_jour() == FinCore(ok=False, texte=OCCUPE)
    etat = await e.etat()
    assert (etat.occupe, etat.mise_a_jour_possible, etat.raison) == (True, False, OCCUPE)
    assert temoins.arrets == 1


async def test_sans_marque_pas_de_redemarrage(depots, temoins):
    (depots.core / "donnees").write_text("un fichier, pas un dossier\n")
    e = entretien(depots, temoins)
    assert e.demander_redemarrage() is None
    fin = temoins.publies[-1]
    assert (fin.ok, fin.texte.endswith("redémarre-le au Terminal.")) == (False, True)
    await asyncio.sleep(0.01)
    assert temoins.arrets == 0 and e.occupe is False


def test_les_tests_ne_touchent_jamais_le_depot_de_david():
    assert module.DEPOT != Path(module.__file__).resolve().parents[2]
    assert Entretien(lambda msg: None).depot == module.DEPOT


def test_une_marque_restee_la_s_efface_au_demarrage(depots, temoins):
    marque(depots.core).parent.mkdir()
    marque(depots.core).touch()
    e = entretien(depots, temoins)
    e.effacer_la_marque()
    assert not marque(depots.core).exists()
    e.effacer_la_marque()  # aucune : rien à faire


async def test_deja_a_jour(depots, temoins):
    e = entretien(depots, temoins)
    assert await e.demander_mise_a_jour() is None
    await e.tache
    assert temoins.publies == [
        CoreEnCours(etape="recuperation", texte="Récupération de la dernière version…"),
        FinCore(ok=True, texte=DEJA_A_JOUR),
    ]
    assert not (depots.core / "installe").exists() and temoins.arrets == 0
    assert e.occupe is False


async def test_les_nouveautes_l_installation_puis_le_redemarrage(depots, temoins):
    depots.pousser(*(f"Nouveauté {n}" for n in range(1, 8)))
    e = entretien(depots, temoins)
    assert await e.demander_mise_a_jour() is None
    await e.tache
    await asyncio.sleep(0.01)
    nouveautes = [f"Nouveauté {n}" for n in (7, 6, 5, 4, 3)] + ["et 2 autres"]
    assert temoins.publies == [
        CoreEnCours(etape="recuperation", texte="Récupération de la dernière version…"),
        CoreEnCours(etape="installation", texte="Installation…", nouveautes=nouveautes),
        CoreEnCours(etape="redemarrage", texte="Redémarrage du Core…", nouveautes=nouveautes),
    ]
    assert git(depots.core, "log", "-1", "--format=%s") == "Nouveauté 7"
    assert (depots.core / "installe").read_text() == "installé\n", "dans le dépôt du Core"
    assert marque(depots.core).exists() and temoins.arrets == 1
    assert e.occupe is True, "jusqu'à l'arrêt : un autre clic ne relance rien"


async def test_hors_de_main_rien_ne_change(depots, temoins):
    git(depots.core, "switch", "-q", "-c", "essai")
    depots.pousser("Nouveauté")
    e = entretien(depots, temoins)
    raison = "Le dépôt du Core est sur la branche essai, pas sur main : mets-le à jour au Terminal."
    assert await e.demander_mise_a_jour() == FinCore(ok=False, texte=raison)
    etat = await e.etat()
    assert (etat.mise_a_jour_possible, etat.raison) == (False, raison)
    assert temoins.publies == [] and e.occupe is False


async def test_un_fichier_suivi_modifie_bloque_la_mise_a_jour(depots, temoins):
    (depots.core / ".env").write_text("ATLAS_WEB_CLE=x\n")  # non suivi : ne compte pas
    (depots.core / "notes.txt").write_text("brouillon\n")
    assert (await entretien(depots, temoins).etat()).mise_a_jour_possible is True
    (depots.core / "LISEZMOI.md").write_text("Atlas, retouché\n")
    raison = "Le dépôt du Core a des modifications : mets-le à jour au Terminal."
    assert await entretien(depots, temoins).demander_mise_a_jour() == FinCore(
        ok=False, texte=raison
    )


async def test_un_historique_divergent_ne_change_rien(depots, temoins):
    git(depots.core, "config", "pull.rebase", "false")  # git fusionnerait, sans --ff-only
    git(depots.core, "commit", "-q", "--allow-empty", "-m", "Local")
    depots.pousser("Distant")
    avant = git(depots.core, "rev-parse", "HEAD")
    e = entretien(depots, temoins)
    await e.demander_mise_a_jour()
    await e.tache
    fin = temoins.publies[-1]
    assert (fin.type, fin.ok, fin.texte) == ("fin_core", False, ECHEC_RECUPERATION)
    assert fin.details, "les dernières lignes de git"
    assert git(depots.core, "rev-parse", "HEAD") == avant
    assert temoins.arrets == 0 and e.occupe is False


async def test_un_fichier_non_suivi_qu_une_nouveaute_ecraserait_arrete_tout(depots, temoins):
    # Review Focus 4 : un fichier laissé dans le dépôt du Core, qu'une nouveauté ajoute aussi.
    (depots.autre / "notes.txt").write_text("la version d'Atlas\n")
    git(depots.autre, "add", "notes.txt")
    depots.pousser("Des notes")
    (depots.core / "notes.txt").write_text("celles de David\n")
    e = entretien(depots, temoins)
    assert await e.demander_mise_a_jour() is None, "non suivi : il ne bloque pas d'avance"
    await e.tache
    fin = temoins.publies[-1]
    assert (fin.ok, fin.texte) == (False, ECHEC_RECUPERATION)
    assert (depots.core / "notes.txt").read_text() == "celles de David\n"
    assert temoins.arrets == 0 and not (depots.core / "installe").exists()


async def test_une_installation_ratee_ne_redemarre_pas(depots, temoins):
    depots.pousser("Nouveauté")
    e = entretien(depots, temoins, installer=RATE)
    await e.demander_mise_a_jour()
    await e.tache
    assert temoins.publies[-1] == FinCore(
        ok=False, texte=ECHEC_INSTALLATION, details=["uv : paquet introuvable"]
    )
    assert not marque(depots.core).exists() and temoins.arrets == 0 and e.occupe is False


async def test_une_installation_trop_longue_est_arretee(depots, temoins, tmp_path):
    depots.pousser("Nouveauté")
    e = entretien(depots, temoins, installer=lente(tmp_path), delais=(30, 0.5))
    await e.demander_mise_a_jour()
    await asyncio.wait_for(e.tache, 5)  # sans attendre la fin de ce qu'elle a lancé
    fin = temoins.publies[-1]
    assert (fin.ok, fin.texte, fin.details[-1]) == (
        False,
        ECHEC_INSTALLATION,
        "Arrêtée : elle a dépassé son délai.",
    )
    await asyncio.sleep(0.1)
    assert mort(tmp_path / "pid"), "ce qu'elle a lancé est arrêté aussi"
    assert temoins.arrets == 0


async def test_l_arret_du_core_arrete_une_mise_a_jour_en_cours(depots, temoins, tmp_path):
    depots.pousser("Nouveauté")
    e = entretien(depots, temoins, installer=lente(tmp_path))
    await e.demander_mise_a_jour()
    while not (tmp_path / "pid").exists() or not (tmp_path / "pid").read_text():
        await asyncio.sleep(0.01)
    assert e.demander_redemarrage() == FinCore(ok=False, texte=OCCUPE)
    await asyncio.wait_for(e.fermer(), 5)
    assert e.tache.done()
    await asyncio.sleep(0.1)
    assert mort(tmp_path / "pid")

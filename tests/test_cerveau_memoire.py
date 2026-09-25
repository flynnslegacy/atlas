"""Le cerveau avec sa mémoire : l'amorçage des conversations et l'annonce des écritures, avec
la doublure du SDK de `test_cerveau_claude.py` et une vraie mémoire sur un dépôt temporaire."""

import asyncio

import pytest
from test_cerveau_claude import (
    BLOQUE,
    MOMENT,
    Fabrique,
    FauxClientClaude,
    Temps,
    debut_texte,
    delta,
    fin,
    reponse,
)

from atlas_core.cerveau import Note
from atlas_core.cerveau_claude import CerveauClaude
from atlas_core.memoire import Memoire
from atlas_core.outils_memoire import ANNONCE_PROFIL, OutilsMemoire

DATE = "[jeudi 24 septembre 2026, 21 h 50]"
PROFIL = "# Profil\n\nDavid, à appeler Dieu.\n"


@pytest.fixture
def outils(tmp_path) -> OutilsMemoire:
    outils = OutilsMemoire(Memoire.ouvrir(tmp_path / "memoire"))
    outils.memoire.ecrire("profil.md", PROFIL)
    return outils


class AppelOutil:
    """Claude appelle un outil au milieu d'un tour : le SDK exécute son gestionnaire."""

    def __init__(self, outils: OutilsMemoire, nom: str, **arguments) -> None:
        self._outil = next(o for o in outils.outils if o.name == nom)
        self._arguments = arguments

    async def __call__(self) -> None:
        await self._outil.handler(self._arguments)


def _cerveau(outils, *clients, temps=None) -> CerveauClaude:
    return CerveauClaude(
        Fabrique(*clients),
        oubli_s=30 * 60,
        horloge=temps or Temps(),
        maintenant=lambda: MOMENT,
        outils=outils,
    )


async def _tout(cerveau: CerveauClaude, texte: str) -> list:
    async def lire() -> list:
        return [f async for f in cerveau.repondre(texte)]

    return await asyncio.wait_for(lire(), timeout=2)


# --- l'amorçage ----------------------------------------------------------------------


async def test_la_premiere_question_d_une_conversation_part_avec_la_memoire(outils):
    client = FauxClientClaude(reponse("Oui."), reponse("Bien sûr."))
    cerveau = _cerveau(outils, client)
    await _tout(cerveau, "Tu te souviens de moi ?")
    await _tout(cerveau, "Et de mon nom ?")
    amorcage = outils.memoire.amorcage(MOMENT.date())
    assert amorcage.startswith("[Mémoire d'Atlas]") and "à appeler Dieu" in amorcage
    assert client.questions == [
        f"{amorcage}\n{DATE}\nTu te souviens de moi ?",
        f"{DATE}\nEt de mon nom ?",
    ]


async def test_une_conversation_neuve_repart_avec_la_memoire_du_moment(outils):
    temps = Temps()
    ancien = FauxClientClaude(reponse("Un."))
    neuf = FauxClientClaude(reponse("Deux."))
    cerveau = _cerveau(outils, ancien, neuf, temps=temps)
    await _tout(cerveau, "un")
    outils.memoire.ecrire("personnes/paul-durand.md", "# Paul Durand\n\nProspect.\n")
    temps.t += 30 * 60
    await _tout(cerveau, "deux")
    assert neuf.questions[0].startswith("[Mémoire d'Atlas]")
    assert "- personnes/paul-durand.md : Prospect." in neuf.questions[0]


async def test_un_claude_relance_en_pleine_conversation_recoit_la_memoire(outils):
    mort = FauxClientClaude(reponse("Un."))
    relance = FauxClientClaude(reponse("Deux."))
    cerveau = _cerveau(outils, mort, relance)
    await _tout(cerveau, "un")
    mort.echec_question = OSError("processus mort")
    await _tout(cerveau, "deux")
    assert relance.questions[0].startswith("[Mémoire d'Atlas]")


async def test_une_memoire_illisible_n_empeche_pas_de_repondre(outils, monkeypatch, caplog):
    def illisible(aujourd_hui):
        raise OSError("disque débranché")

    monkeypatch.setattr(outils.memoire, "amorcage", illisible)
    client = FauxClientClaude(reponse("Oui."))
    assert await _tout(_cerveau(outils, client), "Tu m'entends ?") == ["Oui."]
    assert client.questions == [f"{DATE}\nTu m'entends ?"]
    assert "amorçage de la mémoire impossible" in caplog.text


# --- les annonces ------------------------------------------------------------------


async def test_une_ecriture_s_annonce_a_sa_place_dans_la_reponse(outils):
    tour = [
        debut_texte(),
        delta("D'accord."),
        AppelOutil(
            outils, "memoire_ecrire", chemin="profil.md", contenu=PROFIL + "\nDeux enfants.\n"
        ),
        debut_texte(),
        delta("Autre chose ?"),
        fin(),
    ]
    fragments = await _tout(_cerveau(outils, FauxClientClaude(tour)), "Note mes enfants.")
    assert fragments == ["D'accord.", Note(ANNONCE_PROFIL), " Autre chose ?"]


async def test_une_ecriture_refusee_ne_s_annonce_pas(outils):
    tour = [
        AppelOutil(outils, "memoire_ecrire", chemin="profil.md", contenu="mot de passe : x"),
        debut_texte(),
        delta("Je ne peux pas noter ça."),
        fin(),
    ]
    fragments = await _tout(_cerveau(outils, FauxClientClaude(tour)), "Note mon mot de passe.")
    assert fragments == ["Je ne peux pas noter ça."]


async def test_une_note_d_une_reponse_abandonnee_s_annonce_au_debut_de_la_suivante(outils):
    fiche = "# Paul Durand\n\nProspect.\n"
    client = FauxClientClaude(
        [
            debut_texte(),
            delta("Je le note, "),
            AppelOutil(outils, "memoire_ecrire", chemin="personnes/paul-durand.md", contenu=fiche),
            BLOQUE,
            delta("jamais lu"),
            fin(),
        ],
        reponse("Oui."),
    )
    cerveau = _cerveau(outils, client)
    flux = cerveau.repondre("Note Paul.")
    assert await anext(flux) == "Je le note, "
    await flux.aclose()  # la session lâche la réponse ; le ménage lit le reste
    fragments = await _tout(cerveau, "Tu as noté ?")
    assert fragments == [Note("Je le note dans la fiche Paul Durand."), "Oui."]


async def test_une_note_d_une_reponse_coupee_par_une_autre_question_passe_a_celle_ci(outils):
    ecriture = AppelOutil(
        outils, "memoire_ecrire", chemin="profil.md", contenu=PROFIL + "\nDeux enfants.\n"
    )
    client = FauxClientClaude(
        [debut_texte(), delta("Première "), ecriture, BLOQUE, delta("jamais"), fin()],
        reponse("Seconde."),
    )
    cerveau = _cerveau(outils, client)
    premiere: list = []

    async def lire_la_premiere() -> None:
        async for fragment in cerveau.repondre("une"):
            premiere.append(fragment)

    tache = asyncio.create_task(lire_la_premiere())
    while not premiere:
        await asyncio.sleep(0)
    assert await _tout(cerveau, "deux") == [Note(ANNONCE_PROFIL), "Seconde."]
    await tache
    assert premiere == ["Première "]


async def test_sans_memoire_le_cerveau_ne_recoit_ni_amorcage_ni_outils():
    client = FauxClientClaude(reponse("Oui."))
    cerveau = CerveauClaude(Fabrique(client), maintenant=lambda: MOMENT)
    assert await _tout(cerveau, "Tu m'entends ?") == ["Oui."]
    assert client.questions == [f"{DATE}\nTu m'entends ?"]

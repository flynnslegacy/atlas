"""Les réglages écrits dans le .env du Core depuis la page : relus à l'identique par le vrai
`make`, le reste du fichier intact, et jamais une clé d'Atlas."""

import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from atlas_core import reglages
from atlas_core.connecteurs import API, Manifeste, Reglage
from atlas_core.reglages import (
    CLES_D_ATLAS,
    ReglageRefuse,
    changements_permis,
    ecrire_env,
    modifiable,
)

SOURCES = Path(__file__).resolve().parents[1] / "src"
# Ce que fait `make run-core` du .env : il l'inclut, puis exporte tout.
MAKEFILE = "-include .env\nexport\nafficher:\n\t@printenv CLE\n"


def manifeste(*reglages_: Reglage) -> Manifeste:
    return Manifeste(
        nom="Bonjour", description="Dit bonjour.", version="0.1", auteur="Quelqu'un", api=API,
        reglages=reglages_,
    )  # fmt: skip


NOM = Reglage(variable="ATLAS_BONJOUR_NOM", description="Le nom à saluer")
CLE = Reglage(variable="ATLAS_BONJOUR_CLE", description="La clé du service", secret=True)


def relu_par_make(dossier: Path) -> str:
    environ = {k: v for k, v in os.environ.items() if k != "CLE" and not k.startswith("MAKE")}
    r = subprocess.run(
        ["make", "-s", "afficher"], cwd=dossier, env=environ, capture_output=True, text=True
    )
    assert r.returncode == 0, r.stderr
    return r.stdout.removesuffix("\n")


@pytest.mark.skipif(shutil.which("make") is None, reason="make absent")
@pytest.mark.parametrize(
    "valeur",
    [
        "abc",
        "a$b",
        "$(shell touch temoin)",
        "a#b",
        "#au début",
        "a\\#b",
        "a\\\\#b",
        "a\\b",
        '"entre guillemets"',
        "a b  c",
        "é€😀",
        "a=b:c;d`e",
    ],
)
def test_une_valeur_est_relue_par_make_a_l_identique(tmp_path, valeur):
    (tmp_path / "Makefile").write_text(MAKEFILE)
    ecrire_env(tmp_path / ".env", {"CLE": valeur})
    assert relu_par_make(tmp_path) == valeur
    assert not (tmp_path / "temoin").exists(), "make n'exécute jamais une valeur"


def test_le_reste_du_env_ne_bouge_pas(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "# Les clés d'Atlas\n"
        "ATLAS_WEB_CLE=cle-de-la-page\n"
        "\n"
        "ATLAS_BONJOUR_NOM=Ancien\n"
        "une ligne que personne ne comprend\n"
        "export ATLAS_BONJOUR_NOM = Doublon\n"
        "# ATLAS_BONJOUR_CLE=exemple commenté\n"
        "ATLAS_AUTRE=1\n",
        encoding="utf-8",
    )
    ecrire_env(env, {"ATLAS_BONJOUR_NOM": "David", "ATLAS_BONJOUR_CLE": "sésame"})
    assert env.read_text(encoding="utf-8") == (
        "# Les clés d'Atlas\n"
        "ATLAS_WEB_CLE=cle-de-la-page\n"
        "\n"
        "ATLAS_BONJOUR_NOM=David\n"
        "une ligne que personne ne comprend\n"
        "# ATLAS_BONJOUR_CLE=exemple commenté\n"
        "ATLAS_AUTRE=1\n"
        "ATLAS_BONJOUR_CLE=sésame\n"
    )
    ecrire_env(env, {"ATLAS_BONJOUR_NOM": None})
    assert "ATLAS_BONJOUR_NOM" not in env.read_text(encoding="utf-8")
    assert "ATLAS_WEB_CLE=cle-de-la-page\n" in env.read_text(encoding="utf-8")


def test_une_retouche_a_la_main_entre_deux_enregistrements_reste(tmp_path):
    # Review Focus 2 : David modifie le .env pendant que le Core tourne.
    env = tmp_path / ".env"
    ecrire_env(env, {"ATLAS_BONJOUR_NOM": "David"})
    with env.open("a", encoding="utf-8") as fichier:
        fichier.write("ATLAS_AJOUTE_A_LA_MAIN=1\n")
    ecrire_env(env, {"ATLAS_BONJOUR_NOM": "Camille"})
    assert env.read_text(encoding="utf-8") == (
        "ATLAS_BONJOUR_NOM=Camille\nATLAS_AJOUTE_A_LA_MAIN=1\n"
    )


def test_un_env_en_lien_symbolique_garde_son_lien(tmp_path):
    # Review Focus 3 : un .env rangé ailleurs, et lié dans le dépôt.
    cible = tmp_path / "ailleurs" / "atlas.env"
    cible.parent.mkdir()
    cible.write_text("ATLAS_WEB_CLE=cle\n", encoding="utf-8")
    env = tmp_path / ".env"
    env.symlink_to(cible)
    ecrire_env(env, {"ATLAS_BONJOUR_NOM": "David"})
    assert env.is_symlink()
    assert cible.read_text(encoding="utf-8") == "ATLAS_WEB_CLE=cle\nATLAS_BONJOUR_NOM=David\n"


def test_un_env_absent_est_cree_lisible_par_david_seul(tmp_path):
    env = tmp_path / ".env"
    ecrire_env(env, {"ATLAS_BONJOUR_NOM": "David"})
    assert env.read_text(encoding="utf-8") == "ATLAS_BONJOUR_NOM=David\n"
    assert stat.S_IMODE(env.stat().st_mode) == 0o600
    env.chmod(0o644)  # comme le .env du M5 aujourd'hui
    voisin = tmp_path / ".env.tmp"
    voisin.write_text("laissé par un arrêt brutal\n")
    voisin.chmod(0o644)
    ecrire_env(env, {"ATLAS_BONJOUR_NOM": "Camille"})
    assert stat.S_IMODE(env.stat().st_mode) == 0o600
    assert env.read_text(encoding="utf-8") == "ATLAS_BONJOUR_NOM=Camille\n"
    assert [p.name for p in tmp_path.iterdir()] == [".env"], "aucun fichier voisin ne reste"


def test_une_ecriture_qui_echoue_ne_change_rien(tmp_path):
    env = tmp_path / ".env"
    env.write_text("ATLAS_BONJOUR_NOM=Ancien\n", encoding="utf-8")
    tmp_path.chmod(0o500)  # le dossier ne s'écrit plus
    try:
        with pytest.raises(ReglageRefuse, match="Le .env n'a pas pu s'écrire"):
            ecrire_env(env, {"ATLAS_BONJOUR_NOM": "David"})
    finally:
        tmp_path.chmod(0o755)
    assert env.read_text(encoding="utf-8") == "ATLAS_BONJOUR_NOM=Ancien\n"
    assert [p.name for p in tmp_path.iterdir()] == [".env"]


def test_un_env_illisible_est_un_refus(tmp_path):
    env = tmp_path / ".env"
    env.write_bytes("ATLAS_BONJOUR_NOM=Andr\xe9\n".encode("latin-1"))
    with pytest.raises(ReglageRefuse, match="Le .env ne se lit pas"):
        ecrire_env(env, {"ATLAS_BONJOUR_NOM": "David"})


def test_les_changements_permis_ecrivent_et_effacent():
    changements = changements_permis(
        manifeste(NOM, CLE), {"ATLAS_BONJOUR_NOM": "David"}, ["ATLAS_BONJOUR_CLE"]
    )
    assert changements == {"ATLAS_BONJOUR_NOM": "David", "ATLAS_BONJOUR_CLE": None}


@pytest.mark.parametrize(
    ("valeur", "raison"),
    [
        ("", "vide"),
        ("a\nb", "une seule ligne"),
        ("a\tb", "une seule ligne"),
        ("a\x00b", "une seule ligne"),
        (" David", "pas d'espace au début ni à la fin"),
        ("David ", "pas d'espace au début ni à la fin"),
        ("fin\\", "finir par une barre oblique inverse"),
        ("x" * 4097, "4096 caractères au plus"),
    ],
)
def test_une_valeur_qui_ne_convient_pas_est_refusee(valeur, raison):
    with pytest.raises(ReglageRefuse, match=re.escape(raison)):
        changements_permis(manifeste(NOM), {"ATLAS_BONJOUR_NOM": valeur}, [])


def test_seules_les_variables_declarees_par_le_connecteur():
    with pytest.raises(ReglageRefuse, match="ATLAS_AUTRE n'est pas un réglage de ce connecteur"):
        changements_permis(manifeste(NOM), {"ATLAS_AUTRE": "x"}, [])
    with pytest.raises(ReglageRefuse, match="ATLAS_AUTRE n'est pas un réglage de ce connecteur"):
        changements_permis(manifeste(NOM), {}, ["ATLAS_AUTRE"])
    with pytest.raises(ReglageRefuse, match="à la fois écrit et effacé"):
        changements_permis(manifeste(NOM), {"ATLAS_BONJOUR_NOM": "x"}, ["ATLAS_BONJOUR_NOM"])


def test_une_cle_d_atlas_est_refusee_quoi_que_dise_le_manifeste():
    # Un connecteur de la communauté qui déclarerait la clé de la page comme « réglage ».
    piege = Reglage(variable="ATLAS_WEB_CLE", description="Un réglage", secret=True)
    with pytest.raises(ReglageRefuse, match="ATLAS_WEB_CLE est une clé d'Atlas"):
        changements_permis(manifeste(piege), {"ATLAS_WEB_CLE": "prise"}, [])
    with pytest.raises(ReglageRefuse, match="ATLAS_WEB_CLE est une clé d'Atlas"):
        changements_permis(manifeste(piege), {}, ["ATLAS_WEB_CLE"])
    assert not modifiable("ATLAS_POSTE_CLE") and modifiable("ATLAS_BONJOUR_NOM")


def test_les_cles_d_atlas_sont_celles_que_lit_atlas():
    # Une variable lue par le Core, le client audio ou le poste s'ajoute à la liste, ou ce
    # test échoue : sinon, un manifeste pourrait la déclarer, et la page la réécrire.
    lues = {
        nom
        for chemin in SOURCES.rglob("*.py")
        if chemin.name != "reglages.py"
        for nom in re.findall(r'"(ATLAS_[A-Z0-9_]+)"', chemin.read_text(encoding="utf-8"))
    }
    assert lues == CLES_D_ATLAS - {"CLAUDE_CODE_OAUTH_TOKEN"}
    assert "CLAUDE_CODE_OAUTH_TOKEN" in CLES_D_ATLAS


def test_le_env_des_tests_n_est_jamais_celui_du_depot():
    assert reglages.FICHIER_ENV != reglages.DEPOT / ".env"

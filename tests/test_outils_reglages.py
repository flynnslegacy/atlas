"""Un réglage saisi dans la page prend effet tout de suite : écrit dans le .env, pris par le
Core, et un connecteur actif rechargé avec lui, comme après une bascule."""

import json

import pytest
from test_registre import MANIFESTE, code, deposer

from atlas_core.memoire import ErreurMemoire, Memoire
from atlas_core.outils_memoire import OutilsMemoire
from atlas_core.registre import Registre, fichier_des_interrupteurs
from atlas_core.reglages import ReglageRefuse

ORDINAIRE = """
[[reglages]]
variable = "ATLAS_BONJOUR_NOM"
description = "Le nom à saluer"
"""
SECRET = """
[[reglages]]
variable = "ATLAS_BONJOUR_CLE"
description = "La clé du service"
secret = true
"""
# Le connecteur ne se charge pas avec le nom « Boum ».
CAPRICIEUX = code().replace(
    "def creer(contexte):\n",
    "def creer(contexte):\n"
    "    if contexte.reglages['ATLAS_BONJOUR_NOM'] == 'Boum':\n"
    "        raise RuntimeError('boum')\n",
)


@pytest.fixture
def perso(tmp_path):
    return tmp_path / "connecteurs"


@pytest.fixture
def env(tmp_path):
    return tmp_path / ".env"


def outils_de(tmp_path, perso, env, environ) -> OutilsMemoire:
    registre = Registre(tmp_path / "officiels", perso, environ=environ)
    memoire = Memoire.ouvrir(tmp_path / "memoire")
    return OutilsMemoire(memoire, registre=registre, fichier_env=env)


def etat(outils, id_="salut"):
    return next(f for f in outils.registre.decouvrir() if f.id == id_)


async def dire(outils) -> str:
    outil = next(o for o in outils.outils if o.name == "salut_dire")
    return (await outil.handler({}))["content"][0]["text"]


def test_un_reglage_rend_un_connecteur_activable_aussitot(tmp_path, perso, env):
    deposer(perso, "salut", MANIFESTE.format(nom="Salut") + ORDINAIRE)
    environ: dict[str, str] = {}
    outils = outils_de(tmp_path, perso, env, environ)
    assert etat(outils).etat == "a_configurer"
    assert outils.regler("salut", {"ATLAS_BONJOUR_NOM": "David"}, []) is False
    assert env.read_text(encoding="utf-8") == "ATLAS_BONJOUR_NOM=David\n"
    assert environ == {"ATLAS_BONJOUR_NOM": "David"}
    assert (etat(outils).etat, etat(outils).en_attente) == ("coupe", False)


async def test_un_connecteur_actif_se_recharge_avec_ses_nouveaux_reglages(tmp_path, perso, env):
    deposer(perso, "salut", MANIFESTE.format(nom="Salut") + ORDINAIRE)
    outils = outils_de(tmp_path, perso, env, {"ATLAS_BONJOUR_NOM": "David"})
    outils.basculer("salut", True)
    outils.registre.appliquer()
    assert await dire(outils) == "Bonjour David."
    assert outils.regler("salut", {"ATLAS_BONJOUR_NOM": "Camille"}, []) is True
    assert await dire(outils) == "Bonjour Camille."
    assert (etat(outils).etat, etat(outils).en_attente) == ("actif", True)
    interrupteurs = json.loads(fichier_des_interrupteurs(perso).read_text())
    assert interrupteurs == {"actifs": ["communaute:salut"]}, "son interrupteur ne change pas"


def test_effacer_le_reglage_d_un_connecteur_actif_le_coupe(tmp_path, perso, env):
    deposer(perso, "salut", MANIFESTE.format(nom="Salut") + ORDINAIRE)
    environ = {"ATLAS_BONJOUR_NOM": "David"}
    outils = outils_de(tmp_path, perso, env, environ)
    outils.basculer("salut", True)
    assert outils.regler("salut", {}, ["ATLAS_BONJOUR_NOM"]) is True
    assert environ == {} and outils.connecteurs == []
    assert "mcp__atlas__salut_dire" not in outils.noms
    assert etat(outils).etat == "a_configurer"


def test_un_connecteur_actif_qui_ne_se_recharge_plus_passe_en_erreur(tmp_path, perso, env):
    deposer(perso, "salut", MANIFESTE.format(nom="Salut") + ORDINAIRE, source=CAPRICIEUX)
    outils = outils_de(tmp_path, perso, env, {"ATLAS_BONJOUR_NOM": "David"})
    outils.basculer("salut", True)
    assert outils.regler("salut", {"ATLAS_BONJOUR_NOM": "Boum"}, []) is True
    assert (etat(outils).etat, etat(outils).detail) == ("en_erreur", "RuntimeError : boum")
    assert outils.connecteurs == []


def test_un_nouveau_secret_est_refuse_par_la_memoire(tmp_path, perso, env):
    deposer(perso, "salut", MANIFESTE.format(nom="Salut") + ORDINAIRE + SECRET)
    outils = outils_de(tmp_path, perso, env, {})
    valeurs = {"ATLAS_BONJOUR_CLE": "sesame-assez-long", "ATLAS_BONJOUR_NOM": "Léa-Marie Dupont"}
    outils.regler("salut", valeurs, [])
    with pytest.raises(ErreurMemoire, match="mot de passe"):
        outils.memoire.ecrire("profil.md", "# Profil\n\nDavid.\n\nSa clé : sesame-assez-long\n")
    # Un réglage ordinaire n'est pas un secret ; un secret trop court ne se cherche pas.
    outils.memoire.ecrire("profil.md", "# Profil\n\nDavid.\n\nIl salue Léa-Marie Dupont.\n")
    outils.regler("salut", {"ATLAS_BONJOUR_CLE": "court"}, [])
    outils.memoire.ecrire("profil.md", "# Profil\n\nDavid.\n\nUn court séjour.\n")


def test_un_refus_ne_change_rien(tmp_path, perso, env):
    deposer(perso, "salut", MANIFESTE.format(nom="Salut") + ORDINAIRE)
    environ: dict[str, str] = {}
    outils = outils_de(tmp_path, perso, env, environ)
    with pytest.raises(ReglageRefuse, match="ATLAS_AUTRE n'est pas un réglage de ce connecteur"):
        outils.regler("salut", {"ATLAS_BONJOUR_NOM": "David", "ATLAS_AUTRE": "x"}, [])
    assert not env.exists() and environ == {}
    with pytest.raises(ReglageRefuse, match="Ce connecteur n'a pas de réglages"):
        outils.regler("inconnu", {"ATLAS_BONJOUR_NOM": "David"}, [])
    (perso / "casse").mkdir()  # sans manifeste
    with pytest.raises(ReglageRefuse, match="Ce connecteur n'a pas de réglages"):
        outils.regler("casse", {}, [])


def test_sans_env_ni_registre_pas_de_reglages(tmp_path, perso):
    deposer(perso, "salut", MANIFESTE.format(nom="Salut") + ORDINAIRE)
    registre = Registre(tmp_path / "officiels", perso, environ={})
    sans_env = OutilsMemoire(Memoire.ouvrir(tmp_path / "memoire"), registre=registre)
    sans_registre = OutilsMemoire(Memoire.ouvrir(tmp_path / "m2"), fichier_env=tmp_path / ".env")
    for outils in (sans_env, sans_registre):
        with pytest.raises(ReglageRefuse, match="Les réglages ne s'écrivent pas ici"):
            outils.regler("salut", {"ATLAS_BONJOUR_NOM": "David"}, [])

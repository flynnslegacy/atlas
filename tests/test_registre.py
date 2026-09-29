"""Le registre des connecteurs, avec de faux connecteurs déposés dans des dossiers
temporaires : ce qui est découvert sans rien exécuter, les états, les interrupteurs, le
chargement à l'activation, et un connecteur qui plante sans faire tomber Atlas."""

import json
import logging
import os
import shutil
import stat
import sys
import types
from pathlib import Path

import pytest

from atlas_core.connecteurs import Outil
from atlas_core.registre import DEPOT, Registre, fichier_des_interrupteurs, installer

MANIFESTE = """
nom = "{nom}"
description = "Dit bonjour."
version = "0.1"
auteur = "Quelqu'un"
api = 1
consignes = "Dis bonjour quand David te le demande."
"""

REGLAGE = """
[[reglages]]
variable = "ATLAS_BONJOUR_NOM"
description = "Le nom à saluer"
secret = true
"""

CODE = """
from atlas_core.connecteurs import Connecteur, Niveau, Outil


class Bonjour(Connecteur):
    def __init__(self, contexte):
        self.contexte = contexte

    def outils(self):
        async def dire(arguments):
            return "{salut} " + self.contexte.reglages.get("ATLAS_BONJOUR_NOM", "toi") + "."

        return [Outil("{outil}", "Dit bonjour.", {{}}, Niveau.N1, dire)]


def creer(contexte):
    return Bonjour(contexte)
"""


def code(outil: str = "salut_dire", salut: str = "Bonjour") -> str:
    return CODE.format(salut=salut, outil=outil)


def deposer(
    racine: Path,
    id_: str,
    manifeste: str | None = None,
    source: str | None = None,
    outil: str | None = None,
) -> Path:
    dossier = racine / id_
    dossier.mkdir(parents=True)
    texte = MANIFESTE.format(nom=id_.capitalize()) if manifeste is None else manifeste
    (dossier / "connecteur.toml").write_text(texte, encoding="utf-8")
    source = code(outil or f"{id_.replace('-', '_')}_dire") if source is None else source
    (dossier / "connecteur.py").write_text(source, encoding="utf-8")
    return dossier


@pytest.fixture
def officiels(tmp_path) -> Path:
    return tmp_path / "officiels"


@pytest.fixture
def perso(tmp_path) -> Path:
    return tmp_path / "perso" / "connecteurs"


def registre(officiels: Path, perso: Path, **options) -> Registre:
    options.setdefault("environ", {})
    return Registre(officiels, perso, **options)


def etats(r: Registre) -> dict[str, tuple[str, str, str]]:
    return {f.id: (f.origine, f.etat, f.detail) for f in r.decouvrir()}


async def appeler(outil: Outil) -> str:
    return await outil.gestionnaire({})


# --- la découverte --------------------------------------------------------------------


def test_la_decouverte_lit_les_manifestes_sans_executer_de_code(officiels, perso):
    temoin = perso / "espion" / "importe"
    deposer(perso, "espion", source=f"open({str(temoin)!r}, 'w').close()\n")
    deposer(officiels, "poste")
    (officiels / "LISEZMOI.md").write_text("# Les connecteurs\n")  # un fichier : ignoré
    (officiels / "__pycache__").mkdir()  # un dossier technique : ignoré
    assert etats(registre(officiels, perso)) == {
        "poste": ("atlas", "coupe", ""),
        "espion": ("communaute", "coupe", ""),
    }
    assert not temoin.exists(), "aucun code ne tourne avant l'activation"


def test_sans_repertoire_rien_n_est_decouvert(officiels, perso):
    assert registre(officiels, perso).decouvrir() == []


@pytest.mark.parametrize(
    ("id_", "manifeste", "etat", "detail"),
    [
        ("Mon_Connecteur", None, "en_erreur", "nom de dossier invalide"),
        ("a" * 41, None, "en_erreur", "nom de dossier invalide"),
        ("vide", "", "en_erreur", "connecteur.toml, nom : Field required"),
        ("ancien", MANIFESTE.format(nom="Ancien").replace("api = 1", "api = 2"), "en_erreur",
         "contrat inconnu : api 2"),
        ("salut", MANIFESTE.format(nom="Salut") + REGLAGE, "a_configurer",
         "il manque ATLAS_BONJOUR_NOM dans le .env du Core"),
        ("agenda", MANIFESTE.format(nom="Agenda") + 'dependances = ["caldav>=1.4"]\n',
         "a_installer", "lance make install (il manque caldav)"),
    ],
)  # fmt: skip
def test_chaque_etat_dit_ce_qui_manque(officiels, perso, id_, manifeste, etat, detail):
    deposer(perso, id_, manifeste)
    r = registre(officiels, perso, installe=lambda nom: nom != "caldav")
    origine, etat_trouve, detail_trouve = etats(r)[id_]
    assert (origine, etat_trouve) == ("communaute", etat)
    assert detail in detail_trouve


def test_un_doublon_de_la_communaute_laisse_la_place_a_l_officiel(officiels, perso):
    deposer(officiels, "poste")
    deposer(perso, "poste")
    assert [(f.origine, f.etat, f.detail) for f in registre(officiels, perso).decouvrir()] == [
        ("atlas", "coupe", ""),
        ("communaute", "en_erreur", "déjà fourni par Atlas"),
    ]


# --- l'activation ---------------------------------------------------------------------


async def test_activer_charge_le_code_et_range_l_interrupteur(officiels, perso):
    deposer(perso, "salut", MANIFESTE.format(nom="Salut") + REGLAGE)
    environ = {"ATLAS_BONJOUR_NOM": "David", "ATLAS_WEB_CLE": "une-cle-d-ailleurs"}
    r = registre(officiels, perso, environ=environ)
    assert r.basculer("salut", True) is True
    [actif] = r.actifs()
    assert (actif.id, actif.consignes) == ("salut", "Dis bonjour quand David te le demande.")
    assert await appeler(actif.outils[0]) == "Bonjour David."
    assert actif.connecteur.contexte.reglages == {"ATLAS_BONJOUR_NOM": "David"}
    assert etats(r)["salut"][1] == "actif"
    fichier = fichier_des_interrupteurs(perso)
    assert fichier == perso.parent / "connecteurs.json"
    assert json.loads(fichier.read_text()) == {"actifs": ["communaute:salut"]}
    assert stat.S_IMODE(fichier.stat().st_mode) == 0o600
    # Au redémarrage du Core, un connecteur activé se recharge seul.
    relu = registre(officiels, perso, environ=environ)
    relu.demarrer()
    assert [a.id for a in relu.actifs()] == ["salut"]


def test_couper_decharge_le_connecteur_et_le_retient(officiels, perso):
    deposer(perso, "salut")
    r = registre(officiels, perso)
    r.basculer("salut", True)
    assert r.basculer("salut", False) is True
    assert r.actifs() == [] and etats(r)["salut"][1] == "coupe"
    assert "atlas_connecteurs.salut.connecteur" not in sys.modules
    assert json.loads(fichier_des_interrupteurs(perso).read_text()) == {"actifs": []}
    assert r.basculer("salut", False) is False  # déjà coupé : rien ne change


async def test_un_connecteur_retouche_puis_reactive_relit_son_code(officiels, perso):
    dossier = deposer(perso, "salut")
    r = registre(officiels, perso)
    r.basculer("salut", True)
    r.basculer("salut", False)
    (dossier / "connecteur.py").write_text(code(salut="Salut"))
    r.basculer("salut", True)
    assert await appeler(r.actifs()[0].outils[0]) == "Salut toi."


@pytest.mark.parametrize("id_", ["inconnu", "../perso", "salut/../salut"])
def test_seul_un_connecteur_decouvert_et_activable_s_active(officiels, perso, id_):
    deposer(perso, "salut", MANIFESTE.format(nom="Salut") + REGLAGE)  # à configurer
    r = registre(officiels, perso)
    assert r.basculer(id_, True) is False
    assert r.basculer("salut", True) is False
    assert r.actifs() == [] and not fichier_des_interrupteurs(perso).exists()


def test_seuls_les_connecteurs_qui_declarent_le_poste_le_recoivent(officiels, perso):
    poste, missions = object(), object()
    deposer(officiels, "mac", MANIFESTE.format(nom="Mac") + 'services = ["poste"]\n')
    deposer(perso, "salut")
    r = registre(officiels, perso, poste=poste, missions=missions)
    r.basculer("mac", True)
    r.basculer("salut", True)
    mac, salut = (a.connecteur.contexte for a in r.actifs())
    assert (mac.poste, mac.missions) == (poste, missions)
    assert (salut.poste, salut.missions) == (None, None)


# --- les erreurs ----------------------------------------------------------------------

CASSES = {
    "import": "raise RuntimeError('il manque un point-virgule')\n",
    "creer": "def creer(contexte):\n    raise ValueError('pas de réseau')\n",
    "sortie": "import sys\nsys.exit(3)\n",
    "outils": code().replace("return [Outil(", "return (Outil(").replace("dire)]", "dire),)"),
    "nom": code(outil="Dire-Bonjour"),
    # Claude le voit précédé de « mcp__atlas__ » : 64 caractères au plus en tout.
    "long": code(outil="salut_" + "x" * 47),
    "pris": code(outil="memoire_lire"),
    "niveau": code().replace("Niveau.N1, dire", "2, dire"),
    "double": code().replace(
        "dire)]", "dire), Outil('salut_dire', 'Encore.', {}, Niveau.N1, dire)]"
    ),
    # Ce que l'API de Claude refuserait ferait échouer chaque conversation : refusé d'emblée.
    "description": code().replace('"Dit bonjour."', "42"),
    "parametres": code().replace("{}, Niveau.N1", "'aucun', Niveau.N1"),
    "schema": code().replace(
        "{}, Niveau.N1",
        "{'type': 'object', 'properties': {'jour': {'type': 'date'}}}, Niveau.N1",
    ),
    "gestionnaire": code().replace("Niveau.N1, dire", "Niveau.N1, None"),
}


def test_un_nom_d_outil_de_52_caracteres_passe(officiels, perso):
    deposer(perso, "salut", outil="salut_" + "x" * 46)
    assert registre(officiels, perso).basculer("salut", True) is True


@pytest.mark.parametrize(
    ("cas", "raison"),
    [
        ("import", "RuntimeError : il manque un point-virgule"),
        ("creer", "ValueError : pas de réseau"),
        ("sortie", "SystemExit : 3"),
        ("outils", "outils() doit rendre une liste d'Outil"),
        ("nom", "nom d'outil invalide : Dire-Bonjour"),
        ("long", "nom d'outil invalide : salut_" + "x" * 47),
        ("pris", "nom d'outil déjà pris : memoire_lire"),
        ("niveau", "niveau invalide pour salut_dire"),
        ("double", "nom d'outil déjà pris : salut_dire"),
        ("description", "description invalide pour salut_dire"),
        ("parametres", "paramètres invalides pour salut_dire"),
        ("schema", "paramètres invalides pour salut_dire"),
        ("gestionnaire", "gestionnaire invalide pour salut_dire"),
    ],
)
def test_un_connecteur_qui_plante_passe_en_erreur_sans_rien_casser(
    officiels, perso, caplog, cas, raison
):
    deposer(perso, "salut", source=CASSES[cas])
    r = registre(officiels, perso)
    r.reserver(["memoire_lire"])
    assert r.basculer("salut", True) is False
    assert etats(r)["salut"][1:] == ("en_erreur", raison)
    assert r.actifs() == [] and not fichier_des_interrupteurs(perso).exists()
    assert "le connecteur salut ne se charge pas" in caplog.text
    assert not any(m.startswith("atlas_connecteurs.salut") for m in sys.modules)


def test_un_connecteur_repare_redevient_activable(officiels, perso):
    dossier = deposer(perso, "salut", source=CASSES["import"])
    r = registre(officiels, perso)
    r.basculer("salut", True)
    assert etats(r)["salut"][1] == "en_erreur"
    fichier = dossier / "connecteur.py"
    fichier.write_text(code())
    plus_tard = fichier.stat().st_mtime_ns + 1_000_000_000  # une retouche, une seconde après
    os.utime(fichier, ns=(plus_tard, plus_tard))
    assert etats(r)["salut"][1] == "coupe"
    assert r.basculer("salut", True) is True


def test_deux_connecteurs_ne_partagent_pas_un_nom_d_outil(officiels, perso):
    deposer(perso, "salut", outil="dire_bonjour")
    deposer(perso, "coucou", outil="dire_bonjour")
    r = registre(officiels, perso)
    assert r.basculer("coucou", True) is True
    assert r.basculer("salut", True) is False
    assert etats(r)["salut"][2] == "nom d'outil déjà pris : dire_bonjour"


def test_un_fichier_d_interrupteurs_illisible_coupe_tout(officiels, perso, caplog):
    deposer(perso, "salut")
    fichier = fichier_des_interrupteurs(perso)
    fichier.parent.mkdir(parents=True, exist_ok=True)
    fichier.write_text("{pas du json")
    r = registre(officiels, perso)
    with caplog.at_level(logging.WARNING):
        r.demarrer()
    assert r.actifs() == [] and "interrupteurs des connecteurs illisibles" in caplog.text


# --- la bascule en attente, les secrets, les dépendances -------------------------------


def test_une_bascule_attend_la_conversation_neuve(officiels, perso):
    deposer(perso, "salut")
    r = registre(officiels, perso)
    r.basculer("salut", False)  # déjà coupé : rien ne change, rien n'attend
    assert [f.en_attente for f in r.fiches] == [False]
    r.basculer("salut", True)
    assert [f.en_attente for f in r.fiches] == [True]
    assert r.appliquer() is True
    assert [f.en_attente for f in r.fiches] == [False]
    assert r.appliquer() is False


def test_les_secrets_et_les_dependances_de_tous_les_connecteurs_trouves(officiels, perso):
    deposer(officiels, "salut", MANIFESTE.format(nom="Salut") + REGLAGE)
    deposer(perso, "agenda", MANIFESTE.format(nom="Agenda") + 'dependances = ["caldav>=1.4"]\n')
    deux = 'dependances = ["caldav>=1.4", "icalendar"]\n'
    public = '[[reglages]]\nvariable = "ATLAS_MAIL_SERVEUR"\ndescription = "Le serveur"\n'
    deposer(perso, "mail", MANIFESTE.format(nom="Mail") + deux + public)
    environ = {"ATLAS_BONJOUR_NOM": "un-secret-long", "ATLAS_MAIL_SERVEUR": "imap.exemple.fr"}
    r = registre(officiels, perso, environ=environ)
    r.decouvrir()
    assert r.secrets() == ["un-secret-long"]


def lanceur(echouent: tuple[str, ...] = ()):
    """Un faux `subprocess.run` : note les commandes ; celles qui nomment une des
    exigences données échouent."""
    lancees: list[list[str]] = []

    def lancer(commande, check):
        lancees.append(commande)
        rate = any(e in commande for e in echouent)
        return types.SimpleNamespace(returncode=1 if rate else 0)

    return lancer, lancees


def deposer_des_dependances(officiels, perso):
    deposer(officiels, "ical", MANIFESTE.format(nom="Ical") + 'dependances = ["icalendar"]\n')
    deposer(officiels, "salut")
    deposer(perso, "agenda", MANIFESTE.format(nom="Agenda") + 'dependances = ["caldav>=1.4"]\n')
    deux = 'dependances = ["caldav>=1.4", "vobject"]\n'
    deposer(perso, "mail", MANIFESTE.format(nom="Mail") + deux)


def test_installer_borne_les_dependances_par_le_verrou_d_atlas(officiels, perso):
    # Une dépendance de connecteur ne change jamais une version dont Atlas dépend : les
    # officiels ensemble, puis chaque connecteur de la communauté à part.
    deposer_des_dependances(officiels, perso)
    lancer, lancees = lanceur()
    assert installer(registre(officiels, perso), lancer) == 0
    export = lancees[0]
    verrou = export[export.index("-o") + 1]
    assert export == [
        "uv", "export", "--project", str(DEPOT), "--frozen", "--no-hashes",
        "--no-emit-project", "--all-extras", "--quiet", "-o", verrou,
    ]  # fmt: skip
    installe = ["uv", "pip", "install", "-c", verrou]
    assert lancees[1:] == [
        [*installe, "icalendar"],
        [*installe, "caldav>=1.4"],
        [*installe, "caldav>=1.4", "vobject"],
    ]


def test_un_connecteur_de_la_communaute_qui_ne_s_installe_pas_n_arrete_rien(officiels, perso):
    deposer_des_dependances(officiels, perso)
    lancer, lancees = lanceur(echouent=("caldav>=1.4",))
    assert installer(registre(officiels, perso), lancer) == 0, "make install réussit"
    assert [c[-1] for c in lancees[1:]] == ["icalendar", "caldav>=1.4", "vobject"]


def test_des_dependances_officielles_qui_ne_s_installent_pas_font_echouer(officiels, perso):
    deposer_des_dependances(officiels, perso)
    lancer, lancees = lanceur(echouent=("icalendar",))
    assert installer(registre(officiels, perso), lancer) == 1
    assert len(lancees) == 4, "la communauté s'installe quand même"


def test_sans_le_verrou_rien_ne_s_installe(officiels, perso):
    deposer_des_dependances(officiels, perso)
    lancer, lancees = lanceur(echouent=("export",))
    assert installer(registre(officiels, perso), lancer) == 1
    assert len(lancees) == 1


def test_sans_dependances_rien_ne_se_lance(officiels, perso):
    deposer(officiels, "salut")
    lancer, lancees = lanceur()
    assert installer(registre(officiels, perso), lancer) == 0
    assert installer(registre(officiels / "rien", perso / "rien"), lancer) == 0
    assert lancees == []


def test_une_variable_vide_dans_le_env_manque_encore(officiels, perso):
    # « ATLAS_POSTE_CLE= » tel que dans .env.example : présente, mais vide.
    deposer(perso, "salut", MANIFESTE.format(nom="Salut") + REGLAGE)
    r = registre(officiels, perso, environ={"ATLAS_BONJOUR_NOM": "   "})
    assert etats(r)["salut"][1] == "a_configurer"


def test_au_demarrage_un_connecteur_devenu_a_configurer_ne_se_charge_pas(officiels, perso):
    deposer(perso, "salut", MANIFESTE.format(nom="Salut") + REGLAGE)
    r = registre(officiels, perso, environ={"ATLAS_BONJOUR_NOM": "David"})
    r.basculer("salut", True)
    relu = registre(officiels, perso, environ={})  # la variable a quitté le .env
    relu.demarrer()
    assert relu.actifs() == [] and etats(relu)["salut"][1] == "a_configurer"


def test_les_connecteurs_actifs_suivent_l_ordre_de_la_page(officiels, perso):
    deposer(perso, "salut")
    deposer(officiels, "mac")
    r = registre(officiels, perso)
    r.basculer("salut", True)
    r.basculer("mac", True)
    assert [a.id for a in r.actifs()] == ["mac", "salut"]


def test_les_interrupteurs_restent_prives_meme_apres_un_arret_brutal(officiels, perso):
    deposer(perso, "salut")
    fichier = fichier_des_interrupteurs(perso)
    fichier.parent.mkdir(parents=True, exist_ok=True)
    reste = fichier.with_name(fichier.name + ".tmp")  # laissé par un arrêt en pleine écriture
    reste.write_text("{}")
    reste.chmod(0o644)
    registre(officiels, perso).basculer("salut", True)
    assert stat.S_IMODE(fichier.stat().st_mode) == 0o600


def test_un_connecteur_actif_retire_du_disque_disparait(officiels, perso):
    dossier = deposer(perso, "salut")
    r = registre(officiels, perso)
    r.basculer("salut", True)
    shutil.rmtree(dossier)
    assert r.decouvrir() == [] and r.actifs() == []
    assert "atlas_connecteurs.salut.connecteur" not in sys.modules
    assert json.loads(fichier_des_interrupteurs(perso).read_text()) == {"actifs": []}
    relu = registre(officiels, perso)
    relu.demarrer()
    assert relu.actifs() == []


def test_un_dossier_redepose_sous_le_meme_nom_redemande_confirmation(officiels, perso):
    # Un autre code, déposé sous le nom d'un connecteur activé puis retiré, ne s'active
    # jamais sans que David le voie « Communauté » et le confirme.
    dossier = deposer(perso, "salut")
    registre(officiels, perso).basculer("salut", True)
    shutil.rmtree(dossier)
    registre(officiels, perso).decouvrir()  # une page ouvre ses Paramètres
    temoin = perso / "salut" / "importe"
    deposer(perso, "salut", source=f"open({str(temoin)!r}, 'w').close()\n")
    relu = registre(officiels, perso)
    relu.demarrer()
    assert relu.actifs() == [] and not temoin.exists()
    assert etats(relu)["salut"][:2] == ("communaute", "coupe")


def test_un_officiel_retire_ne_passe_pas_la_main_a_son_homonyme(officiels, perso):
    officiel = deposer(officiels, "meteo")
    temoin = perso / "meteo" / "importe"
    deposer(perso, "meteo", source=f"open({str(temoin)!r}, 'w').close()\n")
    r = registre(officiels, perso)
    r.basculer("meteo", True)
    shutil.rmtree(officiel)  # un git pull l'a retiré
    assert [(f.origine, f.etat) for f in r.decouvrir()] == [("communaute", "coupe")]
    assert r.actifs() == []
    relu = registre(officiels, perso)
    relu.demarrer()
    assert relu.actifs() == [] and not temoin.exists()


def test_un_connecteur_qui_echoue_au_demarrage_reste_coupe(officiels, perso):
    dossier = deposer(perso, "salut")
    registre(officiels, perso).basculer("salut", True)
    fichier = dossier / "connecteur.py"
    fichier.write_text(CASSES["import"])
    relu = registre(officiels, perso)
    relu.demarrer()
    assert etats(relu)["salut"][1] == "en_erreur"
    fichier.write_text(code())  # réparé
    plus_tard = fichier.stat().st_mtime_ns + 1_000_000_000
    os.utime(fichier, ns=(plus_tard, plus_tard))
    encore = registre(officiels, perso)
    encore.demarrer()
    assert encore.actifs() == [] and etats(encore)["salut"][1] == "coupe"


def test_un_repertoire_momentanement_illisible_garde_les_interrupteurs(officiels, perso):
    deposer(perso, "salut")
    registre(officiels, perso).basculer("salut", True)
    perso.chmod(0o000)
    try:
        registre(officiels, perso).decouvrir()
    finally:
        perso.chmod(0o755)
    relu = registre(officiels, perso)
    relu.demarrer()
    assert [a.id for a in relu.actifs()] == ["salut"], "le choix de David tient"


def test_un_repertoire_illisible_laisse_les_officiels(officiels, perso, caplog):
    deposer(officiels, "mac")
    deposer(perso, "salut")
    perso.chmod(0o000)
    try:
        with caplog.at_level(logging.WARNING):
            assert [f.id for f in registre(officiels, perso).decouvrir()] == ["mac"]
    finally:
        perso.chmod(0o755)
    assert "répertoire des connecteurs illisible" in caplog.text

import json
import os
import re
import subprocess
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from test_registre import deposer

from atlas_core import entretien, hub, reglages
from atlas_core.diffuseur import Diffuseur
from atlas_core.protocole import Bonjour

ORIGINE = {"origin": "http://testserver"}
CLE = "cle-de-test"


class RegieEspionne:
    def __init__(self) -> None:
        self.diffuseur = Diffuseur()
        self.saisies: list[str] = []
        self.muets: list[bool] = []
        self.pages: list[str | None] = []
        self.rattachees: list[tuple[str | None, object]] = []
        self.detachees: list = []

    def voix_active(self) -> bool:
        return True

    def rattacher(self, session, page: str | None = None) -> None:
        self.rattachees.append((page, session))

    def detacher(self, session) -> None:
        self.detachees.append(session)

    async def saisie(self, texte: str, page: str | None = None) -> None:
        self.saisies.append(texte)
        self.pages.append(page)

    async def basculer_muet(self, actif: bool) -> None:
        self.muets.append(actif)


@pytest.fixture
def regie(monkeypatch) -> RegieEspionne:
    espionne = RegieEspionne()
    monkeypatch.setattr(hub, "_regie", espionne)
    monkeypatch.setattr(hub, "_config", replace(hub._config, web_cle=CLE))
    return espionne


def _entrer(ws, cle: str = CLE) -> list[str]:
    ws.send_json({"type": "authentification", "cle": cle})
    return [ws.receive_json()["type"] for _ in range(3)]


def test_une_page_authentifiee_recoit_historique_muet_et_etat(regie):
    with TestClient(hub.app) as client, client.websocket_connect("/ws/web", headers=ORIGINE) as ws:
        assert _entrer(ws) == ["historique", "muet", "etat"]


def test_saisie_et_muet_arrivent_a_la_regie(regie):
    with TestClient(hub.app) as client, client.websocket_connect("/ws/web", headers=ORIGINE) as ws:
        _entrer(ws)
        ws.send_json({"type": "saisie", "texte": " quelle heure est-il "})
        ws.send_json({"type": "muet", "actif": True})
        ws.send_json({"type": "saisie", "texte": ""})  # sa réponse prouve que tout est traité
        erreur = ws.receive_json()
    assert erreur["type"] == "erreur" and erreur["code"] == "message_invalide"
    assert "entre 1 et 1000 caractères" in erreur["message"]
    assert regie.saisies == ["quelle heure est-il"] and regie.muets == [True]


@pytest.mark.parametrize("page", [None, "ipad-1"])
def test_une_question_tapee_porte_l_identifiant_de_sa_page(regie, page):
    entree = {"type": "authentification", "cle": CLE} | ({"page": page} if page else {})
    with TestClient(hub.app) as client, client.websocket_connect("/ws/web", headers=ORIGINE) as ws:
        ws.send_json(entree)
        [ws.receive_json() for _ in range(3)]
        ws.send_json({"type": "saisie", "texte": "quelle heure est-il"})
        ws.send_json({"type": "saisie", "texte": ""})  # sa réponse prouve que tout est traité
        ws.receive_json()
    assert regie.saisies == ["quelle heure est-il"] and regie.pages == [page]


# --- les documents et la confirmation ----------------------------------------------

OFFRE = "# Offre de lancement\n\nTrois formules pour les premiers clients.\n"


@pytest.fixture
def memoire(regie, monkeypatch, tmp_path):
    dossier = tmp_path / "memoire"
    config = replace(hub._config, web_cle=CLE, cerveau="claude", memoire_dossier=dossier)
    monkeypatch.setattr(hub, "_config", config)
    monkeypatch.setattr(hub, "DOSSIER_CERVEAU", tmp_path / "cerveau")
    return dossier


def test_une_page_liste_puis_lit_les_documents(memoire):
    with TestClient(hub.app) as client, client.websocket_connect("/ws/web", headers=ORIGINE) as ws:
        _entrer(ws)
        hub._outils.memoire.ecrire_document("offre-de-lancement", OFFRE)
        ws.send_json({"type": "documents"})
        liste = ws.receive_json()
        ws.send_json({"type": "lire_document", "chemin": "documents/offre-de-lancement.md"})
        document = ws.receive_json()
        ws.send_json({"type": "lire_document", "chemin": "documents/absent.md"})
        absent = ws.receive_json()
    assert (liste["type"], liste["disponible"]) == ("liste_documents", True)
    [info] = liste["documents"]
    assert (info["chemin"], info["titre"], info["resume"]) == (
        "documents/offre-de-lancement.md",
        "Offre de lancement",
        "Trois formules pour les premiers clients.",
    )
    assert re.fullmatch(r"\d{1,2}(er)? \w+ \d{4}, \d{1,2} h \d{2}", info["modifie"])
    assert document == {
        "type": "document",
        "chemin": "documents/offre-de-lancement.md",
        "titre": "Offre de lancement",
        "contenu": OFFRE,
        "erreur": None,
    }
    assert (absent["contenu"], absent["erreur"]) == ("", "documents/absent.md n'existe pas.")


def test_une_page_ne_lit_pas_une_fiche_par_le_panneau_des_documents(memoire):
    with TestClient(hub.app) as client, client.websocket_connect("/ws/web", headers=ORIGINE) as ws:
        _entrer(ws)
        ws.send_json({"type": "lire_document", "chemin": "profil.md"})
        erreur = ws.receive_json()
    assert (erreur["type"], erreur["code"]) == ("erreur", "message_invalide")


def test_sans_memoire_la_page_le_sait(regie, monkeypatch):
    monkeypatch.setattr(hub, "_config", replace(hub._config, web_cle=CLE, cerveau="bouchon"))
    with TestClient(hub.app) as client, client.websocket_connect("/ws/web", headers=ORIGINE) as ws:
        _entrer(ws)
        ws.send_json({"type": "documents"})
        liste = ws.receive_json()
        ws.send_json({"type": "lire_document", "chemin": "documents/offre-de-lancement.md"})
        document = ws.receive_json()
    assert liste == {"type": "liste_documents", "disponible": False, "documents": []}
    assert document["erreur"] == "La mémoire n'est pas disponible."


@pytest.fixture
def connecteurs(memoire, monkeypatch, tmp_path):
    dossier = tmp_path / "connecteurs"
    (dossier / "casse").mkdir(parents=True)  # un dossier sans manifeste
    monkeypatch.setattr(hub, "_config", replace(hub._config, connecteurs_dossier=dossier))
    monkeypatch.setenv("ATLAS_POSTE_CLE", "cle-du-poste-de-test")


def _fiche(liste: dict, id_: str = "poste") -> dict:
    """La fiche d'un connecteur dans une liste : les officiels sont triés par nom."""
    [fiche] = [fiche for fiche in liste["connecteurs"] if fiche["id"] == id_]
    return fiche


def test_une_page_liste_les_connecteurs_meme_casses(connecteurs):
    with TestClient(hub.app) as client, client.websocket_connect("/ws/web", headers=ORIGINE) as ws:
        _entrer(ws)
        ws.send_json({"type": "connecteurs"})
        liste = ws.receive_json()
    assert (liste["type"], liste["disponible"]) == ("liste_connecteurs", True)
    poste, casse = _fiche(liste), _fiche(liste, "casse")
    assert liste["connecteurs"][-1] is casse, "les officiels d'abord"
    assert (poste["id"], poste["nom"], poste["origine"], poste["etat"]) == (
        "poste",
        "Le poste du Mac",
        "atlas",
        "coupe",
    )
    assert (poste["version"], poste["auteur"]) == ("1.0.0", "Atlas")
    assert casse == {
        "id": "casse",
        "nom": "casse",
        "description": "",
        "version": "",
        "auteur": "",
        "origine": "communaute",
        "etat": "en_erreur",
        "detail": "connecteur.toml absent",
        "en_attente": False,
        "reglages": [],
    }
    assert poste["reglages"] == [
        {
            "variable": "ATLAS_POSTE_CLE",
            "description": "La clé du poste : la même dans le .env du Core et dans celui du "
            "Mac qui lance make run-poste",
            "secret": True,
            "defini": True,
            "modifiable": False,
            "valeur": "",
        }
    ]


def test_la_liste_demandee_ne_va_qu_a_la_page_qui_la_demande(connecteurs):
    with (
        TestClient(hub.app) as client,
        client.websocket_connect("/ws/web", headers=ORIGINE) as ws,
        client.websocket_connect("/ws/web", headers=ORIGINE) as autre,
    ):
        _entrer(ws)
        _entrer(autre)
        ws.send_json({"type": "connecteurs"})
        assert ws.receive_json()["type"] == "liste_connecteurs"
        autre.send_json({"type": "saisie", "texte": ""})  # sa réponse suit tout ce qu'elle a reçu
        assert autre.receive_json()["type"] == "erreur"


def test_activer_un_connecteur_renouvelle_la_conversation_et_toutes_les_pages_le_voient(
    connecteurs, monkeypatch
):
    with (
        TestClient(hub.app) as client,
        client.websocket_connect("/ws/web", headers=ORIGINE) as ws,
        client.websocket_connect("/ws/web", headers=ORIGINE) as autre,
    ):
        _entrer(ws)
        _entrer(autre)
        renouvellements: list[bool] = []
        monkeypatch.setattr(hub._cerveau, "renouveler", lambda: renouvellements.append(True))
        ws.send_json({"type": "activer_connecteur", "id": "poste", "actif": True})
        autre.send_json(
            {"type": "activer_connecteur", "id": "poste", "actif": True}
        )  # en même temps
        for page in (ws, autre, ws, autre):
            fiche = _fiche(page.receive_json())
            assert (fiche["etat"], fiche["en_attente"]) == ("actif", True)
        assert renouvellements == [True], "une seule conversation neuve"
        assert "mcp__atlas__mac_mission" in hub._outils.noms
        ws.send_json({"type": "activer_connecteur", "id": "inconnu", "actif": True})
        assert "inconnu" not in [f["id"] for f in ws.receive_json()["connecteurs"]]
        ws.send_json({"type": "activer_connecteur", "id": "../memoire", "actif": True})
        erreur = ws.receive_json()
    assert (erreur["type"], erreur["code"]) == ("erreur", "message_invalide")
    assert renouvellements == [True], "rien n'a changé : la conversation continue"


def test_la_note_d_attente_tient_jusqu_a_la_question_suivante(connecteurs):
    # Sans doublure du cerveau : la conversation se clôt pour de bon, mais aucune question
    # n'a encore ouvert la suivante.
    with TestClient(hub.app) as client, client.websocket_connect("/ws/web", headers=ORIGINE) as ws:
        _entrer(ws)
        ws.send_json({"type": "activer_connecteur", "id": "poste", "actif": True})
        assert _fiche(ws.receive_json())["en_attente"] is True
        for _ in range(3):
            ws.send_json({"type": "connecteurs"})
            fiche = _fiche(ws.receive_json())
        assert (fiche["etat"], fiche["en_attente"]) == ("actif", True)


BONJOUR = """nom = "Bonjour"
description = "Atlas te salue."
version = "0.1"
auteur = "Quelqu'un"
api = 1

[[reglages]]
variable = "ATLAS_BONJOUR_NOM"
description = "Le nom à saluer"

[[reglages]]
variable = "ATLAS_BONJOUR_CLE"
description = "La clé du service"
secret = true

[[reglages]]
variable = "ATLAS_AUDIO_CLE"
description = "Une clé d'Atlas déclarée comme un réglage ordinaire"
"""
SECRET = "sesame-de-test-bien-long"


def bonjour(liste: dict) -> dict:
    return next(f for f in liste["connecteurs"] if f["id"] == "bonjour")  # après le poste


@pytest.fixture
def reglables(memoire, monkeypatch, tmp_path):
    dossier = tmp_path / "connecteurs"
    deposer(dossier, "bonjour", BONJOUR)
    monkeypatch.setattr(hub, "_config", replace(hub._config, connecteurs_dossier=dossier))
    for variable in ("ATLAS_BONJOUR_NOM", "ATLAS_BONJOUR_CLE"):
        monkeypatch.setenv(variable, "")  # rendue telle qu'avant le test, quoi qu'il écrive
        monkeypatch.delenv(variable)
    monkeypatch.setenv("ATLAS_AUDIO_CLE", "cle-audio-de-test")


def test_une_page_regle_un_connecteur_et_toutes_les_pages_le_voient(reglables, caplog):
    with (
        TestClient(hub.app) as client,
        client.websocket_connect("/ws/web", headers=ORIGINE) as ws,
        client.websocket_connect("/ws/web", headers=ORIGINE) as autre,
    ):
        _entrer(ws)
        _entrer(autre)
        valeurs = {"ATLAS_BONJOUR_NOM": "David", "ATLAS_BONJOUR_CLE": SECRET}
        ws.send_json({"type": "regler_connecteur", "id": "bonjour", "valeurs": valeurs})
        recus = [ws.receive_text(), ws.receive_text(), autre.receive_text()]
    resultat, liste, vue_par_l_autre = (json.loads(r) for r in recus)
    assert resultat == {"type": "resultat_reglage", "id": "bonjour", "ok": True,
                        "message": "Enregistré."}  # fmt: skip
    assert liste == vue_par_l_autre
    fiche = bonjour(liste)
    assert fiche["etat"] == "coupe"
    nom, cle, audio = fiche["reglages"]
    assert (nom["defini"], nom["valeur"], nom["modifiable"]) == (True, "David", True)
    assert (cle["defini"], cle["valeur"], cle["secret"]) == (True, "", True)
    assert (audio["defini"], audio["valeur"], audio["modifiable"]) == (True, "", False)
    ecrit = reglages.FICHIER_ENV.read_text(encoding="utf-8")
    assert ecrit == f"ATLAS_BONJOUR_NOM=David\nATLAS_BONJOUR_CLE={SECRET}\n"
    assert not any(SECRET in r or "cle-audio-de-test" in r for r in recus)
    assert SECRET not in caplog.text


def test_un_reglage_refuse_ne_va_qu_a_la_page_qui_l_a_saisi(reglables):
    with (
        TestClient(hub.app) as client,
        client.websocket_connect("/ws/web", headers=ORIGINE) as ws,
        client.websocket_connect("/ws/web", headers=ORIGINE) as autre,
    ):
        _entrer(ws)
        _entrer(autre)
        ws.send_json({"type": "connecteurs"})
        nom, cle, _ = bonjour(ws.receive_json())["reglages"]
        assert (nom["defini"], nom["valeur"], cle["defini"]) == (False, "", False)
        valeurs = {"ATLAS_AUDIO_CLE": "prise"}
        ws.send_json({"type": "regler_connecteur", "id": "bonjour", "valeurs": valeurs})
        assert ws.receive_json() == {
            "type": "resultat_reglage",
            "id": "bonjour",
            "ok": False,
            "message": "ATLAS_AUDIO_CLE est une clé d'Atlas : elle se change au Terminal.",
        }
        autre.send_json({"type": "saisie", "texte": ""})  # sa réponse suit tout ce qu'elle a reçu
        assert autre.receive_json()["type"] == "erreur"
    assert not reglages.FICHIER_ENV.exists()


def test_regler_un_connecteur_actif_renouvelle_la_conversation(reglables, monkeypatch):
    monkeypatch.setenv("ATLAS_BONJOUR_NOM", "David")
    monkeypatch.setenv("ATLAS_BONJOUR_CLE", SECRET)
    with TestClient(hub.app) as client, client.websocket_connect("/ws/web", headers=ORIGINE) as ws:
        _entrer(ws)
        renouvellements: list[bool] = []
        monkeypatch.setattr(hub._cerveau, "renouveler", lambda: renouvellements.append(True))
        ws.send_json({"type": "activer_connecteur", "id": "bonjour", "actif": True})
        ws.receive_json()
        valeurs = {"ATLAS_BONJOUR_NOM": "Camille"}
        ws.send_json({"type": "regler_connecteur", "id": "bonjour", "valeurs": valeurs})
        assert ws.receive_json()["ok"] is True
        fiche = bonjour(ws.receive_json())
    assert (fiche["etat"], fiche["en_attente"]) == ("actif", True)
    assert renouvellements == [True, True]


@pytest.fixture
def depot(regie, monkeypatch, tmp_path):
    """Un dépôt git sur main, un commit : celui du Core, le temps du test."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    for cle, valeur in {"NAME": "Test", "EMAIL": "test@example.com"}.items():
        monkeypatch.setenv(f"GIT_AUTHOR_{cle}", valeur)
        monkeypatch.setenv(f"GIT_COMMITTER_{cle}", valeur)
    dossier = tmp_path / "depot"
    for commande in (["init", "-q", "-b", "main", str(dossier)], ["-C", str(dossier), "commit",
                     "-q", "--allow-empty", "-m", "Premier"]):  # fmt: skip
        subprocess.run(["git", *commande], check=True)
    monkeypatch.setattr(entretien, "DEPOT", dossier)
    monkeypatch.setattr(entretien, "DELAI_ARRET_S", 0)
    return dossier


def test_la_page_demande_la_version_du_core(depot):
    with TestClient(hub.app) as client, client.websocket_connect("/ws/web", headers=ORIGINE) as ws:
        _entrer(ws)
        ws.send_json({"type": "demande_core"})
        etat = ws.receive_json()
    version = subprocess.run(
        ["git", "-C", str(depot), "rev-parse", "--short", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    assert etat["type"] == "etat_core" and etat["version"] == version
    assert (etat["occupe"], etat["mise_a_jour_possible"], etat["raison"]) == (False, True, "")


def test_redemarrer_depuis_une_page_toutes_les_pages_le_voient(depot, monkeypatch):
    arrets: list[bool] = []
    monkeypatch.setattr(entretien, "arreter_le_core", lambda: arrets.append(True))
    with (
        TestClient(hub.app) as client,
        client.websocket_connect("/ws/web", headers=ORIGINE) as ws,
        client.websocket_connect("/ws/web", headers=ORIGINE) as autre,
    ):
        _entrer(ws)
        _entrer(autre)
        ws.send_json({"type": "redemarrer_core"})
        attendu = {"type": "core_en_cours", "etape": "redemarrage",
                   "texte": "Redémarrage du Core…", "nouveautes": []}  # fmt: skip
        assert ws.receive_json() == attendu and autre.receive_json() == attendu
        assert (depot / "donnees" / "redemarrer").exists()
        ws.send_json({"type": "redemarrer_core"})  # un deuxième clic
        refus = ws.receive_json()
        autre.send_json({"type": "saisie", "texte": ""})  # sa réponse suit tout ce qu'elle a reçu
        assert autre.receive_json()["type"] == "erreur"
    assert (refus["type"], refus["ok"], refus["texte"]) == ("fin_core", False, entretien.OCCUPE)
    assert arrets == [True]


def test_mettre_a_jour_hors_de_main_est_refuse_a_la_page_qui_le_demande(depot):
    subprocess.run(["git", "-C", str(depot), "switch", "-q", "-c", "essai"], check=True)
    with TestClient(hub.app) as client, client.websocket_connect("/ws/web", headers=ORIGINE) as ws:
        _entrer(ws)
        ws.send_json({"type": "mettre_a_jour_core"})
        refus = ws.receive_json()
    assert (refus["type"], refus["ok"]) == ("fin_core", False)
    assert refus["texte"] == (
        "Le dépôt du Core est sur la branche essai, pas sur main : mets-le à jour au Terminal."
    )


def test_au_demarrage_une_marque_restee_la_s_efface(depot):
    (depot / "donnees").mkdir()
    (depot / "donnees" / "redemarrer").touch()
    with TestClient(hub.app):
        assert not (depot / "donnees" / "redemarrer").exists()


def test_l_arret_du_core_arrete_l_entretien(depot, monkeypatch):
    fermes: list[bool] = []

    async def fermer(self) -> None:
        fermes.append(True)

    monkeypatch.setattr(entretien.Entretien, "fermer", fermer)
    with TestClient(hub.app):
        assert fermes == []
    assert fermes == [True]


def test_sans_memoire_pas_de_connecteurs(regie, monkeypatch):
    monkeypatch.setattr(hub, "_config", replace(hub._config, web_cle=CLE, cerveau="bouchon"))
    with TestClient(hub.app) as client, client.websocket_connect("/ws/web", headers=ORIGINE) as ws:
        _entrer(ws)
        ws.send_json({"type": "connecteurs"})
        liste = ws.receive_json()
        ws.send_json({"type": "activer_connecteur", "id": "poste", "actif": True})
        apres = ws.receive_json()
        valeurs = {"ATLAS_POSTE_CLE": "x"}
        ws.send_json({"type": "regler_connecteur", "id": "poste", "valeurs": valeurs})
        refus = ws.receive_json()
    assert liste == apres == {"type": "liste_connecteurs", "disponible": False, "connecteurs": []}
    assert (refus["ok"], refus["message"]) == (
        False,
        "La mémoire n'est pas disponible : pas de connecteurs.",
    )


class _Attente:
    def __init__(self, en_attente: bool) -> None:
        self.en_attente = en_attente


class _Outils:
    def __init__(self, en_attente: bool) -> None:
        self.confirmations = _Attente(en_attente)


@pytest.mark.parametrize(("en_attente", "saisies"), [(True, ["oui", "non"]), (False, [])])
def test_les_boutons_repondent_comme_une_saisie_de_leur_page(
    regie, monkeypatch, en_attente, saisies
):
    with TestClient(hub.app) as client, client.websocket_connect("/ws/web", headers=ORIGINE) as ws:
        ws.send_json({"type": "authentification", "cle": CLE, "page": "iphone-1"})
        [ws.receive_json() for _ in range(3)]
        monkeypatch.setattr(hub, "_outils", _Outils(en_attente))
        ws.send_json({"type": "confirmer", "oui": True})
        ws.send_json({"type": "confirmer", "oui": False})
        ws.send_json({"type": "saisie", "texte": ""})  # sa réponse prouve que tout est traité
        ws.receive_json()
    assert regie.saisies == saisies and regie.pages == ["iphone-1"] * len(saisies)


class _Mission:
    def __init__(self, en_cours: str | None) -> None:
        self.en_cours = en_cours


class _OutilsDuPoste:
    def __init__(self, en_cours: str | None) -> None:
        self.missions = _Mission(en_cours)


@pytest.mark.parametrize(("en_cours", "saisies"), [("écrire bonjour", ["stop"]), (None, [])])
def test_le_bouton_stop_revient_a_taper_stop_depuis_sa_page(regie, monkeypatch, en_cours, saisies):
    with TestClient(hub.app) as client, client.websocket_connect("/ws/web", headers=ORIGINE) as ws:
        ws.send_json({"type": "authentification", "cle": CLE, "page": "iphone-1"})
        [ws.receive_json() for _ in range(3)]
        monkeypatch.setattr(hub, "_outils", _OutilsDuPoste(en_cours))
        ws.send_json({"type": "stop"})
        ws.send_json({"type": "saisie", "texte": ""})  # sa réponse prouve que tout est traité
        ws.receive_json()
    assert regie.saisies == saisies and regie.pages == ["iphone-1"] * len(saisies)


def test_une_mauvaise_cle_ferme_la_connexion(regie):
    with TestClient(hub.app) as client, client.websocket_connect("/ws/web", headers=ORIGINE) as ws:
        ws.send_json({"type": "authentification", "cle": "pas-la-bonne"})
        with pytest.raises(WebSocketDisconnect) as fermeture:
            ws.receive_json()
    assert fermeture.value.code == hub.FERMETURE_NON_AUTORISE


def test_un_autre_premier_message_ferme_la_connexion(regie):
    with TestClient(hub.app) as client, client.websocket_connect("/ws/web", headers=ORIGINE) as ws:
        ws.send_json({"type": "saisie", "texte": "sans clé"})
        with pytest.raises(WebSocketDisconnect) as fermeture:
            ws.receive_json()
    assert fermeture.value.code == hub.FERMETURE_NON_AUTORISE
    assert regie.saisies == []


def test_sans_authentification_la_connexion_se_ferme(regie, monkeypatch):
    monkeypatch.setattr(hub, "DELAI_AUTHENTIFICATION_S", 0.05)
    with TestClient(hub.app) as client, client.websocket_connect("/ws/web", headers=ORIGINE) as ws:
        with pytest.raises(WebSocketDisconnect) as fermeture:
            ws.receive_json()
    assert fermeture.value.code == hub.FERMETURE_NON_AUTORISE


def test_sans_cle_configuree_la_page_est_prevenue(regie, monkeypatch):
    monkeypatch.setattr(hub, "_config", replace(hub._config, web_cle=""))
    with TestClient(hub.app) as client, client.websocket_connect("/ws/web", headers=ORIGINE) as ws:
        erreur = ws.receive_json()
        with pytest.raises(WebSocketDisconnect) as fermeture:
            ws.receive_json()
    assert erreur["code"] == "cle_absente" and "ATLAS_WEB_CLE" in erreur["message"]
    assert fermeture.value.code == hub.FERMETURE_CLE_ABSENTE


def test_une_autre_origine_est_refusee_avant_meme_d_accepter(regie):
    with TestClient(hub.app) as client:
        with pytest.raises(WebSocketDisconnect) as fermeture:
            with client.websocket_connect("/ws/web", headers={"origin": "http://ailleurs.example"}):
                pass
    assert fermeture.value.code == hub.FERMETURE_ORIGINE


def test_la_page_est_servie_avec_sa_politique_de_securite():
    with TestClient(hub.app) as client:
        r = client.get("/")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert r.headers["content-security-policy"].startswith("default-src 'self'")
    assert "ws://testserver" in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff"


def test_les_fichiers_de_la_page_ne_sont_jamais_mis_en_cache_sans_revalidation():
    with TestClient(hub.app) as client:
        assert client.get("/").headers["cache-control"] == "no-cache"
        assert client.get("/app.js").headers["cache-control"] == "no-cache"


def test_la_route_de_sante_reste_disponible():
    with TestClient(hub.app) as client:
        assert client.get("/sante").json()["ok"] is True


def test_une_page_web_ne_peut_pas_se_brancher_sur_ws_audio():
    with TestClient(hub.app) as client:
        for origine in ("http://ailleurs.example", "http://testserver"):
            with pytest.raises(WebSocketDisconnect) as fermeture:
                with client.websocket_connect("/ws/audio", headers={"origin": origine}):
                    pass
            assert fermeture.value.code == hub.FERMETURE_ORIGINE


class SessionAudioEspionne:
    def __init__(self, envoyer_json, envoyer_binaire) -> None:
        pass

    async def sur_message(self, msg) -> None:
        pass

    async def sur_audio(self, pcm: bytes) -> None:
        pass

    async def fermer(self) -> None:
        pass


def test_le_client_audio_est_rattache_puis_detache_de_la_regie(monkeypatch):
    fake = SessionAudioEspionne(None, None)
    monkeypatch.setattr(hub, "creer_session", lambda envoyer_json, envoyer_binaire: fake)
    monkeypatch.setattr(hub, "_config", replace(hub._config, audio_cle="cle-audio"))
    with TestClient(hub.app) as client, client.websocket_connect("/ws/audio") as ws:
        ws.send_text(Bonjour(client="test", cle="cle-audio").model_dump_json())
        ws.send_text('{"type":"nimporte_quoi"}')
        assert ws.receive_json()["code"] == "message_invalide"  # la boucle est atteinte
        assert hub._regie._sessions == [(None, fake)]
        ws.close()
    assert hub._regie._sessions == []

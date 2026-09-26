import re
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from atlas_core import hub
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

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from atlas_core import hub
from atlas_core.diffuseur import Diffuseur

ORIGINE = {"origin": "http://testserver"}
CLE = "cle-de-test"


class RegieEspionne:
    def __init__(self) -> None:
        self.diffuseur = Diffuseur()
        self.saisies: list[str] = []
        self.muets: list[bool] = []

    def voix_active(self) -> bool:
        return True

    def rattacher(self, session) -> None:
        pass

    def detacher(self, session) -> None:
        pass

    async def saisie(self, texte: str) -> None:
        self.saisies.append(texte)

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
    with TestClient(hub.app) as client, client.websocket_connect("/ws/audio") as ws:
        assert hub._regie._session_audio is fake
        ws.close()
    assert hub._regie._session_audio is None

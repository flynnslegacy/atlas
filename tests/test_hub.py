import json

from fastapi.testclient import TestClient

from helios_core import hub
from helios_core.protocole import TAILLE_BLOC_OCTETS, Bonjour, encoder_audio_entrant


class SessionEspionne:
    def __init__(self, envoyer_json, envoyer_binaire) -> None:
        self.envoyer_json = envoyer_json
        self.messages: list = []
        self.audio: list[bytes] = []

    async def sur_message(self, msg) -> None:
        self.messages.append(msg)

    async def sur_audio(self, pcm: bytes) -> None:
        self.audio.append(pcm)

    async def fermer(self) -> None:
        pass


def test_la_route_de_sante_repond():
    with TestClient(hub.app) as client:
        r = client.get("/sante")
        assert r.status_code == 200 and r.json()["ok"] is True


def test_un_bonjour_arrive_jusqu_a_la_session(monkeypatch):
    espionnes: list[SessionEspionne] = []

    def fabrique(envoyer_json, envoyer_binaire):
        s = SessionEspionne(envoyer_json, envoyer_binaire)
        espionnes.append(s)
        return s

    monkeypatch.setattr(hub, "creer_session", fabrique)
    with TestClient(hub.app) as client, client.websocket_connect("/ws/audio") as ws:
        ws.send_text(Bonjour(client="test").model_dump_json())
        ws.send_bytes(encoder_audio_entrant(b"\x00" * TAILLE_BLOC_OCTETS))
        ws.close()

    assert isinstance(espionnes[0].messages[0], Bonjour)
    assert espionnes[0].audio == [b"\x00" * TAILLE_BLOC_OCTETS]


def test_un_message_invalide_renvoie_une_erreur_sans_couper(monkeypatch):
    monkeypatch.setattr(hub, "creer_session", SessionEspionne)
    with TestClient(hub.app) as client, client.websocket_connect("/ws/audio") as ws:
        ws.send_text('{"type":"nimporte_quoi"}')
        recu = json.loads(ws.receive_text())
        assert recu["type"] == "erreur"
        assert recu["code"] == "message_invalide"
        ws.close()

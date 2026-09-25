import json
import os
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from atlas_core import hub
from atlas_core.cerveau import CerveauBouchon
from atlas_core.cerveau_claude import CerveauClaude
from atlas_core.protocole import (
    TAILLE_BLOC_OCTETS,
    Bonjour,
    Reveil,
    encoder_audio_entrant,
)

CLE_AUDIO = "cle-audio-de-test"


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


@pytest.fixture
def cle_audio(monkeypatch) -> str:
    monkeypatch.setattr(hub, "_config", replace(hub._config, audio_cle=CLE_AUDIO))
    return CLE_AUDIO


def _bonjour(cle: str = CLE_AUDIO) -> str:
    return Bonjour(client="test", cle=cle).model_dump_json()


def test_la_route_de_sante_repond():
    with TestClient(hub.app) as client:
        r = client.get("/sante")
        assert r.status_code == 200 and r.json()["ok"] is True


def test_apres_le_bonjour_les_messages_arrivent_a_la_session(monkeypatch, cle_audio):
    espionnes: list[SessionEspionne] = []

    def fabrique(envoyer_json, envoyer_binaire):
        s = SessionEspionne(envoyer_json, envoyer_binaire)
        espionnes.append(s)
        return s

    monkeypatch.setattr(hub, "creer_session", fabrique)
    with TestClient(hub.app) as client, client.websocket_connect("/ws/audio") as ws:
        ws.send_text(_bonjour())
        ws.send_text(Reveil(confiance=1.0, horodatage=0.0).model_dump_json())
        ws.send_bytes(encoder_audio_entrant(b"\x00" * TAILLE_BLOC_OCTETS))
        ws.close()

    assert [type(m) for m in espionnes[0].messages] == [Reveil], "le bonjour reste au hub"
    assert espionnes[0].audio == [b"\x00" * TAILLE_BLOC_OCTETS]


def test_un_message_invalide_renvoie_une_erreur_sans_couper(monkeypatch, cle_audio):
    monkeypatch.setattr(hub, "creer_session", SessionEspionne)
    with TestClient(hub.app) as client, client.websocket_connect("/ws/audio") as ws:
        ws.send_text(_bonjour())
        ws.send_text('{"type":"nimporte_quoi"}')
        recu = json.loads(ws.receive_text())
        assert recu["type"] == "erreur"
        assert recu["code"] == "message_invalide"
        ws.close()


@pytest.mark.parametrize(
    "premier",
    [
        Bonjour(client="test", cle="pas-la-bonne").model_dump_json(),
        Bonjour(client="test").model_dump_json(),
        Reveil(confiance=1.0, horodatage=0.0).model_dump_json(),
        "pas du json",
    ],
)
def test_sans_la_bonne_cle_ws_audio_se_ferme(monkeypatch, cle_audio, premier):
    espionnes: list = []
    monkeypatch.setattr(hub, "creer_session", lambda j, b: espionnes.append(1))
    with TestClient(hub.app) as client, client.websocket_connect("/ws/audio") as ws:
        ws.send_text(premier)
        with pytest.raises(WebSocketDisconnect) as fermeture:
            ws.receive_text()
    assert fermeture.value.code == hub.FERMETURE_NON_AUTORISE
    assert espionnes == [], "aucune session pour un client refusé"


def test_sans_bonjour_a_temps_ws_audio_se_ferme(monkeypatch, cle_audio):
    monkeypatch.setattr(hub, "DELAI_AUTHENTIFICATION_S", 0.05)
    with TestClient(hub.app) as client, client.websocket_connect("/ws/audio") as ws:
        with pytest.raises(WebSocketDisconnect) as fermeture:
            ws.receive_text()
    assert fermeture.value.code == hub.FERMETURE_NON_AUTORISE


def test_sans_cle_configuree_ws_audio_refuse_tout(monkeypatch):
    monkeypatch.setattr(hub, "_config", replace(hub._config, audio_cle=""))
    with TestClient(hub.app) as client, client.websocket_connect("/ws/audio") as ws:
        erreur = json.loads(ws.receive_text())
        with pytest.raises(WebSocketDisconnect) as fermeture:
            ws.receive_text()
    assert erreur["code"] == "cle_absente" and "ATLAS_AUDIO_CLE" in erreur["message"]
    assert fermeture.value.code == hub.FERMETURE_CLE_ABSENTE


# --- le cerveau ------------------------------------------------------------------


def test_le_bouchon_se_choisit_par_la_configuration():
    assert isinstance(hub.creer_cerveau(replace(hub._config, cerveau="bouchon")), CerveauBouchon)


def test_le_cerveau_claude_ne_demarre_rien_avant_la_premiere_question(monkeypatch, tmp_path):
    dossier = tmp_path / "cerveau"
    monkeypatch.setattr(hub, "DOSSIER_CERVEAU", dossier)
    config = replace(hub._config, cerveau="claude", cerveau_modele="claude-sonnet-5")

    cerveau = hub.creer_cerveau(config)

    assert isinstance(cerveau, CerveauClaude)
    assert not dossier.exists(), "rien sur le disque tant que personne n'a rien demandé"
    client = cerveau._fabrique()  # ce que fera la première question
    assert dossier.is_dir()
    assert client.options.cwd == dossier and client.options.model == "claude-sonnet-5"


def test_les_cles_d_api_sont_retirees_de_l_environnement_du_core(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ne-doit-pas-servir")
    hub.creer_cerveau(replace(hub._config, cerveau="claude"))
    assert "ANTHROPIC_API_KEY" not in os.environ


def test_la_voix_et_le_clavier_partagent_le_meme_cerveau(monkeypatch):
    monkeypatch.setattr(hub, "_config", replace(hub._config, cerveau="bouchon"))

    async def rien(_):
        pass

    with TestClient(hub.app):
        voix = hub.creer_session(rien, rien)
        ecrite = hub.creer_session_ecrite()
        assert voix._cerveau is ecrite._cerveau is hub._cerveau


def test_le_cerveau_est_ferme_a_l_arret_du_core(monkeypatch):
    class CerveauEspion(CerveauBouchon):
        ferme = False

        async def fermer(self) -> None:
            CerveauEspion.ferme = True

    monkeypatch.setattr(hub, "creer_cerveau", lambda config: CerveauEspion())
    with TestClient(hub.app):
        assert not CerveauEspion.ferme
    assert CerveauEspion.ferme


async def test_le_client_http_se_ferme_meme_si_le_cerveau_leve_une_exception(monkeypatch):
    class CerveauQuiExplose(CerveauBouchon):
        async def fermer(self) -> None:
            raise RuntimeError("boum")

    monkeypatch.setattr(hub, "creer_cerveau", lambda config: CerveauQuiExplose())

    with pytest.raises(RuntimeError, match="boum"):
        async with hub._cycle_de_vie(hub.app):
            pass

    assert hub._http is None, "le client HTTP doit se fermer même si le cerveau plante"
    assert hub._cerveau is None

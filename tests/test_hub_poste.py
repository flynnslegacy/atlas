"""La route /ws/poste du Core : la clé du poste, puis les actions et leurs réponses."""

import json
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from atlas_core import hub
from atlas_core.poste import ErreurPoste
from atlas_core.protocole_poste import Capturer, Ouvrir

CLE = "cle-du-poste-de-test"


@pytest.fixture
def cle(monkeypatch):
    monkeypatch.setattr(hub, "_config", replace(hub._config, poste_cle=CLE, cerveau="bouchon"))


def _presenter(ws, cle: str = CLE) -> dict:
    ws.send_json({"type": "bonjour", "cle": cle})
    return ws.receive_json()


def test_le_poste_se_presente_puis_repond_aux_actions(cle):
    with TestClient(hub.app) as client, client.websocket_connect("/ws/poste") as ws:
        assert _presenter(ws) == {"type": "pret"}
        assert hub._poste.connecte
        demande = client.portal.start_task_soon(hub._poste.demander, Capturer())
        action = ws.receive_json()
        assert (action["type"], action["geste"]) == ("action", {"nom": "capturer"})
        ws.send_json({"type": "resultat", "id": action["id"], "ok": True, "image": "AAA"})
        assert demande.result(timeout=2).image == "AAA"
        echec = client.portal.start_task_soon(hub._poste.demander, Ouvrir(app="Spotifi"))
        action = ws.receive_json()
        ws.send_json(
            {"type": "resultat", "id": action["id"], "ok": False, "erreur": "Introuvable."}
        )
        with pytest.raises(ErreurPoste, match="Introuvable."):
            echec.result(timeout=2)
    assert not hub._poste.connecte


@pytest.mark.parametrize(
    "premier",
    [
        {"type": "bonjour", "cle": "mauvaise"},
        {"type": "resultat", "id": 1, "ok": True},
    ],
)
def test_sans_la_bonne_cle_d_abord_la_connexion_se_ferme(cle, premier):
    with TestClient(hub.app) as client, client.websocket_connect("/ws/poste") as ws:
        ws.send_json(premier)
        with pytest.raises(WebSocketDisconnect) as fermeture:
            ws.receive_json()
    assert fermeture.value.code == 4401
    assert not hub._poste.connecte


def test_sans_cle_configuree_le_core_refuse_tout_poste(monkeypatch):
    monkeypatch.setattr(hub, "_config", replace(hub._config, poste_cle="", cerveau="bouchon"))
    with TestClient(hub.app) as client, client.websocket_connect("/ws/poste") as ws:
        erreur = ws.receive_json()
        with pytest.raises(WebSocketDisconnect) as fermeture:
            ws.receive_json()
    assert (erreur["type"], erreur["code"]) == ("erreur", "cle_absente")
    assert "ATLAS_POSTE_CLE" in erreur["message"]
    assert fermeture.value.code == 4000


def test_une_page_web_ne_peut_pas_se_brancher_sur_ws_poste(cle):
    with TestClient(hub.app) as client, pytest.raises(WebSocketDisconnect) as fermeture:
        with client.websocket_connect("/ws/poste", headers={"origin": "http://testserver"}) as ws:
            ws.receive_json()
    assert fermeture.value.code == 1008


def test_un_message_invalide_du_poste_est_ignore(cle):
    with TestClient(hub.app) as client, client.websocket_connect("/ws/poste") as ws:
        _presenter(ws)
        ws.send_text("pas du json")
        ws.send_text(json.dumps({"type": "resultat", "id": "x"}))
        ws.send_json({"type": "bonjour", "cle": CLE})  # déjà présenté : sans effet
        demande = client.portal.start_task_soon(hub._poste.demander, Capturer())
        action = ws.receive_json()
        ws.send_json({"type": "resultat", "id": action["id"], "ok": True})
        assert demande.result(timeout=2).ok

"""La route /ws/poste du Core : le poste et le Core se prouvent la clé sans l'envoyer, puis
les actions et leurs réponses, signées de la clé de la session."""

import json
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from atlas_core import hub
from atlas_core.poste import ErreurPoste
from atlas_core.protocole_poste import (
    ActionPoste,
    Capturer,
    Ouvrir,
    ResultatPoste,
    cle_de_session,
    est_signe,
    preuve_du_core,
    preuve_du_poste,
    preuve_valide,
    signer,
)

CLE = "cle-du-poste-de-test"
NONCE = "a" * 32


@pytest.fixture
def cle(monkeypatch):
    monkeypatch.setattr(hub, "_config", replace(hub._config, poste_cle=CLE, cerveau="bouchon"))


def _presenter(ws, cle: str = CLE) -> str:
    """La poignée de main du poste ; rend la clé de la session."""
    ws.send_json({"type": "bonjour", "nonce": NONCE})
    defi = ws.receive_json()
    assert defi["type"] == "defi"
    assert preuve_valide(preuve_du_core(CLE, NONCE, defi["nonce"]), defi["preuve"])
    ws.send_json({"type": "reponse", "preuve": preuve_du_poste(cle, NONCE, defi["nonce"])})
    assert ws.receive_json() == {"type": "pret"}
    return cle_de_session(cle, NONCE, defi["nonce"])


def _repondre(ws, session: str, **resultat) -> None:
    ws.send_text(signer(session, ResultatPoste(**resultat)).model_dump_json())


def test_le_poste_se_presente_puis_repond_aux_actions(cle):
    with TestClient(hub.app) as client, client.websocket_connect("/ws/poste") as ws:
        session = _presenter(ws)
        assert hub._poste.connecte
        demande = client.portal.start_task_soon(hub._poste.demander, Capturer())
        action = ws.receive_json()
        assert (action["type"], action["geste"]) == ("action", {"nom": "capturer"})
        assert est_signe(session, ActionPoste(**action)), "le Core signe chaque action"
        _repondre(ws, session, id=action["id"], ok=True, image="AAA")
        assert demande.result(timeout=2).image == "AAA"
        echec = client.portal.start_task_soon(hub._poste.demander, Ouvrir(app="Spotifi"))
        action = ws.receive_json()
        _repondre(ws, session, id=action["id"], ok=False, erreur="Introuvable.")
        with pytest.raises(ErreurPoste, match="Introuvable."):
            echec.result(timeout=2)
    assert not hub._poste.connecte


def test_une_mauvaise_preuve_ferme_la_connexion(cle):
    with TestClient(hub.app) as client, client.websocket_connect("/ws/poste") as ws:
        ws.send_json({"type": "bonjour", "nonce": NONCE})
        defi = ws.receive_json()
        ws.send_json(
            {"type": "reponse", "preuve": preuve_du_poste("mauvaise", NONCE, defi["nonce"])}
        )
        with pytest.raises(WebSocketDisconnect) as fermeture:
            ws.receive_json()
    assert fermeture.value.code == 4401
    assert not hub._poste.connecte


@pytest.mark.parametrize(
    "premier",
    [
        {"type": "bonjour", "cle": CLE},  # la clé en clair : l'ancien protocole, refusé
        {"type": "resultat", "id": 1, "ok": True},
    ],
)
def test_sans_bonjour_d_abord_la_connexion_se_ferme(cle, premier):
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


def test_un_message_invalide_ou_non_signe_du_poste_est_ignore(cle):
    with TestClient(hub.app) as client, client.websocket_connect("/ws/poste") as ws:
        session = _presenter(ws)
        ws.send_text("pas du json")
        ws.send_text(json.dumps({"type": "resultat", "id": "x"}))
        ws.send_json({"type": "bonjour", "nonce": NONCE})  # déjà présenté : sans effet
        demande = client.portal.start_task_soon(hub._poste.demander, Capturer())
        action = ws.receive_json()
        # Une fausse capture, non signée : un intrus sur le réseau n'abuse pas Claude.
        ws.send_json({"type": "resultat", "id": action["id"], "ok": True, "image": "FAUX"})
        _repondre(ws, session, id=action["id"], ok=True, image="VRAI")
        assert demande.result(timeout=2).image == "VRAI"

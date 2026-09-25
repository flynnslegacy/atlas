"""La route /ws/voix : l'entrée d'une page, et ce qu'elle transmet au client audio que le
Core fait tourner pour elle (remplacé ici par un espion)."""

import asyncio
from dataclasses import replace
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from test_hub_web import RegieEspionne

from atlas_audio.connexion import PeripheriqueEnPanne
from atlas_core import hub

ORIGINE = {"origin": "http://testserver"}
CLE = "cle-de-test"
BLOC = b"\x01" * 640


class PageEspionne:
    def __init__(self, fabrique_session, modeles, reglages, marge_sortie_s, hey_atlas, panne):
        self.fabrique_session = fabrique_session
        self.modeles = modeles
        self.reglages = reglages
        self.marge_sortie_s = marge_sortie_s
        self.blocs: list[bytes] = []
        self.peripherique = SimpleNamespace(recevoir=self.blocs.append)
        self.reveilleur = SimpleNamespace(actif=hey_atlas)
        self.paroles = 0
        self.reprises = 0
        self.client = SimpleNamespace(demander_la_parole=self._parler, reamorcer=self._reprendre)
        self.session = SimpleNamespace(fermee=False, fermer=self._fermer)
        self.servie_jusqu_au_bout = False
        self._panne = panne

    def _parler(self) -> None:
        self.paroles += 1

    def _reprendre(self) -> None:
        self.reprises += 1

    async def _fermer(self) -> None:
        self.session.fermee = True

    async def servir(self) -> None:
        if self._panne:
            raise self._panne
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.servie_jusqu_au_bout = True
            raise


@pytest.fixture
def banc(monkeypatch):
    banc = SimpleNamespace(regie=RegieEspionne(), pages=[], panne=None)

    def monter(envoyer_json, envoyer_binaire, fabrique, modeles, reglages, marge, hey_atlas):
        banc.pages.append(PageEspionne(fabrique, modeles, reglages, marge, hey_atlas, banc.panne))
        return banc.pages[-1]

    monkeypatch.setattr(hub, "_regie", banc.regie)
    config = replace(hub._config, web_cle=CLE, voix_marge_s=0.3, voix_bargein_dbfs=-33.0)
    monkeypatch.setattr(hub, "_config", config)
    monkeypatch.setattr(hub, "charger_modeles", lambda seuil: ("detecteur", "mot-cle"))
    monkeypatch.setattr(hub, "monter_page", monter)
    return banc


def _entrer(ws, hey_atlas: bool = True) -> None:
    ws.send_json({"type": "authentification", "cle": CLE, "page": "ipad", "hey_atlas": hey_atlas})
    assert ws.receive_json() == {"type": "pret"}


def test_une_page_entre_avec_les_reglages_du_navigateur(banc):
    with TestClient(hub.app) as client, client.websocket_connect("/ws/voix", headers=ORIGINE) as ws:
        _entrer(ws, hey_atlas=False)
        [page] = banc.pages
        assert page.modeles == ("detecteur", "mot-cle")
        assert page.fabrique_session is hub.creer_session
        assert page.marge_sortie_s == 0.3 and page.reglages.bargein_dbfs == -33.0
        assert page.reveilleur.actif is False
        assert banc.regie.rattachees == [("ipad", page.session)]


def test_les_messages_de_la_page_arrivent_a_son_client(banc):
    with TestClient(hub.app) as client, client.websocket_connect("/ws/voix", headers=ORIGINE) as ws:
        _entrer(ws)
        ws.send_bytes(BLOC)
        ws.send_json({"type": "parler"})
        ws.send_json({"type": "hey_atlas", "actif": False})
        ws.send_json({"type": "reprise"})
        ws.send_bytes(BLOC)
        ws.send_json({"type": "nimporte_quoi"})  # sa réponse prouve que tout est traité
        assert ws.receive_json()["code"] == "message_invalide"
    [page] = banc.pages
    assert page.blocs == [BLOC, BLOC]
    assert page.paroles == 1 and page.reprises == 1 and page.reveilleur.actif is False


def test_un_bloc_de_la_mauvaise_taille_est_signale_et_jete(banc):
    with TestClient(hub.app) as client, client.websocket_connect("/ws/voix", headers=ORIGINE) as ws:
        _entrer(ws)
        ws.send_bytes(BLOC[:-1])
        ws.send_json({"type": "nimporte_quoi"})  # répond à coup sûr : le test ne bloque jamais
        erreur = ws.receive_json()
    assert erreur["code"] == "trame_invalide" and "attendu 640" in erreur["message"]
    assert banc.pages[0].blocs == []


def test_quand_la_page_part_sa_session_est_fermee_et_detachee(banc):
    with TestClient(hub.app) as client, client.websocket_connect("/ws/voix", headers=ORIGINE) as ws:
        _entrer(ws)
        ws.close()
    [page] = banc.pages
    assert page.servie_jusqu_au_bout and page.session.fermee
    assert banc.regie.detachees == [page.session]


def test_si_la_voix_de_la_page_tombe_en_panne_la_connexion_se_ferme(banc, caplog):
    banc.panne = RuntimeError("le détecteur de voix a planté")
    with TestClient(hub.app) as client, client.websocket_connect("/ws/voix", headers=ORIGINE) as ws:
        _entrer(ws)
        ws.send_bytes(BLOC)
        with pytest.raises(WebSocketDisconnect) as fermeture:
            ws.receive_json()
    assert fermeture.value.code == hub.FERMETURE_PANNE
    [page] = banc.pages
    assert page.session.fermee and banc.regie.detachees == [page.session]
    assert "le détecteur de voix a planté" in caplog.text


def test_une_page_partie_pendant_qu_atlas_lui_parle_ne_laisse_aucune_erreur(banc, caplog):
    # Le son envoyé à une page déjà partie échoue avant que sa déconnexion n'arrive.
    banc.panne = PeripheriqueEnPanne("le périphérique audio est mort")
    with TestClient(hub.app) as client, client.websocket_connect("/ws/voix", headers=ORIGINE) as ws:
        _entrer(ws)
        ws.close()
    [page] = banc.pages
    assert page.session.fermee and banc.regie.detachees == [page.session]
    assert not [r for r in caplog.records if r.levelname == "ERROR"]


def test_sans_les_modeles_sur_la_machine_du_core_la_page_est_prevenue(banc, monkeypatch):
    def absents(seuil):
        raise FileNotFoundError("Modèle Silero introuvable sur la machine du Core")

    monkeypatch.setattr(hub, "charger_modeles", absents)
    with TestClient(hub.app) as client, client.websocket_connect("/ws/voix", headers=ORIGINE) as ws:
        ws.send_json({"type": "authentification", "cle": CLE, "page": "ipad"})
        erreur = ws.receive_json()
        with pytest.raises(WebSocketDisconnect) as fermeture:
            ws.receive_json()
    assert erreur["code"] == "modeles_absents" and "Silero" in erreur["message"]
    assert fermeture.value.code == hub.FERMETURE_CLE_ABSENTE
    assert banc.pages == [] and banc.regie.rattachees == []


@pytest.mark.parametrize(
    "entree",
    [
        {"type": "authentification", "cle": "pas-la-bonne", "page": "ipad"},
        {"type": "authentification", "cle": CLE},  # l'entrée de /ws/web, sans page
        {"type": "authentification", "cle": CLE, "page": "../ipad"},
        {"type": "parler"},
    ],
)
def test_une_entree_refusee_ferme_la_connexion_sans_rien_monter(banc, entree):
    with TestClient(hub.app) as client, client.websocket_connect("/ws/voix", headers=ORIGINE) as ws:
        ws.send_json(entree)
        with pytest.raises(WebSocketDisconnect) as fermeture:
            ws.receive_json()
    assert fermeture.value.code == hub.FERMETURE_NON_AUTORISE
    assert banc.pages == []


def test_sans_authentification_a_temps_la_connexion_se_ferme(banc, monkeypatch):
    monkeypatch.setattr(hub, "DELAI_AUTHENTIFICATION_S", 0.05)
    with TestClient(hub.app) as client, client.websocket_connect("/ws/voix", headers=ORIGINE) as ws:
        with pytest.raises(WebSocketDisconnect) as fermeture:
            ws.receive_json()
    assert fermeture.value.code == hub.FERMETURE_NON_AUTORISE


def test_sans_cle_configuree_la_page_est_prevenue(banc, monkeypatch):
    monkeypatch.setattr(hub, "_config", replace(hub._config, web_cle=""))
    with TestClient(hub.app) as client, client.websocket_connect("/ws/voix", headers=ORIGINE) as ws:
        erreur = ws.receive_json()
        with pytest.raises(WebSocketDisconnect) as fermeture:
            ws.receive_json()
    assert erreur["code"] == "cle_absente"
    assert fermeture.value.code == hub.FERMETURE_CLE_ABSENTE


def test_une_autre_origine_est_refusee_avant_meme_d_accepter(banc):
    with TestClient(hub.app) as client:
        with pytest.raises(WebSocketDisconnect) as fermeture:
            with client.websocket_connect(
                "/ws/voix", headers={"origin": "http://ailleurs.example"}
            ):
                pass
    assert fermeture.value.code == hub.FERMETURE_ORIGINE

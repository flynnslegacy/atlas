"""Le client du poste : se présenter, exécuter les gestes hors de la boucle, répondre à
chacun, et se reconnecter comme le client audio."""

import json
import logging
import threading

import pytest
from websockets.exceptions import ConnectionClosedError
from websockets.frames import Close

from atlas_audio.connexion import boucle_de_connexion
from atlas_core.protocole_poste import ActionPoste, Ouvrir, ResultatPoste, Taper
from atlas_poste.client import URL_PAR_DEFAUT, lire_reglages, servir


class FauxWs:
    """Une connexion au Core : ce qu'il envoie au poste, ce que le poste lui répond."""

    def __init__(self, *recus: str | bytes) -> None:
        self.recus = list(recus)
        self.envoyes: list[dict] = []

    async def send(self, texte: str) -> None:
        self.envoyes.append(json.loads(texte))

    def __aiter__(self):
        return self

    async def __anext__(self) -> str | bytes:
        if not self.recus:
            raise StopAsyncIteration
        return self.recus.pop(0)


class FauxGestes:
    def __init__(self) -> None:
        self.faites: list[ActionPoste] = []
        self.fils: list[int] = []

    def executer(self, action: ActionPoste) -> ResultatPoste:
        self.fils.append(threading.get_ident())
        self.faites.append(action)
        return ResultatPoste(id=action.id, ok=True)


def _action(identifiant: int, geste) -> str:
    return ActionPoste(id=identifiant, geste=geste).model_dump_json()


def test_les_reglages_du_poste(monkeypatch):
    monkeypatch.delenv("ATLAS_POSTE_URL", raising=False)
    monkeypatch.setenv("ATLAS_POSTE_CLE", " cle-du-poste ")
    assert URL_PAR_DEFAUT == "ws://127.0.0.1:8080/ws/poste"
    assert lire_reglages() == (URL_PAR_DEFAUT, "cle-du-poste")
    monkeypatch.setenv("ATLAS_POSTE_URL", "ws://neo.local:8080/ws/poste")
    assert lire_reglages()[0] == "ws://neo.local:8080/ws/poste"


def test_sans_cle_le_poste_ne_demarre_pas(monkeypatch):
    monkeypatch.setenv("ATLAS_POSTE_CLE", "")
    with pytest.raises(ValueError, match="ATLAS_POSTE_CLE"):
        lire_reglages()


async def test_le_poste_se_presente_puis_repond_a_chaque_action_dans_l_ordre():
    ws = FauxWs(
        '{"type":"pret"}',
        _action(1, Ouvrir(app="Safari")),
        _action(2, Taper(texte="bonjour")),
    )
    gestes = FauxGestes()
    await servir(ws, gestes, "cle-du-poste")
    assert ws.envoyes[0] == {"type": "bonjour", "cle": "cle-du-poste"}
    assert [(r["type"], r["id"], r["ok"]) for r in ws.envoyes[1:]] == [
        ("resultat", 1, True),
        ("resultat", 2, True),
    ]
    assert [a.id for a in gestes.faites] == [1, 2]
    assert threading.get_ident() not in gestes.fils, "les gestes tournent hors de la boucle"


async def test_un_geste_refuse_repond_sans_rien_executer(caplog):
    refuse = json.dumps({"type": "action", "id": 5, "geste": {"nom": "ouvrir", "app": "/bin/sh"}})
    ws = FauxWs(
        refuse,
        b"\x00",  # une trame binaire : le Core n'en envoie jamais, le poste l'ignore
        "pas du json",
        '{"type":"action","geste":{"nom":"executer"}}',
        '{"type":"action","id":"7","geste":{"nom":"executer"}}',
    )
    gestes = FauxGestes()
    with caplog.at_level(logging.WARNING, logger="atlas_poste.client"):
        await servir(ws, gestes, "cle")
    assert gestes.faites == []
    [reponse] = ws.envoyes[1:]  # sans identifiant entier, rien à répondre : seulement noté
    assert (reponse["id"], reponse["ok"]) == (5, False)
    assert reponse["erreur"].startswith("Geste refusé par le poste :")
    assert caplog.text.count("geste refusé") == 4


def _refus(code: int) -> ConnectionClosedError:
    return ConnectionClosedError(Close(code, ""), None)


class Fin(Exception):
    pass


class Ouverture:
    async def __aenter__(self):
        return "connexion"

    async def __aexit__(self, *exc) -> bool:
        return False


@pytest.mark.parametrize("code", [4401, 4000])
async def test_une_cle_du_poste_refusee_se_dit_avec_son_nom(caplog, code):
    async def servir_refuse(ws) -> None:
        raise _refus(code)

    async def attendre(secondes: float) -> None:
        raise Fin

    with caplog.at_level(logging.ERROR, logger="atlas_audio.connexion"), pytest.raises(Fin):
        await boucle_de_connexion(
            Ouverture, servir_refuse, attendre=attendre, nom_cle="ATLAS_POSTE_CLE"
        )
    assert "ATLAS_POSTE_CLE" in caplog.text and "ATLAS_AUDIO_CLE" not in caplog.text

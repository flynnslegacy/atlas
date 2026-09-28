"""Le client du poste : prouver la clé sans l'envoyer, n'obéir qu'au serveur qui la prouve
aussi, exécuter les gestes signés hors de la boucle, répondre à chacun, et se reconnecter
comme le client audio."""

import json
import logging
import threading
from collections.abc import Callable

import pytest
from websockets.exceptions import ConnectionClosedError
from websockets.frames import Close

from atlas_audio.connexion import CleNonProuvee, boucle_de_connexion
from atlas_core.protocole_poste import (
    ActionPoste,
    DefiPoste,
    Ouvrir,
    PretPoste,
    ResultatPoste,
    Taper,
    cle_de_session,
    est_signe,
    preuve_du_core,
    preuve_du_poste,
    preuve_valide,
    signer,
)
from atlas_poste.client import URL_PAR_DEFAUT, lire_reglages, servir

CLE = "cle-du-poste-de-test"
NONCE_CORE = "c" * 32

# Ce que le faux Core envoie une fois la poignée de main faite, selon la clé de session.
Envoi = Callable[[str], str | bytes]


def signee(identifiant: int, geste) -> Envoi:
    return lambda session: signer(
        session, ActionPoste(id=identifiant, geste=geste)
    ).model_dump_json()


def brut(texte: str | bytes) -> Envoi:
    return lambda session: texte


class FauxCore:
    """Le bout de la connexion côté Core : il prouve la clé qu'il connaît (sur le nonce du
    poste), vérifie la preuve du poste, puis envoie « pret » et ses messages."""

    def __init__(self, *envois: Envoi, cle: str = CLE, sans_defi: bool = False) -> None:
        self.envois = envois
        self.cle = cle
        self.sans_defi = sans_defi  # un serveur qui ne se prouve pas : il envoie tout de suite
        self.a_recevoir: list[str | bytes] = [e("") for e in envois] if sans_defi else []
        self.envoyes: list[dict] = []
        self.session: str | None = None

    async def send(self, texte: str) -> None:
        message = json.loads(texte)
        self.envoyes.append(message)
        if message["type"] == "bonjour" and not self.sans_defi:
            self.nonce_poste = message["nonce"]
            preuve = preuve_du_core(self.cle, self.nonce_poste, NONCE_CORE)
            self.a_recevoir.append(DefiPoste(nonce=NONCE_CORE, preuve=preuve).model_dump_json())
        elif message["type"] == "reponse":
            attendue = preuve_du_poste(self.cle, self.nonce_poste, NONCE_CORE)
            assert preuve_valide(attendue, message["preuve"]), "le poste prouve la clé"
            self.session = cle_de_session(self.cle, self.nonce_poste, NONCE_CORE)
            self.a_recevoir.append(PretPoste().model_dump_json())
            self.a_recevoir.extend(envoi(self.session) for envoi in self.envois)

    def __aiter__(self):
        return self

    async def __anext__(self) -> str | bytes:
        if not self.a_recevoir:
            raise StopAsyncIteration
        return self.a_recevoir.pop(0)

    def resultats(self) -> list[dict]:
        return [m for m in self.envoyes if m["type"] == "resultat"]


class FauxGestes:
    def __init__(self) -> None:
        self.faites: list[ActionPoste] = []
        self.fils: list[int] = []

    def executer(self, action: ActionPoste) -> ResultatPoste:
        self.fils.append(threading.get_ident())
        self.faites.append(action)
        return ResultatPoste(id=action.id, ok=True)


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


async def test_le_poste_prouve_la_cle_sans_l_envoyer_puis_repond_a_chaque_action():
    core = FauxCore(signee(1, Ouvrir(app="Safari")), signee(2, Taper(texte="bonjour")))
    gestes = FauxGestes()
    await servir(core, gestes, CLE)
    assert [m["type"] for m in core.envoyes[:2]] == ["bonjour", "reponse"]
    assert CLE not in json.dumps(core.envoyes), "la clé ne circule jamais"
    resultats = core.resultats()
    assert [(r["id"], r["ok"]) for r in resultats] == [(1, True), (2, True)]
    assert all(est_signe(core.session, ResultatPoste(**r)) for r in resultats)
    assert [a.id for a in gestes.faites] == [1, 2]
    assert threading.get_ident() not in gestes.fils, "les gestes tournent hors de la boucle"


@pytest.mark.parametrize(
    "core",
    [
        FauxCore(signee(1, Taper(texte="x")), cle="une-autre-cle"),
        FauxCore(brut(ActionPoste(id=1, geste=Taper(texte="x")).model_dump_json()), sans_defi=True),
        FauxCore(brut('{"type":"pret"}'), sans_defi=True),
    ],
    ids=["mauvaise-preuve", "action-sans-defi", "pret-sans-defi"],
)
async def test_un_serveur_qui_ne_prouve_pas_la_cle_n_obtient_rien(core):
    # N'importe quel appareil peut répondre à l'adresse du Core : le poste ne lui dit pas
    # la clé, ne lui prouve rien, et n'exécute rien.
    gestes = FauxGestes()
    with pytest.raises(CleNonProuvee):
        await servir(core, gestes, CLE)
    assert gestes.faites == []
    assert [m["type"] for m in core.envoyes] == ["bonjour"]


async def test_une_action_non_signee_ou_rejouee_n_est_pas_executee(caplog):
    sans_preuve = ActionPoste(id=1, geste=Taper(texte="intrus")).model_dump_json()
    autre_session = cle_de_session(CLE, "d" * 32, NONCE_CORE)
    mal_signee = signer(autre_session, ActionPoste(id=3, geste=Taper(texte="intrus")))
    core = FauxCore(
        brut(sans_preuve),
        signee(2, Taper(texte="bonjour")),
        signee(2, Taper(texte="bonjour")),  # la même, rejouée
        brut(mal_signee.model_dump_json()),
    )
    gestes = FauxGestes()
    with caplog.at_level(logging.WARNING, logger="atlas_poste.client"):
        await servir(core, gestes, CLE)
    assert [a.id for a in gestes.faites] == [2]
    assert [r["id"] for r in core.resultats()] == [2]
    assert caplog.text.count("action non signée ou rejouée") == 3


async def test_un_geste_refuse_repond_sans_rien_executer(caplog):
    refuse = json.dumps({"type": "action", "id": 5, "geste": {"nom": "ouvrir", "app": "/bin/sh"}})
    core = FauxCore(
        brut(refuse),
        brut(b"\x00"),  # une trame binaire : le Core n'en envoie jamais, le poste l'ignore
        brut("pas du json"),
        brut('{"type":"action","geste":{"nom":"executer"}}'),
        brut('{"type":"action","id":"7","geste":{"nom":"executer"}}'),
    )
    gestes = FauxGestes()
    with caplog.at_level(logging.WARNING, logger="atlas_poste.client"):
        await servir(core, gestes, CLE)
    assert gestes.faites == []
    [reponse] = core.resultats()  # sans identifiant entier, rien à répondre : seulement noté
    assert (reponse["id"], reponse["ok"]) == (5, False)
    assert reponse["erreur"].startswith("Geste refusé par le poste :")
    assert est_signe(core.session, ResultatPoste(**reponse))
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


@pytest.mark.parametrize(
    ("refus", "message"),
    [
        (_refus(4401), "le Core refuse la clé"),
        (_refus(4000), "le Core n'a pas de clé"),
        (CleNonProuvee(), "ne prouve pas"),
    ],
)
async def test_une_cle_du_poste_refusee_se_dit_avec_son_nom(caplog, refus, message):
    async def servir_refuse(ws) -> None:
        raise refus

    delais: list[float] = []

    async def attendre(secondes: float) -> None:
        delais.append(secondes)
        if len(delais) == 2:
            raise Fin

    with caplog.at_level(logging.ERROR, logger="atlas_audio.connexion"), pytest.raises(Fin):
        await boucle_de_connexion(
            Ouverture, servir_refuse, attendre=attendre, nom_cle="ATLAS_POSTE_CLE"
        )
    assert message in caplog.text
    assert "ATLAS_POSTE_CLE" in caplog.text and "ATLAS_AUDIO_CLE" not in caplog.text
    assert delais == [1, 2], "un refus ne remet pas le compte des tentatives à zéro"

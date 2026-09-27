"""Le poste vu du Core : la connexion du Mac de David, et les gestes qu'on lui demande.

Un seul poste à la fois : un nouveau remplace l'ancien. Chaque geste part avec son `id` et
attend sa réponse, dans un délai ; le poste peut être absent, muet, ou répondre qu'il n'a
pas pu. `servir_poste` tient la route /ws/poste : la preuve de la clé, dans les deux sens,
puis les réponses du poste, signées de la clé de la session.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable

from fastapi import WebSocket, WebSocketDisconnect

from .protocole import Erreur
from .protocole_poste import (
    ActionPoste,
    BonjourPoste,
    Capturer,
    DefiPoste,
    Geste,
    PretPoste,
    ReponsePoste,
    ResultatPoste,
    cle_de_session,
    decoder_message_poste,
    est_signe,
    nouveau_nonce,
    preuve_du_core,
    preuve_du_poste,
    preuve_valide,
    signer,
)

_journal = logging.getLogger(__name__)

DELAI_S = 10.0
DELAI_CAPTURE_S = 5.0
DELAI_AUTHENTIFICATION_S = 5.0
ABSENT = "Ton Mac n'est pas connecté."
MUET = "Le poste ne répond pas."
# Les mêmes codes que les autres routes du hub.
FERMETURE_CLE_ABSENTE = 4000
FERMETURE_NON_AUTORISE = 4401
FERMETURE_ORIGINE = 1008

Envoyer = Callable[[ActionPoste], Awaitable[None]]


class ErreurPoste(Exception):
    """Le geste n'a pas pu se faire ; le message, en français, va à Claude."""


class Poste:
    def __init__(self, delai_s: float = DELAI_S, delai_capture_s: float = DELAI_CAPTURE_S) -> None:
        self._delai_s = delai_s
        self._delai_capture_s = delai_capture_s
        self._envoyer: Envoyer | None = None
        self._jeton: object | None = None
        self._attentes: dict[int, asyncio.Future[ResultatPoste]] = {}
        self._dernier_id = 0

    @property
    def connecte(self) -> bool:
        return self._envoyer is not None

    def rattacher(self, envoyer: Envoyer) -> object:
        """Le poste qui vient de se présenter remplace l'ancien ; rend son jeton, pour
        `detacher`."""
        self._abandonner_les_attentes()
        self._envoyer, self._jeton = envoyer, object()
        return self._jeton

    def detacher(self, jeton: object) -> None:
        """Le poste de ce jeton est parti ; celui qui l'a remplacé, lui, reste."""
        if jeton is self._jeton:
            self._abandonner_les_attentes()
            self._envoyer = self._jeton = None

    def recevoir(self, resultat: ResultatPoste) -> None:
        attente = self._attentes.pop(resultat.id, None)
        if attente is not None and not attente.done():
            attente.set_result(resultat)

    async def demander(self, geste: Geste) -> ResultatPoste:
        """Fait faire un geste au Mac ; rend sa réponse, ou lève `ErreurPoste`."""
        envoyer = self._envoyer
        if envoyer is None:
            raise ErreurPoste(ABSENT)
        self._dernier_id += 1
        identifiant = self._dernier_id
        attente = asyncio.get_running_loop().create_future()
        self._attentes[identifiant] = attente
        delai = self._delai_capture_s if isinstance(geste, Capturer) else self._delai_s
        try:
            await envoyer(ActionPoste(id=identifiant, geste=geste))
            async with asyncio.timeout(delai):
                resultat = await attente
        except TimeoutError:
            raise ErreurPoste(MUET) from None
        except ErreurPoste:
            raise
        except Exception as e:  # noqa: BLE001 — la connexion s'est perdue pendant l'envoi
            raise ErreurPoste(ABSENT) from e
        finally:
            self._attentes.pop(identifiant, None)
        if not resultat.ok:
            raise ErreurPoste(resultat.erreur or MUET)
        return resultat

    def _abandonner_les_attentes(self) -> None:
        """Les gestes partis vers un poste qui n'est plus là ne reviendront jamais."""
        attentes, self._attentes = self._attentes, {}
        for attente in attentes.values():
            if not attente.done():
                attente.set_exception(ErreurPoste(ABSENT))


async def _recevoir_texte(ws: WebSocket) -> str | None:
    while True:
        recu = await ws.receive()
        if recu["type"] == "websocket.disconnect":
            return None
        if (texte := recu.get("text")) is not None:
            return texte


async def _message[M](ws: WebSocket, attendu: type[M]) -> M | None:
    """Le message suivant du poste, s'il est du type attendu et reçu à temps."""
    try:
        brut = await asyncio.wait_for(_recevoir_texte(ws), DELAI_AUTHENTIFICATION_S)
        message = decoder_message_poste(brut) if brut is not None else None
    except (TimeoutError, ValueError):
        return None
    return message if isinstance(message, attendu) else None


async def _session(ws: WebSocket, cle: str) -> str | None:
    """Le poste et le Core se prouvent la clé sans l'envoyer ; rend la clé de la session, ou
    None si le poste ne la prouve pas."""
    bonjour = await _message(ws, BonjourPoste)
    if bonjour is None:
        return None
    nonce = nouveau_nonce()
    preuve = preuve_du_core(cle, bonjour.nonce, nonce)
    await ws.send_text(DefiPoste(nonce=nonce, preuve=preuve).model_dump_json())
    reponse = await _message(ws, ReponsePoste)
    attendue = preuve_du_poste(cle, bonjour.nonce, nonce)
    if reponse is None or not preuve_valide(attendue, reponse.preuve):
        return None
    return cle_de_session(cle, bonjour.nonce, nonce)


async def servir_poste(ws: WebSocket, poste: Poste, cle: str) -> None:
    """La route /ws/poste : un programme, jamais un navigateur ; la clé ; puis les réponses
    du poste, jusqu'à ce qu'il parte."""
    if ws.headers.get("origin") is not None:
        await ws.close(code=FERMETURE_ORIGINE)  # un navigateur envoie toujours un Origin
        return
    await ws.accept()
    if not cle:
        message = (
            "La clé du poste n'est pas configurée : ajoute ATLAS_POSTE_CLE dans le .env du Core, "
            "puis redémarre-le."
        )
        await ws.send_text(Erreur(code="cle_absente", message=message).model_dump_json())
        await ws.close(code=FERMETURE_CLE_ABSENTE)
        return
    session = await _session(ws, cle)
    if session is None:
        with contextlib.suppress(Exception):
            await ws.close(code=FERMETURE_NON_AUTORISE)
        return

    async def envoyer(action: ActionPoste) -> None:
        await ws.send_text(signer(session, action).model_dump_json())

    await ws.send_text(PretPoste().model_dump_json())
    jeton = poste.rattacher(envoyer)
    _journal.info("poste connecté")
    try:
        while (texte := await _recevoir_texte(ws)) is not None:
            try:
                message = decoder_message_poste(texte)
            except ValueError as e:
                _journal.warning("message du poste ignoré : %s", e)
                continue
            if isinstance(message, ResultatPoste):
                if est_signe(session, message):
                    poste.recevoir(message)
                else:
                    _journal.warning("résultat du poste non signé : ignoré")
    except WebSocketDisconnect:
        pass
    finally:
        poste.detacher(jeton)
        _journal.info("poste déconnecté")

"""La connexion du client audio au Core : la servir, et la retrouver quand elle se perd."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable, Sequence
from contextlib import AbstractAsyncContextManager
from typing import Protocol

from pydantic import TypeAdapter, ValidationError

from atlas_core.protocole import MessageCore

_journal = logging.getLogger(__name__)

# Entre deux tentatives de connexion au Core ; le dernier délai se répète.
DELAIS_RECONNEXION_S = (1, 2, 4, 8, 16, 30)
# Fermetures du Core qui disent que la clé du client est absente ou refusée.
FERMETURE_CLE_ABSENTE = 4000
FERMETURE_NON_AUTORISE = 4401

_MESSAGES_CORE: TypeAdapter[MessageCore] = TypeAdapter(MessageCore)


class ClientConnecte(Protocol):
    """Ce que la connexion attend du client audio (`ClientAudio`)."""

    async def boucle_capture(self) -> None: ...
    async def sur_message(self, msg) -> None: ...
    async def sur_trame(self, trame: bytes) -> None: ...
    async def arreter(self) -> None: ...


async def servir_connexion(ws, client: ClientConnecte) -> None:
    """Sert une connexion au Core jusqu'à sa fin. L'audio d'Atlas part dans une file que
    la tâche de lecture vide à son rythme ; les messages de contrôle, eux, sont traités
    dès leur arrivée : un `StopAudio` n'attend jamais derrière des secondes de son."""
    file: asyncio.Queue[bytes] = asyncio.Queue()
    taches = [
        asyncio.create_task(client.boucle_capture()),
        asyncio.create_task(_jouer_la_file(client, file)),
    ]
    try:
        async for recu in ws:
            if isinstance(recu, bytes):
                file.put_nowait(recu)
                continue
            try:
                msg = _MESSAGES_CORE.validate_json(recu)
            except ValidationError as e:
                _journal.warning("message du Core illisible : %s", e)
                continue
            await client.sur_message(msg)
    finally:
        for tache in taches:
            tache.cancel()
        for tache in taches:
            with contextlib.suppress(asyncio.CancelledError):
                await tache
        await client.arreter()


async def _jouer_la_file(client: ClientConnecte, file: asyncio.Queue[bytes]) -> None:
    while True:
        trame = await file.get()
        try:
            await client.sur_trame(trame)
        except ValueError as e:
            _journal.warning("trame audio du Core illisible : %s", e)


def _code_de_fermeture(e: BaseException) -> int | None:
    """Le code de fermeture envoyé par le Core, si l'exception en porte un."""
    return getattr(getattr(e, "rcvd", None), "code", None)


async def boucle_de_connexion(
    ouvrir: Callable[[], AbstractAsyncContextManager],
    servir: Callable[[object], Awaitable[None]],
    attendre: Callable[[float], Awaitable[None]] = asyncio.sleep,
    delais: Sequence[float] = DELAIS_RECONNEXION_S,
) -> None:
    """Garde le client branché au Core : s'il disparaît, on se reconnecte, de plus en
    plus patiemment (1, 2, 4, 8, 16 puis 30 s). Une connexion acceptée remet ce compte à
    zéro ; une clé refusée, non."""
    echecs = 0
    while True:
        acceptee = False
        try:
            async with ouvrir() as ws:
                acceptee = True
                await servir(ws)
            _journal.warning("le Core a fermé la connexion")
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 — on se reconnecte, quoi qu'il arrive
            code = _code_de_fermeture(e)
            if code == FERMETURE_NON_AUTORISE:
                acceptee = False
                _journal.error("le Core refuse la clé : vérifie ATLAS_AUDIO_CLE des deux côtés")
            elif code == FERMETURE_CLE_ABSENTE:
                acceptee = False
                _journal.error("le Core n'a pas de clé : ajoute ATLAS_AUDIO_CLE dans son .env")
            else:
                _journal.warning("Core injoignable ou connexion perdue (%s)", type(e).__name__)
        if acceptee:
            echecs = 0
        delai = delais[min(echecs, len(delais) - 1)]
        echecs += 1
        _journal.info("nouvelle tentative de connexion dans %s s", delai)
        await attendre(delai)

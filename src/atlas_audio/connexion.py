"""La connexion du client audio au Core : la servir, et la retrouver quand elle se perd."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable, Sequence
from contextlib import AbstractAsyncContextManager
from typing import Protocol

from pydantic import TypeAdapter, ValidationError
from websockets.exceptions import ConnectionClosed, InvalidHandshake, InvalidURI

from atlas_core.protocole import MessageCore, StopAudio

_journal = logging.getLogger(__name__)

# Ce qu'une coupure réseau ordinaire peut lever : le Core disparaît, redémarre, refuse la
# poignée de main… Tout le reste (un bogue du mot de réveil ou du VAD, par exemple) est
# journalisé avec sa trace, sinon il repasserait inaperçu toutes les secondes.
_ERREURS_RESEAU = (OSError, TimeoutError, ConnectionClosed, InvalidHandshake, InvalidURI)

# Entre deux tentatives de connexion au Core ; le dernier délai se répète.
DELAIS_RECONNEXION_S = (1, 2, 4, 8, 16, 30)
# Fermetures du Core qui disent que la clé du client est absente ou refusée.
FERMETURE_CLE_ABSENTE = 4000
FERMETURE_NON_AUTORISE = 4401

_MESSAGES_CORE: TypeAdapter[MessageCore] = TypeAdapter(MessageCore)


class PeripheriqueEnPanne(Exception):
    """Le périphérique audio (capture ou lecture) est mort. Ce n'est pas une coupure
    réseau : la connexion ne se retente pas, elle s'arrête, comme avant cette tâche."""


class ClientConnecte(Protocol):
    """Ce que la connexion attend du client audio (`ClientAudio`)."""

    async def boucle_capture(self) -> None: ...
    async def sur_message(self, msg) -> None: ...
    async def sur_trame(self, trame: bytes) -> None: ...
    async def arreter(self) -> None: ...


async def servir_connexion(ws, client: ClientConnecte) -> None:
    """Sert une connexion au Core jusqu'à sa fin. Les trames et les messages du Core
    (sauf `StopAudio`) partagent une seule file, jouée dans l'ordre par sa propre tâche :
    un `Dire` suivi de ses trames ne doit jamais être doublé par l'état qui le suit, sans
    quoi la relance pourrait rouvrir l'écoute avant que la réponse n'ait fini de jouer.
    Seul `StopAudio` est traité aussitôt par le lecteur, pour ne jamais attendre derrière
    des secondes de son déjà en file.

    Si le périphérique audio meurt (capture ou lecture), la connexion s'arrête avec
    `PeripheriqueEnPanne` — levée à la frontière du périphérique (`client._frontiere_peripherique`),
    pas devinée ici d'après la tâche fautive : la capture fait aussi des envois réseau, et
    une coupure du Core en plein envoi (`ConnectionClosed`) doit se reconnecter comme les
    autres, pas arrêter le programme. Une annulation de cette coroutine, elle, relève une
    simple `CancelledError`."""
    file: asyncio.Queue[bytes | MessageCore] = asyncio.Queue()
    capture = asyncio.create_task(client.boucle_capture())
    lecture = asyncio.create_task(_traiter_la_file(client, file))
    flux = asyncio.create_task(_lire_le_flux(ws, client, file))
    en_cours = {capture, lecture, flux}
    try:
        while True:
            fait, en_cours = await asyncio.wait(en_cours, return_when=asyncio.FIRST_COMPLETED)
            for tache in fait:
                if tache.cancelled():
                    continue
                erreur = tache.exception()
                if erreur is not None:
                    raise erreur  # déjà PeripheriqueEnPanne si la cause était le périphérique
            if flux in fait:
                break  # le flux du Core s'est terminé normalement : rien à relever
    finally:
        for tache in (capture, lecture, flux):
            tache.cancel()
        for tache in (capture, lecture, flux):
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await tache
        await client.arreter()


async def _lire_le_flux(ws, client: ClientConnecte, file: asyncio.Queue) -> None:
    """Lit le flux du Core. `StopAudio` est traité aussitôt ; tout le reste (trames et
    messages) rejoint la file, jouée dans l'ordre par `_traiter_la_file`."""
    async for recu in ws:
        if isinstance(recu, bytes):
            file.put_nowait(recu)
            continue
        try:
            msg = _MESSAGES_CORE.validate_json(recu)
        except ValidationError as e:
            _journal.warning("message du Core illisible : %s", e)
            continue
        if isinstance(msg, StopAudio):
            await client.sur_message(msg)
        else:
            file.put_nowait(msg)


async def _traiter_la_file(client: ClientConnecte, file: asyncio.Queue) -> None:
    while True:
        item = await file.get()
        if isinstance(item, bytes):
            try:
                await client.sur_trame(item)
            except ValueError as e:
                _journal.warning("trame audio du Core illisible : %s", e)
        else:
            await client.sur_message(item)


def _code_de_fermeture(e: BaseException) -> int | None:
    """Le code de fermeture envoyé par le Core, si l'exception en porte un."""
    return getattr(getattr(e, "rcvd", None), "code", None)


def _demarrer_absence(
    pendant_l_absence: Callable[[], Awaitable[None]] | None,
) -> asyncio.Task | None:
    return asyncio.create_task(pendant_l_absence()) if pendant_l_absence is not None else None


async def _arreter_absence(absence: asyncio.Task | None) -> None:
    """Annule la tâche qui occupe le micro pendant l'absence du Core, et relève sa panne
    si elle en a une (déjà `PeripheriqueEnPanne`, levée à la frontière du périphérique
    par `client._vider_le_micro`) : un périphérique mort pendant l'absence est aussi
    fatal que pendant le service, sinon un micro mort passerait inaperçu tant que le Core
    reste injoignable."""
    if absence is None:
        return
    absence.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await absence


async def boucle_de_connexion(
    ouvrir: Callable[[], AbstractAsyncContextManager],
    servir: Callable[[object], Awaitable[None]],
    attendre: Callable[[float], Awaitable[None]] = asyncio.sleep,
    delais: Sequence[float] = DELAIS_RECONNEXION_S,
    pendant_l_absence: Callable[[], Awaitable[None]] | None = None,
) -> None:
    """Garde le client branché au Core : s'il disparaît, on se reconnecte, de plus en
    plus patiemment (1, 2, 4, 8, 16 puis 30 s). Une connexion acceptée remet ce compte à
    zéro ; une clé refusée, non.

    `pendant_l_absence`, si fourni, tourne en tâche de fond tant qu'aucune connexion n'est
    servie (dès le départ, pendant les tentatives et les attentes) : sans elle, personne
    ne lit le micro entre deux connexions, et le son s'accumule jusqu'au rebranchement.
    Elle est arrêtée juste avant que `servir` ne démarre, et relancée quand il rend la
    main."""
    echecs = 0
    absence = _demarrer_absence(pendant_l_absence)
    try:
        while True:
            acceptee = False
            try:
                async with ouvrir() as ws:
                    acceptee = True
                    await _arreter_absence(absence)
                    absence = None
                    await servir(ws)
                _journal.warning("le Core a fermé la connexion")
            except asyncio.CancelledError:
                raise
            except PeripheriqueEnPanne:
                raise
            except Exception as e:  # noqa: BLE001 — on se reconnecte, quoi qu'il arrive
                code = _code_de_fermeture(e)
                if code == FERMETURE_NON_AUTORISE:
                    acceptee = False
                    _journal.error("le Core refuse la clé : vérifie ATLAS_AUDIO_CLE des deux côtés")
                elif code == FERMETURE_CLE_ABSENTE:
                    acceptee = False
                    _journal.error("le Core n'a pas de clé : ajoute ATLAS_AUDIO_CLE dans son .env")
                elif isinstance(e, _ERREURS_RESEAU):
                    _journal.warning("Core injoignable ou connexion perdue (%s)", type(e).__name__)
                else:
                    # Pas une coupure réseau : la trace complète, sinon un bogue (mot de
                    # réveil, VAD…) reviendrait toutes les secondes sans jamais se laisser
                    # diagnostiquer.
                    _journal.warning(
                        "Core injoignable ou connexion perdue (%s)",
                        type(e).__name__,
                        exc_info=True,
                    )
            if absence is None:
                absence = _demarrer_absence(pendant_l_absence)
            if acceptee:
                echecs = 0
            delai = delais[min(echecs, len(delais) - 1)]
            echecs += 1
            _journal.info("nouvelle tentative de connexion dans %s s", delai)
            await attendre(delai)
    finally:
        await _arreter_absence(absence)

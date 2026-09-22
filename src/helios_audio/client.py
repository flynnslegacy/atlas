"""Le daemon audio du M5.

Deux boucles concurrentes : l'une lit le micro et parle au Core, l'autre reçoit
du Core et joue le son. Le client ne décide de rien d'autre que du barge-in —
il le décide localement parce que 200 ms d'aller-retour réseau rendraient
l'interruption molle.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time
from typing import Protocol

from helios_core.protocole import (
    Bonjour,
    Dire,
    Etat,
    FinEnonce,
    Interruption,
    Reveil,
    StopAudio,
    decoder_audio_sortant,
    encoder_audio_entrant,
)

from .aec import ouvrir_peripherique
from .reveilleur import ReveilleurTouche
from .vad import DetecteurVoix, Endpointeur

_journal = logging.getLogger(__name__)

URL_CORE = os.environ.get("HELIOS_CORE_URL", "ws://127.0.0.1:8080/ws/audio")


class Transport(Protocol):
    async def envoyer_json(self, msg) -> None: ...
    async def envoyer_binaire(self, trame: bytes) -> None: ...


class ClientAudio:
    def __init__(
        self, transport, peripherique, detecteur, endpointeur, reveilleur, bargein=None
    ) -> None:
        self._transport = transport
        self._peripherique = peripherique
        self._detecteur = detecteur
        self._endpointeur = endpointeur
        self._reveilleur = reveilleur
        self._capture = False
        self._helios_parle = False
        self._id_courant = 0
        self._bargein = bargein or Endpointeur(silence_ms=400, parole_min_ms=300)

    # --- micro vers Core --------------------------------------------------

    async def boucle_capture(self) -> None:
        with contextlib.suppress(asyncio.CancelledError, asyncio.IncompleteReadError):
            while True:
                bloc = await self._peripherique.lire_bloc()
                await self._traiter_bloc(bloc)

    async def _traiter_bloc(self, bloc: bytes) -> None:
        if self._helios_parle:
            await self._surveiller_bargein(bloc)
            return

        if not self._capture:
            if self._reveilleur.examiner(bloc):
                self._capture = True
                self._endpointeur.reinitialiser()
                await self._transport.envoyer_json(Reveil(confiance=1.0, horodatage=time.time()))
            return

        await self._transport.envoyer_binaire(encoder_audio_entrant(bloc))
        if self._endpointeur.ajouter(self._detecteur.parle(bloc)) == "fin":
            self._capture = False
            await self._transport.envoyer_json(FinEnonce(duree_ms=0))

    async def _surveiller_bargein(self, bloc: bytes) -> None:
        if self._bargein.ajouter(self._detecteur.parle(bloc)) != "debut":
            return
        _journal.info("interruption détectée")
        self._helios_parle = False
        await self._peripherique.vider()
        await self._transport.envoyer_json(Interruption(horodatage=time.time()))
        self._capture = True
        self._endpointeur.reinitialiser()

    # --- Core vers haut-parleur -------------------------------------------

    async def sur_message(self, msg) -> None:
        if isinstance(msg, Dire):
            self._id_courant = msg.id_enonce
            self._helios_parle = True
            self._bargein.reinitialiser()
        elif isinstance(msg, StopAudio):
            self._helios_parle = False
            await self._peripherique.vider()
        elif isinstance(msg, Etat):
            if msg.valeur == "parole":
                self._helios_parle = True
                self._bargein.reinitialiser()
            elif msg.valeur in ("repos", "ecoute"):
                self._helios_parle = False

    async def sur_trame(self, trame: bytes) -> None:
        identifiant, pcm = decoder_audio_sortant(trame)
        if identifiant != self._id_courant:
            return  # trame d'un énoncé interrompu : on la jette
        await self._peripherique.jouer(pcm)


class TransportWebSocket:
    def __init__(self, ws) -> None:
        self._ws = ws

    async def envoyer_json(self, msg) -> None:
        await self._ws.send(msg.model_dump_json())

    async def envoyer_binaire(self, trame: bytes) -> None:
        await self._ws.send(trame)


async def principal() -> None:
    import json

    import websockets
    from pydantic import TypeAdapter

    from helios_core.protocole import MessageCore

    adaptateur = TypeAdapter(MessageCore)
    logging.basicConfig(level=logging.INFO)
    peripherique = await ouvrir_peripherique()

    async with websockets.connect(URL_CORE) as ws:
        transport = TransportWebSocket(ws)
        client = ClientAudio(
            transport=transport,
            peripherique=peripherique,
            detecteur=DetecteurVoix(),
            endpointeur=Endpointeur(),
            reveilleur=ReveilleurTouche(),
        )
        await transport.envoyer_json(Bonjour(client="m5", capacites=["aec", "vad"]))
        capture = asyncio.create_task(client.boucle_capture())
        try:
            async for recu in ws:
                if isinstance(recu, bytes):
                    await client.sur_trame(recu)
                else:
                    await client.sur_message(adaptateur.validate_python(json.loads(recu)))
        finally:
            capture.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await capture
            await peripherique.fermer()


if __name__ == "__main__":
    asyncio.run(principal())

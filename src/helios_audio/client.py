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
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from helios_core.protocole import (
    DUREE_BLOC_MS,
    Bonjour,
    Dire,
    FinEnonce,
    Interruption,
    Reveil,
    StopAudio,
    decoder_audio_sortant,
    encoder_audio_entrant,
)

from .aec import ouvrir_peripherique
from .reveilleur import PredicteurOpenWakeWord, ReveilleurMotCle, ReveilleurTouche
from .vad import DetecteurVoix, Endpointeur

_journal = logging.getLogger(__name__)

URL_CORE = os.environ.get("HELIOS_CORE_URL", "ws://127.0.0.1:8080/ws/audio")

DUREE_BLOC_S = DUREE_BLOC_MS / 1000  # 0,020 s joués par trame
MARGE_SORTIE_S = 0.15  # latence de sortie du haut-parleur, à régler au banc


@dataclass(frozen=True)
class Reglages:
    """Les trois seuils que le banc de mesure (tâche 14) sert à choisir."""

    seuil_reveil: float
    silence_ms: int
    bargein_ms: int


def lire_reglages() -> Reglages:
    """Lit les réglages dans l'environnement, sinon les valeurs par défaut actuelles."""
    return Reglages(
        seuil_reveil=float(os.environ.get("HELIOS_REVEIL_SEUIL", "0.5")),
        silence_ms=int(os.environ.get("HELIOS_SILENCE_MS", "400")),
        bargein_ms=int(os.environ.get("HELIOS_BARGEIN_MS", "300")),
    )


class Transport(Protocol):
    async def envoyer_json(self, msg) -> None: ...
    async def envoyer_binaire(self, trame: bytes) -> None: ...


class ClientAudio:
    def __init__(
        self,
        transport,
        peripherique,
        detecteur,
        endpointeur,
        reveilleur,
        bargein=None,
        horloge: Callable[[], float] | None = None,
    ) -> None:
        self._transport = transport
        self._peripherique = peripherique
        self._detecteur = detecteur
        self._endpointeur = endpointeur
        self._reveilleur = reveilleur
        self._capture = False
        self._id_courant = 0
        # Plus grand identifiant d'énoncé coupé : ni ses phrases encore en vol ni
        # ses trames ne doivent plus jamais sonner, ni ré-armer le barge-in.
        self._id_coupe = 0
        self._bargein = bargein or Endpointeur(silence_ms=400, parole_min_ms=300)
        self._horloge = horloge or time.monotonic
        # Échéance, sur notre propre horloge, de la fin de l'audio déjà confié au
        # haut-parleur. Le Core finit d'ENVOYER bien avant que le son finisse de jouer.
        self._fin_lecture = 0.0

    def _helios_parle_encore(self) -> bool:
        # Une échéance expire d'elle-même : le micro ne peut jamais rester sourd.
        return self._horloge() < self._fin_lecture + MARGE_SORTIE_S

    # --- micro vers Core --------------------------------------------------

    async def boucle_capture(self) -> None:
        with contextlib.suppress(asyncio.CancelledError, asyncio.IncompleteReadError):
            while True:
                bloc = await self._peripherique.lire_bloc()
                await self._traiter_bloc(bloc)

    async def _traiter_bloc(self, bloc: bytes) -> None:
        if self._helios_parle_encore():
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
        self._couper()
        await self._peripherique.vider()
        await self._transport.envoyer_json(Interruption(horodatage=time.time()))
        self._capture = True
        self._endpointeur.reinitialiser()

    def _couper(self) -> None:
        """Marque l'énoncé courant comme coupé ; son audio vient d'être vidé."""
        self._id_coupe = max(self._id_coupe, self._id_courant)
        self._id_courant = 0
        self._fin_lecture = 0.0

    # --- Core vers haut-parleur -------------------------------------------

    async def sur_message(self, msg) -> None:
        if isinstance(msg, Dire):
            if msg.id_enonce <= self._id_coupe:
                return  # phrase en vol d'une réponse coupée : on l'ignore
            if msg.id_enonce != self._id_courant:
                # Nouvel énoncé seulement : remettre le compteur à zéro à chaque
                # phrase effacerait la parole que l'utilisateur a déjà accumulée.
                self._id_courant = msg.id_enonce
                self._bargein.reinitialiser()
        elif isinstance(msg, StopAudio):
            self._couper()
            await self._peripherique.vider()
        # Etat n'arme ni ne désarme rien : « repos » dit que le Core a fini
        # d'ENVOYER, pas que le son est joué. Seule l'horloge de lecture tranche.

    async def sur_trame(self, trame: bytes) -> None:
        identifiant, pcm = decoder_audio_sortant(trame)
        if identifiant <= self._id_coupe or identifiant != self._id_courant:
            return  # trame d'un énoncé interrompu : on la jette
        await self._peripherique.jouer(pcm)
        self._fin_lecture = max(self._horloge(), self._fin_lecture) + DUREE_BLOC_S


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
    reglages = lire_reglages()

    if os.environ.get("HELIOS_REVEILLEUR", "touche") == "motcle":
        reveilleur = ReveilleurMotCle(PredicteurOpenWakeWord(), seuil=reglages.seuil_reveil)
    else:
        reveilleur = ReveilleurTouche()

    async with websockets.connect(URL_CORE) as ws:
        transport = TransportWebSocket(ws)
        client = ClientAudio(
            transport=transport,
            peripherique=peripherique,
            detecteur=DetecteurVoix(),
            endpointeur=Endpointeur(silence_ms=reglages.silence_ms),
            reveilleur=reveilleur,
            bargein=Endpointeur(parole_min_ms=reglages.bargein_ms),
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

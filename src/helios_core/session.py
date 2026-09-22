"""Orchestration d'un tour de parole, pour une connexion cliente.

Une Session par client audio. Elle ne connaît ni le réseau ni le transport :
elle reçoit des messages décodés et appelle deux fonctions d'envoi. C'est ce qui
la rend testable sans WebSocket.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable

from .cerveau import Cerveau
from .etat import MachineEtat
from .phrases import DecoupeurPhrases
from .protocole import (
    Dire,
    Erreur,
    Etat,
    FinEnonce,
    Interruption,
    MessageClient,
    MessageCore,
    Reveil,
    StopAudio,
    Transcription,
    encoder_audio_sortant,
)

_journal = logging.getLogger(__name__)

EnvoyerJson = Callable[[MessageCore], Awaitable[None]]
EnvoyerBinaire = Callable[[bytes], Awaitable[None]]


class Session:
    def __init__(
        self,
        envoyer_json: EnvoyerJson,
        envoyer_binaire: EnvoyerBinaire,
        transcription,
        synthese,
        cerveau: Cerveau,
    ) -> None:
        self._envoyer_json = envoyer_json
        self._envoyer_binaire = envoyer_binaire
        self._transcription = transcription
        self._synthese = synthese
        self._cerveau = cerveau
        self._machine = MachineEtat()
        self._tampon: list[bytes] = []
        self._tache: asyncio.Task | None = None
        self._id_enonce = 0

    # --- entrées ---------------------------------------------------------

    async def sur_message(self, msg: MessageClient) -> None:
        if isinstance(msg, Reveil):
            await self._reveiller()
        elif isinstance(msg, FinEnonce):
            await self._fin_enonce()
        elif isinstance(msg, Interruption):
            await self._interrompre()

    async def sur_audio(self, pcm: bytes) -> None:
        if self._machine.valeur == "ecoute":
            self._tampon.append(pcm)

    async def fermer(self) -> None:
        await self._annuler_tache()

    # --- transitions -----------------------------------------------------

    async def _reveiller(self) -> None:
        if self._machine.valeur in ("parole", "reflexion"):
            await self._interrompre()
        if self._machine.valeur == "repos":
            self._machine.aller_vers("ecoute")
        self._tampon.clear()
        await self._etat("ecoute")

    async def _fin_enonce(self) -> None:
        if self._machine.valeur != "ecoute":
            return
        self._machine.aller_vers("reflexion")
        await self._etat("reflexion")
        self._tache = asyncio.create_task(self._tour())

    async def _interrompre(self) -> None:
        await self._annuler_tache()
        await self._envoyer_json(StopAudio(id_enonce=self._id_enonce))
        if self._machine.valeur == "parole":
            self._machine.aller_vers("ecoute")
            self._tampon.clear()
            await self._etat("ecoute")
        elif self._machine.valeur == "reflexion":
            self._machine.aller_vers("repos")
            await self._etat("repos")
        elif self._machine.valeur == "repos":
            # Le tour s'est déjà terminé quand l'interruption arrive (on a coupé
            # juste à la fin de la phrase) : sans cette branche, le Core reste au
            # repos sans écouter, alors que le client, lui, s'est déjà remis à
            # capturer et à envoyer de l'audio.
            self._machine.aller_vers("ecoute")
            self._tampon.clear()
            await self._etat("ecoute")

    async def _annuler_tache(self) -> None:
        if self._tache and not self._tache.done():
            self._tache.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._tache
        self._tache = None

    # --- le tour lui-même ------------------------------------------------

    async def _tour(self) -> None:
        try:
            pcm = b"".join(self._tampon)
            self._tampon.clear()

            texte = await self._transcription.transcrire(pcm)
            await self._envoyer_json(Transcription(texte=texte, finale=True))

            if not texte.strip():
                self._machine.aller_vers("repos")
                await self._etat("repos")
                return

            self._machine.aller_vers("parole")
            await self._etat("parole")
            self._id_enonce += 1
            identifiant = self._id_enonce

            decoupeur = DecoupeurPhrases()
            rang = 0
            async with contextlib.aclosing(self._cerveau.repondre(texte)) as fragments:
                async for fragment in fragments:
                    for phrase in decoupeur.ajouter(fragment):
                        rang += 1
                        await self._dire(identifiant, rang, phrase)
            for phrase in decoupeur.vider():
                rang += 1
                await self._dire(identifiant, rang, phrase)

            self._machine.aller_vers("repos")
            await self._etat("repos")
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 — on ne laisse jamais mourir la session
            _journal.exception("échec du tour de parole")
            await self._envoyer_json(Erreur(code="tour", message=f"Je n'ai pas pu répondre : {e}"))
            if self._machine.peut_aller_vers("repos"):
                self._machine.aller_vers("repos")
                await self._etat("repos")

    async def _dire(self, identifiant: int, rang: int, phrase: str) -> None:
        await self._envoyer_json(Dire(id_enonce=identifiant, rang=rang, texte=phrase))
        n = 0
        async with contextlib.aclosing(self._synthese.synthetiser(phrase)) as blocs:
            async for bloc in blocs:
                n += 1
                await self._envoyer_binaire(encoder_audio_sortant(identifiant, bloc))
        if n == 0 and phrase.strip():
            # Sans cela, une synthèse muette (voix absente…) rend Helios silencieux
            # sans que rien, nulle part, ne dise pourquoi.
            raise RuntimeError(f"la synthèse n'a produit aucun audio pour « {phrase} »")

    async def _etat(self, valeur) -> None:
        await self._envoyer_json(Etat(valeur=valeur))

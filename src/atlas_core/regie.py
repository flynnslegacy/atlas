"""La régie : ce que partagent toutes les connexions du Core.

Le diffuseur des pages, le mode muet, et la session qui reçoit les questions tapées :
celle du client audio connecté, pour qu'Atlas réponde à voix haute, ou à défaut une
session sans voix.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from .diffuseur import Diffuseur
from .protocole_web import Muet


class SessionPilotable(Protocol):
    async def sur_saisie(self, texte: str) -> None: ...

    async def taire(self) -> None: ...


class Regie:
    def __init__(
        self, diffuseur: Diffuseur, fabrique_session_ecrite: Callable[[], SessionPilotable]
    ) -> None:
        self.diffuseur = diffuseur
        self._fabrique_session_ecrite = fabrique_session_ecrite
        self._session_audio: SessionPilotable | None = None
        self._session_ecrite: SessionPilotable | None = None
        self._muet = False

    @property
    def muet(self) -> bool:
        return self._muet

    def voix_active(self) -> bool:
        return not self._muet

    def rattacher(self, session: SessionPilotable) -> None:
        """Un client audio vient de se connecter : il répondra aux questions tapées."""
        self._session_audio = session

    def detacher(self, session: SessionPilotable) -> None:
        if self._session_audio is session:
            self._session_audio = None

    async def saisie(self, texte: str) -> None:
        session = self._session_audio
        if session is None:
            if self._session_ecrite is None:
                self._session_ecrite = self._fabrique_session_ecrite()
            session = self._session_ecrite
        await session.sur_saisie(texte)

    async def basculer_muet(self, actif: bool) -> None:
        self._muet = actif
        self.diffuseur.publier(Muet(actif=actif))
        if actif and self._session_audio is not None:
            await self._session_audio.taire()

"""La régie : ce que partagent toutes les connexions du Core.

Le diffuseur des pages, le mode muet, et les sessions qui reçoivent les questions
tapées : celle de la page qui l'a tapée si son micro est allumé, sinon la plus récente
des sessions audio (le client du Mac ou une page), pour qu'Atlas réponde à voix haute,
ou à défaut une session sans voix.
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
        # Les sessions audio, de la plus ancienne à la plus récente, avec la page qui
        # les porte (None : le client audio du Mac).
        self._sessions: list[tuple[str | None, SessionPilotable]] = []
        self._session_ecrite: SessionPilotable | None = None
        self._muet = False

    @property
    def muet(self) -> bool:
        return self._muet

    def voix_active(self) -> bool:
        return not self._muet

    def rattacher(self, session: SessionPilotable, page: str | None = None) -> None:
        """Un client audio vient de se connecter, ou une page d'allumer son micro."""
        self._sessions.append((page, session))

    def detacher(self, session: SessionPilotable) -> None:
        self._sessions = [(p, s) for p, s in self._sessions if s is not session]

    def _session_pour(self, page: str | None) -> SessionPilotable:
        if page is not None:
            for p, session in reversed(self._sessions):
                if p == page:
                    return session
        if self._sessions:
            return self._sessions[-1][1]
        if self._session_ecrite is None:
            self._session_ecrite = self._fabrique_session_ecrite()
        return self._session_ecrite

    async def saisie(self, texte: str, page: str | None = None) -> None:
        await self._session_pour(page).sur_saisie(texte)

    async def basculer_muet(self, actif: bool) -> None:
        self._muet = actif
        self.diffuseur.publier(Muet(actif=actif))
        if actif:
            for _, session in list(self._sessions):
                await session.taire()

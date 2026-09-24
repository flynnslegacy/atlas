"""Relaie vers les pages ce qui se passe dans le Core, et garde les derniers échanges.

La publication est synchrone : le Core ne ralentit jamais pour une page. Chaque page
a sa file, vidée par sa propre tâche vers sa connexion.
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
from collections import deque
from collections.abc import Awaitable, Callable

from pydantic import BaseModel

from .protocole import Erreur, Etat
from .protocole_web import Echange, Historique, Latences, Muet, Niveau, Question, Reponse

TAILLE_HISTORIQUE = 50
# Une page qui n'arrive pas à suivre perd des niveaux (l'orbe saute une image), jamais
# un état, un texte ou une erreur.
RETARD_MAX_NIVEAUX = 32

Envoyer = Callable[[BaseModel], Awaitable[None]]


def _heure_locale() -> str:
    return dt.datetime.now().strftime("%H:%M")


class Abonnement:
    """Une page abonnée : sa file, et la tâche qui la vide vers la connexion."""

    def __init__(self, diffuseur: Diffuseur, envoyer: Envoyer) -> None:
        self._diffuseur = diffuseur
        self._file: asyncio.Queue[BaseModel] = asyncio.Queue()
        self._tache = asyncio.create_task(self._pomper(envoyer))

    def deposer(self, msg: BaseModel) -> None:
        if isinstance(msg, Niveau) and self._file.qsize() >= RETARD_MAX_NIVEAUX:
            return
        self._file.put_nowait(msg)

    def envoyer_prive(self, msg: BaseModel) -> None:
        """Pour cette page seulement : une erreur de saisie, par exemple."""
        self._file.put_nowait(msg)

    async def _pomper(self, envoyer: Envoyer) -> None:
        try:
            while True:
                await envoyer(await self._file.get())
        finally:
            # Une page qui ne reçoit plus (connexion rompue) quitte la diffusion d'elle-même.
            self._diffuseur.retirer(self)

    async def fermer(self) -> None:
        self._diffuseur.retirer(self)
        self._tache.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await self._tache


class Diffuseur:
    def __init__(
        self,
        taille_historique: int = TAILLE_HISTORIQUE,
        heure: Callable[[], str] | None = None,
    ) -> None:
        self._abonnements: list[Abonnement] = []
        self._echanges: deque[Echange] = deque(maxlen=taille_historique)
        self._en_cours: Echange | None = None
        self._dernier_etat = Etat(valeur="repos")
        self._muet = False
        self._heure = heure or _heure_locale

    def abonner(self, envoyer: Envoyer) -> Abonnement:
        """Abonne une page : elle reçoit d'abord l'historique, le mode muet et l'état courant."""
        abonnement = Abonnement(self, envoyer)
        for msg in (self.historique(), Muet(actif=self._muet), self._dernier_etat):
            abonnement.deposer(msg)
        self._abonnements.append(abonnement)
        return abonnement

    def retirer(self, abonnement: Abonnement) -> None:
        if abonnement in self._abonnements:
            self._abonnements.remove(abonnement)

    def historique(self) -> Historique:
        return Historique(echanges=[e.model_copy(deep=True) for e in self._echanges])

    def publier(self, msg: BaseModel) -> None:
        self._noter(msg)
        for abonnement in list(self._abonnements):
            abonnement.deposer(msg)

    def _noter(self, msg: BaseModel) -> None:
        if isinstance(msg, Etat):
            self._dernier_etat = msg
            if msg.valeur in ("repos", "ecoute"):
                self._en_cours = None
        elif isinstance(msg, Muet):
            self._muet = msg.actif
        elif isinstance(msg, Question):
            self._en_cours = Echange(heure=self._heure(), source=msg.source, question=msg.texte)
            self._echanges.append(self._en_cours)
        elif isinstance(msg, Reponse) and self._en_cours is not None:
            self._en_cours.reponse = f"{self._en_cours.reponse} {msg.texte}".strip()
        elif isinstance(msg, Latences) and self._en_cours is not None:
            self._en_cours.latences = msg
        elif isinstance(msg, Erreur):
            if self._en_cours is not None:
                self._en_cours.erreur = msg.message
            else:
                self._echanges.append(
                    Echange(heure=self._heure(), source="voix", question="", erreur=msg.message)
                )

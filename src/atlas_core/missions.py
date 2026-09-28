"""Les missions sur le Mac de David (spec du poste, §5) : un service du Core, que le
connecteur du poste utilise.

Une mission s'ouvre au « oui » de David, et ne vit que le temps de la réponse qui suit : elle
s'arrête quand Claude la termine, au bout de sa durée, quand David parle, quand la réponse se
termine, ou quand la conversation se ferme. Hors mission, les gestes refusent.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from .poste import ErreurPoste

DUREE_S = 180.0
AUCUNE_MISSION = "Aucune mission en cours : demande d'abord à David avec mac_mission."
TEMPS_ECOULE = "Le temps de la mission est écoulé."


class Missions:
    """La mission en cours : ouverte par le « oui » de David, fermée par sa fin, sa durée, une
    phrase de David, la fin de la réponse ou celle de la conversation. `sur_debut` et
    `sur_fin` préviennent les pages."""

    def __init__(
        self,
        duree_s: float = DUREE_S,
        attendre: Callable[[float], Awaitable[None]] = asyncio.sleep,
        sur_debut: Callable[[str], None] | None = None,
        sur_fin: Callable[[str], None] | None = None,
    ) -> None:
        self.duree_s = duree_s
        self._attendre = attendre
        self.sur_debut = sur_debut or (lambda texte: None)
        self.sur_fin = sur_fin or (lambda texte: None)
        self.en_cours: str | None = None
        self._expiree = False
        self._minuterie: asyncio.Task | None = None

    def ouvrir(self, description: str) -> None:
        self.fermer("Mission arrêtée.")
        self.en_cours, self._expiree = description, False
        self._minuterie = asyncio.create_task(self._expirer())
        self.sur_debut(f"Mission en cours : {description}")

    def fermer(self, fin: str) -> None:
        """Ferme la mission en cours, s'il y en a une, et le dit aux pages."""
        self._expiree = False
        if self.en_cours is None:
            return
        self._arreter_la_minuterie()
        self.en_cours = None
        self.sur_fin(fin)

    def verifier(self) -> None:
        """Un geste n'a lieu que pendant une mission ; sinon `ErreurPoste`, pour Claude."""
        if self.en_cours is None:
            raise ErreurPoste(TEMPS_ECOULE if self._expiree else AUCUNE_MISSION)

    async def _expirer(self) -> None:
        await self._attendre(self.duree_s)
        self._minuterie = None  # c'est elle qui sonne : rien à annuler
        if self.en_cours is not None:
            self.en_cours, self._expiree = None, True
            self.sur_fin("Temps de la mission écoulé.")

    def _arreter_la_minuterie(self) -> None:
        if self._minuterie is not None:
            self._minuterie.cancel()
            self._minuterie = None

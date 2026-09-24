"""Le volume de la voix, ramené de 0 à 1 pour l'orbe des pages.

Deux sources : la voix de David, reçue pendant l'écoute, et celle d'Atlas, envoyée
pendant la parole. La synthèse va environ deux fois plus vite que la lecture : les
niveaux de la voix d'Atlas sont donc calés sur le moment où chaque morceau sera joué.
"""

from __future__ import annotations

import asyncio
import math
import sys
from array import array
from collections.abc import Callable
from typing import Protocol

from .protocole import FREQUENCE_HZ

PLANCHER_DBFS = -60.0
PLAFOND_DBFS = -10.0
CADENCE_HZ = 15  # au plus 15 niveaux par seconde vers les pages
INTERVALLE_S = 1 / CADENCE_HZ


def niveau(pcm: bytes) -> float:
    """Niveau efficace d'un morceau PCM s16le : 0 sous −60 dBFS, 1 au-dessus de −10 dBFS."""
    utile = len(pcm) - len(pcm) % 2
    if utile == 0:
        return 0.0
    echantillons = array("h")
    echantillons.frombytes(pcm[:utile])
    if sys.byteorder == "big":
        echantillons.byteswap()
    rms = math.sqrt(sum(e * e for e in echantillons) / len(echantillons)) / 32768
    if rms <= 0:
        return 0.0
    dbfs = 20 * math.log10(rms)
    return min(1.0, max(0.0, (dbfs - PLANCHER_DBFS) / (PLAFOND_DBFS - PLANCHER_DBFS)))


class Poignee(Protocol):
    def cancel(self) -> None: ...


Planifier = Callable[[float, Callable[[float], None], float], Poignee]


def _planifier_sur_la_boucle(delai: float, rappel: Callable[[float], None], valeur: float):
    return asyncio.get_running_loop().call_later(max(0.0, delai), rappel, valeur)


class CalendrierNiveaux:
    """Publie le niveau de chaque morceau de la voix d'Atlas au moment où il sera joué."""

    def __init__(
        self,
        publier: Callable[[float], None],
        horloge: Callable[[], float],
        planifier: Planifier | None = None,
    ) -> None:
        self._publier = publier
        self._horloge = horloge
        self._planifier = planifier or _planifier_sur_la_boucle
        self._fin_lecture = 0.0
        self._dernier = -math.inf
        self._poignees: list[Poignee] = []

    def ajouter(self, pcm: bytes) -> None:
        maintenant = self._horloge()
        if maintenant >= self._fin_lecture:
            self._poignees.clear()  # tout ce qui était prévu a déjà été joué
        debut = max(maintenant, self._fin_lecture)
        self._fin_lecture = debut + len(pcm) / 2 / FREQUENCE_HZ
        if debut - self._dernier < INTERVALLE_S:
            return
        self._dernier = debut
        self._poignees.append(self._planifier(debut - maintenant, self._publier, niveau(pcm)))

    def annuler(self) -> None:
        """Interruption : plus rien ne doit bouger l'orbe au nom de la phrase coupée."""
        for poignee in self._poignees:
            poignee.cancel()
        self._poignees.clear()
        self._fin_lecture = 0.0
        self._dernier = -math.inf

    def en_lecture(self) -> bool:
        """Vrai s'il reste de la voix d'Atlas programmée, pas encore jouée."""
        return self._fin_lecture > self._horloge()

    def apres_lecture(self, rappel: Callable[[], None]) -> None:
        """Appelle `rappel` une fois que tout ce qui est programmé aura fini de jouer.

        Tout de suite s'il ne reste rien à jouer ; sinon à la fin de la lecture prévue.
        La poignée est rangée avec les autres, pour qu'une interruption l'annule aussi.
        """
        maintenant = self._horloge()
        if self._fin_lecture <= maintenant:
            rappel()
            return
        self._poignees.append(
            self._planifier(self._fin_lecture - maintenant, lambda _valeur: rappel(), 0.0)
        )

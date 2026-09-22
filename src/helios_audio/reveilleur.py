"""Ce qui décide qu'on veut parler à Helios.

En phase 1 c'est la touche Entrée : zéro faux déclenchement pendant qu'on met au
point le reste. Le wake word arrive en tâche 13, derrière le même protocole.
"""

from __future__ import annotations

import sys
import threading
from typing import Protocol


class Reveilleur(Protocol):
    def examiner(self, bloc: bytes) -> bool:
        """Rend True une seule fois, au moment où il faut se réveiller."""
        ...


class ReveilleurTouche:
    """Appuyer sur Entrée pour parler."""

    def __init__(self) -> None:
        self._arme = False
        self._verrou = threading.Lock()
        fil = threading.Thread(target=self._ecouter, daemon=True)
        fil.start()
        print("Appuie sur Entrée pour parler à Helios.", file=sys.stderr)

    def _ecouter(self) -> None:
        for _ in sys.stdin:
            with self._verrou:
                self._arme = True

    def examiner(self, bloc: bytes) -> bool:
        with self._verrou:
            if self._arme:
                self._arme = False
                return True
        return False

"""Ce qui décide qu'on veut parler à Helios.

En phase 1 c'est la touche Entrée : zéro faux déclenchement pendant qu'on met au
point le reste. Le wake word arrive en tâche 13, derrière le même protocole.
"""

from __future__ import annotations

import os
import sys
import threading
from typing import Protocol as _Protocol


class Reveilleur(_Protocol):
    def examiner(self, bloc: bytes) -> bool:
        """Rend True une seule fois, au moment où il faut se réveiller."""
        ...


DUREE_BLOC_MS = 20


class Predicteur(_Protocol):
    def score(self, bloc: bytes) -> float:
        """Rend la probabilité que le mot de réveil vienne d'être prononcé."""
        ...


class PredicteurOpenWakeWord:
    def __init__(self, chemin: str | None = None) -> None:
        import numpy as np
        import openwakeword

        self._np = np
        chemin = chemin or os.environ.get("HELIOS_MOT_REVEIL", "models/hey_helios.onnx")
        self._modele = openwakeword.Model(wakeword_models=[chemin], inference_framework="onnx")
        self._nom = list(self._modele.models.keys())[0]

    def score(self, bloc: bytes) -> float:
        echantillons = self._np.frombuffer(bloc, dtype="<i2")
        return float(self._modele.predict(echantillons)[self._nom])


class ReveilleurMotCle:
    """Réveille sur le mot-clé, avec une période réfractaire.

    Sans réfractaire, une seule prononciation déclenche une dizaine de réveils :
    le score reste au-dessus du seuil pendant toute la durée du mot.
    """

    def __init__(
        self, predicteur: Predicteur, seuil: float = 0.5, refractaire_ms: int = 2000
    ) -> None:
        self._predicteur = predicteur
        self._seuil = seuil
        self._blocs_refractaires = refractaire_ms // DUREE_BLOC_MS
        self._attente = 0

    def examiner(self, bloc: bytes) -> bool:
        if self._attente > 0:
            self._attente -= 1
            self._predicteur.score(bloc)  # on consomme quand même le bloc
            return False
        if self._predicteur.score(bloc) >= self._seuil:
            self._attente = self._blocs_refractaires
            return True
        return False


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

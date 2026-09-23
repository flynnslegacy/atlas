"""Repère les scores suspects d'une écoute continue et garde 3 s autour de chacun."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np

DUREE_BLOC_S = 0.02


@dataclass
class Alerte:
    instant_s: float  # moment du premier score au-dessus du seuil, depuis le début
    score: float  # le plus haut score de l'épisode
    audio: np.ndarray  # float32 16 kHz : avant, déclencheur, après


class Veilleur:
    def __init__(
        self,
        seuil_journal: float = 0.3,
        avant_s: float = 1.5,
        apres_s: float = 1.5,
        refractaire_s: float = 2.0,
    ) -> None:
        self._seuil = seuil_journal
        self._avant: deque[bytes] = deque(maxlen=round(avant_s / DUREE_BLOC_S))
        self._apres = round(apres_s / DUREE_BLOC_S)
        self._refractaire = round(refractaire_s / DUREE_BLOC_S)
        self._vus = 0
        self._attente = 0
        self._episode: dict | None = None

    def ajouter(self, bloc: bytes, score: float) -> Alerte | None:
        self._vus += 1
        if self._episode is not None:
            episode = self._episode
            episode["blocs"].append(bloc)
            episode["score"] = max(episode["score"], score)
            episode["restant"] -= 1
            if episode["restant"] > 0:
                return None
            self._episode = None
            self._attente = self._refractaire
            pcm = np.frombuffer(b"".join(episode["blocs"]), dtype="<i2")
            return Alerte(episode["instant"], episode["score"], pcm.astype(np.float32) / 32768.0)
        if self._attente > 0:
            self._attente -= 1
        elif score >= self._seuil:
            self._episode = {
                "instant": self._vus * DUREE_BLOC_S,
                "score": score,
                "blocs": list(self._avant) + [bloc],
                "restant": self._apres,
            }
            self._avant.clear()
            return None
        self._avant.append(bloc)
        return None

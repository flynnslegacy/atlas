"""Détection de voix (Silero) et décision de fin de phrase.

Le modèle et la décision sont séparés : le premier est une boîte noire, qu'on
vérifie sur de la vraie parole ; le second est de la logique pure, qu'on teste
exhaustivement.
"""

from __future__ import annotations

import os
from typing import Literal

import numpy as np

from atlas_core.protocole import TAILLE_BLOC_OCTETS

DUREE_BLOC_MS = 20
_FENETRE_SILERO = 512  # échantillons attendus par le modèle v5 à 16 kHz
# Silero v5 veut aussi les 64 échantillons qui précèdent chaque fenêtre, comme le
# fait son enveloppe officielle. Sans eux, il rend des probabilités proches de
# zéro sur de la vraie parole : ni fin de phrase, ni interruption, jamais.
_CONTEXTE_SILERO = 64

CHEMIN_MODELE = os.environ.get("ATLAS_VAD_MODELE", "models/silero_vad.onnx")


def verifier_bloc(bloc: bytes) -> None:
    """Refuse tout bloc qui n'est pas un bloc de 20 ms, pour échouer franchement."""
    if len(bloc) != TAILLE_BLOC_OCTETS:
        raise ValueError(f"Bloc invalide : {len(bloc)} octets reçus, {TAILLE_BLOC_OCTETS} attendus")


class DetecteurVoix:
    """Enveloppe Silero. Accumule jusqu'à la fenêtre attendue par le modèle,
    précédée de son contexte."""

    def __init__(self, seuil: float = 0.5, chemin: str = CHEMIN_MODELE) -> None:
        import onnxruntime

        self.seuil = seuil
        self._session = onnxruntime.InferenceSession(chemin, providers=["CPUExecutionProvider"])
        self._etat = np.zeros((2, 1, 128), dtype=np.float32)
        self._contexte = np.zeros(_CONTEXTE_SILERO, dtype=np.float32)
        self._reste = np.zeros(0, dtype=np.float32)
        self._derniere = 0.0

    def probabilite(self, bloc: bytes) -> float:
        verifier_bloc(bloc)
        echantillons = np.frombuffer(bloc, dtype="<i2").astype(np.float32) / 32768.0
        self._reste = np.concatenate([self._reste, echantillons])
        while self._reste.size >= _FENETRE_SILERO:
            entree = np.concatenate([self._contexte, self._reste[:_FENETRE_SILERO]])
            self._reste = self._reste[_FENETRE_SILERO:]
            sortie, self._etat = self._session.run(
                None,
                {
                    "input": entree.reshape(1, -1),
                    "state": self._etat,
                    "sr": np.array(16000, dtype=np.int64),
                },
            )
            self._contexte = entree[-_CONTEXTE_SILERO:]
            self._derniere = float(sortie[0][0])
        return self._derniere

    def parle(self, bloc: bytes) -> bool:
        return self.probabilite(bloc) >= self.seuil


class Endpointeur:
    """Décide du début et de la fin d'un énoncé à partir d'un flux de booléens."""

    def __init__(self, silence_ms: int = 400, parole_min_ms: int = 200) -> None:
        self._blocs_silence = max(1, silence_ms // DUREE_BLOC_MS)
        self._blocs_parole_min = max(1, parole_min_ms // DUREE_BLOC_MS)
        self.reinitialiser()

    @property
    def blocs_parole_min(self) -> int:
        """Nombre de blocs de 20 ms de parole continue avant un « debut »."""
        return self._blocs_parole_min

    def reinitialiser(self) -> None:
        self._en_cours = False
        self._parole = 0
        self._silence = 0

    def ajouter(self, parle: bool) -> Literal["rien", "debut", "fin"]:
        if parle:
            self._silence = 0
            self._parole += 1
            if not self._en_cours and self._parole >= self._blocs_parole_min:
                self._en_cours = True
                return "debut"
            return "rien"

        if not self._en_cours:
            self._parole = 0
            return "rien"

        self._silence += 1
        if self._silence >= self._blocs_silence:
            self.reinitialiser()
            return "fin"
        return "rien"

"""Ce que mesure evaluer.py, séparé du modèle et des fichiers pour être testé."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from atlas_audio.reveilleur import ReveilleurMotCle

from .audio import FREQUENCE

ECHANTILLONS_BLOC = 320
SILENCE_ENTRE_S = 2.0
MARGE_APRES_BLOCS = 50  # un réveil jusqu'à 1 s après la fin de l'extrait compte encore
SEUILS = tuple(round(0.1 * i, 1) for i in range(1, 10))


class PredicteurRejoue:
    """Rejoue des scores déjà calculés : le modèle ne passe qu'une fois par flux."""

    def __init__(self, scores: list[float]) -> None:
        self._scores = iter(scores)

    def score(self, bloc: bytes) -> float:
        return next(self._scores)


def reveils(scores: list[float], seuil: float, refractaire_ms: int = 2000) -> list[int]:
    """Indices des blocs où le client se réveillerait : la logique exacte de ReveilleurMotCle."""
    reveilleur = ReveilleurMotCle(
        PredicteurRejoue(scores), seuil=seuil, refractaire_ms=refractaire_ms
    )
    return [i for i in range(len(scores)) if reveilleur.examiner(b"")]


@dataclass(frozen=True)
class Segment:
    nom: str
    debut: int  # premier bloc de l'extrait
    fin: int  # premier bloc après l'extrait


def assembler(extraits: dict[str, np.ndarray]) -> tuple[np.ndarray, list[Segment]]:
    """Met les extraits bout à bout, séparés de 2 s de silence, et note leurs blocs.

    Le silence laisse le modèle oublier l'extrait précédent : un seul flux suffit,
    comme dans la vraie vie.
    """
    silence = np.zeros(int(SILENCE_ENTRE_S * FREQUENCE), dtype=np.float32)
    morceaux = [silence]
    segments = []
    position = silence.size
    for nom in sorted(extraits):
        audio = np.asarray(extraits[nom], dtype=np.float32)
        debut = position // ECHANTILLONS_BLOC
        position += audio.size
        segments.append(Segment(nom, debut, -(-position // ECHANTILLONS_BLOC)))
        morceaux += [audio, silence]
        position += silence.size
    return np.concatenate(morceaux), segments


def detectes(indices: list[int], segments: list[Segment]) -> set[str]:
    return {
        s.nom for s in segments if any(s.debut <= i < s.fin + MARGE_APRES_BLOCS for i in indices)
    }


def par_heure(nombre: int, blocs: int) -> float:
    heures = blocs * ECHANTILLONS_BLOC / FREQUENCE / 3600
    return nombre / heures if heures else 0.0


def seuil_conseille(lignes: list[dict]) -> float | None:
    """Le plus bas seuil sans aucun réveil sur « Atlas » seul ni sur les négatifs de test."""
    for ligne in sorted(lignes, key=lambda x: x["seuil"]):
        if ligne["atlas_seul"] == 0 and ligne["faux"] == 0:
            return ligne["seuil"]
    return None

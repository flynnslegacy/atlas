"""Ce que disent les voix de synthèse, et ce que Whisper doit y entendre."""

from __future__ import annotations

import re
import unicodedata

# espeak-ng (le phonétiseur de Piper) lit « Hey Atlas » /ɛ atla/ ; « Eille Atlasse »
# donne /ɛj atlas/, la prononciation de David (vérifié avec piper-tts 1.3.0).
POSITIVES = ["Eille Atlasse", "Eille Atlasse !", "Eille, Atlasse.", "Eille Atlasse ?"]

# « Atlas » seul ne doit pas réveiller : David parle de son projet Atlas en visio.
NEGATIVES = [
    "Atlasse",
    "Atlasse.",
    "Le projet Atlasse avance bien.",
    "Atlasse, c'est prêt ?",
    "Hélas",
    "Hélas, non.",
    "Et là",
    "C'est là",
    "Est-ce là ?",
    "Halte-là !",
    "À las",
    "Eh, t'as vu ?",
    "Eille Nicolas",
    "Eille Thomas",
    "Eille Lucas",
    "Eille Alex",
    "Au Texas",
    "Dallasse",
    "Un palace",
    "L'atlas routier",
    "L'océan Atlantique",
]

_INTERJECTIONS = ("hey", "hei", "hay", "he", "eh", "ey", "eille", "heille")
_REVEIL = re.compile(r"\b(?:" + "|".join(_INTERJECTIONS) + r")\s+atlas(?:se)?\b")

DUREE_MAX_POSITIF_S = 2.0
DUREE_MAX_NEGATIF_S = 3.5


def normaliser(texte: str) -> str:
    """Minuscules, sans accents ni ponctuation, espaces simples."""
    decompose = unicodedata.normalize("NFD", texte.lower())
    sans_accents = "".join(c for c in decompose if unicodedata.category(c) != "Mn")
    return " ".join(re.sub(r"[^a-z]+", " ", sans_accents).split())


def entend_hey_atlas(transcription: str) -> bool:
    return _REVEIL.search(normaliser(transcription)) is not None


def a_garder(transcription: str, positif: bool, duree_s: float) -> bool:
    """Décide si un extrait synthétisé mérite d'entrer dans l'entraînement."""
    if positif:
        return duree_s <= DUREE_MAX_POSITIF_S and entend_hey_atlas(transcription)
    # Un négatif que Whisper entend comme « hey atlas » fausserait l'étiquette.
    return duree_s <= DUREE_MAX_NEGATIF_S and not entend_hey_atlas(transcription)

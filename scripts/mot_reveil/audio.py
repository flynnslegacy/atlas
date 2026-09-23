"""Outils audio communs au pipeline du mot de réveil.

Tout ce qui entre dans l'entraînement est du WAV 16 kHz mono int16 : c'est ce
qu'exige train.py d'openWakeWord, et ce qu'entend le client Atlas. Ce module
tourne aussi dans le conteneur d'entraînement, en Python 3.10.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

FREQUENCE = 16000


def lire_wav(chemin: Path) -> tuple[np.ndarray, int]:
    """Rend le premier canal en float32, et la fréquence du fichier."""
    import soundfile as sf

    audio, frequence = sf.read(str(chemin), dtype="float32", always_2d=True)
    return audio[:, 0], int(frequence)


def ecrire_wav(chemin: Path, audio: np.ndarray) -> None:
    """Écrit du 16 kHz mono int16, en créant le dossier au besoin."""
    import soundfile as sf

    chemin.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype("<i2")
    sf.write(str(chemin), pcm, FREQUENCE, subtype="PCM_16")


def ramener_16k(audio: np.ndarray, frequence: int) -> np.ndarray:
    audio = np.asarray(audio, dtype=np.float32)
    if frequence == FREQUENCE:
        return audio
    import soxr

    return soxr.resample(audio, frequence, FREQUENCE).astype(np.float32)


def couper_silences(
    audio: np.ndarray, seuil_dbfs: float = -45.0, marge_s: float = 0.1
) -> np.ndarray:
    """Retire le silence du début et de la fin, en gardant `marge_s` autour de la voix.

    Rend un tableau vide si rien ne dépasse le seuil : l'appelant jette alors l'extrait.
    """
    trame = FREQUENCE // 100  # 10 ms
    n = audio.size // trame
    if n == 0:
        return audio[:0]
    energie = np.mean(audio[: n * trame].reshape(n, trame) ** 2, axis=1)
    actives = np.flatnonzero(10 * np.log10(energie + 1e-12) > seuil_dbfs)
    if actives.size == 0:
        return audio[:0]
    marge = int(marge_s * FREQUENCE)
    debut = max(0, int(actives[0]) * trame - marge)
    fin = min(audio.size, (int(actives[-1]) + 1) * trame + marge)
    return audio[debut:fin]


def fenetres(audio: np.ndarray, duree_s: float = 2.0) -> np.ndarray:
    """Découpe en fenêtres jointives de `duree_s` ; le reste trop court est jeté."""
    n = int(duree_s * FREQUENCE)
    k = audio.size // n
    return audio[: k * n].reshape(k, n)


def en_blocs(audio: np.ndarray, echantillons: int = 320) -> list[bytes]:
    """Blocs de 20 ms en s16le, comme ceux que le client Atlas reçoit du micro."""
    pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype("<i2")
    n = pcm.size // echantillons
    return [pcm[i * echantillons : (i + 1) * echantillons].tobytes() for i in range(n)]

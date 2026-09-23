"""Ramène un dossier de WAV à 16 kHz mono (fonds sonores d'ESC-50, par exemple).

python -m scripts.mot_reveil.convertir <source> <cible>
"""

from __future__ import annotations

import sys
from pathlib import Path

from .audio import ecrire_wav, lire_wav, ramener_16k


def convertir_dossier(source: Path, cible: Path) -> int:
    convertis = 0
    for chemin in sorted(source.glob("*.wav")):
        destination = cible / chemin.name
        if destination.exists():
            continue
        audio, frequence = lire_wav(chemin)
        ecrire_wav(destination, ramener_16k(audio, frequence))
        convertis += 1
    return convertis


if __name__ == "__main__":
    n = convertir_dossier(Path(sys.argv[1]), Path(sys.argv[2]))
    print(f"{n} fichiers convertis en 16 kHz.")

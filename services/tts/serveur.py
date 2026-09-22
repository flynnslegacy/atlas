"""Service de synthèse vocale, moteur interchangeable.

Rend toujours du PCM 16 kHz mono s16le, quel que soit le moteur : la conversion
de fréquence appartient au service, jamais au reste du pipeline.
"""

from __future__ import annotations

import os
import struct
import subprocess
from collections.abc import Iterator
from typing import Protocol

import numpy as np
import soxr
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

MOTEUR = os.environ.get("HELIOS_TTS_MOTEUR", "piper")
VOIX_DEFAUT = os.environ.get("HELIOS_TTS_VOIX", "fr_FR-siwis-medium")
FREQUENCE_SORTIE = 16000
TAILLE_MORCEAU = 640  # 20 ms


class MoteurTTS(Protocol):
    nom: str

    def synthetiser(self, texte: str, voix: str) -> Iterator[bytes]:
        """Rend des morceaux de PCM 16 kHz mono s16le."""
        ...


def aligner_sur_echantillons(donnees: bytes) -> tuple[bytes, bytes]:
    """Sépare les octets alignés sur des échantillons de 16 bits du dernier octet orphelin."""
    if len(donnees) % 2:
        return donnees[:-1], donnees[-1:]
    return donnees, b""


def en_blocs(tampon: bytes) -> tuple[list[bytes], bytes]:
    """Découpe en blocs de 20 ms et rend ce qui reste, pour la lecture suivante."""
    blocs = []
    while len(tampon) >= TAILLE_MORCEAU:
        blocs.append(tampon[:TAILLE_MORCEAU])
        tampon = tampon[TAILLE_MORCEAU:]
    return blocs, tampon


class MoteurPiper:
    nom = "piper"

    def __init__(self, dossier_modeles: str = "/modeles") -> None:
        self._dossier = dossier_modeles

    def synthetiser(self, texte: str, voix: str) -> Iterator[bytes]:
        modele = f"{self._dossier}/{voix or VOIX_DEFAUT}.onnx"
        proc = subprocess.Popen(
            ["piper", "--model", modele, "--output_raw"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
        )
        assert proc.stdin and proc.stdout
        proc.stdin.write(texte.encode("utf-8"))
        proc.stdin.close()

        # Rééchantillonneur à état : garde son filtre d'une lecture à l'autre pour
        # éviter les discontinuités aux frontières de bloc (soxr.resample le
        # réinitialiserait à chaque appel).
        rechantillonneur = soxr.ResampleStream(22050, FREQUENCE_SORTIE, 1, dtype="float32")

        orphelin = b""  # octet isolé d'un échantillon coupé par une lecture
        tampon = b""  # PCM rééchantillonné pas encore découpé en blocs
        while True:
            brut = proc.stdout.read(4096)
            if not brut:
                break
            donnees, orphelin = aligner_sur_echantillons(orphelin + brut)
            if not donnees:
                continue
            echantillons = np.frombuffer(donnees, dtype="<i2").astype(np.float32)
            ramene = rechantillonneur.resample_chunk(echantillons)
            tampon += np.clip(ramene, -32768, 32767).astype("<i2").tobytes()
            blocs, tampon = en_blocs(tampon)
            yield from blocs
        proc.wait()

        dernier = rechantillonneur.resample_chunk(np.empty(0, dtype=np.float32), last=True)
        tampon += np.clip(dernier, -32768, 32767).astype("<i2").tobytes()
        blocs, tampon = en_blocs(tampon)
        yield from blocs
        if tampon:
            yield tampon + b"\x00" * (TAILLE_MORCEAU - len(tampon))


_moteurs: dict[str, MoteurTTS] = {"piper": MoteurPiper()}


def obtenir_moteur() -> MoteurTTS:
    if MOTEUR not in _moteurs:
        raise HTTPException(status_code=500, detail=f"moteur inconnu : {MOTEUR}")
    return _moteurs[MOTEUR]


def entete_wav_streaming() -> bytes:
    """En-tête WAV pour un flux de longueur inconnue.

    Les tailles sont mises au maximum : c'est la convention pour un WAV streamé,
    et tous les lecteurs de flux l'acceptent.
    """
    return (
        b"RIFF"
        + struct.pack("<I", 0xFFFFFFFF)
        + b"WAVE"
        + b"fmt "
        + struct.pack("<IHHIIHH", 16, 1, 1, FREQUENCE_SORTIE, FREQUENCE_SORTIE * 2, 2, 16)
        + b"data"
        + struct.pack("<I", 0xFFFFFFFF)
    )


class DemandeSynthese(BaseModel):
    text: str
    voice: str = ""


app = FastAPI(title="helios-tts")


@app.post("/synthesize")
def synthetiser(
    demande: DemandeSynthese,
    moteur: MoteurTTS = Depends(obtenir_moteur),  # noqa: B008
) -> StreamingResponse:
    if not demande.text.strip():
        raise HTTPException(status_code=400, detail="texte vide")

    def flux() -> Iterator[bytes]:
        yield entete_wav_streaming()
        yield from moteur.synthetiser(demande.text, demande.voice or VOIX_DEFAUT)

    return StreamingResponse(flux(), media_type="audio/wav")


@app.get("/sante")
def sante() -> dict:
    return {"ok": True, "moteur": MOTEUR}

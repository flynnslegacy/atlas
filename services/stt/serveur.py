"""Service de transcription : faster-whisper derrière une route HTTP.

Le modèle se charge à la demande et se décharge après inactivité, parce que les
12 Go de VRAM sont partagés avec ComfyUI. Ce comportement disparaîtra avec la 3090.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import os
import threading
import time
import wave
from contextlib import asynccontextmanager
from typing import Protocol

from fastapi import Body, Depends, FastAPI, HTTPException

MODELE = os.environ.get("HELIOS_STT_MODELE", "large-v3")
DECHARGEMENT_S = int(os.environ.get("HELIOS_STT_DECHARGEMENT_S", "300"))
INTERVALLE_DECHARGEMENT_S = 30


class Transcripteur(Protocol):
    def transcrire(self, wav: bytes) -> tuple[str, str, int]:
        """Rend (texte, langue, durée en millisecondes)."""
        ...


class MoteurWhisper:
    """Charge le modèle à la demande, le décharge après inactivité."""

    def __init__(self, modele: str, dechargement_s: int) -> None:
        self._nom = modele
        self._dechargement_s = dechargement_s
        self._modele = None
        self._dernier_usage = 0.0
        self._en_cours = 0
        self._verrou = threading.Lock()

    @property
    def charge(self) -> bool:
        return self._modele is not None

    def _obtenir(self):
        from faster_whisper import WhisperModel

        with self._verrou:
            if self._modele is None:
                self._modele = WhisperModel(self._nom, device="cuda", compute_type="float16")
            self._en_cours += 1
            return self._modele

    def _liberer(self) -> None:
        with self._verrou:
            self._en_cours -= 1
            self._dernier_usage = time.monotonic()

    def decharger_si_inactif(self) -> None:
        with self._verrou:
            if (
                self._modele is not None
                and self._en_cours == 0
                and time.monotonic() - self._dernier_usage > self._dechargement_s
            ):
                self._modele = None

    def transcrire(self, wav: bytes) -> tuple[str, str, int]:
        modele = self._obtenir()
        try:
            segments, info = modele.transcribe(io.BytesIO(wav), language="fr", vad_filter=False)
            texte = "".join(s.text for s in segments).strip()
            return texte, info.language, int(info.duration * 1000)
        finally:
            self._liberer()


_moteur = MoteurWhisper(MODELE, DECHARGEMENT_S)


def obtenir_transcripteur() -> Transcripteur:
    return _moteur


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    """Gère la boucle de fond pour le déchargement du modèle."""
    tache = asyncio.create_task(_boucle_dechargement())
    yield
    tache.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await tache


async def _boucle_dechargement() -> None:
    """Boucle infinie qui décharge le modèle après inactivité."""
    while True:
        await asyncio.sleep(INTERVALLE_DECHARGEMENT_S)
        await asyncio.to_thread(_moteur.decharger_si_inactif)


app = FastAPI(title="helios-stt", lifespan=lifespan)


def _verifier_wav(corps: bytes) -> None:
    if not corps:
        raise HTTPException(status_code=400, detail="corps vide")
    try:
        with wave.open(io.BytesIO(corps), "rb") as f:
            if f.getnchannels() != 1 or f.getsampwidth() != 2:
                raise HTTPException(status_code=400, detail="attendu : WAV mono 16 bits")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"WAV illisible : {e}") from e


@app.post("/transcribe")
def transcrire(
    corps: bytes = Body(b"", media_type="audio/wav"),
    transcripteur: Transcripteur = Depends(obtenir_transcripteur),  # noqa: B008
) -> dict:
    _verifier_wav(corps)
    texte, langue, duree_ms = transcripteur.transcrire(corps)
    return {"text": texte, "language": langue, "duration_ms": duree_ms}


@app.get("/sante")
def sante() -> dict:
    return {"ok": True, "modele": MODELE, "charge": _moteur.charge}

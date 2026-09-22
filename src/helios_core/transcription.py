"""Client du service helios-stt."""

from __future__ import annotations

import io
import wave

import httpx

from .protocole import FREQUENCE_HZ


def pcm_vers_wav(pcm: bytes, frequence: int = FREQUENCE_HZ) -> bytes:
    """Emballe du PCM s16le mono dans un WAV, pour que le service reste testable au curl."""
    tampon = io.BytesIO()
    with wave.open(tampon, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(frequence)
        f.writeframes(pcm)
    return tampon.getvalue()


class ClientTranscription:
    def __init__(self, base_url: str, http: httpx.AsyncClient) -> None:
        self._base = base_url.rstrip("/")
        self._http = http

    async def transcrire(self, pcm: bytes) -> str:
        reponse = await self._http.post(
            f"{self._base}/transcribe",
            content=pcm_vers_wav(pcm),
            headers={"Content-Type": "audio/wav"},
            timeout=30.0,
        )
        if reponse.status_code != 200:
            raise RuntimeError(
                f"transcription en échec ({reponse.status_code}) : {reponse.text[:200]}"
            )
        return reponse.json()["text"]

"""Configuration lue dans l'environnement. Aucun secret, seulement des adresses."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    stt_url: str
    tts_url: str
    tts_voix: str
    port_core: int

    @staticmethod
    def depuis_environnement() -> Config:
        return Config(
            stt_url=os.environ.get("ATLAS_STT_URL", "http://unraid.local:9010"),
            tts_url=os.environ.get("ATLAS_TTS_URL", "http://unraid.local:9011"),
            tts_voix=os.environ.get("ATLAS_TTS_VOIX", "fr_FR-siwis-medium"),
            port_core=int(os.environ.get("ATLAS_CORE_PORT", "8080")),
        )

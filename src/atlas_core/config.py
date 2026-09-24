"""Configuration lue dans l'environnement.

Des adresses, et la clé d'accès des pages web : jamais écrite dans le code, elle ne
vient que du .env du Core.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    stt_url: str
    tts_url: str
    tts_voix: str  # vide : le service TTS prend la voix par défaut de son moteur
    port_core: int
    web_cle: str  # vide : la page web reste fermée

    @staticmethod
    def depuis_environnement() -> Config:
        return Config(
            stt_url=os.environ.get("ATLAS_STT_URL", "http://unraid.local:9010"),
            tts_url=os.environ.get("ATLAS_TTS_URL", "http://unraid.local:9011"),
            tts_voix=os.environ.get("ATLAS_TTS_VOIX", ""),
            port_core=int(os.environ.get("ATLAS_CORE_PORT", "8080")),
            web_cle=os.environ.get("ATLAS_WEB_CLE", "").strip(),
        )

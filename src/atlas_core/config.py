"""Configuration lue dans l'environnement.

Des adresses, des réglages, et les clés d'accès des pages web et du client audio :
jamais écrites dans le code, elles ne viennent que du .env du Core.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass

CERVEAUX = ("claude", "bouchon")
MODELE_PAR_DEFAUT = "claude-sonnet-5"


@dataclass(frozen=True)
class Config:
    stt_url: str
    tts_url: str
    tts_voix: str  # vide : le service TTS prend la voix par défaut de son moteur
    port_core: int
    web_cle: str  # vide : la page web reste fermée
    cerveau: str = "claude"  # « claude », ou « bouchon » pour faire tourner Atlas sans Claude
    cerveau_modele: str = MODELE_PAR_DEFAUT
    cerveau_oubli_min: float = 30.0  # au-delà, sans échange, la conversation repart de zéro
    audio_cle: str = ""  # vide : /ws/audio refuse tout client audio

    @staticmethod
    def depuis_environnement() -> Config:
        return Config(
            stt_url=os.environ.get("ATLAS_STT_URL", "http://unraid.local:9010"),
            tts_url=os.environ.get("ATLAS_TTS_URL", "http://unraid.local:9011"),
            tts_voix=os.environ.get("ATLAS_TTS_VOIX", ""),
            port_core=int(os.environ.get("ATLAS_CORE_PORT", "8080")),
            web_cle=os.environ.get("ATLAS_WEB_CLE", "").strip(),
            cerveau=_lire_cerveau(),
            cerveau_modele=os.environ.get("ATLAS_CERVEAU_MODELE", "").strip() or MODELE_PAR_DEFAUT,
            cerveau_oubli_min=_lire_oubli_min(),
            audio_cle=os.environ.get("ATLAS_AUDIO_CLE", "").strip(),
        )


def _lire_cerveau() -> str:
    brute = os.environ.get("ATLAS_CERVEAU", "claude")
    valeur = brute.strip().lower()
    if valeur not in CERVEAUX:
        raise ValueError(f"ATLAS_CERVEAU invalide : {brute!r} (claude ou bouchon)")
    return valeur


def _lire_oubli_min() -> float:
    brute = os.environ.get("ATLAS_CERVEAU_OUBLI_MIN", "30")
    try:
        valeur = float(brute)
    except ValueError as erreur:
        raise ValueError(
            f"ATLAS_CERVEAU_OUBLI_MIN invalide : {brute!r} n'est pas un nombre"
        ) from erreur
    if not math.isfinite(valeur) or valeur <= 0:
        raise ValueError(
            f"ATLAS_CERVEAU_OUBLI_MIN invalide : {brute!r} doit être un nombre de minutes positif"
        )
    return valeur

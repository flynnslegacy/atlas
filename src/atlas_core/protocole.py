"""Messages échangés entre le client audio et le Core.

Deux canaux sur la même WebSocket : les messages de contrôle en JSON texte,
l'audio en trames binaires préfixées d'un octet de type.
"""

from __future__ import annotations

import struct
from typing import Annotated, Literal

from pydantic import BaseModel, Field, TypeAdapter, ValidationError

FREQUENCE_HZ = 16000
DUREE_BLOC_MS = 20
TAILLE_BLOC_OCTETS = FREQUENCE_HZ * DUREE_BLOC_MS // 1000 * 2  # 640

_TYPE_AUDIO_ENTRANT = 0x01
_TYPE_AUDIO_SORTANT = 0x02


# --- client vers core ---------------------------------------------------


class Bonjour(BaseModel):
    type: Literal["bonjour"] = "bonjour"
    client: str
    frequence: int = FREQUENCE_HZ
    capacites: list[str] = Field(default_factory=list)


class Reveil(BaseModel):
    type: Literal["reveil"] = "reveil"
    confiance: float
    horodatage: float


class FinEnonce(BaseModel):
    type: Literal["fin_enonce"] = "fin_enonce"
    duree_ms: int


class Interruption(BaseModel):
    type: Literal["interruption"] = "interruption"
    horodatage: float


class ReponseConfirmation(BaseModel):
    type: Literal["reponse_confirmation"] = "reponse_confirmation"
    id_demande: str
    acceptee: bool


MessageClient = Annotated[
    Bonjour | Reveil | FinEnonce | Interruption | ReponseConfirmation,
    Field(discriminator="type"),
]
_adaptateur_client = TypeAdapter(MessageClient)


# --- core vers client ---------------------------------------------------


class Etat(BaseModel):
    type: Literal["etat"] = "etat"
    valeur: Literal["repos", "ecoute", "reflexion", "parole"]


class Transcription(BaseModel):
    type: Literal["transcription"] = "transcription"
    texte: str
    finale: bool


class Dire(BaseModel):
    type: Literal["dire"] = "dire"
    id_enonce: int
    rang: int
    texte: str


class StopAudio(BaseModel):
    type: Literal["stop_audio"] = "stop_audio"
    id_enonce: int


class Confirmation(BaseModel):
    type: Literal["confirmation"] = "confirmation"
    id_demande: str
    action: str
    niveau: int
    expiration_s: int


class Erreur(BaseModel):
    type: Literal["erreur"] = "erreur"
    code: str
    message: str


MessageCore = Annotated[
    Etat | Transcription | Dire | StopAudio | Confirmation | Erreur,
    Field(discriminator="type"),
]


def decoder_message(brut: str) -> MessageClient:
    """Décode un message de contrôle venant du client.

    Lève ValueError sur tout ce qui n'est pas un message connu et valide.
    """
    try:
        return _adaptateur_client.validate_json(brut)
    except ValidationError as e:
        raise ValueError(f"message client invalide : {e}") from e


# --- trames binaires ----------------------------------------------------


def _verifier_bloc(pcm: bytes) -> None:
    if len(pcm) != TAILLE_BLOC_OCTETS:
        raise ValueError(
            f"bloc de {len(pcm)} octets, attendu {TAILLE_BLOC_OCTETS} "
            f"({DUREE_BLOC_MS} ms à {FREQUENCE_HZ} Hz en s16le)"
        )


def encoder_audio_entrant(pcm: bytes) -> bytes:
    _verifier_bloc(pcm)
    return bytes([_TYPE_AUDIO_ENTRANT]) + pcm


def decoder_audio_entrant(trame: bytes) -> bytes:
    if not trame or trame[0] != _TYPE_AUDIO_ENTRANT:
        raise ValueError("trame audio entrante attendue")
    pcm = trame[1:]
    _verifier_bloc(pcm)
    return pcm


def encoder_audio_sortant(id_enonce: int, pcm: bytes) -> bytes:
    _verifier_bloc(pcm)
    return bytes([_TYPE_AUDIO_SORTANT]) + struct.pack(">I", id_enonce) + pcm


def decoder_audio_sortant(trame: bytes) -> tuple[int, bytes]:
    if not trame or trame[0] != _TYPE_AUDIO_SORTANT:
        raise ValueError("trame audio sortante attendue")
    if len(trame) < 5:
        raise ValueError(
            f"trame audio sortante trop courte : {len(trame)} octets, "
            f"attendu au moins 5 (type + id_enonce)"
        )
    (id_enonce,) = struct.unpack(">I", trame[1:5])
    pcm = trame[5:]
    _verifier_bloc(pcm)
    return id_enonce, pcm

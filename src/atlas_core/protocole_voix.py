"""Messages de la connexion /ws/voix, entre une page qui a allumé son micro et le Core.

L'audio y passe en binaire dans les deux sens, en blocs bruts de 20 ms à 16 kHz
(640 octets, s16le) : sur cette connexion, tout ce qui est binaire est de l'audio. Les
messages de contrôle passent en JSON.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from .protocole import TAILLE_BLOC_OCTETS
from .protocole_web import MOTIF_PAGE, TAILLE_MAX_CLE

# --- page vers Core -----------------------------------------------------


class AuthentificationVoix(BaseModel):
    """Le premier message : la clé des pages, l'identifiant de la page, et l'état de son
    interrupteur « Hey Atlas »."""

    type: Literal["authentification"] = "authentification"
    cle: str = Field(max_length=TAILLE_MAX_CLE)
    page: str = Field(pattern=MOTIF_PAGE)
    hey_atlas: bool = False


class Parler(BaseModel):
    """L'orbe a été touchée : écouter, ou couper Atlas s'il parle."""

    type: Literal["parler"] = "parler"


class HeyAtlas(BaseModel):
    type: Literal["hey_atlas"] = "hey_atlas"
    actif: bool


class Reprise(BaseModel):
    """Le son de la page reprend après une interruption d'iOS (écran verrouillé…)."""

    type: Literal["reprise"] = "reprise"


# --- Core vers page -----------------------------------------------------


class Pret(BaseModel):
    """La clé est acceptée : la page peut envoyer son micro."""

    type: Literal["pret"] = "pret"


class Vider(BaseModel):
    """Le son en cours s'arrête net."""

    type: Literal["vider"] = "vider"


MessageVoix = Annotated[
    AuthentificationVoix | Parler | HeyAtlas | Reprise, Field(discriminator="type")
]
_adaptateur_voix = TypeAdapter(MessageVoix)


def decoder_message_voix(brut: str) -> MessageVoix:
    """Décode un message de /ws/voix. Lève ValueError sur tout ce qui n'est pas valide."""
    try:
        return _adaptateur_voix.validate_json(brut)
    except ValidationError as e:
        raise ValueError(f"message de voix invalide : {e.errors()[0].get('msg')}") from e


def verifier_bloc_page(donnees: bytes) -> bytes:
    """Un bloc de micro reçu d'une page : exactement 20 ms à 16 kHz, en s16le."""
    if len(donnees) != TAILLE_BLOC_OCTETS:
        raise ValueError(f"bloc de {len(donnees)} octets, attendu {TAILLE_BLOC_OCTETS}")
    return donnees

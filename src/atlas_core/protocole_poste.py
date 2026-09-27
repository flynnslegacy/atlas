"""Messages échangés entre le poste (le programme du Mac de David) et le Core, sur /ws/poste.

Le poste et le Core se prouvent l'un à l'autre qu'ils connaissent `ATLAS_POSTE_CLE`, sans
jamais l'envoyer : le poste se présente avec un nonce (`BonjourPoste`), le Core prouve la clé
sur ce nonce et lance le sien (`DefiPoste`), le poste prouve la clé à son tour
(`ReponsePoste`), et le Core l'accepte (`PretPoste`). Chaque action, et chaque résultat,
porte ensuite la preuve de la clé de la session : un appareil qui répondrait à l'adresse du
Core n'obtient ni la clé ni un geste, et un intrus sur le réseau n'en glisse aucun.

Les gestes sont fermés : chacun est vérifié ici, et le poste comme le Core passent par ces
modèles, si bien qu'aucun geste hors de cette liste n'est jamais exécuté.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    Field,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)

MOTIF_NONCE = r"^[0-9a-f]{32}$"
MOTIF_PREUVE = r"^[0-9a-f]{64}$"
TEXTE_MAX = 2_000
QUANTITE_MAX = 20
COORDONNEE_MAX = 10_000
# Une app par son simple nom : ni chemin (« / »), ni option (« - » en tête), ni « . » en tête.
MOTIF_APP = r"^[^-./\\\x00-\x1f][^/\\\x00-\x1f]{0,79}$"
# Une page web, et rien d'autre : ni fichier, ni script, ni espace.
MOTIF_ADRESSE = r"^https?://\S+$"
MODIFICATEURS = ("cmd", "maj", "alt", "ctrl")
TOUCHES_NOMMEES = (
    "entrée",
    "tab",
    "échap",
    "espace",
    "effacer",
    "haut",
    "bas",
    "gauche",
    "droite",
    "début",
    "fin",
    "page haut",
    "page bas",
)


def verifier_touches(touches: str) -> str:
    """« cmd+maj+t » : des modificateurs distincts, puis une touche (une lettre, un chiffre,
    ou une touche nommée). Rend la combinaison normalisée ; sinon `ValueError`."""
    parties = [partie.strip() for partie in touches.lower().split("+")]
    *modificateurs, touche = parties
    touche_permise = touche in TOUCHES_NOMMEES or (
        len(touche) == 1 and (touche.isascii() and touche.isalnum())
    )
    if (
        not touche_permise
        or any(m not in MODIFICATEURS for m in modificateurs)
        or len(set(modificateurs)) != len(modificateurs)
    ):
        raise ValueError(
            f"« {touches} » n'est pas une combinaison permise : cmd, maj, alt ou ctrl, puis une "
            "lettre, un chiffre ou une touche nommée (entrée, tab, échap, les flèches…)."
        )
    return "+".join([*modificateurs, touche])


# --- les gestes ---------------------------------------------------------------------


class Ouvrir(BaseModel):
    """Une app par son nom, ou une page web : l'un ou l'autre."""

    nom: Literal["ouvrir"] = "ouvrir"
    app: str | None = Field(default=None, pattern=MOTIF_APP)
    adresse: str | None = Field(default=None, pattern=MOTIF_ADRESSE, max_length=TEXTE_MAX)

    @model_validator(mode="after")
    def _l_un_ou_l_autre(self) -> Ouvrir:
        if (self.app is None) == (self.adresse is None):
            raise ValueError("ouvrir demande une app ou une adresse, pas les deux")
        return self


class Capturer(BaseModel):
    nom: Literal["capturer"] = "capturer"


class Cliquer(BaseModel):
    """Un point de la dernière capture, en pixels, depuis son coin haut gauche."""

    nom: Literal["cliquer"] = "cliquer"
    x: int = Field(ge=0, le=COORDONNEE_MAX)
    y: int = Field(ge=0, le=COORDONNEE_MAX)
    bouton: Literal["gauche", "droit"] = "gauche"
    double: bool = False


class Taper(BaseModel):
    nom: Literal["taper"] = "taper"
    texte: str = Field(min_length=1, max_length=TEXTE_MAX)


class Touches(BaseModel):
    nom: Literal["touches"] = "touches"
    touches: str

    @field_validator("touches")
    @classmethod
    def _permises(cls, touches: str) -> str:
        return verifier_touches(touches)


class Defiler(BaseModel):
    nom: Literal["defiler"] = "defiler"
    sens: Literal["haut", "bas"]
    quantite: int = Field(ge=1, le=QUANTITE_MAX)


Geste = Annotated[
    Ouvrir | Capturer | Cliquer | Taper | Touches | Defiler, Field(discriminator="nom")
]


# --- Core vers poste ----------------------------------------------------------------


class DefiPoste(BaseModel):
    """Le Core prouve qu'il connaît la clé, sur le nonce du poste, et lance son propre nonce."""

    type: Literal["defi"] = "defi"
    nonce: str = Field(pattern=MOTIF_NONCE)
    preuve: str = Field(pattern=MOTIF_PREUVE)


class PretPoste(BaseModel):
    """La preuve du poste est acceptée : il attend ses actions."""

    type: Literal["pret"] = "pret"


class ActionPoste(BaseModel):
    type: Literal["action"] = "action"
    id: int
    geste: Geste
    preuve: str = ""  # la preuve de la session (`signer`)


# --- poste vers Core ----------------------------------------------------------------


class BonjourPoste(BaseModel):
    """Le premier message du poste : un nonce, jamais la clé."""

    type: Literal["bonjour"] = "bonjour"
    nonce: str = Field(pattern=MOTIF_NONCE)


class ReponsePoste(BaseModel):
    """Le poste prouve qu'il connaît la clé, sur les deux nonces."""

    type: Literal["reponse"] = "reponse"
    preuve: str = Field(pattern=MOTIF_PREUVE)


class ResultatPoste(BaseModel):
    """La réponse à une action : réussie ou non (`erreur` dit pourquoi) ; une capture porte
    son image (JPEG en base64) et sa taille en pixels."""

    type: Literal["resultat"] = "resultat"
    id: int
    ok: bool
    erreur: str | None = None
    image: str | None = None
    largeur: int | None = None
    hauteur: int | None = None
    preuve: str = ""  # la preuve de la session (`signer`)


MessagePoste = Annotated[BonjourPoste | ReponsePoste | ResultatPoste, Field(discriminator="type")]
MessageVersPoste = Annotated[DefiPoste | PretPoste | ActionPoste, Field(discriminator="type")]


# --- les preuves ----------------------------------------------------------------------


def nouveau_nonce() -> str:
    return secrets.token_hex(16)


def _preuve(cle: str, *parties: str) -> str:
    return hmac.new(cle.encode(), "|".join(parties).encode(), hashlib.sha256).hexdigest()


def preuve_du_core(cle: str, nonce_poste: str, nonce_core: str) -> str:
    return _preuve(cle, "core", nonce_poste, nonce_core)


def preuve_du_poste(cle: str, nonce_poste: str, nonce_core: str) -> str:
    return _preuve(cle, "poste", nonce_poste, nonce_core)


def cle_de_session(cle: str, nonce_poste: str, nonce_core: str) -> str:
    """La clé qui signe les actions et les résultats d'une connexion, et d'elle seule."""
    return _preuve(cle, "session", nonce_poste, nonce_core)


def preuve_valide(attendue: str, recue: str) -> bool:
    return hmac.compare_digest(attendue.encode(), recue.encode())


def signer[M: (ActionPoste, ResultatPoste)](session: str, message: M) -> M:
    return message.model_copy(update={"preuve": _preuve(session, _contenu(message))})


def est_signe(session: str, message: ActionPoste | ResultatPoste) -> bool:
    return preuve_valide(_preuve(session, _contenu(message)), message.preuve)


def _contenu(message: ActionPoste | ResultatPoste) -> str:
    return message.model_dump_json(exclude={"preuve"})


_adaptateur_poste = TypeAdapter(MessagePoste)
_adaptateur_vers_poste = TypeAdapter(MessageVersPoste)


def _decoder(adaptateur: TypeAdapter, brut: str):
    try:
        return adaptateur.validate_json(brut)
    except ValidationError as e:
        premiere = e.errors()[0]
        raise ValueError(str(premiere.get("msg", "message invalide"))) from e


def decoder_message_poste(brut: str) -> MessagePoste:
    """Un message du poste. Lève ValueError si le message n'est pas permis."""
    return _decoder(_adaptateur_poste, brut)


def decoder_message_vers_poste(brut: str) -> MessageVersPoste:
    """Un message du Core, lu par le poste. Lève ValueError si le geste n'est pas permis."""
    return _decoder(_adaptateur_vers_poste, brut)

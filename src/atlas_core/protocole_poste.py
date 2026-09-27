"""Messages échangés entre le poste (le programme du Mac de David) et le Core, sur /ws/poste.

Le poste se présente (`BonjourPoste`, avec sa clé), le Core l'accepte (`PretPoste`), puis
lui envoie des actions ; le poste répond à chacune par un `ResultatPoste` du même `id`. Les
gestes sont fermés : chacun est vérifié ici, et le poste comme le Core passent par ces
modèles, si bien qu'aucun geste hors de cette liste n'est jamais exécuté.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    Field,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)

TAILLE_MAX_CLE = 256
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


class PretPoste(BaseModel):
    """La clé est acceptée : le poste attend ses actions."""

    type: Literal["pret"] = "pret"


class ActionPoste(BaseModel):
    type: Literal["action"] = "action"
    id: int
    geste: Geste


# --- poste vers Core ----------------------------------------------------------------


class BonjourPoste(BaseModel):
    """Le premier message du poste : il porte `ATLAS_POSTE_CLE`, sans laquelle le Core
    ferme la connexion."""

    type: Literal["bonjour"] = "bonjour"
    cle: str = Field(max_length=TAILLE_MAX_CLE)


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


MessagePoste = Annotated[BonjourPoste | ResultatPoste, Field(discriminator="type")]
MessageVersPoste = Annotated[PretPoste | ActionPoste, Field(discriminator="type")]
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

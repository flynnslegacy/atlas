"""Le contrat d'un connecteur (spec des connecteurs, §4) : son manifeste, et ce qu'importe
son code.

Un connecteur est un dossier. Son manifeste, `connecteur.toml`, se lit sans exécuter aucun
code : son nom, sa description, sa version, son auteur, la version du contrat (`api`), ses
dépendances, les services du Core qu'il utilise, ses consignes pour Claude, et ses réglages
(des variables du `.env`). Son code, `connecteur.py`, définit `creer(contexte)`, qui rend un
`Connecteur` et ses outils ; le Core les enrobe comme ceux du socle (outils.py) : annonces,
confirmations, refus pendant le résumé, et jamais une panne d'Atlas.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .confirmation import Action
from .outils import Capture, ErreurConnecteur, Fait, Niveau, Outil

if TYPE_CHECKING:
    from .outils_poste import Missions
    from .poste import Poste

__all__ = [
    "Action",
    "Capture",
    "Connecteur",
    "Contexte",
    "ErreurConnecteur",
    "Fait",
    "Manifeste",
    "Niveau",
    "Outil",
    "Reglage",
    "distribution",
    "lire_manifeste",
]

API = 1
FICHIER_MANIFESTE = "connecteur.toml"
MOTIF_ID = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
ID_MAX = 40
MOTIF_OUTIL = r"^[a-z][a-z0-9_]{0,63}$"
MOTIF_VARIABLE = r"^ATLAS_[A-Z0-9_]{1,60}$"
# Une exigence pip : un nom de distribution, des extras et des versions au besoin. Jamais une
# option (« --index-url … ») ni une adresse : `make install` la passe telle quelle à uv.
MOTIF_DEPENDANCE = (
    r"^[A-Za-z0-9][A-Za-z0-9._-]*"  # le nom de distribution
    r"(?:\[[A-Za-z0-9._, -]+\])?"  # des extras
    r"(?:\s*[<>=!~]=?\s*[A-Za-z0-9.*+_-]+\s*,?)*$"  # des versions
)
_DISTRIBUTION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")

Dependance = Annotated[str, Field(pattern=MOTIF_DEPENDANCE, max_length=100)]


class Reglage(BaseModel):
    """Une variable du `.env` du Core dont le connecteur a besoin."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    variable: str = Field(pattern=MOTIF_VARIABLE)
    description: str = Field(min_length=1, max_length=200)
    secret: bool = False


class Manifeste(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    nom: str = Field(min_length=1, max_length=60)
    description: str = Field(min_length=1, max_length=300)
    version: str = Field(min_length=1, max_length=20)
    auteur: str = Field(min_length=1, max_length=60)
    api: int
    dependances: tuple[Dependance, ...] = ()
    services: tuple[Literal["poste"], ...] = ()
    consignes: str = Field(default="", max_length=4000)
    reglages: tuple[Reglage, ...] = ()

    @field_validator("api")
    @classmethod
    def _contrat_connu(cls, api: int) -> int:
        if api != API:
            raise ValueError(f"contrat inconnu : api {api} (Atlas connaît api {API})")
        return api


def lire_manifeste(dossier: Path) -> Manifeste:
    """Le manifeste d'un dossier de connecteur ; `ValueError`, avec une raison lisible, s'il
    manque ou ne convient pas. Aucun code du connecteur n'est exécuté."""
    chemin = dossier / FICHIER_MANIFESTE
    try:
        donnees = tomllib.loads(chemin.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(f"{FICHIER_MANIFESTE} absent") from None
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
        raise ValueError(f"{FICHIER_MANIFESTE} illisible : {e}") from None
    try:
        return Manifeste.model_validate(donnees)
    except ValidationError as e:
        premiere = e.errors()[0]
        lieu = ".".join(str(partie) for partie in premiere["loc"])
        message = str(premiere["msg"]).removeprefix("Value error, ")
        raise ValueError(f"{FICHIER_MANIFESTE}, {lieu} : {message}") from None


def distribution(exigence: str) -> str:
    """Le nom de distribution d'une exigence pip : « caldav>=1.4 » → « caldav »."""
    trouve = _DISTRIBUTION.match(exigence)
    return trouve.group(0) if trouve else exigence


@dataclass(frozen=True)
class Contexte:
    """Ce que le Core donne à un connecteur : ses réglages (les seules variables de son
    manifeste, lues dans l'environnement du Core), et les services qu'il a déclarés — pour
    `poste`, le lien avec le Mac et les missions."""

    reglages: dict[str, str]
    poste: Poste | None = None
    missions: Missions | None = None


class Connecteur:
    """Un connecteur chargé : ses outils. Le Core le prévient au fil de la conversation ;
    par défaut, il n'en fait rien."""

    def outils(self) -> list[Outil]:
        raise NotImplementedError

    def fin_du_tour(self, arretee: bool) -> None:
        """La réponse de Claude est finie ; `arretee` : David l'a coupée."""

    def nouvelle_phrase(self) -> None:
        """David vient de parler."""

    def nouvelle_conversation(self) -> None:
        """La conversation se termine ; la suivante repartira de zéro."""

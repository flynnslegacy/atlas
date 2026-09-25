"""Messages échangés entre le Core et les pages web, sur la connexion /ws/web.

`Etat` et `Erreur` viennent du protocole audio, à l'identique : une page et le
client audio lisent les mêmes.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, TypeAdapter, ValidationError, field_validator

LONGUEUR_MAX_SAISIE = 1000
TAILLE_MAX_CLE = 256
# L'identifiant qu'une page tire au hasard à son ouverture, le même sur /ws/web et sur
# /ws/voix : une question tapée trouve ainsi la voix de sa page.
MOTIF_PAGE = r"^[A-Za-z0-9_-]{1,64}$"
# Le panneau « Documents » ne lit que des documents : jamais une fiche ni le journal.
MOTIF_DOCUMENT = r"^documents/[a-z0-9]+(?:-[a-z0-9]+)*\.md$"
CHEMIN_DOCUMENT_MAX = len("documents/") + 60 + len(".md")  # un nom : 60 au plus (memoire.py)

Source = Literal["voix", "clavier"]


# --- Core vers page -----------------------------------------------------


class Niveau(BaseModel):
    type: Literal["niveau"] = "niveau"
    valeur: float = Field(ge=0.0, le=1.0)


class Question(BaseModel):
    type: Literal["question"] = "question"
    texte: str
    source: Source


class Reponse(BaseModel):
    type: Literal["reponse"] = "reponse"
    texte: str


class Latences(BaseModel):
    type: Literal["latences"] = "latences"
    transcription_ms: int | None = None
    reflexion_ms: int | None = None
    premiere_voix_ms: int | None = None


class Muet(BaseModel):
    """Dans les deux sens : la page le demande, le Core le confirme à toutes les pages."""

    type: Literal["muet"] = "muet"
    actif: bool


class Echange(BaseModel):
    heure: str
    source: Source
    question: str
    reponse: str = ""
    erreur: str | None = None
    latences: Latences | None = None


class Historique(BaseModel):
    type: Literal["historique"] = "historique"
    echanges: list[Echange]


class ResumeDocument(BaseModel):
    chemin: str
    titre: str
    resume: str
    modifie: str  # « 25 septembre 2026, 21 h 14 »


class ListeDocuments(BaseModel):
    """Les documents, du plus récent au plus ancien ; `disponible` est faux sans mémoire."""

    type: Literal["liste_documents"] = "liste_documents"
    disponible: bool = True
    documents: list[ResumeDocument] = []


class Document(BaseModel):
    type: Literal["document"] = "document"
    chemin: str
    titre: str = ""
    contenu: str = ""
    erreur: str | None = None


class DocumentsChanges(BaseModel):
    """À toutes les pages : un document a été écrit, supprimé ou remis."""

    type: Literal["documents_changes"] = "documents_changes"


class AttenteConfirmation(BaseModel):
    """À toutes les pages : Atlas attend le « oui » de David ; `texte` est la question."""

    type: Literal["confirmation"] = "confirmation"
    texte: str


class FinConfirmation(BaseModel):
    """À toutes les pages : l'attente est finie ; `texte` dit comment."""

    type: Literal["confirmation_finie"] = "confirmation_finie"
    texte: str


# --- page vers Core -----------------------------------------------------


class Authentification(BaseModel):
    type: Literal["authentification"] = "authentification"
    cle: str = Field(max_length=TAILLE_MAX_CLE)
    page: str | None = Field(default=None, pattern=MOTIF_PAGE)


class Saisie(BaseModel):
    type: Literal["saisie"] = "saisie"
    texte: str

    @field_validator("texte")
    @classmethod
    def _longueur(cls, texte: str) -> str:
        texte = texte.strip()
        if not 1 <= len(texte) <= LONGUEUR_MAX_SAISIE:
            raise ValueError(f"la question doit faire entre 1 et {LONGUEUR_MAX_SAISIE} caractères")
        return texte


class DemandeDocuments(BaseModel):
    type: Literal["documents"] = "documents"


class LireDocument(BaseModel):
    type: Literal["lire_document"] = "lire_document"
    chemin: str = Field(pattern=MOTIF_DOCUMENT, max_length=CHEMIN_DOCUMENT_MAX)


class Confirmer(BaseModel):
    """Les boutons « Confirmer » et « Annuler » : comme taper « oui » ou « non »."""

    type: Literal["confirmer"] = "confirmer"
    oui: bool


MessagePage = Annotated[
    Authentification | Saisie | Muet | DemandeDocuments | LireDocument | Confirmer,
    Field(discriminator="type"),
]
_adaptateur_page = TypeAdapter(MessagePage)


def decoder_message_page(brut: str) -> MessagePage:
    """Décode un message de page. Lève ValueError, avec un message que la page peut afficher."""
    try:
        return _adaptateur_page.validate_json(brut)
    except ValidationError as e:
        premiere = e.errors()[0]
        message = str(premiere.get("msg", "message invalide")).removeprefix("Value error, ")
        raise ValueError(message) from e

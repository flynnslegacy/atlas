"""Rendre un texte prononçable, et reconnaître ce que Whisper invente.

Tout ce qu'Atlas écrit est dit à voix haute : les consignes interdisent déjà la mise en
forme, ce filtre est un filet. Et sur un bruit bref, Whisper produit parfois une phrase
fantôme (« Merci. », « Sous-titres réalisés par… ») : mieux vaut ne rien entendre que
répondre à un fantôme.
"""

from __future__ import annotations

import re

_LIEN_MARKDOWN = re.compile(r"\[([^\]]+)\]\([^)\s]*\)")
# Une adresse finit sur autre chose qu'une ponctuation : le point de la phrase reste.
_ADRESSE_WEB = re.compile(r"(?:https?://|www\.)\S*[^\s.,;:!?)»]", re.IGNORECASE)
_TITRE = re.compile(r"^[ \t]*#{1,6}[ \t]*", re.MULTILINE)
_PUCE = re.compile(r"^[ \t]*(?:[-*•+–]|\d{1,2}[.)])[ \t]+", re.MULTILINE)
_BLANCS = re.compile(r"\s+")


def nettoyer(texte: str) -> str:
    """Le texte sans mise en forme : ni astérisques, ni dièses de titre, ni puces, ni
    accents graves, et toute adresse web devient « un lien »."""
    texte = _LIEN_MARKDOWN.sub(r"\1", texte)
    texte = _ADRESSE_WEB.sub("un lien", texte)
    texte = _TITRE.sub("", texte)
    texte = _PUCE.sub("", texte)
    texte = texte.replace("*", "").replace("`", "")
    return _BLANCS.sub(" ", texte).strip()


# Phrases fantômes connues de Whisper, une fois normalisées (voir `_normaliser`).
_FANTOMES = {
    "",
    "merci",
    "merci beaucoup",
    "merci à tous",
    "merci de votre attention",
    "musique",
    "applaudissements",
    "rires",
}
_DEBUTS_FANTOMES = (
    "sous-titres réalisés par",
    "sous-titrage",
    "sous-titres par",
    "merci d'avoir regardé",
    "abonnez-vous",
    "n'oubliez pas de vous abonner",
)
_PONCTUATION = re.compile(r"[^\w\s'-]")


def _normaliser(texte: str) -> str:
    texte = texte.lower().replace("'", "'")
    texte = _PONCTUATION.sub(" ", texte)
    return _BLANCS.sub(" ", texte).strip()


def est_hallucination(texte: str) -> bool:
    """Vrai si la transcription n'est qu'une phrase fantôme de Whisper (ou rien du tout)."""
    normal = _normaliser(texte)
    return normal in _FANTOMES or normal.startswith(_DEBUTS_FANTOMES)

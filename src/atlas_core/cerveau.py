"""L'interface du cerveau, et le cerveau de la phase 1 : des réponses figées.

Claude est branché en phase 2 (`cerveau_claude.py`). Le bouchon reste : il valide la
chaîne audio seule — si la voix ne marche pas, on veut le savoir sans avoir à déboguer
un LLM en même temps — et fait tourner Atlas sans Claude (`ATLAS_CERVEAU=bouchon`).
"""

from __future__ import annotations

import asyncio
import datetime as dt
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Protocol

_UNITES = {
    0: "zéro",
    1: "une",
    2: "deux",
    3: "trois",
    4: "quatre",
    5: "cinq",
    6: "six",
    7: "sept",
    8: "huit",
    9: "neuf",
    10: "dix",
    11: "onze",
    12: "douze",
    13: "treize",
    14: "quatorze",
    15: "quinze",
    16: "seize",
    17: "dix-sept",
    18: "dix-huit",
    19: "dix-neuf",
    20: "vingt",
    30: "trente",
    40: "quarante",
    50: "cinquante",
}


def en_lettres(n: int) -> str:
    """Nombres de 0 à 59 en toutes lettres — le TTS lit mieux les mots que les chiffres."""
    if n in _UNITES:
        return _UNITES[n]
    dizaine, unite = divmod(n, 10)
    base = _UNITES[dizaine * 10]
    if unite == 1:
        return f"{base} et une"
    return f"{base}-{_UNITES[unite]}"


def dire_heure(h: int, m: int) -> str:
    """« Il est une heure cinq. », « Il est minuit. », « Il est midi dix. »…"""
    if h == 0:
        heure = "minuit"
    elif h == 12:
        heure = "midi"
    elif h == 1:
        heure = "une heure"
    else:
        heure = f"{en_lettres(h)} heures"
    minutes = f" {en_lettres(m)}" if m else ""
    return f"Il est {heure}{minutes}."


def _heure_actuelle() -> tuple[int, int]:
    # Une seule lecture : deux appels à now() autour d'un changement d'heure
    # donneraient l'heure d'avant avec les minutes d'après.
    maintenant = dt.datetime.now()
    return maintenant.hour, maintenant.minute


@dataclass(frozen=True)
class Recherche:
    """Dans le flux d'une réponse : le cerveau commence une recherche sur le web."""


RECHERCHE = Recherche()


@dataclass(frozen=True)
class Note:
    """Dans le flux d'une réponse : Atlas vient d'écrire dans sa mémoire ; `annonce` est la
    phrase à dire (« Je le note dans la fiche Paul Durand. »)."""

    annonce: str


@dataclass(frozen=True)
class Confirmation(Note):
    """Dans le flux d'une réponse : Atlas demande à David de confirmer une action (N3) ;
    `annonce` est la question (« Je supprime le document X. Tu confirmes ? »), dite comme
    une note."""


class ErreurCerveau(Exception):
    """Le cerveau n'a pas pu répondre. Le message est en français, prêt à être dit."""


class Cerveau(Protocol):
    def repondre(self, texte: str) -> AsyncIterator[str | Recherche | Note]:
        """Rend la réponse en fragments de texte, au fil de l'eau ; signale une recherche
        sur le web par `RECHERCHE`, et une écriture dans la mémoire par une `Note`. Lève
        `ErreurCerveau` si la réponse est impossible.

        Fermer le flux avant la fin (`aclose`) abandonne la réponse."""
        ...

    async def fermer(self) -> None:
        """Arrêt du Core : le cerveau libère ce qu'il tient."""
        ...


class CerveauBouchon:
    def __init__(self, heure: Callable[[], tuple[int, int]] | None = None) -> None:
        self._heure = heure or _heure_actuelle

    async def repondre(self, texte: str) -> AsyncIterator[str]:
        demande = texte.lower()
        if "heure" in demande:
            phrase = dire_heure(*self._heure())
        elif "bonjour" in demande or "salut" in demande:
            phrase = "Bonjour David. Je t'écoute."
        else:
            phrase = (
                "Je n'ai pas encore de cerveau, on est en phase un. Demande-moi l'heure, pour voir."
            )

        # On rend mot à mot pour que le découpage en phrases soit réellement exercé.
        for mot in phrase.split(" "):
            yield mot + " "
            await asyncio.sleep(0)

    async def fermer(self) -> None:
        """Rien à libérer."""

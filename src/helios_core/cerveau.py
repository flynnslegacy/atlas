"""Le cerveau de la phase 1 : des réponses figées.

Claude arrive en phase 2. Ce bouchon existe pour valider la chaîne audio seule —
si la voix ne marche pas, on veut le savoir sans avoir à déboguer un LLM en même temps.
"""

from __future__ import annotations

import asyncio
import datetime as dt
from collections.abc import AsyncIterator, Callable
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


class Cerveau(Protocol):
    def repondre(self, texte: str) -> AsyncIterator[str]:
        """Rend la réponse en fragments, au fil de l'eau."""
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

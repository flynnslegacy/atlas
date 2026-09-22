"""Découpage d'un flux de texte français en phrases prononçables.

Le cerveau écrit au fil de l'eau ; on veut envoyer chaque phrase au TTS dès
qu'elle est complète, sans couper au milieu d'une abréviation ou d'un nombre.
"""

from __future__ import annotations

import re

_FINS = ".!?"

# Abréviations françaises courantes après lesquelles un point ne finit pas la phrase.
_ABREVIATIONS = {
    "m",
    "mm",
    "mme",
    "mlle",
    "dr",
    "pr",
    "st",
    "ste",
    "av",
    "bd",
    "cf",
    "ex",
    "etc",
    "env",
    "art",
    "fig",
    "p",
    "pp",
    "vol",
    "no",
    "n°",
}

_MOT_FINAL = re.compile(r"([A-Za-zÀ-ÿ°]+)\.$")


class DecoupeurPhrases:
    """Accumule du texte et rend les phrases au fur et à mesure."""

    def __init__(self) -> None:
        self._tampon = ""

    def ajouter(self, fragment: str) -> list[str]:
        """Ajoute un fragment et rend les phrases devenues complètes."""
        self._tampon += fragment
        phrases: list[str] = []
        while True:
            coupe = self._trouver_coupe()
            if coupe is None:
                break
            phrases.append(self._tampon[:coupe].strip())
            self._tampon = self._tampon[coupe:].lstrip()
        return [p for p in phrases if p]

    def vider(self) -> list[str]:
        """Rend ce qui reste en fin de génération."""
        reste = self._tampon.strip()
        self._tampon = ""
        return [reste] if reste else []

    def _trouver_coupe(self) -> int | None:
        """Position juste après la ponctuation finale, ou None.

        Utilise une boucle while indexée pour sauter les séries de
        ponctuation identiques (« ... », « !! »), évitant la re-visite.
        """
        i, n = 0, len(self._tampon)
        while i < n:
            c = self._tampon[i]
            if c not in _FINS:
                i += 1
                continue
            fin = i + 1
            while fin < n and self._tampon[fin] == c:
                fin += 1
            if fin - i > 1:  # série : « ... », « !! »
                if self._suit_une_nouvelle_phrase(fin):
                    return fin
                i = fin
                continue
            if self._est_une_decimale(i) or self._est_une_abreviation(fin):
                i = fin
                continue
            if fin < n and not self._tampon[fin].isspace():
                i = fin
                continue  # ponctuation collée à la suite : on attend
            return fin
        return None

    def _est_une_decimale(self, i: int) -> bool:
        """Vérifie si le point est dans un nombre décimal."""
        avant = self._tampon[i - 1] if i > 0 else ""
        apres = self._tampon[i + 1] if i + 1 < len(self._tampon) else ""
        return avant.isdigit() and apres.isdigit()

    def _est_une_abreviation(self, fin: int) -> bool:
        """Vérifie si le mot avant le point est une abréviation connue."""
        m = _MOT_FINAL.search(self._tampon[:fin])
        return bool(m) and m.group(1).lower() in _ABREVIATIONS

    def _suit_une_nouvelle_phrase(self, fin: int) -> bool:
        """Vérifie si une nouvelle phrase majuscule commence après la position."""
        reste = self._tampon[fin:]
        if not reste:
            return True
        if not reste[0].isspace():
            return False
        suite = reste.lstrip()
        return bool(suite) and suite[0].isupper()

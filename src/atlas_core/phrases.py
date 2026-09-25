"""Découpage d'un flux de texte français en phrases prononçables.

Le cerveau écrit au fil des mots ; on veut envoyer chaque phrase au TTS dès qu'elle
est complète, sans couper au milieu d'une abréviation ou d'un nombre. Une ponctuation
qui termine le texte reçu ne suffit pas : « 3. » peut devenir « 3.5 », « M. » devenir
« M. Dupont ». On attend donc le caractère suivant, sauf quand le flux est fini
(`vider`). Une phrase trop longue est coupée avant la limite : le premier son arrive
plus vite, et la synthèse n'est jamais débordée.
"""

from __future__ import annotations

import re

_FINS = ".!?…"
LIMITE = 250  # caractères au plus par phrase envoyée au TTS (qui en accepte 1 000)

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
# Une coupe douce, pour une phrase trop longue : virgule, point-virgule ou deux-points
# suivis d'une espace (« 3,5 » n'en est pas une).
_COUPE_DOUCE = re.compile(r"[,;:](?=\s)")
_ESPACE = re.compile(r"\s")


class DecoupeurPhrases:
    """Accumule du texte et rend les phrases au fur et à mesure."""

    def __init__(self, limite: int = LIMITE) -> None:
        self._tampon = ""
        self._limite = limite

    def ajouter(self, fragment: str) -> list[str]:
        """Ajoute un fragment et rend les phrases devenues complètes."""
        self._tampon += fragment
        return self._extraire(final=False)

    def vider(self) -> list[str]:
        """Rend ce qui reste en fin de génération."""
        phrases = self._extraire(final=True)
        reste = self._tampon.strip()
        self._tampon = ""
        if reste:
            phrases.append(reste)
        return phrases

    def _extraire(self, final: bool) -> list[str]:
        phrases: list[str] = []
        while (coupe := self._trouver_coupe(final)) is not None:
            phrase = self._tampon[:coupe].strip()
            self._tampon = self._tampon[coupe:].lstrip()
            if phrase:
                phrases.append(phrase)
        return phrases

    def _trouver_coupe(self, final: bool) -> int | None:
        fin = self._fin_de_phrase(final)
        if fin is not None and fin <= self._limite:
            return fin
        if fin is not None or len(self._tampon) > self._limite:
            return self._coupe_forcee()
        return None

    def _fin_de_phrase(self, final: bool) -> int | None:
        """Position juste après la première ponctuation finale, ou None.

        Une boucle indexée saute d'un coup les séries de ponctuation (« ... », « ?! »).
        """
        texte = self._tampon
        i, n = 0, len(texte)
        while i < n:
            c = texte[i]
            if c not in _FINS:
                i += 1
                continue
            fin = i + 1
            while fin < n and texte[fin] in _FINS:
                fin += 1
            if fin == n and not final:
                return None  # le caractère suivant peut encore tout changer : on attend
            if fin - i > 1 or c == "…":  # série : « ... », « !! », « ?! »
                suite = self._suit_une_nouvelle_phrase(fin, final)
                if suite is None:
                    return None
                if suite:
                    return fin
                i = fin
                continue
            if self._est_une_decimale(i) or self._est_une_abreviation(fin):
                i = fin
                continue
            if self._est_un_numero_de_liste(i):
                i = fin
                continue
            if fin < n and not texte[fin].isspace():
                i = fin
                continue  # ponctuation collée à la suite (« amara.org ») : pas une fin
            return fin
        return None

    def _coupe_forcee(self) -> int:
        """Coupe d'une phrase trop longue : la dernière virgule, le dernier point-virgule
        ou deux-points avant la limite, sinon le dernier espace, sinon la limite."""
        fenetre = self._tampon[: self._limite + 1]
        douces = list(_COUPE_DOUCE.finditer(fenetre))
        if douces:
            return douces[-1].end()
        espaces = [m.start() for m in _ESPACE.finditer(fenetre) if m.start() > 0]
        if espaces:
            return espaces[-1]
        return self._limite

    def _est_une_decimale(self, i: int) -> bool:
        """Le point est-il entre deux chiffres (« 3.5 ») ?"""
        avant = self._tampon[i - 1] if i > 0 else ""
        apres = self._tampon[i + 1] if i + 1 < len(self._tampon) else ""
        return avant.isdigit() and apres.isdigit()

    def _est_une_abreviation(self, fin: int) -> bool:
        """Le mot avant le point est-il une abréviation connue ?"""
        m = _MOT_FINAL.search(self._tampon[:fin])
        return bool(m) and m.group(1).lower() in _ABREVIATIONS

    def _est_un_numero_de_liste(self, i: int) -> bool:
        """« 1. » en début de ligne numérote une liste : ce n'est pas une fin de phrase."""
        debut = i
        while debut > 0 and self._tampon[debut - 1].isdigit():
            debut -= 1
        if not 1 <= i - debut <= 2:
            return False
        avant = self._tampon[:debut].rstrip(" \t")
        return avant == "" or avant.endswith("\n")

    def _suit_une_nouvelle_phrase(self, fin: int, final: bool) -> bool | None:
        """Après une série, une majuscule ouvre une nouvelle phrase. None : on ne sait
        pas encore, le texte reçu s'arrête avant."""
        reste = self._tampon[fin:]
        if reste and not reste[0].isspace():
            return False
        suite = reste.lstrip()
        if not suite:
            return True if final else None
        return suite[0].isupper()

"""Les événements Quartz du poste (pyobjc, extra `poste`) : les clics, la frappe, le
défilement, la taille de l'écran, et les deux autorisations macOS. Importé seulement sur le
Mac du poste : ni les tests, ni le Core n'en ont besoin.
"""

from __future__ import annotations

# Un morceau de texte par événement clavier, en unités UTF-16 : au-delà, macOS en perd une
# partie.
MORCEAU = 20
# Des lignes de défilement par cran demandé.
LIGNES_PAR_CRAN = 3


def morceaux(texte: str, taille: int = MORCEAU) -> list[str]:
    """Le texte en morceaux d'au plus `taille` unités UTF-16 (un emoji en compte deux), sans
    jamais couper un caractère."""
    parties: list[str] = []
    courant, unites = "", 0
    for caractere in texte:
        largeur = 2 if ord(caractere) > 0xFFFF else 1
        if unites + largeur > taille:
            parties.append(courant)
            courant, unites = "", 0
        courant += caractere
        unites += largeur
    if courant:
        parties.append(courant)
    return parties


class EvenementsQuartz:
    def __init__(self) -> None:
        import Quartz

        self._q = Quartz

    def demander_les_autorisations(self) -> None:
        """Au démarrage du poste : macOS propose d'autoriser l'enregistrement de l'écran et
        l'accessibilité, s'ils manquent."""
        self._q.CGRequestScreenCaptureAccess()
        self._q.CGRequestPostEventAccess()

    def peut_capturer(self) -> bool:
        return bool(self._q.CGPreflightScreenCaptureAccess())

    def peut_agir(self) -> bool:
        return bool(self._q.CGPreflightPostEventAccess())

    def taille_ecran(self) -> tuple[float, float]:
        cadre = self._q.CGDisplayBounds(self._q.CGMainDisplayID())
        return float(cadre.size.width), float(cadre.size.height)

    def _poster(self, evenement) -> None:
        self._q.CGEventPost(self._q.kCGHIDEventTap, evenement)

    def cliquer(self, x: float, y: float, bouton: str, double: bool) -> None:
        q = self._q
        point = q.CGPointMake(x, y)
        if bouton == "droit":
            bas, haut, code = (
                q.kCGEventRightMouseDown,
                q.kCGEventRightMouseUp,
                q.kCGMouseButtonRight,
            )
        else:
            bas, haut, code = q.kCGEventLeftMouseDown, q.kCGEventLeftMouseUp, q.kCGMouseButtonLeft
        self._poster(q.CGEventCreateMouseEvent(None, q.kCGEventMouseMoved, point, code))
        for clic in (1, 2) if double else (1,):
            for type_ in (bas, haut):
                evenement = q.CGEventCreateMouseEvent(None, type_, point, code)
                q.CGEventSetIntegerValueField(evenement, q.kCGMouseEventClickState, clic)
                self._poster(evenement)

    def taper(self, texte: str) -> None:
        q = self._q
        for morceau in morceaux(texte):
            unites = len(morceau.encode("utf-16-le")) // 2
            for appuye in (True, False):
                evenement = q.CGEventCreateKeyboardEvent(None, 0, appuye)
                q.CGEventKeyboardSetUnicodeString(evenement, unites, morceau)
                self._poster(evenement)

    def defiler(self, sens: str, quantite: int) -> None:
        q = self._q
        lignes = quantite * LIGNES_PAR_CRAN * (1 if sens == "haut" else -1)
        self._poster(q.CGEventCreateScrollWheelEvent(None, q.kCGScrollEventUnitLine, 1, lignes))

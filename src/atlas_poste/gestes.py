"""Les gestes du poste, sur macOS : ouvrir, capturer, cliquer, taper, appuyer, défiler.

Chaque geste arrive déjà vérifié (`protocole_poste`) ; ici, il devient une commande macOS
(`open`, `screencapture`, `sips`, `osascript`) ou un événement Quartz (`quartz.py`). Les
commandes et les événements sont injectés : les tests les remplacent par des doublures. Un
geste qui échoue rend son explication, en une phrase ; il ne fait jamais tomber le poste.
"""

from __future__ import annotations

import base64
import logging
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from atlas_core.protocole_poste import (
    ActionPoste,
    Capturer,
    Cliquer,
    Defiler,
    Ouvrir,
    ResultatPoste,
    Taper,
    Touches,
)

_journal = logging.getLogger(__name__)

LARGEUR_CAPTURE = 1280
MODIFICATEURS_APPLESCRIPT = {
    "cmd": "command down",
    "maj": "shift down",
    "alt": "option down",
    "ctrl": "control down",
}
# Les touches nommées, par leur code : la même touche physique sur tous les claviers.
CODES_TOUCHES = {
    "entrée": 36,
    "tab": 48,
    "espace": 49,
    "effacer": 51,
    "échap": 53,
    "gauche": 123,
    "droite": 124,
    "bas": 125,
    "haut": 126,
    "début": 115,
    "fin": 119,
    "page haut": 116,
    "page bas": 121,
}
CAPTURE_INTERDITE = "Autorise l'enregistrement de l'écran pour le poste dans les Réglages."
ACTION_INTERDITE = "Autorise l'accessibilité pour le poste dans les Réglages."
AUTOMATISATION_INTERDITE = (
    "Autorise le poste à contrôler « System Events » dans les Réglages (Automatisation)."
)

Lancer = Callable[[list[str]], subprocess.CompletedProcess]


class Evenements(Protocol):
    """Ce que le poste attend de Quartz (voir `quartz.py`)."""

    def peut_capturer(self) -> bool: ...
    def peut_agir(self) -> bool: ...
    def taille_ecran(self) -> tuple[float, float]: ...
    def cliquer(self, x: float, y: float, bouton: str, double: bool) -> None: ...
    def taper(self, texte: str) -> None: ...
    def defiler(self, sens: str, quantite: int) -> None: ...


class ErreurGeste(Exception):
    """Le geste n'a pas pu se faire ; le message, en français, va à Claude."""


def lancer(commande: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(commande, capture_output=True, text=True, timeout=10, check=False)


def script_des_touches(touches: str) -> str:
    """La combinaison, pour System Events : les lettres et les chiffres par leur caractère
    (System Events connaît la disposition du clavier : sur un AZERTY, le code physique de
    « a » en QWERTY taperait « q »), les touches nommées par leur code."""
    *modificateurs, touche = touches.split("+")
    if touche in CODES_TOUCHES:
        frappe = f"key code {CODES_TOUCHES[touche]}"
    else:
        frappe = f'keystroke "{touche}"'
    if modificateurs:
        frappe += " using {" + ", ".join(MODIFICATEURS_APPLESCRIPT[m] for m in modificateurs) + "}"
    return f'tell application "System Events" to {frappe}'


class Gestes:
    def __init__(self, lancer: Lancer = lancer, evenements: Evenements | None = None) -> None:
        if evenements is None:
            from .quartz import EvenementsQuartz  # seulement sur le Mac du poste

            evenements = EvenementsQuartz()
        self._lancer = lancer
        self._evenements = evenements
        self._derniere: tuple[int, int] | None = None  # la taille de la dernière capture

    def executer(self, action: ActionPoste) -> ResultatPoste:
        geste = action.geste
        try:
            match geste:
                case Ouvrir():
                    self._ouvrir(geste)
                case Capturer():
                    image, largeur, hauteur = self._capturer()
                    return ResultatPoste(
                        id=action.id, ok=True, image=image, largeur=largeur, hauteur=hauteur
                    )
                case Cliquer():
                    self._cliquer(geste)
                case Taper():
                    self._agir()
                    self._evenements.taper(geste.texte)
                case Touches():
                    self._touches(geste)
                case Defiler():
                    self._agir()
                    self._evenements.defiler(geste.sens, geste.quantite)
        except ErreurGeste as e:
            return ResultatPoste(id=action.id, ok=False, erreur=str(e))
        except Exception as e:  # noqa: BLE001 — un geste raté ne fait jamais tomber le poste
            _journal.exception("le geste %s a échoué", geste.nom)
            return ResultatPoste(
                id=action.id, ok=False, erreur=f"Le geste a échoué ({type(e).__name__})."
            )
        return ResultatPoste(id=action.id, ok=True)

    def _ouvrir(self, geste: Ouvrir) -> None:
        commande = ["open", "-a", geste.app] if geste.app else ["open", geste.adresse]
        fait = self._lancer(commande)
        if fait.returncode != 0:
            if geste.app:
                raise ErreurGeste(f"Je ne trouve pas l'app {geste.app}.")
            raise ErreurGeste(f"Je n'arrive pas à ouvrir {geste.adresse}.")

    def _capturer(self) -> tuple[str, int, int]:
        if not self._evenements.peut_capturer():
            raise ErreurGeste(CAPTURE_INTERDITE)
        # Un dossier jetable, effacé aussitôt : aucune capture ne reste sur le disque.
        with tempfile.TemporaryDirectory(prefix="atlas-poste-") as dossier:
            fichier = str(Path(dossier) / "ecran.jpg")
            if self._lancer(["screencapture", "-x", "-t", "jpg", fichier]).returncode != 0:
                raise ErreurGeste("La capture de l'écran a échoué.")
            self._lancer(["sips", "-Z", str(LARGEUR_CAPTURE), fichier])
            taille = self._lancer(["sips", "-g", "pixelWidth", "-g", "pixelHeight", fichier])
            largeur = int(taille.stdout.split("pixelWidth:")[1].split()[0])
            hauteur = int(taille.stdout.split("pixelHeight:")[1].split()[0])
            image = base64.b64encode(Path(fichier).read_bytes()).decode("ascii")
        self._derniere = (largeur, hauteur)
        return image, largeur, hauteur

    def _agir(self) -> None:
        if not self._evenements.peut_agir():
            raise ErreurGeste(ACTION_INTERDITE)

    def _cliquer(self, geste: Cliquer) -> None:
        self._agir()
        if self._derniere is None:
            raise ErreurGeste(
                "Capture l'écran d'abord : un clic vise un point de la dernière capture."
            )
        largeur, hauteur = self._derniere
        if geste.x >= largeur or geste.y >= hauteur:
            raise ErreurGeste("Ce point sort de la dernière capture.")
        # La capture est réduite ; l'écran se compte en points (Retina : deux pixels par point).
        largeur_ecran, hauteur_ecran = self._evenements.taille_ecran()
        x = geste.x * largeur_ecran / largeur
        y = geste.y * hauteur_ecran / hauteur
        self._evenements.cliquer(x, y, geste.bouton, geste.double)

    def _touches(self, geste: Touches) -> None:
        self._agir()
        fait = self._lancer(["osascript", "-e", script_des_touches(geste.touches)])
        if fait.returncode != 0:
            raise ErreurGeste(AUTOMATISATION_INTERDITE)

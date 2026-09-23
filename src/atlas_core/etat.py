"""Machine à états d'un tour de parole."""

from __future__ import annotations

from typing import Literal

Valeur = Literal["repos", "ecoute", "reflexion", "parole"]

_PERMISES: dict[Valeur, set[Valeur]] = {
    "repos": {"ecoute"},
    "ecoute": {"reflexion", "repos"},
    "reflexion": {"parole", "repos"},
    "parole": {"repos", "ecoute"},  # « ecoute » est le chemin de l'interruption
}


class TransitionInterdite(Exception):
    pass


class MachineEtat:
    def __init__(self, depart: Valeur = "repos") -> None:
        self._valeur: Valeur = depart

    @property
    def valeur(self) -> Valeur:
        return self._valeur

    def peut_aller_vers(self, valeur: Valeur) -> bool:
        return valeur in _PERMISES[self._valeur]

    def aller_vers(self, valeur: Valeur) -> None:
        if not self.peut_aller_vers(valeur):
            raise TransitionInterdite(f"{self._valeur} ne mène pas à {valeur}")
        self._valeur = valeur

"""Machine à états d'un tour de parole."""

from __future__ import annotations

from typing import Literal

Valeur = Literal["repos", "ecoute", "reflexion", "parole"]

_PERMISES: dict[Valeur, set[Valeur]] = {
    "repos": {"ecoute", "reflexion"},  # « reflexion » : une question tapée, sans écoute
    "ecoute": {"reflexion", "repos"},
    "reflexion": {"parole", "repos"},
    # « ecoute » est le chemin de l'interruption ; « reflexion », celui d'une recherche web
    # qui commence après la phrase d'attente.
    "parole": {"repos", "ecoute", "reflexion"},
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

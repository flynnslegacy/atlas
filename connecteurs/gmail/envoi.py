"""L'envoi d'un mail, qui attend le « oui » de David (spec de Gmail et de Google Agenda, §6.3).

La question lit les adresses exactes, l'objet et le texte (un long texte jusqu'à 300 caractères,
puis son nombre de mots) : ce que David entend est ce qui part. `executer` ne tourne qu'après le
« oui », hors de la boucle du Core ; un échec dit pourquoi (`ratee`).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import ClassVar

from atlas_core.connecteurs import ErreurConnecteur

from .mails import Brouillon

LU_JUSQU_A = 300


def _rien() -> None:
    pass


def _lu(texte: str) -> str:
    """« Je serai là jeudi. », ou les 300 premiers caractères, puis le nombre de mots."""
    dit = " ".join(texte.split())
    if len(dit) <= LU_JUSQU_A:
        return f"« {dit} »"
    return f"« {dit[:LU_JUSQU_A].rstrip()}… » ({len(dit.split())} mots en tout)"


class Envoi:
    nom: ClassVar[str] = "Envoi"
    poursuivre: ClassVar[bool] = False
    refusee: ClassVar[str] = "D'accord, je n'envoie rien."
    abandonnee: ClassVar[str] = "Je n'envoie rien."
    rien: ClassVar[str] = "rien n'a été envoyé"

    def __init__(
        self,
        brouillon: Brouillon,
        faire: Callable[[], None],
        apres: Callable[[], None] = _rien,
    ) -> None:
        self.brouillon = brouillon
        self._faire = faire
        self.apres = apres
        self._raison: str | None = None

    def executer(self) -> None:
        try:
            self._faire()
        except ErreurConnecteur as e:  # Google ne répond pas, le brouillon a disparu…
            self._raison = str(e)
            raise

    @property
    def _a(self) -> str:
        return ", ".join(self.brouillon.a)

    @property
    def question(self) -> str:
        verbe = "Je réponds à" if self.brouillon.fil else "J'envoie à"
        copie = f", copie à {', '.join(self.brouillon.copie)}" if self.brouillon.copie else ""
        objet = self.brouillon.objet
        return f"{verbe} {self._a}{copie}, objet « {objet} » : {_lu(self.brouillon.texte)} ?"

    @property
    def faite(self) -> str:
        return f"C'est parti : mail envoyé à {self._a}."

    @property
    def ratee(self) -> str:
        return self._raison or "Je n'ai pas pu envoyer le mail."

    @property
    def objet(self) -> str:
        return f"l'envoi du mail « {self.brouillon.objet} »"

    @property
    def bilan(self) -> str:
        return f"le mail « {self.brouillon.objet} » est envoyé à {self._a}"

    @property
    def page_faite(self) -> str:
        return f"Mail envoyé : {self.brouillon.objet}."

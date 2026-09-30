"""Ce qui attend le « oui » de David dans l'agenda (spec de l'agenda et des contacts, §5.5) :
modifier ou supprimer un rendez-vous.

Atlas pose la question ; `executer` ne tourne qu'après le « oui », hors de la boucle du Core,
et `apres`, dans la boucle, une fois l'écriture faite. Un rendez-vous changé entre-temps n'est
pas écrasé ; un échec dit pourquoi à David (`ratee`).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from typing import Any, ClassVar

from atlas_core.connecteurs import ErreurConnecteur

from .agenda import Change, RendezVous
from .dire import heure_dite, jour_court, quand

CETTE_FOIS = " (cette fois seulement)"


def _vers(debut: dt.date, fin: dt.date) -> str:
    """« au vendredi 2 octobre à 20 h », « du lundi 5 octobre au mardi 6 octobre »."""
    moment = quand(debut, fin)
    return moment if moment.startswith("du ") else f"au {moment}"


def _deplacement(avant: RendezVous, debut: dt.date) -> str | None:
    """« , jeudi 1er octobre, de 19 h à 20 h », « du jeudi 1er octobre, 19 h, au vendredi 2
    octobre, 20 h », « du lundi 5 octobre au mardi 6 octobre » ; None quand le rendez-vous
    passe d'une heure à la journée entière, ou l'inverse."""
    ancien = avant.debut
    if isinstance(ancien, dt.datetime) and isinstance(debut, dt.datetime):
        jour = jour_court(ancien.date())
        if ancien.date() == debut.date():
            return f", {jour}, de {heure_dite(ancien)} à {heure_dite(debut)}"
        nouveau = jour_court(debut.date())
        return f" du {jour}, {heure_dite(ancien)}, au {nouveau}, {heure_dite(debut)}"
    if isinstance(ancien, dt.datetime) or isinstance(debut, dt.datetime):
        return None
    return f" du {jour_court(ancien)} au {jour_court(debut)}"


class _SurUnRendezVous:
    """Ce que la modification et la suppression d'un rendez-vous ont en commun."""

    poursuivre: ClassVar[bool] = False
    refusee: ClassVar[str] = "D'accord, je n'y touche pas."
    abandonnee: ClassVar[str] = "Je n'y touche pas."
    _verbe: ClassVar[str]

    def __init__(
        self, rendezvous: RendezVous, faire: Callable[[], None], apres: Callable[[], None]
    ) -> None:
        self.rendezvous = rendezvous
        self._faire = faire
        self.apres = apres
        self._raison: str | None = None

    def executer(self) -> None:
        try:
            self._faire()
        except Change:
            titre = self.rendezvous.titre
            self._raison = f"« {titre} » a changé entre-temps : je n'y ai pas touché."
            raise
        except ErreurConnecteur as e:  # iCloud refuse, ne répond pas, ou l'agenda est fermé
            self._raison = str(e)
            raise

    @property
    def ratee(self) -> str:
        return self._raison or f"Je n'ai pas pu {self._verbe} « {self.rendezvous.titre} »."

    @property
    def _cette_fois(self) -> str:
        return CETTE_FOIS if self.rendezvous.repete else ""


class Modification(_SurUnRendezVous):
    """`changements` : ce qui change (`titre`, `debut` et `fin` ensemble, `lieu`, `notes`)."""

    nom: ClassVar[str] = "Modification"
    rien: ClassVar[str] = "le rendez-vous n'a pas changé"
    _verbe: ClassVar[str] = "changer"

    def __init__(
        self,
        rendezvous: RendezVous,
        changements: dict[str, Any],
        faire: Callable[[], None],
        apres: Callable[[], None],
    ) -> None:
        super().__init__(rendezvous, faire, apres)
        self.changements = changements

    @property
    def _titre(self) -> str:
        return str(self.changements.get("titre", self.rendezvous.titre))

    @property
    def _nouveau_moment(self) -> str | None:
        if "debut" not in self.changements:
            return None
        return _vers(self.changements["debut"], self.changements["fin"])

    @property
    def question(self) -> str:
        avant = self.rendezvous
        if set(self.changements) == {"debut", "fin"}:
            deplacement = _deplacement(avant, self.changements["debut"])
            if deplacement is not None:
                return f"Je déplace « {avant.titre} »{deplacement}{self._cette_fois} ?"
        morceaux = []
        if "titre" in self.changements:
            morceaux.append(f"le titre devient « {self._titre} »")
        if self._nouveau_moment is not None:
            morceaux.append(f"il passe {self._nouveau_moment}")
        if "lieu" in self.changements:
            morceaux.append(f"le lieu devient « {self.changements['lieu']} »")
        if "notes" in self.changements:
            morceaux.append("les notes changent")
        moment = quand(avant.debut, avant.fin)
        return f"Je change « {avant.titre} », {moment} : {' ; '.join(morceaux)}{self._cette_fois} ?"

    @property
    def _ce_qui_est_fait(self) -> str:
        if self._nouveau_moment is not None:
            return f"le rendez-vous « {self._titre} » est déplacé {self._nouveau_moment}"
        return f"le rendez-vous « {self._titre} » est changé"

    @property
    def faite(self) -> str:
        return f"C'est fait : {self._ce_qui_est_fait}."

    @property
    def objet(self) -> str:
        return f"la modification du rendez-vous « {self.rendezvous.titre} »"

    @property
    def bilan(self) -> str:
        return self._ce_qui_est_fait

    @property
    def page_faite(self) -> str:
        return f"Rendez-vous changé : {self._titre}."


class Suppression(_SurUnRendezVous):
    nom: ClassVar[str] = "Suppression"
    rien: ClassVar[str] = "le rendez-vous n'est pas supprimé"
    _verbe: ClassVar[str] = "supprimer"

    @property
    def question(self) -> str:
        avant = self.rendezvous
        return f"Je supprime « {avant.titre} », {quand(avant.debut, avant.fin)}{self._cette_fois} ?"

    @property
    def faite(self) -> str:
        suite = ", cette fois seulement" if self.rendezvous.repete else ""
        return f"C'est fait : {self.bilan}{suite}."

    @property
    def objet(self) -> str:
        return f"la suppression du rendez-vous « {self.rendezvous.titre} »"

    @property
    def bilan(self) -> str:
        return f"le rendez-vous « {self.rendezvous.titre} » est supprimé"

    @property
    def page_faite(self) -> str:
        return f"Rendez-vous supprimé : {self.rendezvous.titre}."

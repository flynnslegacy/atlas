"""Les rendez-vous d'un agenda, quel que soit son serveur (spec de Gmail et de Google Agenda,
D10 ; spec de l'agenda et des contacts, §5) : ce qu'on en sait, ce qu'Atlas en dit, et les
actions qui attendent le « oui » de David. L'agenda iCloud et Google Agenda s'en servent tous
deux, chacun avec son client.

Pour modifier ou supprimer, Atlas pose la question ; `executer` ne tourne qu'après le « oui »,
hors de la boucle du Core, et `apres`, dans la boucle, une fois l'écriture faite. Un rendez-vous
changé entre-temps n'est pas écrasé (`Change`) ; un échec dit pourquoi à David (`ratee`).
"""

from __future__ import annotations

import datetime as dt
import os
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .consignes import date_en_lettres, heure_en_chiffres
from .outils import ErreurConnecteur

JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
CETTE_FOIS = " (cette fois seulement)"


class Change(Exception):
    """Le rendez-vous a changé (ou disparu) depuis sa lecture : rien n'est écrit."""


def fuseau_du_mac() -> dt.tzinfo:
    """Le fuseau du Mac du Core : `TZ` s'il est posé, sinon celui que nomme /etc/localtime."""
    nom = os.environ.get("TZ", "").lstrip(":")
    if not nom:
        cible = str(Path("/etc/localtime").resolve())
        nom = cible.split("zoneinfo/", 1)[1] if "zoneinfo/" in cible else ""
    try:
        return ZoneInfo(nom)
    except (ZoneInfoNotFoundError, ValueError):
        return dt.datetime.now().astimezone().tzinfo or dt.UTC


@dataclass(frozen=True)
class Agenda:
    """Un agenda : son nom, et ce qui le désigne pour son serveur (`cle` : l'adresse CalDAV,
    l'identifiant Google) ; son serveur dit parfois qu'il est en lecture seule, ou principal."""

    nom: str
    cle: str
    lecture_seule: bool = False
    principal: bool = False


def lecture_seule(agenda: Agenda) -> str:
    return f"L'agenda « {agenda.nom} » ne se modifie pas d'ici."


@dataclass(frozen=True)
class RendezVous:
    """Une fois d'un rendez-vous : un événement seul, ou l'une des fois d'une série, que
    désigne `origine` (sa date d'origine dans la série ; None hors série). `evenement` désigne
    l'événement (toutes ses fois) pour son serveur ; `cle`, cette fois-ci, quand le serveur lui
    en donne une (Google). Les heures sont celles du Mac ; une journée entière a des dates, et
    sa `fin` est exclue."""

    agenda: Agenda
    evenement: str
    etag: str
    titre: str
    debut: dt.date  # un dt.datetime pour un rendez-vous à l'heure
    fin: dt.date
    lieu: str = ""
    notes: str = ""
    invites: bool = False
    origine: dt.date | None = None
    annule: bool = False  # une invitation annulée, gardée jusqu'à ce que David la retire
    refuse: bool = False  # une invitation que David a refusée
    cle: str = ""

    @property
    def journee(self) -> bool:
        return not isinstance(self.debut, dt.datetime)

    @property
    def repete(self) -> bool:
        return self.origine is not None


def normaliser(texte: str) -> str:
    """Sans accents ni majuscules : « Réunion » et « reunion » se valent."""
    decompose = unicodedata.normalize("NFKD", texte)
    return "".join(c for c in decompose if not unicodedata.combining(c)).casefold().strip()


def jour_de(moment: dt.date) -> dt.date:
    return moment.date() if isinstance(moment, dt.datetime) else moment


def ordre(rendezvous: RendezVous) -> tuple:
    debut = rendezvous.debut
    minutes = debut.hour * 60 + debut.minute if isinstance(debut, dt.datetime) else -1
    return jour_de(debut), minutes, normaliser(rendezvous.titre)


# Ce qu'Atlas en dit.


def jour_long(jour: dt.date) -> str:
    """« jeudi 2 octobre 2026 »."""
    return f"{JOURS[jour.weekday()]} {date_en_lettres(jour)}"


def jour_court(jour: dt.date) -> str:
    """« jeudi 2 octobre »."""
    return jour_long(jour).removesuffix(f" {jour.year}")


def periode(debut: dt.date, fin: dt.date) -> str:
    """« le jeudi 2 octobre 2026 », « du jeudi 2 octobre 2026 au samedi 4 octobre 2026 »."""
    if debut == fin:
        return f"le {jour_long(debut)}"
    return f"du {jour_long(debut)} au {jour_long(fin)}"


def horaire(rendezvous: RendezVous) -> str:
    """« 15 h 00 – 16 h 00 », « 15 h 00 » (sans fin), « journée entière », « journée entière,
    jusqu'au lundi 6 octobre »."""
    debut, fin = rendezvous.debut, rendezvous.fin
    if rendezvous.journee:
        dernier = fin - dt.timedelta(days=1)
        return (
            "journée entière"
            if dernier <= debut
            else f"journée entière, jusqu'au {jour_court(dernier)}"
        )
    assert isinstance(debut, dt.datetime) and isinstance(fin, dt.datetime)
    if fin == debut:
        return heure_en_chiffres(debut)
    if jour_de(fin) == jour_de(debut):
        return f"{heure_en_chiffres(debut)} – {heure_en_chiffres(fin)}"
    return f"{heure_en_chiffres(debut)} – {jour_court(jour_de(fin))}, {heure_en_chiffres(fin)}"


def ligne(etiquette: str, rendezvous: RendezVous) -> str:
    """« e3 · 15 h 00 – 16 h 00 · Dentiste · Domicile · 12 rue des Lilas »."""
    morceaux = [etiquette, horaire(rendezvous), rendezvous.titre, rendezvous.agenda.nom]
    if rendezvous.lieu:
        morceaux.append(rendezvous.lieu)
    if rendezvous.annule:
        morceaux.append("annulé")
    if rendezvous.refuse:
        morceaux.append("invitation refusée")
    if rendezvous.repete:
        morceaux.append("répété")
    if rendezvous.invites:
        morceaux.append("avec invités")
    return "  " + " · ".join(morceaux)


def heure_dite(moment: dt.datetime) -> str:
    """« 15 h », « 9 h 05 » : pour la voix."""
    return f"{moment.hour} h" if moment.minute == 0 else heure_en_chiffres(moment)


def quand(debut: dt.date, fin: dt.date) -> str:
    """« jeudi 1er octobre à 15 h », « lundi 5 octobre », « du lundi 5 octobre au vendredi 9
    octobre » (une journée entière a sa `fin` exclue)."""
    if isinstance(debut, dt.datetime):
        return f"{jour_court(debut.date())} à {heure_dite(debut)}"
    dernier = fin - dt.timedelta(days=1)
    if dernier <= debut:
        return jour_court(debut)
    return f"du {jour_court(debut)} au {jour_court(dernier)}"


# Ce qui attend le « oui » de David.


def _vers(debut: dt.date, fin: dt.date) -> str:
    """« au vendredi 2 octobre à 20 h », « du lundi 5 octobre au mardi 6 octobre »."""
    moment = quand(debut, fin)
    return moment if moment.startswith("du ") else f"au {moment}"


def _deplace(avant: RendezVous, debut: dt.date, fin: dt.date) -> bool:
    """Le début change et la durée reste : un déplacement."""
    meme_genre = isinstance(debut, dt.datetime) == isinstance(avant.debut, dt.datetime)
    return debut != avant.debut and meme_genre and fin - debut == avant.fin - avant.debut


def _deplacement(avant: RendezVous, debut: dt.date) -> str:
    """« , jeudi 1er octobre, de 19 h à 20 h », « du jeudi 1er octobre, 19 h, au vendredi 2
    octobre, 20 h », « du lundi 5 octobre au mardi 6 octobre » (un déplacement, `_deplace`)."""
    ancien = avant.debut
    if isinstance(ancien, dt.datetime) and isinstance(debut, dt.datetime):
        jour = jour_court(ancien.date())
        if ancien.date() == debut.date():
            return f", {jour}, de {heure_dite(ancien)} à {heure_dite(debut)}"
        nouveau = jour_court(debut.date())
        return f" du {jour}, {heure_dite(ancien)}, au {nouveau}, {heure_dite(debut)}"
    return f" du {jour_court(ancien)} au {jour_court(debut)}"


def _horaire(avant: RendezVous, debut: dt.date, fin: dt.date) -> str:
    """Ce que devient l'horaire, en entier : « il finit à 23 h », « il passe au vendredi 2
    octobre, de 20 h à 23 h », « il passe du lundi 5 octobre au mardi 6 octobre »."""
    a_l_heure = isinstance(debut, dt.datetime) and isinstance(fin, dt.datetime)
    if not a_l_heure or _deplace(avant, debut, fin):  # des jours, ou la même durée
        return f"il passe {_vers(debut, fin)}"
    if debut == avant.debut:
        if fin.date() == debut.date():
            return f"il finit à {heure_dite(fin)}"
        return f"il finit le {jour_court(fin.date())} à {heure_dite(fin)}"
    if fin.date() == debut.date():
        jour = jour_court(debut.date())
        return f"il passe au {jour}, de {heure_dite(debut)} à {heure_dite(fin)}"
    de, a = jour_court(debut.date()), jour_court(fin.date())
    return f"il passe du {de}, {heure_dite(debut)}, au {a}, {heure_dite(fin)}"


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
    def _deplace(self) -> bool:
        if "debut" not in self.changements:
            return False
        return _deplace(self.rendezvous, self.changements["debut"], self.changements["fin"])

    @property
    def _horaire(self) -> str | None:
        if "debut" not in self.changements:
            return None
        return _horaire(self.rendezvous, self.changements["debut"], self.changements["fin"])

    @property
    def question(self) -> str:
        avant = self.rendezvous
        if set(self.changements) == {"debut", "fin"} and self._deplace:
            deplacement = _deplacement(avant, self.changements["debut"])
            return f"Je déplace « {avant.titre} »{deplacement}{self._cette_fois} ?"
        morceaux = []
        if "titre" in self.changements:
            morceaux.append(f"le titre devient « {self._titre} »")
        if self._horaire is not None:
            morceaux.append(self._horaire)
        if "lieu" in self.changements:
            morceaux.append(f"le lieu devient « {self.changements['lieu']} »")
        if "notes" in self.changements:
            morceaux.append("les notes changent")
        moment = quand(avant.debut, avant.fin)
        return f"Je change « {avant.titre} », {moment} : {' ; '.join(morceaux)}{self._cette_fois} ?"

    @property
    def _ce_qui_est_fait(self) -> str:
        if self._deplace:
            vers = _vers(self.changements["debut"], self.changements["fin"])
            return f"le rendez-vous « {self._titre} » est déplacé {vers}"
        if self._horaire is not None:
            return f"le rendez-vous « {self._titre} » est changé : {self._horaire}"
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

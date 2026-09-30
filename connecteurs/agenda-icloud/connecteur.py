"""L'agenda iCloud de David, en connecteur (spec de l'agenda et des contacts, §5) : lire une
période et chercher (N1), ajouter (N2), modifier et supprimer après son « oui » (N3).

Chaque rendez-vous lu reçoit une étiquette (`e1`, `e2`…), que Claude rend pour désigner un
rendez-vous ; chaque fois d'un événement répété a la sienne. Les étiquettes valent pour la
conversation : la suivante les oublie, et relit l'agenda. Un rendez-vous modifié ou supprimé
perd la sienne jusqu'à ce qu'on le relise : ce qu'on en savait n'est plus vrai.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import re
from collections.abc import Callable
from typing import Any

from atlas_core.connecteurs import Connecteur, Contexte, ErreurConnecteur, Fait, Niveau, Outil

from .actions import Modification, Suppression
from .agenda import ADRESSE, DELAI_S, Agenda, Calendrier, RendezVous, jour_de, normaliser
from .dire import jour_long, ligne, periode, quand

MAX_JOURS = 62
MAX_JOURS_CHERCHES = 400
MAX_RENDEZVOUS = 100

LIRE = (
    "Les rendez-vous de l'agenda iCloud de David entre deux dates (debut et fin, AAAA-MM-JJ, "
    "fin comprise, 62 jours au plus), dans tous ses agendas, ou dans celui qu'il nomme "
    "(agenda). Chaque rendez-vous a une étiquette (e1, e2…), qui le désigne pour le modifier "
    "ou le supprimer."
)
_SCHEMA_LIRE = {
    "type": "object",
    "properties": {
        "debut": {"type": "string"},
        "fin": {"type": "string"},
        "agenda": {"type": "string"},
    },
    "required": ["debut", "fin"],
}
CHERCHER = (
    "Cherche dans l'agenda iCloud de David les rendez-vous dont le titre, le lieu ou les notes "
    "contiennent un texte (texte), sans tenir compte des accents ni des majuscules : par défaut "
    "d'un mois en arrière à un an en avant, ou entre debut et fin (AAAA-MM-JJ) ; dans tous ses "
    "agendas, ou dans celui qu'il nomme (agenda)."
)
_SCHEMA_CHERCHER = {
    "type": "object",
    "properties": {
        "texte": {"type": "string"},
        "debut": {"type": "string"},
        "fin": {"type": "string"},
        "agenda": {"type": "string"},
    },
    "required": ["texte"],
}
AJOUTER = (
    "Ajoute un rendez-vous à l'agenda iCloud de David quand il le demande : titre, debut "
    "(AAAA-MM-JJTHH:MM, ou AAAA-MM-JJ pour une journée entière), et au besoin fin (sinon une "
    "heure, ou la journée ; pour une journée entière, le dernier jour), lieu, notes, alerte "
    "(minutes avant le début) et agenda (sinon celui de ses réglages). Atlas l'annonce : ne "
    "l'annonce pas toi-même."
)
_SCHEMA_AJOUTER = {
    "type": "object",
    "properties": {
        "titre": {"type": "string"},
        "debut": {"type": "string"},
        "fin": {"type": "string"},
        "lieu": {"type": "string"},
        "notes": {"type": "string"},
        "alerte": {"type": "integer"},
        "agenda": {"type": "string"},
    },
    "required": ["titre", "debut"],
}
MODIFIER = (
    "Modifie un rendez-vous de l'agenda iCloud de David, désigné par son étiquette (evenement : "
    "e1, e2…, lue par agenda_lire ou agenda_chercher) : un nouveau titre, debut, fin, lieu ou "
    "notes (debut et fin en AAAA-MM-JJTHH:MM, ou AAAA-MM-JJ pour une journée entière ; un "
    "nouveau début sans fin garde la durée). D'un événement répété, seule cette fois change. "
    "Atlas demande à David de confirmer : n'ajoute rien après l'appel."
)
_SCHEMA_MODIFIER = {
    "type": "object",
    "properties": {
        "evenement": {"type": "string"},
        "titre": {"type": "string"},
        "debut": {"type": "string"},
        "fin": {"type": "string"},
        "lieu": {"type": "string"},
        "notes": {"type": "string"},
    },
    "required": ["evenement"],
}
SUPPRIMER = (
    "Supprime un rendez-vous de l'agenda iCloud de David, désigné par son étiquette (evenement : "
    "e1, e2…) ; d'un événement répété, cette fois seulement. Atlas demande à David de "
    "confirmer : n'ajoute rien après l'appel."
)
INVITES = (
    "Ce rendez-vous a des invités : Atlas ne le change pas, pour ne pas leur écrire en ton nom. "
    "Change-le dans Calendrier."
)
RIEN_A_CHANGER = "Dis ce qui change : le titre, le début, la fin, le lieu ou les notes."
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_MOMENT = re.compile(r"\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}(:\d{2})?)?")
_UNE_HEURE = dt.timedelta(hours=1)
_UN_JOUR = dt.timedelta(days=1)


def _date(arguments: dict[str, Any], cle: str, defaut: dt.date | None = None) -> dt.date:
    texte = str(arguments.get(cle) or "").strip()
    if not texte and defaut is not None:
        return defaut
    if _DATE.fullmatch(texte):
        try:
            return dt.date.fromisoformat(texte)
        except ValueError:
            pass
    raise ErreurConnecteur(f"{cle} : une date de la forme AAAA-MM-JJ, par exemple 2026-10-02.")


def _periode(
    arguments: dict[str, Any],
    maximum: int,
    defauts: tuple[dt.date | None, dt.date | None] = (None, None),
) -> tuple[dt.date, dt.date]:
    debut, fin = _date(arguments, "debut", defauts[0]), _date(arguments, "fin", defauts[1])
    if fin < debut:
        raise ErreurConnecteur("La fin vient avant le début.")
    if (fin - debut).days + 1 > maximum:
        raise ErreurConnecteur(f"{maximum} jours au plus : demande une période plus courte.")
    return debut, fin


def _moment(arguments: dict[str, Any], cle: str, fuseau: dt.tzinfo) -> dt.date | None:
    """Une date avec heure (à l'heure du Mac), une date seule (une journée entière), ou rien."""
    texte = str(arguments.get(cle) or "").strip()
    if not texte:
        return None
    if _MOMENT.fullmatch(texte):
        try:
            if "T" not in texte:
                return dt.date.fromisoformat(texte)
            return dt.datetime.fromisoformat(texte).replace(tzinfo=fuseau)
        except ValueError:
            pass
    raise ErreurConnecteur(
        f"{cle} : AAAA-MM-JJTHH:MM pour une heure, par exemple 2026-10-02T15:00, ou AAAA-MM-JJ "
        "pour une journée entière."
    )


def _horaires(debut: dt.date, fin: dt.date | None) -> tuple[dt.date, dt.date]:
    """Le début et la fin d'un rendez-vous ; une journée entière finit le lendemain de son
    dernier jour, comme le veut iCalendar."""
    a_l_heure = isinstance(debut, dt.datetime)
    if fin is not None and isinstance(fin, dt.datetime) != a_l_heure:
        raise ErreurConnecteur(
            "debut et fin : deux dates avec heure, ou deux dates pour une journée entière."
        )
    if a_l_heure:
        fin = debut + _UNE_HEURE if fin is None else fin
    else:
        fin = (debut if fin is None else fin) + _UN_JOUR
    if fin <= debut:
        raise ErreurConnecteur("La fin vient avant le début.")
    return debut, fin


def _nouvelles_heures(
    rendezvous: RendezVous, debut: dt.date | None, fin: dt.date | None
) -> tuple[dt.date, dt.date]:
    """Les heures d'un rendez-vous modifié : un nouveau début sans fin garde la durée (sauf
    s'il passe d'une heure à la journée entière, ou l'inverse)."""
    debut = rendezvous.debut if debut is None else debut
    meme_genre = isinstance(debut, dt.datetime) == isinstance(rendezvous.debut, dt.datetime)
    if fin is None and meme_genre:
        return debut, debut + (rendezvous.fin - rendezvous.debut)
    return _horaires(debut, fin)


def _alerte(arguments: dict[str, Any]) -> int | None:
    valeur = arguments.get("alerte")
    if valeur is None or valeur == "":
        return None
    try:
        minutes = int(valeur)
    except (TypeError, ValueError):
        minutes = -1
    if not 0 <= minutes <= 40320:
        raise ErreurConnecteur("alerte : un nombre de minutes avant le début, par exemple 30.")
    return minutes


class AgendaIcloud(Connecteur):
    """`adresse` : la racine CalDAV, celle d'iCloud ; les tests passent celle de leur serveur,
    et le jour qu'il est (`aujourd_hui`)."""

    def __init__(
        self,
        reglages: dict[str, str],
        *,
        adresse: str = ADRESSE,
        fuseau: dt.tzinfo | None = None,
        delai_s: float = DELAI_S,
        aujourd_hui: Callable[[], dt.date] | None = None,
    ) -> None:
        self._calendrier = Calendrier(
            reglages["ATLAS_ICLOUD_IDENTIFIANT"],
            reglages["ATLAS_ICLOUD_MOT_DE_PASSE"],
            adresse=adresse,
            fuseau=fuseau,
            delai_s=delai_s,
        )
        self._etiquettes: dict[str, RendezVous] = {}
        self._par_fois: dict[tuple[str, object], str] = {}
        self._defaut = reglages["ATLAS_ICLOUD_AGENDA"]
        self._aujourd_hui = aujourd_hui or (lambda: dt.datetime.now(self._calendrier.fuseau).date())
        self._outils = [
            Outil("agenda_lire", LIRE, _SCHEMA_LIRE, Niveau.N1, self._lire),
            Outil("agenda_chercher", CHERCHER, _SCHEMA_CHERCHER, Niveau.N1, self._chercher),
            Outil("agenda_ajouter", AJOUTER, _SCHEMA_AJOUTER, Niveau.N2, self._ajouter),
            Outil("agenda_modifier", MODIFIER, _SCHEMA_MODIFIER, Niveau.N3, self._modifier),
            Outil("agenda_supprimer", SUPPRIMER, {"evenement": str}, Niveau.N3, self._supprimer),
        ]

    def outils(self) -> list[Outil]:
        return self._outils

    def nouvelle_conversation(self) -> None:
        self._etiquettes.clear()
        self._par_fois.clear()
        self._calendrier.oublier()

    async def _lire(self, arguments: dict[str, Any]) -> str:
        debut, fin = _periode(arguments, MAX_JOURS)
        agenda = await self._agenda(arguments.get("agenda"))
        trouves = await asyncio.to_thread(self._calendrier.lire, debut, fin, agenda)
        if not trouves:
            ou = f"l'agenda « {agenda.nom} »" if agenda else "l'agenda"
            return f"Rien dans {ou} {periode(debut, fin)}."
        return self._liste(trouves, debut)

    async def _chercher(self, arguments: dict[str, Any]) -> str:
        texte = str(arguments.get("texte") or "").strip()
        if len(texte) < 2:
            raise ErreurConnecteur("Cherche au moins deux lettres.")
        jour = self._aujourd_hui()
        defauts = (jour - dt.timedelta(days=30), jour + dt.timedelta(days=365))
        debut, fin = _periode(arguments, MAX_JOURS_CHERCHES, defauts)
        agenda = await self._agenda(arguments.get("agenda"))
        cherche = normaliser(texte)
        trouves = [
            rendezvous
            for rendezvous in await asyncio.to_thread(self._calendrier.lire, debut, fin, agenda)
            if any(
                cherche in normaliser(champ)
                for champ in (rendezvous.titre, rendezvous.lieu, rendezvous.notes)
            )
        ]
        if not trouves:
            return f"Aucun rendez-vous ne contient « {texte} » {periode(debut, fin)}."
        return self._liste(trouves, debut)

    async def _ajouter(self, arguments: dict[str, Any]) -> Fait:
        titre = str(arguments.get("titre") or "").strip()
        if not titre:
            raise ErreurConnecteur("Donne un titre au rendez-vous.")
        fuseau = self._calendrier.fuseau
        debut = _moment(arguments, "debut", fuseau)
        if debut is None:
            raise ErreurConnecteur("debut : le jour du rendez-vous, et son heure s'il en a une.")
        debut, fin = _horaires(debut, _moment(arguments, "fin", fuseau))
        alerte = _alerte(arguments)
        agenda = await self._agenda(arguments.get("agenda") or self._defaut)
        assert agenda is not None
        await asyncio.to_thread(
            self._calendrier.ajouter,
            agenda,
            titre,
            debut,
            fin,
            lieu=str(arguments.get("lieu") or "").strip(),
            notes=str(arguments.get("notes") or "").strip(),
            alerte=alerte,
        )
        ou = "" if normaliser(agenda.nom) == normaliser(self._defaut) else f" dans {agenda.nom}"
        return Fait(
            f"C'est ajouté à l'agenda « {agenda.nom} ».",
            f"C'est noté{ou} : {titre}, {quand(debut, fin)}.",
        )

    async def _modifier(self, arguments: dict[str, Any]) -> Modification:
        etiquette, rendezvous = self._designe(arguments)
        changements: dict[str, Any] = {}
        for cle, avant in [
            ("titre", rendezvous.titre),
            ("lieu", rendezvous.lieu),
            ("notes", rendezvous.notes),
        ]:
            valeur = str(arguments.get(cle) or "").strip()
            if valeur and valeur != avant:
                changements[cle] = valeur
        fuseau = self._calendrier.fuseau
        debut, fin = _moment(arguments, "debut", fuseau), _moment(arguments, "fin", fuseau)
        if debut is not None or fin is not None:
            debut, fin = _nouvelles_heures(rendezvous, debut, fin)
            if (debut, fin) != (rendezvous.debut, rendezvous.fin):
                changements.update(debut=debut, fin=fin)
        if not changements:
            raise ErreurConnecteur(RIEN_A_CHANGER)
        return Modification(
            rendezvous,
            changements,
            faire=lambda: self._calendrier.modifier(rendezvous, **changements),
            apres=lambda: self._etiquettes.pop(etiquette, None),
        )

    async def _supprimer(self, arguments: dict[str, Any]) -> Suppression:
        etiquette, rendezvous = self._designe(arguments)
        return Suppression(
            rendezvous,
            faire=lambda: self._calendrier.supprimer(rendezvous),
            apres=lambda: self._etiquettes.pop(etiquette, None),
        )

    def _designe(self, arguments: dict[str, Any]) -> tuple[str, RendezVous]:
        """Le rendez-vous que désigne l'étiquette, s'il peut changer sans écrire à personne."""
        etiquette = str(arguments.get("evenement") or "").strip()
        rendezvous = self._etiquettes.get(etiquette)
        if rendezvous is None:
            raise ErreurConnecteur(f"Je ne connais pas « {etiquette} » : relis l'agenda d'abord.")
        if rendezvous.invites:
            raise ErreurConnecteur(INVITES)
        return etiquette, rendezvous

    async def _agenda(self, nom: object) -> Agenda | None:
        """L'agenda que David nomme (sans tenir compte des accents ni des majuscules)."""
        nom = str(nom or "").strip()
        if not nom:
            return None
        agendas = await asyncio.to_thread(self._calendrier.agendas)
        for agenda in agendas:
            if normaliser(agenda.nom) == normaliser(nom):
                return agenda
        noms = ", ".join(agenda.nom for agenda in agendas)
        raise ErreurConnecteur(f"Pas d'agenda « {nom} » dans ton iCloud. Tes agendas : {noms}.")

    def _etiqueter(self, rendezvous: RendezVous) -> str:
        """La même fois d'un rendez-vous garde son étiquette pendant la conversation."""
        cle = (rendezvous.url, rendezvous.origine)
        etiquette = self._par_fois.get(cle)
        if etiquette is None:
            etiquette = f"e{len(self._par_fois) + 1}"
            self._par_fois[cle] = etiquette
        self._etiquettes[etiquette] = rendezvous
        return etiquette

    def _liste(self, trouves: list[RendezVous], debut: dt.date) -> str:
        """Groupés par jour ; un rendez-vous commencé avant la période est à son premier jour."""
        lignes: list[str] = []
        jour_courant = None
        for rendezvous in trouves[:MAX_RENDEZVOUS]:
            jour = max(jour_de(rendezvous.debut), debut)
            if jour != jour_courant:
                lignes.append(jour_long(jour))
                jour_courant = jour
            lignes.append(ligne(self._etiqueter(rendezvous), rendezvous))
        if len(trouves) > MAX_RENDEZVOUS:
            reste = len(trouves) - MAX_RENDEZVOUS
            lignes.append(f"… et {reste} autres : demande une période plus courte.")
        return "\n".join(lignes)


def creer(contexte: Contexte) -> AgendaIcloud:
    return AgendaIcloud(contexte.reglages)

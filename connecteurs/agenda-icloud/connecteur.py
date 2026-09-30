"""L'agenda iCloud de David, en connecteur (spec de l'agenda et des contacts, §5) : lire une
période et chercher (N1).

Chaque rendez-vous lu reçoit une étiquette (`e1`, `e2`…), que Claude rend pour désigner un
rendez-vous ; chaque fois d'un événement répété a la sienne. Les étiquettes valent pour la
conversation : la suivante les oublie, et relit l'agenda.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import re
from collections.abc import Callable
from typing import Any

from atlas_core.connecteurs import Connecteur, Contexte, ErreurConnecteur, Niveau, Outil

from .agenda import ADRESSE, DELAI_S, Agenda, Calendrier, RendezVous, jour_de, normaliser
from .dire import jour_long, ligne, periode

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
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


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
        self._aujourd_hui = aujourd_hui or (lambda: dt.datetime.now(self._calendrier.fuseau).date())
        self._outils = [
            Outil("agenda_lire", LIRE, _SCHEMA_LIRE, Niveau.N1, self._lire),
            Outil("agenda_chercher", CHERCHER, _SCHEMA_CHERCHER, Niveau.N1, self._chercher),
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

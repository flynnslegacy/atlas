"""Un agenda en connecteur, quel que soit son serveur (spec de Gmail et de Google Agenda, D10 ;
spec de l'agenda et des contacts, §5) : lire une période et chercher (N1), ajouter (N2),
modifier et supprimer après le « oui » de David (N3). L'agenda iCloud et Google Agenda le
branchent chacun sur son client (`Calendrier`).

Chaque rendez-vous lu reçoit une étiquette (`e1`, `g1`… : la lettre du connecteur), que Claude
rend pour désigner un rendez-vous ; chaque fois d'un événement répété a la sienne. Les étiquettes
valent pour la conversation : la suivante les oublie, et relit l'agenda. Un événement modifié ou
supprimé, ou changé entre-temps, perd les étiquettes de toutes ses fois jusqu'à ce qu'on le
relise : ce qu'on en savait n'est plus vrai.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import re
from collections.abc import Callable
from typing import Any, Protocol

from .connecteurs import Connecteur, ErreurConnecteur, Fait, Niveau, Outil
from .rendez_vous import (
    Agenda,
    Change,
    Modification,
    RendezVous,
    Suppression,
    jour_de,
    jour_long,
    lecture_seule,
    ligne,
    normaliser,
    periode,
    quand,
)

MAX_JOURS = 62
MAX_JOURS_CHERCHES = 400
MAX_RENDEZVOUS = 100
RIEN_A_CHANGER = "Dis ce qui change : le titre, le début, la fin, le lieu ou les notes."
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_MOMENT = re.compile(r"\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}(:\d{2})?)?")
_UNE_HEURE = dt.timedelta(hours=1)
_UN_JOUR = dt.timedelta(days=1)


class Calendrier(Protocol):
    """Ce qu'un client d'agenda donne au moteur. Tout est synchrone : le moteur l'appelle par
    `asyncio.to_thread`. `modifier` et `supprimer` lèvent `Change` si le rendez-vous a changé
    depuis sa lecture."""

    fuseau: dt.tzinfo

    def oublier(self) -> None: ...

    def agendas(self) -> list[Agenda]: ...

    def lire(
        self, debut: dt.date, fin: dt.date, agenda: Agenda | None = None
    ) -> list[RendezVous]: ...

    def ajouter(
        self,
        agenda: Agenda,
        titre: str,
        debut: dt.date,
        fin: dt.date,
        *,
        lieu: str = "",
        notes: str = "",
        alerte: int | None = None,
    ) -> None: ...

    def modifier(self, rendezvous: RendezVous, **changements: Any) -> None: ...

    def supprimer(self, rendezvous: RendezVous) -> None: ...


def _schema(requis: list[str], **proprietes: str) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {nom: {"type": genre} for nom, genre in proprietes.items()},
        "required": requis,
    }


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


class ConnecteurAgenda(Connecteur):
    """Les cinq outils d'agenda, sur `calendrier`. `service` : « iCloud », « Google » ;
    `prefixe` : celui des noms d'outils (`agenda`, `google_agenda`) ; `lettre` : celle des
    étiquettes ; `application` : l'app où David change ce qu'Atlas ne change pas ; `compte` :
    comment dire son compte (« iCloud », « compte Google ») ; `defaut` : le nom de l'agenda des
    ajouts (None : l'agenda principal que le serveur désigne) ; `aujourd_hui` : le jour qu'il
    est (les tests le fixent)."""

    def __init__(
        self,
        calendrier: Calendrier,
        *,
        service: str,
        prefixe: str,
        lettre: str,
        application: str,
        compte: str | None = None,
        defaut: str | None = None,
        aujourd_hui: Callable[[], dt.date] | None = None,
    ) -> None:
        self._calendrier = calendrier
        self._compte, self._lettre, self._defaut = compte or service, lettre, defaut
        self._invites = (
            "Ce rendez-vous a des invités : Atlas ne le change pas, pour ne pas leur écrire en "
            f"ton nom. Change-le dans {application}."
        )
        self._etiquettes: dict[str, RendezVous] = {}
        self._par_fois: dict[tuple[str, object], str] = {}
        self._aujourd_hui = aujourd_hui or (lambda: dt.datetime.now(calendrier.fuseau).date())
        exemples = f"{lettre}1, {lettre}2…"
        sinon = "celui de ses réglages" if defaut else "son agenda principal"
        self._outils = [
            Outil(
                f"{prefixe}_lire",
                f"Les rendez-vous de l'agenda {service} de David entre deux dates (debut et fin, "
                "AAAA-MM-JJ, fin comprise, 62 jours au plus), dans tous ses agendas, ou dans "
                f"celui qu'il nomme (agenda). Chaque rendez-vous a une étiquette ({exemples}), "
                "qui le désigne pour le modifier ou le supprimer.",
                _schema(["debut", "fin"], debut="string", fin="string", agenda="string"),
                Niveau.N1,
                self._lire,
            ),
            Outil(
                f"{prefixe}_chercher",
                f"Cherche dans l'agenda {service} de David les rendez-vous dont le titre, le lieu "
                "ou les notes contiennent un texte (texte), sans tenir compte des accents ni des "
                "majuscules : par défaut d'un mois en arrière à un an en avant, ou entre debut et "
                "fin (AAAA-MM-JJ) ; dans tous ses agendas, ou dans celui qu'il nomme (agenda).",
                _schema(["texte"], texte="string", debut="string", fin="string", agenda="string"),
                Niveau.N1,
                self._chercher,
            ),
            Outil(
                f"{prefixe}_ajouter",
                f"Ajoute un rendez-vous à l'agenda {service} de David quand il le demande : "
                "titre, debut (AAAA-MM-JJTHH:MM, ou AAAA-MM-JJ pour une journée entière), et au "
                "besoin fin (sinon une heure, ou la journée ; pour une journée entière, le "
                "dernier jour), lieu, notes, alerte (minutes avant le début) et agenda (sinon "
                f"{sinon}). Atlas l'annonce : ne l'annonce pas toi-même.",
                _schema(
                    ["titre", "debut"],
                    titre="string",
                    debut="string",
                    fin="string",
                    lieu="string",
                    notes="string",
                    alerte="integer",
                    agenda="string",
                ),
                Niveau.N2,
                self._ajouter,
            ),
            Outil(
                f"{prefixe}_modifier",
                f"Modifie un rendez-vous de l'agenda {service} de David, désigné par son "
                f"étiquette (evenement : {exemples}, lue par {prefixe}_lire ou "
                f"{prefixe}_chercher) : un nouveau titre, debut, fin, lieu ou notes (debut et fin "
                "en AAAA-MM-JJTHH:MM, ou AAAA-MM-JJ pour une journée entière ; un nouveau début "
                "sans fin garde la durée). D'un événement répété, seule cette fois change. Atlas "
                "demande à David de confirmer : n'ajoute rien après l'appel.",
                _schema(
                    ["evenement"],
                    evenement="string",
                    titre="string",
                    debut="string",
                    fin="string",
                    lieu="string",
                    notes="string",
                ),
                Niveau.N3,
                self._modifier,
            ),
            Outil(
                f"{prefixe}_supprimer",
                f"Supprime un rendez-vous de l'agenda {service} de David, désigné par son "
                f"étiquette (evenement : {exemples}) ; d'un événement répété, cette fois "
                "seulement. Atlas demande à David de confirmer : n'ajoute rien après l'appel.",
                {"evenement": str},
                Niveau.N3,
                self._supprimer,
            ),
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
        nom = str(arguments.get("agenda") or "").strip() or self._defaut
        agenda = await self._agenda(nom) if nom else await self._principal()
        assert agenda is not None
        if agenda.lecture_seule:
            raise ErreurConnecteur(lecture_seule(agenda))
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
        ou = "" if self._est_le_defaut(agenda) else f" dans {agenda.nom}"
        return Fait(
            f"C'est ajouté à l'agenda « {agenda.nom} ».",
            f"C'est noté{ou} : {titre}, {quand(debut, fin)}.",
        )

    async def _modifier(self, arguments: dict[str, Any]) -> Modification:
        rendezvous = self._designe(arguments)
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
            faire=self._sinon_relire(rendezvous, self._calendrier.modifier, **changements),
            apres=lambda: self._oublier(rendezvous.evenement),
        )

    async def _supprimer(self, arguments: dict[str, Any]) -> Suppression:
        rendezvous = self._designe(arguments)
        return Suppression(
            rendezvous,
            faire=self._sinon_relire(rendezvous, self._calendrier.supprimer),
            apres=lambda: self._oublier(rendezvous.evenement),
        )

    def _sinon_relire(
        self, rendezvous: RendezVous, ecrire: Callable[..., None], **changements: Any
    ) -> Callable[[], None]:
        """L'écriture après le « oui » ; si l'événement a changé entre-temps, ses étiquettes
        sont oubliées : Claude le relira avant de réessayer."""

        def faire() -> None:
            try:
                ecrire(rendezvous, **changements)
            except Change:
                self._oublier(rendezvous.evenement)
                raise

        return faire

    def _oublier(self, evenement: str) -> None:
        """Les étiquettes de toutes les fois d'un événement : son ETag n'est plus le bon."""
        self._etiquettes = {e: r for e, r in self._etiquettes.items() if r.evenement != evenement}

    def _designe(self, arguments: dict[str, Any]) -> RendezVous:
        """Le rendez-vous que désigne l'étiquette, s'il peut changer sans écrire à personne,
        dans un agenda qui se modifie."""
        etiquette = str(arguments.get("evenement") or "").strip()
        rendezvous = self._etiquettes.get(etiquette)
        if rendezvous is None:
            raise ErreurConnecteur(f"Je ne connais pas « {etiquette} » : relis l'agenda d'abord.")
        if rendezvous.invites:
            raise ErreurConnecteur(self._invites)
        if rendezvous.agenda.lecture_seule:
            raise ErreurConnecteur(lecture_seule(rendezvous.agenda))
        return rendezvous

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
        raise ErreurConnecteur(
            f"Pas d'agenda « {nom} » dans ton {self._compte}. Tes agendas : {noms}."
        )

    async def _principal(self) -> Agenda:
        """L'agenda principal que le serveur désigne (Google), où vont les ajouts."""
        agendas = await asyncio.to_thread(self._calendrier.agendas)
        for agenda in agendas:
            if agenda.principal:
                return agenda
        raise ErreurConnecteur(f"Je ne trouve pas ton agenda principal dans ton {self._compte}.")

    def _est_le_defaut(self, agenda: Agenda) -> bool:
        if self._defaut is None:
            return agenda.principal
        return normaliser(agenda.nom) == normaliser(self._defaut)

    def _etiqueter(self, rendezvous: RendezVous) -> str:
        """La même fois d'un rendez-vous garde son étiquette pendant la conversation."""
        cle = (rendezvous.evenement, rendezvous.origine)
        etiquette = self._par_fois.get(cle)
        if etiquette is None:
            etiquette = f"{self._lettre}{len(self._par_fois) + 1}"
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

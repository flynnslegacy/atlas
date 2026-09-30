"""Le client CalDAV de l'agenda iCloud (spec de l'agenda et des contacts, §5).

iCloud parle CalDAV, avec l'identifiant Apple de David et un mot de passe d'app : on demande à
sa racine le « principal » de David, au principal son dossier d'agendas, puis les agendas qui
portent des rendez-vous. Une période se lit par une requête bornée dans le temps
(`calendar-query`) ; les événements répétés sont dépliés ici, chaque fois avec sa date
d'origine dans la série, et toutes les heures sont ramenées au fuseau du Mac du Core. Un
rendez-vous s'ajoute par un PUT, qui ne remplace jamais rien (`If-None-Match: *`).

Tout est synchrone (httpx) : le connecteur appelle ce client par `asyncio.to_thread`.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
import unicodedata
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
import icalendar
import recurring_ical_events

from atlas_core.connecteurs import ErreurConnecteur

_journal = logging.getLogger(__name__)

ADRESSE = "https://caldav.icloud.com/"
DELAI_S = 15.0
REFUS = (
    "iCloud refuse l'identifiant ou le mot de passe d'app : vérifie-les dans Paramètres › "
    "Connecteurs › Réglages."
)
MUET = "iCloud ne répond pas : réessaie dans un moment."

_DAV = "{DAV:}"
_CALDAV = "{urn:ietf:params:xml:ns:caldav}"
_XML = {"Content-Type": "application/xml; charset=utf-8"}
_ICS = {"Content-Type": "text/calendar; charset=utf-8"}
_PROPFIND = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
    "<d:prop>{}</d:prop></d:propfind>"
)
_PERIODE = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
    "<d:prop><d:getetag/><c:calendar-data/></d:prop>"
    '<c:filter><c:comp-filter name="VCALENDAR"><c:comp-filter name="VEVENT">'
    '<c:time-range start="{debut}" end="{fin}"/>'
    "</c:comp-filter></c:comp-filter></c:filter></c:calendar-query>"
)


class ErreurDav(Exception):
    """Une réponse inattendue d'iCloud : le Core la note, et Claude apprend l'échec."""


def lecture_seule(agenda: Agenda) -> str:
    return f"L'agenda « {agenda.nom} » ne se modifie pas d'ici."


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
    nom: str
    url: str


@dataclass(frozen=True)
class RendezVous:
    """Une fois d'un rendez-vous : un événement seul, ou l'une des fois d'une série, que
    désigne `origine` (sa date d'origine dans la série ; None hors série). Les heures sont
    celles du Mac ; une journée entière a des dates, et sa `fin` est exclue."""

    agenda: Agenda
    url: str
    etag: str
    titre: str
    debut: dt.date  # un dt.datetime pour un rendez-vous à l'heure
    fin: dt.date
    lieu: str = ""
    notes: str = ""
    invites: bool = False
    origine: dt.date | None = None

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


def _utc(moment: dt.datetime) -> str:
    return moment.astimezone(dt.UTC).strftime("%Y%m%dT%H%M%SZ")


def _ordre(rendezvous: RendezVous) -> tuple:
    debut = rendezvous.debut
    minutes = debut.hour * 60 + debut.minute if isinstance(debut, dt.datetime) else -1
    return jour_de(debut), minutes, normaliser(rendezvous.titre)


class Calendrier:
    """Les agendas iCloud de David. `adresse` : la racine CalDAV (celle d'iCloud, écrite ici ;
    les tests passent celle de leur serveur)."""

    def __init__(
        self,
        identifiant: str,
        mot_de_passe: str,
        *,
        adresse: str = ADRESSE,
        fuseau: dt.tzinfo | None = None,
        delai_s: float = DELAI_S,
    ) -> None:
        self._adresse = adresse
        self.fuseau = fuseau or fuseau_du_mac()
        self._http = httpx.Client(
            auth=(identifiant, mot_de_passe), timeout=delai_s, follow_redirects=True
        )
        self._agendas: list[Agenda] | None = None

    def oublier(self) -> None:
        """La conversation suivante relit la liste des agendas."""
        self._agendas = None

    def agendas(self) -> list[Agenda]:
        """Les agendas qui portent des rendez-vous, par nom."""
        if self._agendas is None:
            principal = self._lien(self._adresse, "current-user-principal", _DAV)
            maison = self._lien(principal, "calendar-home-set", _CALDAV)
            self._agendas = sorted(self._lister(maison), key=lambda a: normaliser(a.nom))
        return self._agendas

    def lire(self, debut: dt.date, fin: dt.date, agenda: Agenda | None = None) -> list[RendezVous]:
        """Les rendez-vous qui touchent la période, du début du jour `debut` à la fin du jour
        `fin`, dans tous les agendas ou dans `agenda`, triés."""
        de = dt.datetime.combine(debut, dt.time(), self.fuseau)
        a = dt.datetime.combine(fin + dt.timedelta(days=1), dt.time(), self.fuseau)
        corps = _PERIODE.format(debut=_utc(de), fin=_utc(a))
        trouves: list[RendezVous] = []
        for lu in [agenda] if agenda is not None else self.agendas():
            reponse = self._envoyer("REPORT", lu.url, corps, {"Depth": "1", **_XML})
            for url, proprietes in self._multistatus(reponse):
                donnees = proprietes.findtext(f"{_CALDAV}calendar-data")
                if not donnees:
                    continue
                etag = proprietes.findtext(f"{_DAV}getetag", "")
                try:
                    trouves += self._deplier(lu, url, etag, donnees, de, a)
                except Exception as e:  # noqa: BLE001 — un événement illisible n'empêche pas les autres
                    _journal.warning("événement illisible, laissé de côté : %s (%s)", url, e)
        return sorted(trouves, key=_ordre)

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
    ) -> None:
        """Un rendez-vous neuf, sans invités ; une journée entière a des dates, sa `fin`
        exclue. `alerte` : une alerte, ce nombre de minutes avant le début."""
        uid = str(uuid.uuid4()).upper()
        evenement = icalendar.Event()
        evenement.add("uid", uid)
        evenement.add("dtstamp", dt.datetime.now(dt.UTC))
        evenement.add("dtstart", debut)
        evenement.add("dtend", fin)
        evenement.add("summary", titre)
        if lieu:
            evenement.add("location", lieu)
        if notes:
            evenement.add("description", notes)
        if alerte is not None:
            alarme = icalendar.Alarm()
            alarme.add("action", "DISPLAY")
            alarme.add("description", titre)
            alarme.add("trigger", -dt.timedelta(minutes=alerte))
            evenement.add_component(alarme)
        calendrier = icalendar.Calendar()
        calendrier.add("prodid", "-//Atlas//Agenda iCloud//FR")
        calendrier.add("version", "2.0")
        calendrier.add_component(evenement)
        calendrier.add_missing_timezones()
        entetes = {"If-None-Match": "*", **_ICS}
        reponse = self._envoyer("PUT", f"{agenda.url}{uid}.ics", calendrier.to_ical(), entetes)
        self._verifier_l_ecriture(reponse, agenda)

    def _verifier_l_ecriture(self, reponse: httpx.Response, agenda: Agenda) -> None:
        if reponse.status_code == 403:
            raise ErreurConnecteur(lecture_seule(agenda))
        if not reponse.is_success:
            raise ErreurDav(f"{reponse.request.method} : {reponse.status_code}")

    def _deplier(
        self, agenda: Agenda, url: str, etag: str, donnees: str, de: dt.datetime, a: dt.datetime
    ) -> list[RendezVous]:
        calendrier = icalendar.Calendar.from_ical(donnees)
        serie = any(
            nom in composant
            for composant in calendrier.walk("VEVENT")
            for nom in ("RRULE", "RDATE", "RECURRENCE-ID")
        )
        return [
            self._rendezvous(agenda, url, etag, fois, serie)
            for fois in recurring_ical_events.of(calendrier).between(de, a)
        ]

    def _rendezvous(
        self, agenda: Agenda, url: str, etag: str, fois: icalendar.Event, serie: bool
    ) -> RendezVous:
        origine = fois.get("RECURRENCE-ID") if serie else None
        return RendezVous(
            agenda=agenda,
            url=url,
            etag=etag,
            titre=str(fois.get("SUMMARY", "")).strip() or "(sans titre)",
            debut=self._local(fois["DTSTART"].dt),
            fin=self._local(fois["DTEND"].dt),  # donnée à chaque fois, même sans fin écrite
            lieu=str(fois.get("LOCATION", "")).strip(),
            notes=str(fois.get("DESCRIPTION", "")).strip(),
            invites="ATTENDEE" in fois or "ORGANIZER" in fois,
            origine=origine.dt if origine is not None else None,
        )

    def _local(self, moment: dt.date) -> dt.date:
        if not isinstance(moment, dt.datetime):
            return moment
        if moment.tzinfo is None:  # une heure « flottante » : celle du Mac
            return moment.replace(tzinfo=self.fuseau)
        return moment.astimezone(self.fuseau)

    def _lien(self, url: str, propriete: str, espace: str) -> str:
        prefixe = "d" if espace == _DAV else "c"
        corps = _PROPFIND.format(f"<{prefixe}:{propriete}/>")
        reponse = self._envoyer("PROPFIND", url, corps, {"Depth": "0", **_XML})
        for _, proprietes in self._multistatus(reponse):
            href = proprietes.findtext(f"{espace}{propriete}/{_DAV}href")
            if href:
                return urljoin(str(reponse.url), href.strip())
        raise ErreurDav(f"{propriete} introuvable à {url}")

    def _lister(self, maison: str) -> list[Agenda]:
        demande = "<d:displayname/><d:resourcetype/><c:supported-calendar-component-set/>"
        reponse = self._envoyer(
            "PROPFIND", maison, _PROPFIND.format(demande), {"Depth": "1", **_XML}
        )
        agendas = []
        for url, proprietes in self._multistatus(reponse):
            if proprietes.find(f"{_DAV}resourcetype/{_CALDAV}calendar") is None:
                continue
            composants = proprietes.find(f"{_CALDAV}supported-calendar-component-set")
            if composants is not None and all(c.get("name") != "VEVENT" for c in composants):
                continue  # un agenda de tâches : les anciens Rappels
            nom = (proprietes.findtext(f"{_DAV}displayname") or "").strip()
            url = url if url.endswith("/") else f"{url}/"
            agendas.append(Agenda(nom or url.rstrip("/").rsplit("/", 1)[-1], url))
        return agendas

    def _multistatus(self, reponse: httpx.Response) -> list[tuple[str, ET.Element]]:
        """Chaque réponse d'un 207 : son adresse, et ses propriétés trouvées."""
        if reponse.status_code != 207:
            raise ErreurDav(f"{reponse.request.method} : {reponse.status_code}")
        resultats = []
        for element in ET.fromstring(reponse.content).iter(f"{_DAV}response"):
            proprietes = ET.Element("prop")
            for propstat in element.iter(f"{_DAV}propstat"):
                trouvees = propstat.find(f"{_DAV}prop")
                if trouvees is not None and " 200 " in propstat.findtext(f"{_DAV}status", ""):
                    proprietes.extend(trouvees)
            href = element.findtext(f"{_DAV}href", "").strip()
            resultats.append((urljoin(str(reponse.url), href), proprietes))
        return resultats

    def _envoyer(
        self, methode: str, url: str, corps: str | bytes | None, entetes: dict[str, str]
    ) -> httpx.Response:
        try:
            reponse = self._http.request(methode, url, content=corps, headers=entetes)
        except httpx.TransportError:  # injoignable, ou muet au-delà du délai
            raise ErreurConnecteur(MUET) from None
        if reponse.status_code == 401:
            raise ErreurConnecteur(REFUS)
        return reponse

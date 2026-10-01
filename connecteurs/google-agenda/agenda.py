"""Le client de l'API Google Agenda (spec de Gmail et de Google Agenda, §5).

Les agendas de David viennent de sa liste d'agendas (`calendarList`) : ceux qu'il affiche, avec
ce que Google en dit (le principal, ceux en lecture seule). Une période se lit agenda par
agenda, séries dépliées par Google (`singleEvents=true`), dans le fuseau du Mac du Core. Les
écritures ne préviennent jamais personne (`sendUpdates=none`) ; une modification ou une
suppression exige que le rendez-vous n'ait pas changé depuis sa lecture (`If-Match`). Une fois
d'une série se change ou se supprime par son propre identifiant : Google en fait une exception.
Google ne rend pas les rendez-vous annulés (`showDeleted` n'est pas demandé).

Tout est synchrone : le moteur d'agenda l'appelle par `asyncio.to_thread`.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any
from urllib.parse import quote

import httpx

from atlas_core.connecteurs import ErreurConnecteur
from atlas_core.google import Autorisation
from atlas_core.rendez_vous import (
    Agenda,
    Change,
    RendezVous,
    fuseau_du_mac,
    lecture_seule,
    normaliser,
    ordre,
)

_journal = logging.getLogger(__name__)

ADRESSE = "https://www.googleapis.com/calendar/v3"
SERVICE = "l'Agenda"
PAGE = 2500  # le plus que Google donne par page
# Les rendez-vous d'un agenda dans une lecture : au-delà, laissés de côté. Assez pour une recherche
# de 395 jours dans un agenda chargé (un rendez-vous quotidien en fait déjà 395).
MAX_FOIS = 2500
LECTURE_SEULE = {"reader", "freeBusyReader"}


class ErreurAgenda(Exception):
    """Une réponse inattendue de Google : le Core la note, et Claude apprend l'échec."""


class AgendaDisparu(ErreurAgenda):
    """Un agenda de la liste que Google ne connaît plus (404, 410) : retiré, ou plus partagé."""


def _id(texte: str) -> str:
    return quote(texte, safe="")


class Calendrier:
    """Les agendas Google de David, par son autorisation."""

    def __init__(self, autorisation: Autorisation, *, fuseau: dt.tzinfo | None = None) -> None:
        self._autorisation = autorisation
        self.fuseau = fuseau or fuseau_du_mac()
        self._agendas: list[Agenda] | None = None

    def oublier(self) -> None:
        """La conversation suivante relit la liste des agendas."""
        self._agendas = None

    def agendas(self) -> list[Agenda]:
        """Les agendas que David affiche dans Google Agenda, par nom."""
        if self._agendas is None:
            agendas = []
            for entree in self._pages(f"{ADRESSE}/users/me/calendarList", {}):
                if not entree.get("selected") and not entree.get("primary"):
                    continue  # un agenda que David masque
                agendas.append(
                    Agenda(
                        str(entree.get("summaryOverride") or entree.get("summary") or entree["id"]),
                        str(entree["id"]),
                        lecture_seule=entree.get("accessRole") in LECTURE_SEULE,
                        principal=bool(entree.get("primary")),
                    )
                )
            self._agendas = sorted(agendas, key=lambda a: normaliser(a.nom))
        return self._agendas

    def lire(self, debut: dt.date, fin: dt.date, agenda: Agenda | None = None) -> list[RendezVous]:
        """Les rendez-vous qui touchent la période, du début du jour `debut` à la fin du jour
        `fin`, dans tous les agendas ou dans `agenda`, triés."""
        de = dt.datetime.combine(debut, dt.time(), self.fuseau)
        a = dt.datetime.combine(fin + dt.timedelta(days=1), dt.time(), self.fuseau)
        params = {
            "timeMin": de.isoformat(),
            "timeMax": a.isoformat(),
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": PAGE,
        }
        if zone := getattr(self.fuseau, "key", None):
            params["timeZone"] = zone
        trouves: list[RendezVous] = []
        for lu in [agenda] if agenda is not None else self.agendas():
            adresse = f"{ADRESSE}/calendars/{_id(lu.cle)}/events"
            try:
                evenements = self._pages(adresse, params)
            except AgendaDisparu as e:
                if agenda is not None:
                    raise
                # Un agenda retiré ou plus partagé n'empêche pas de lire les autres.
                _journal.warning("agenda illisible, laissé de côté : %s (%s)", lu.nom, e)
                continue
            dans_l_agenda = 0
            for evenement in evenements:
                if dans_l_agenda == MAX_FOIS:
                    modele = (
                        "%s : plus de %d rendez-vous dans la période, le reste est laissé de côté"
                    )
                    _journal.warning(modele, lu.nom, MAX_FOIS)
                    break
                try:
                    trouves.append(self._rendezvous(lu, evenement))
                    dans_l_agenda += 1
                except (KeyError, TypeError, ValueError) as e:  # illisible : pas les autres
                    _journal.warning("rendez-vous illisible, laissé de côté : %s (%s)", lu.nom, e)
        return sorted(trouves, key=ordre)

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
        exclue. `alerte` : une notification, ce nombre de minutes avant le début."""
        corps: dict[str, Any] = {
            "summary": titre,
            "start": self._moment_google(debut),
            "end": self._moment_google(fin),
        }
        if lieu:
            corps["location"] = lieu
        if notes:
            corps["description"] = notes
        if alerte is not None:
            corps["reminders"] = {
                "useDefault": False,
                "overrides": [{"method": "popup", "minutes": alerte}],
            }
        adresse = f"{ADRESSE}/calendars/{_id(agenda.cle)}/events"
        self._verifier(self._ecrire("POST", adresse, corps), agenda)

    def modifier(
        self,
        rendezvous: RendezVous,
        *,
        titre: str | None = None,
        debut: dt.date | None = None,
        fin: dt.date | None = None,
        lieu: str | None = None,
        notes: str | None = None,
    ) -> None:
        """Change ce qui est donné ; `debut` et `fin` vont ensemble. Pour une fois d'une série,
        seule cette fois change. `Change` si le rendez-vous a changé depuis sa lecture."""
        corps: dict[str, Any] = {}
        for nom, valeur in [("summary", titre), ("location", lieu), ("description", notes)]:
            if valeur is not None:
                corps[nom] = valeur
        if debut is not None and fin is not None:
            corps["start"] = self._moment_google(debut, effacer=True)
            corps["end"] = self._moment_google(fin, effacer=True)
        reponse = self._ecrire("PATCH", self._adresse(rendezvous), corps, rendezvous.etag)
        self._verifier(reponse, rendezvous.agenda)

    def supprimer(self, rendezvous: RendezVous) -> None:
        """Supprime le rendez-vous, ou cette fois seulement de sa série. `Change` s'il a changé
        depuis sa lecture."""
        reponse = self._ecrire("DELETE", self._adresse(rendezvous), None, rendezvous.etag)
        self._verifier(reponse, rendezvous.agenda)

    def _rendezvous(self, agenda: Agenda, evenement: dict[str, Any]) -> RendezVous:
        invites = evenement.get("attendees") or []
        organisateur = evenement.get("organizer") or {}
        origine = evenement.get("originalStartTime")
        return RendezVous(
            agenda=agenda,
            evenement=str(evenement.get("recurringEventId") or evenement["id"]),
            etag=str(evenement["etag"]),
            titre=str(evenement.get("summary") or "").strip() or "(sans titre)",
            debut=self._moment(evenement["start"]),
            fin=self._moment(evenement["end"]),
            lieu=str(evenement.get("location") or "").strip(),
            notes=str(evenement.get("description") or "").strip(),
            # Un invité autre que David, ou un organisateur qui n'est pas cet agenda.
            invites=any(not i.get("self") for i in invites) or not organisateur.get("self"),
            origine=self._moment(origine) if "recurringEventId" in evenement and origine else None,
            refuse=any(i.get("self") and i.get("responseStatus") == "declined" for i in invites),
            cle=str(evenement["id"]),
        )

    def _moment(self, valeur: dict[str, str]) -> dt.date:
        if "date" in valeur:
            return dt.date.fromisoformat(valeur["date"])
        return dt.datetime.fromisoformat(valeur["dateTime"]).astimezone(self.fuseau)

    def _moment_google(self, moment: dt.date, *, effacer: bool = False) -> dict[str, str | None]:
        """Un début ou une fin au format de Google. `effacer`, pour un PATCH, que Google fusionne
        avec l'existant : l'autre forme est mise à `null`, pour qu'un rendez-vous passe d'une
        heure à la journée entière, ou l'inverse."""
        valeur: dict[str, str | None]
        if not isinstance(moment, dt.datetime):
            valeur = {"date": moment.isoformat()}
            if effacer:
                valeur.update(dateTime=None, timeZone=None)
            return valeur
        valeur = {"dateTime": moment.isoformat()}
        if zone := getattr(self.fuseau, "key", None):
            valeur["timeZone"] = zone
        if effacer:
            valeur["date"] = None
        return valeur

    def _adresse(self, rendezvous: RendezVous) -> str:
        return f"{ADRESSE}/calendars/{_id(rendezvous.agenda.cle)}/events/{_id(rendezvous.cle)}"

    def _ecrire(
        self, methode: str, adresse: str, corps: Any, etag: str | None = None
    ) -> httpx.Response:
        entetes = {"If-Match": etag} if etag else {}
        return self._autorisation.appeler(
            methode,
            adresse,
            service=SERVICE,
            params={"sendUpdates": "none"},
            json=corps,
            entetes=entetes,
        )

    def _verifier(self, reponse: httpx.Response, agenda: Agenda) -> None:
        if reponse.status_code in {404, 410, 412}:  # disparu, ou changé depuis la lecture
            raise Change()
        if reponse.status_code == 403:
            raise ErreurConnecteur(lecture_seule(agenda))
        if not reponse.is_success:
            raise ErreurAgenda(f"{reponse.request.method} : {reponse.status_code}")

    def _pages(self, adresse: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Toutes les pages d'une liste de Google."""
        elements: list[dict[str, Any]] = []
        jeton: str | None = None
        while True:
            demande = {**params, **({"pageToken": jeton} if jeton else {})}
            reponse = self._autorisation.appeler("GET", adresse, service=SERVICE, params=demande)
            if reponse.status_code in {404, 410}:
                raise AgendaDisparu(f"GET : {reponse.status_code}")
            if not reponse.is_success:
                raise ErreurAgenda(f"GET : {reponse.status_code}")
            page = reponse.json()
            elements += page.get("items", [])
            jeton = page.get("nextPageToken")
            if not jeton or len(elements) > MAX_FOIS:
                return elements

"""L'API Google Agenda, dans la doublure de Google (doublure_google.py), comme sa documentation la
décrit : la liste des agendas de David (`calendarList`), leurs événements avec leur ETag, les
séries dépliées (`singleEvents=true` : chaque fois a son identifiant, `<id>_<début en UTC>`,
avec `recurringEventId` et `originalStartTime`), les exceptions d'une série, et les écritures,
refusées dans un agenda en lecture seule et soumises à `If-Match`. Un PATCH fusionne les objets,
comme chez Google : un champ envoyé à `null` s'efface, et un début ou une fin qui garderait à la
fois `date` et `dateTime` est refusé. Les séries n'ont ici que des règles simples (`FREQ=DAILY`
ou `WEEKLY`, et `COUNT`).
"""

from __future__ import annotations

import copy
import datetime as dt
from typing import Any
from urllib.parse import unquote
from zoneinfo import ZoneInfo

import httpx
from doublure_google import DoublureGoogle, corps, erreur, repondre

HOTE = r"www\.googleapis\.com/calendar/v3"
LECTURE_SEULE = {"reader", "freeBusyReader"}


def moment(valeur: dt.date, fuseau: str = "Europe/Paris") -> dict[str, str]:
    """Un début ou une fin au format de Google : une date, ou une heure dans un fuseau."""
    if isinstance(valeur, dt.datetime):
        return {"dateTime": valeur.isoformat(), "timeZone": fuseau}
    return {"date": valeur.isoformat()}


def _lire(valeur: dict[str, str], fuseau: ZoneInfo) -> dt.datetime:
    if "date" in valeur:
        return dt.datetime.combine(dt.date.fromisoformat(valeur["date"]), dt.time(), fuseau)
    return dt.datetime.fromisoformat(valeur["dateTime"]).astimezone(fuseau)


def _fusionner(cible: dict[str, Any], changements: dict[str, Any]) -> None:
    """Un PATCH de Google : les objets se fusionnent, un champ à `null` s'efface."""
    for cle, valeur in changements.items():
        if valeur is None:
            cible.pop(cle, None)
        elif isinstance(valeur, dict) and isinstance(cible.get(cle), dict):
            _fusionner(cible[cle], valeur)
        else:
            cible[cle] = valeur


def _dire(instant: dt.datetime, journee: bool, fuseau: ZoneInfo) -> dict[str, str]:
    if journee:
        return {"date": instant.date().isoformat()}
    return {"dateTime": instant.astimezone(fuseau).isoformat()}


class AgendaGoogle:
    """`agendas` : l'entrée de chaque agenda dans `calendarList` ; `evenements` : par agenda,
    les événements (une série n'y est qu'une fois, avec `recurrence`) ; `exceptions` : les fois
    changées ou supprimées d'une série, par identifiant de fois."""

    def __init__(self, doublure: DoublureGoogle) -> None:
        self.agendas: dict[str, dict[str, Any]] = {}
        self.evenements: dict[str, dict[str, dict[str, Any]]] = {}
        self.exceptions: dict[str, dict[str, Any]] = {}
        self.pannes: dict[str, tuple[int, str]] = {}  # agenda → (statut, raison) de sa lecture
        self._numero = 0
        doublure.route("GET", rf"{HOTE}/users/me/calendarList", self._liste)
        doublure.route("GET", rf"{HOTE}/calendars/([^/]+)/events", self._lire_la_periode)
        doublure.route("POST", rf"{HOTE}/calendars/([^/]+)/events", self._creer)
        doublure.route("PATCH", rf"{HOTE}/calendars/([^/]+)/events/([^/]+)", self._changer)
        doublure.route("DELETE", rf"{HOTE}/calendars/([^/]+)/events/([^/]+)", self._supprimer)

    def agenda(
        self, id_: str, nom: str, role: str = "owner", principal: bool = False, affiche: bool = True
    ) -> None:
        entree = {"id": id_, "summary": nom, "accessRole": role, "selected": affiche}
        if principal:
            entree["primary"] = True
        self.agendas[id_] = entree
        self.evenements.setdefault(id_, {})

    def evenement(
        self, agenda: str, id_: str, debut: dt.date, fin: dt.date, titre: str, **autres: Any
    ) -> dict[str, Any]:
        """Un événement, tel que David ou un autre l'a écrit (`autres` : location,
        description, attendees, organizer, recurrence, status…)."""
        evenement = {
            "id": id_,
            "etag": '"1"',
            "status": "confirmed",
            "summary": titre,
            "start": moment(debut),
            "end": moment(fin),
            "organizer": {"email": agenda, "self": True},
            **autres,
        }
        self.evenements[agenda][id_] = evenement
        return evenement

    def changer_ailleurs(self, agenda: str, id_: str, **champs: Any) -> None:
        """Un changement fait ailleurs (sur l'iPhone), à un événement ou à une seule fois d'une
        série : l'ETag change."""
        cible = self._trouver(agenda, id_)
        assert cible is not None
        cible.update(champs)
        cible["etag"] = self._etag_neuf()

    def _etag_neuf(self) -> str:
        self._numero += 1
        return f'"{self._numero + 100}"'

    def _liste(self, requete: httpx.Request) -> httpx.Response:
        return repondre(200, {"items": list(self.agendas.values())})

    def _fois(self, agenda: str, fuseau: ZoneInfo) -> list[dict[str, Any]]:
        """Toutes les fois de tous les événements de l'agenda, séries dépliées sur deux ans."""
        tout = []
        for evenement in self.evenements[agenda].values():
            regle = next(iter(evenement.get("recurrence", [])), "")
            if not regle:
                tout.append(evenement)
                continue
            parties = dict(p.split("=") for p in regle.removeprefix("RRULE:").split(";"))
            pas = dt.timedelta(days=7 if parties["FREQ"] == "WEEKLY" else 1)
            debut, fin = _lire(evenement["start"], fuseau), _lire(evenement["end"], fuseau)
            journee = "date" in evenement["start"]
            for rang in range(int(parties.get("COUNT", 730))):
                origine = debut + rang * pas
                marque = (
                    origine.strftime("%Y%m%d")
                    if journee
                    else (origine.astimezone(dt.UTC).strftime("%Y%m%dT%H%M%SZ"))
                )
                id_fois = f"{evenement['id']}_{marque}"
                fois = {k: v for k, v in evenement.items() if k != "recurrence"}
                fois.update(
                    id=id_fois,
                    etag=evenement["etag"][:-1] + f'-{marque}"',
                    recurringEventId=evenement["id"],
                    originalStartTime=_dire(origine, journee, fuseau),
                    start=_dire(origine, journee, fuseau),
                    end=_dire(origine + (fin - debut), journee, fuseau),
                )
                tout.append(self.exceptions.get(id_fois, fois))
        return [fois for fois in tout if fois.get("status") != "cancelled"]

    def _lire_la_periode(self, requete: httpx.Request, agenda: str) -> httpx.Response:
        agenda = unquote(agenda)
        if agenda not in self.evenements:  # retiré, ou plus partagé
            return erreur(404, "notFound")
        if agenda in self.pannes:
            return erreur(*self.pannes[agenda])
        params = requete.url.params
        assert params["singleEvents"] == "true" and params["orderBy"] == "startTime"
        fuseau = ZoneInfo(params.get("timeZone", "UTC"))
        de = dt.datetime.fromisoformat(params["timeMin"])
        a = dt.datetime.fromisoformat(params["timeMax"])
        fois = [
            f
            for f in self._fois(agenda, fuseau)
            if _lire(f["end"], fuseau) > de and _lire(f["start"], fuseau) < a
        ]
        fois.sort(key=lambda f: _lire(f["start"], fuseau))
        rendues = []
        for f in fois:
            journee = "date" in f["start"]
            rendue = dict(f)
            rendue["start"] = _dire(_lire(f["start"], fuseau), journee, fuseau)
            rendue["end"] = _dire(_lire(f["end"], fuseau), journee, fuseau)
            rendues.append(rendue)
        depart = int(params.get("pageToken", "0"))
        taille = int(params.get("maxResults", "250"))
        page = {"items": rendues[depart : depart + taille]}
        if depart + taille < len(rendues):
            page["nextPageToken"] = str(depart + taille)
        return repondre(200, page)

    def _refus(self, agenda: str) -> httpx.Response | None:
        if self.agendas[agenda]["accessRole"] in LECTURE_SEULE:
            return erreur(403, "forbidden")
        return None

    def _creer(self, requete: httpx.Request, agenda: str) -> httpx.Response:
        agenda = unquote(agenda)
        if (refus := self._refus(agenda)) is not None:
            return refus
        donnees = corps(requete)
        id_ = f"cree{len(self.evenements[agenda]) + 1}"
        evenement = {
            "id": id_,
            "etag": self._etag_neuf(),
            "status": "confirmed",
            "organizer": {"email": agenda, "self": True},
            **donnees,
        }
        self.evenements[agenda][id_] = evenement
        return repondre(200, evenement)

    def _trouver(self, agenda: str, id_: str) -> dict[str, Any] | None:
        if id_ in self.exceptions:
            return self.exceptions[id_]
        if id_ in self.evenements[agenda]:
            return self.evenements[agenda][id_]
        fuseau = ZoneInfo("Europe/Paris")
        trouvee = next((f for f in self._fois(agenda, fuseau) if f["id"] == id_), None)
        if trouvee is not None:  # une fois d'une série : elle devient une exception
            self.exceptions[id_] = dict(trouvee)
            return self.exceptions[id_]
        return None

    def _changer(self, requete: httpx.Request, agenda: str, id_: str) -> httpx.Response:
        agenda, id_ = unquote(agenda), unquote(id_)
        if (refus := self._refus(agenda)) is not None:
            return refus
        cible = self._trouver(agenda, id_)
        if cible is None or cible.get("status") == "cancelled":
            return erreur(404, "notFound")
        attendu = requete.headers.get("if-match")
        if attendu is not None and attendu != cible["etag"]:
            return erreur(412, "conditionNotMet")
        change = copy.deepcopy(cible)
        _fusionner(change, corps(requete))
        if any({"date", "dateTime"} <= set(change.get(bord, {})) for bord in ("start", "end")):
            return erreur(400, "invalid")  # « Invalid start time. »
        cible.clear()
        cible.update(change)
        cible["etag"] = self._etag_neuf()
        return repondre(200, cible)

    def _supprimer(self, requete: httpx.Request, agenda: str, id_: str) -> httpx.Response:
        agenda, id_ = unquote(agenda), unquote(id_)
        if (refus := self._refus(agenda)) is not None:
            return refus
        cible = self._trouver(agenda, id_)
        if cible is None or cible.get("status") == "cancelled":
            return erreur(410, "deleted")
        attendu = requete.headers.get("if-match")
        if attendu is not None and attendu != cible["etag"]:
            return erreur(412, "conditionNotMet")
        if id_ in self.exceptions:
            self.exceptions[id_]["status"] = "cancelled"
        else:
            del self.evenements[agenda][id_]
        return repondre(204)

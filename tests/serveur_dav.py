"""Un vrai serveur d'agendas et de contacts pour les tests des connecteurs iCloud (spec de
l'agenda et des contacts, §8) : Radicale, dans un fil, sur un port libre de 127.0.0.1, rangé
dans un dossier temporaire. Jamais le vrai iCloud.

Le serveur demande un identifiant et un mot de passe, comme iCloud. `interdire` lui fait
refuser l'écriture dans un agenda (un agenda partagé en lecture seule), ce que Radicale seul
ne sait pas faire ; `ecrits` note chaque écriture reçue telle quelle, avant que Radicale ne
range (et ne complète) ce qu'il garde. Les tests construisent le connecteur avec l'adresse de ce
serveur (`charger` et `appeler` : aides_connecteurs.py).
"""

from __future__ import annotations

import io
import logging
import re
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from wsgiref.simple_server import WSGIRequestHandler, make_server

import httpx
import radicale
import radicale.config
from aides_connecteurs import appeler, charger  # noqa: F401 — les tests iCloud les prennent ici

IDENTIFIANT = "david@example.com"
MOT_DE_PASSE = "abcd-efgh-ijkl-mnop"

_AGENDA = """<?xml version="1.0" encoding="utf-8"?>
<c:mkcalendar xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">
  <d:set><d:prop>
    <d:displayname>{nom}</d:displayname>
    <c:supported-calendar-component-set>
      <c:comp name="{composant}"/>
    </c:supported-calendar-component-set>
  </d:prop></d:set>
</c:mkcalendar>"""

_CARNET = """<?xml version="1.0" encoding="utf-8"?>
<d:mkcol xmlns:d="DAV:" xmlns:a="urn:ietf:params:xml:ns:carddav">
  <d:set><d:prop>
    <d:resourcetype><d:collection/><a:addressbook/></d:resourcetype>
    <d:displayname>{nom}</d:displayname>
  </d:prop></d:set>
</d:mkcol>"""


class _Muet(WSGIRequestHandler):
    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass


class ServeurDav:
    """Radicale, avec un compte : `url` est sa racine, comme `https://caldav.icloud.com/`."""

    def __init__(self, dossier: Path) -> None:
        (dossier / "comptes").write_text(f"{IDENTIFIANT}:{MOT_DE_PASSE}\n")
        reglages = radicale.config.load()
        reglages.update(
            {
                "storage": {
                    "filesystem_folder": str(dossier / "collections"),
                    "_filesystem_fsync": "False",  # un dossier temporaire : pas besoin
                },
                "auth": {
                    "type": "htpasswd",
                    "htpasswd_filename": str(dossier / "comptes"),
                    "htpasswd_encryption": "plain",
                    "delay": "0",  # Radicale ralentit exprès les mots de passe faux
                },
                "rights": {"type": "owner_only"},
            },
            "tests",
            privileged=True,
        )
        logging.getLogger("radicale").setLevel(logging.ERROR)
        self._radicale = radicale.Application(reglages)
        self._interdits: list[str] = []
        self.ecrits: list[tuple[str, str, dict[str, str], str]] = []
        self._http = make_server("127.0.0.1", 0, self._application, handler_class=_Muet)
        self.url = f"http://127.0.0.1:{self._http.server_port}/"
        self.maison = f"{self.url}{IDENTIFIANT}/"
        self._fil = threading.Thread(target=self._http.serve_forever, args=(0.05,), daemon=True)
        self._fil.start()
        self.client = httpx.Client(auth=(IDENTIFIANT, MOT_DE_PASSE), timeout=5)

    def _application(self, environ, start_response):
        chemin = environ.get("PATH_INFO", "")
        ecrit = environ["REQUEST_METHOD"] in {"PUT", "DELETE"}
        if ecrit:
            corps = environ["wsgi.input"].read(int(environ.get("CONTENT_LENGTH") or 0))
            environ["wsgi.input"] = io.BytesIO(corps)
            conditions = {
                "If-Match": environ.get("HTTP_IF_MATCH", ""),
                "If-None-Match": environ.get("HTTP_IF_NONE_MATCH", ""),
            }
            self.ecrits.append((environ["REQUEST_METHOD"], chemin, conditions, corps.decode()))
        if ecrit and any(chemin.startswith(interdit) for interdit in self._interdits):
            start_response("403 Forbidden", [("Content-Type", "text/plain")])
            return [b"lecture seule"]
        return self._radicale(environ, start_response)

    def arreter(self) -> None:
        self.client.close()
        self._http.shutdown()
        self._http.server_close()

    def creer_agenda(self, chemin: str, nom: str, composant: str = "VEVENT") -> str:
        url = f"{self.maison}{chemin}/"
        corps = _AGENDA.format(nom=nom, composant=composant)
        reponse = self.client.request("MKCALENDAR", url, content=corps)
        assert reponse.status_code == 201, reponse.text
        return url

    def creer_carnet(self, chemin: str, nom: str) -> str:
        url = f"{self.maison}{chemin}/"
        reponse = self.client.request("MKCOL", url, content=_CARNET.format(nom=nom))
        assert reponse.status_code == 201, reponse.text
        return url

    def deposer(self, url_collection: str, nom: str, contenu: str) -> str:
        """Dépose un événement (.ics) ou une fiche (.vcf), et rend son ETag."""
        genre = "text/vcard" if nom.endswith(".vcf") else "text/calendar"
        reponse = self.client.put(
            url_collection + nom,
            content=contenu.replace("\n", "\r\n").encode(),
            headers={"Content-Type": f"{genre}; charset=utf-8"},
        )
        assert reponse.status_code in {201, 204}, reponse.text
        return reponse.headers["etag"]

    def lire(self, url: str) -> str | None:
        reponse = self.client.get(url)
        return None if reponse.status_code == 404 else reponse.text

    def contenus(self, url_collection: str) -> list[str]:
        """Les événements ou les fiches d'une collection, tels que le serveur les garde."""
        reponse = self.client.request("PROPFIND", url_collection, headers={"Depth": "1"})
        chemins = re.findall(r"<href>([^<]+\.(?:ics|vcf))</href>", reponse.text)
        return [self.client.get(httpx.URL(self.url).join(chemin)).text for chemin in chemins]

    def interdire(self, url_collection: str) -> None:
        """L'écriture dans cette collection est refusée (403), comme un agenda partagé en
        lecture seule."""
        self._interdits.append(httpx.URL(url_collection).path)


@contextmanager
def serveur_dav(dossier: Path) -> Iterator[ServeurDav]:
    serveur = ServeurDav(dossier)
    try:
        yield serveur
    finally:
        serveur.arreter()


def reglages(**autres: str) -> dict[str, str]:
    """Les réglages des connecteurs iCloud, avec le compte du serveur de test."""
    return {
        "ATLAS_ICLOUD_IDENTIFIANT": IDENTIFIANT,
        "ATLAS_ICLOUD_MOT_DE_PASSE": MOT_DE_PASSE,
        "ATLAS_ICLOUD_AGENDA": "Domicile",
        **autres,
    }


def ics(*evenements: str) -> str:
    """Un calendrier iCalendar autour de ses événements."""
    return (
        "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//Atlas//tests//FR\n"
        + "".join(evenements)
        + ("END:VCALENDAR\n")
    )


def evenement(uid: str, debut: str, fin: str, titre: str, *lignes: str) -> str:
    """Un VEVENT ; `debut` et `fin` à la façon d'iCalendar (« ;TZID=Europe/Paris:20261001T150000 »,
    « ;VALUE=DATE:20261001 », « :20261001T080000Z »)."""
    suite = "".join(f"{ligne}\n" for ligne in lignes)
    return (
        f"BEGIN:VEVENT\nUID:{uid}\nDTSTAMP:20260901T000000Z\nDTSTART{debut}\nDTEND{fin}\n"
        f"SUMMARY:{titre}\n{suite}END:VEVENT\n"
    )


def paris(moment: str) -> str:
    return f";TZID=Europe/Paris:{moment}"


def jour(date: str) -> str:
    return f";VALUE=DATE:{date}"

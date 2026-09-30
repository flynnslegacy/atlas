"""Le client CardDAV des contacts iCloud (spec de l'agenda et des contacts, §6).

Comme pour l'agenda : la racine d'iCloud donne le « principal » de David, le principal son
dossier de carnets, puis ses carnets. Chaque carnet se liste, puis ses fiches se lisent par
paquets de cent (`addressbook-multiget`). Les fiches restent dix minutes en mémoire vive, jamais
sur le disque ; on n'en garde ni les notes ni les photos.

Tout est synchrone (httpx) : le connecteur appelle ce client par `asyncio.to_thread`. Le code
CardDAV est propre à ce dossier : un connecteur ne dépend pas d'un autre.
"""

from __future__ import annotations

import datetime as dt
import logging
import re
import time
import unicodedata
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urljoin
from xml.sax.saxutils import escape

import httpx
import vobject

from atlas_core.connecteurs import ErreurConnecteur

_journal = logging.getLogger(__name__)

ADRESSE = "https://contacts.icloud.com/"
DELAI_S = 15.0
GARDE_S = 600.0
PAQUET = 100
REFUS = (
    "iCloud refuse l'identifiant ou le mot de passe d'app : vérifie-les dans Paramètres › "
    "Connecteurs › Réglages."
)
MUET = "iCloud ne répond pas : réessaie dans un moment."

_DAV = "{DAV:}"
_CARDDAV = "{urn:ietf:params:xml:ns:carddav}"
_XML = {"Content-Type": "application/xml; charset=utf-8"}
_PROPFIND = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<d:propfind xmlns:d="DAV:" xmlns:a="urn:ietf:params:xml:ns:carddav">'
    "<d:prop>{}</d:prop></d:propfind>"
)
_MULTIGET = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<a:addressbook-multiget xmlns:d="DAV:" xmlns:a="urn:ietf:params:xml:ns:carddav">'
    "<d:prop><d:getetag/><a:address-data/></d:prop>{}</a:addressbook-multiget>"
)

# Les libellés d'Apple (`item1.X-ABLabel`), puis les types de la norme (`TYPE=CELL`).
LIBELLES_APPLE = {
    "mobile": "mobile",
    "iphone": "iPhone",
    "home": "domicile",
    "work": "travail",
    "main": "principal",
    "homefax": "fax domicile",
    "workfax": "fax travail",
    "otherfax": "fax",
    "pager": "bip",
    "school": "école",
    "other": "autre",
}
TYPES = {
    "CELL": "mobile",
    "IPHONE": "iPhone",
    "HOME": "domicile",
    "WORK": "travail",
    "MAIN": "principal",
    "FAX": "fax",
    "PAGER": "bip",
    "OTHER": "autre",
}
_APPLE = re.compile(r"_\$!<(.+)>!\$_")
_ANNIVERSAIRE = re.compile(r"(\d{4}|--)-?(\d{2})-?(\d{2})(?:T.*)?")
ANNEE_INCONNUE = 1604  # l'année qu'Apple écrit quand David ne l'a pas donnée


class ErreurDav(Exception):
    """Une réponse inattendue d'iCloud : le Core la note, et Claude apprend l'échec."""


@dataclass(frozen=True)
class Coordonnee:
    libelle: str  # « mobile », « travail », « Club » ; vide sans libellé
    valeur: str


@dataclass(frozen=True)
class Anniversaire:
    mois: int
    jour: int
    annee: int | None = None


@dataclass(frozen=True)
class Fiche:
    nom: str
    surnom: str = ""
    entreprise: str = ""
    telephones: tuple[Coordonnee, ...] = ()
    mails: tuple[Coordonnee, ...] = ()
    adresses: tuple[Coordonnee, ...] = ()
    anniversaire: Anniversaire | None = None


def normaliser(texte: str) -> str:
    """Sans accents ni majuscules : « Élodie » et « elodie » se valent."""
    decompose = unicodedata.normalize("NFKD", texte)
    return "".join(c for c in decompose if not unicodedata.combining(c)).casefold().strip()


def _libelle(propriete, libelles: dict[str, str]) -> str:
    etiquette = libelles.get(propriete.group or "")
    if etiquette is not None:
        apple = _APPLE.fullmatch(etiquette)
        if apple is None:
            return etiquette
        return LIBELLES_APPLE.get(apple[1].casefold(), apple[1].casefold())
    for genre in propriete.params.get("TYPE", []):
        if genre.upper() in TYPES:
            return TYPES[genre.upper()]
    return ""


def _adresse(valeur) -> str:
    """« 12 rue des Lilas, 69003 Lyon, France »."""
    rue = ", ".join(ligne for ligne in str(valeur.street or "").splitlines() if ligne.strip())
    ville = " ".join(morceau for morceau in (valeur.code, valeur.city) if morceau)
    morceaux = [rue, ville, str(valeur.region or ""), str(valeur.country or "")]
    return ", ".join(morceau.strip() for morceau in morceaux if morceau and morceau.strip())


def _anniversaire(carte) -> Anniversaire | None:
    """`1990-05-12`, `19900512`, `--0512`, ou l'année 1604 d'Apple : sans année."""
    proprietes = carte.contents.get("bday")
    if not proprietes:
        return None
    lu = _ANNIVERSAIRE.fullmatch(str(proprietes[0].value).strip())
    if lu is None:
        return None
    mois, jour = int(lu[2]), int(lu[3])
    try:
        dt.date(2000, mois, jour)  # une année bissextile : le 29 février est une vraie date
    except ValueError:
        return None
    sans_annee = lu[1] == "--" or int(lu[1]) == ANNEE_INCONNUE
    return Anniversaire(mois, jour, None if sans_annee else int(lu[1]))


def lire_fiche(texte: str) -> Fiche:
    """Une fiche vCard, sans ses notes ni sa photo."""
    carte = vobject.readOne(texte)
    contenu = carte.contents
    libelles = {p.group: str(p.value) for p in contenu.get("x-ablabel", []) if p.group}

    def premier(nom: str) -> str:
        valeurs = contenu.get(nom, [])
        return str(valeurs[0].value).strip() if valeurs else ""

    def coordonnees(nom: str, lire: Callable = lambda valeur: str(valeur).strip()):
        return tuple(Coordonnee(_libelle(p, libelles), lire(p.value)) for p in contenu.get(nom, []))

    organisation = contenu.get("org", [])
    entreprise = " ".join(organisation[0].value).strip() if organisation else ""
    mails = coordonnees("email")
    nom = premier("fn") or entreprise or (mails[0].valeur if mails else "(sans nom)")
    return Fiche(
        nom=nom,
        surnom=premier("nickname"),
        entreprise=entreprise,
        telephones=coordonnees("tel"),
        mails=mails,
        adresses=coordonnees("adr", _adresse),
        anniversaire=_anniversaire(carte),
    )


class Carnet:
    """Les contacts iCloud de David. `adresse` : la racine CardDAV (celle d'iCloud, écrite ici ;
    les tests passent celle de leur serveur, et leur horloge)."""

    def __init__(
        self,
        identifiant: str,
        mot_de_passe: str,
        *,
        adresse: str = ADRESSE,
        delai_s: float = DELAI_S,
        horloge: Callable[[], float] = time.monotonic,
    ) -> None:
        self._adresse = adresse
        self._horloge = horloge
        self._http = httpx.Client(
            auth=(identifiant, mot_de_passe), timeout=delai_s, follow_redirects=True
        )
        self._fiches: list[Fiche] = []
        self._lues_a: float | None = None

    def fiches(self) -> list[Fiche]:
        """Toutes les fiches, par nom ; relues au plus toutes les dix minutes."""
        maintenant = self._horloge()
        if self._lues_a is None or maintenant - self._lues_a >= GARDE_S:
            self._fiches = sorted(self._lire(), key=lambda fiche: normaliser(fiche.nom))
            self._lues_a = maintenant
        return self._fiches

    def _lire(self) -> list[Fiche]:
        principal = self._lien(self._adresse, "d:current-user-principal", _DAV)
        maison = self._lien(principal, "a:addressbook-home-set", _CARDDAV)
        fiches = []
        for carnet in self._carnets(maison):
            cartes = self._cartes(carnet)
            for debut in range(0, len(cartes), PAQUET):
                fiches += self._paquet(carnet, cartes[debut : debut + PAQUET])
        return fiches

    def _carnets(self, maison: str) -> list[str]:
        reponse = self._propfind(maison, "<d:resourcetype/>", "1")
        return [
            urljoin(str(reponse.url), href)
            for href, proprietes in self._multistatus(reponse)
            if proprietes.find(f"{_DAV}resourcetype/{_CARDDAV}addressbook") is not None
        ]

    def _cartes(self, carnet: str) -> list[str]:
        """Les adresses des fiches d'un carnet, telles que le serveur les écrit."""
        reponse = self._propfind(carnet, "<d:resourcetype/><d:getetag/>", "1")
        return [
            href
            for href, proprietes in self._multistatus(reponse)
            if proprietes.find(f"{_DAV}resourcetype/{_DAV}collection") is None
        ]

    def _paquet(self, carnet: str, cartes: list[str]) -> list[Fiche]:
        demande = "".join(f"<d:href>{escape(href)}</d:href>" for href in cartes)
        corps = _MULTIGET.format(demande)
        reponse = self._envoyer("REPORT", carnet, corps, {"Depth": "1", **_XML})
        fiches = []
        for href, proprietes in self._multistatus(reponse):
            texte = proprietes.findtext(f"{_CARDDAV}address-data")
            if not texte:
                continue
            try:
                fiches.append(lire_fiche(texte))
            except Exception as e:  # noqa: BLE001 — une fiche illisible n'empêche pas les autres
                _journal.warning("fiche illisible, laissée de côté : %s (%s)", href, e)
        return fiches

    def _lien(self, url: str, propriete: str, espace: str) -> str:
        reponse = self._propfind(url, f"<{propriete}/>", "0")
        nom = propriete.split(":", 1)[1]
        for _, proprietes in self._multistatus(reponse):
            href = proprietes.findtext(f"{espace}{nom}/{_DAV}href")
            if href:
                return urljoin(str(reponse.url), href.strip())
        raise ErreurDav(f"{nom} introuvable à {url}")

    def _propfind(self, url: str, proprietes: str, profondeur: str) -> httpx.Response:
        corps = _PROPFIND.format(proprietes)
        return self._envoyer("PROPFIND", url, corps, {"Depth": profondeur, **_XML})

    def _multistatus(self, reponse: httpx.Response) -> list[tuple[str, ET.Element]]:
        """Chaque réponse d'un 207 : son adresse telle que le serveur l'écrit, et ses
        propriétés trouvées."""
        if reponse.status_code != 207:
            raise ErreurDav(f"{reponse.request.method} : {reponse.status_code}")
        resultats = []
        for element in ET.fromstring(reponse.content).iter(f"{_DAV}response"):
            proprietes = ET.Element("prop")
            for propstat in element.iter(f"{_DAV}propstat"):
                trouvees = propstat.find(f"{_DAV}prop")
                if trouvees is not None and " 200 " in propstat.findtext(f"{_DAV}status", ""):
                    proprietes.extend(trouvees)
            resultats.append((element.findtext(f"{_DAV}href", "").strip(), proprietes))
        return resultats

    def _envoyer(
        self, methode: str, url: str, corps: str, entetes: dict[str, str]
    ) -> httpx.Response:
        try:
            reponse = self._http.request(methode, url, content=corps, headers=entetes)
        except httpx.TransportError:  # injoignable, ou muet au-delà du délai
            raise ErreurConnecteur(MUET) from None
        if reponse.status_code == 401:
            raise ErreurConnecteur(REFUS)
        return reponse

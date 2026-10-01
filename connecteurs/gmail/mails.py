"""Les mails, tels que l'API Gmail les rend (spec de Gmail et de Google Agenda, §6.2) : leurs
en-têtes décodés, leur texte (la partie texte, sinon la partie HTML convertie en texte), leurs
pièces jointes nommées et jamais ouvertes ; et les mails qu'Atlas écrit (§6.3) : du texte
simple, sans copie cachée ni pièce jointe, une réponse gardant son fil. Rien ici ne parle au
réseau."""

from __future__ import annotations

import base64
import datetime as dt
import html
import re
from dataclasses import dataclass
from email import message_from_bytes, policy
from email.errors import HeaderParseError
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import parseaddr
from html.parser import HTMLParser
from typing import Any

from atlas_core.connecteurs import ErreurConnecteur

_ADRESSE = re.compile(r"[^@\s<>,;\"]+@[^@\s<>,;\"]+\.[^@\s<>,;\"]+")
MAX_TEXTE = 8000
COUPE = "\n… (la suite est coupée)"
EN_GMAIL = "Ce brouillon a une copie cachée ou une pièce jointe : envoie-le depuis Gmail."
_BLOCS = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "table"}
_MUETS = {"script", "style", "head", "title"}


@dataclass(frozen=True)
class Resume:
    """Un mail dans une liste : de quoi le reconnaître."""

    id: str
    date: dt.datetime
    expediteur: str
    objet: str
    extrait: str
    non_lu: bool = False
    important: bool = False
    piece_jointe: bool = False


@dataclass(frozen=True)
class Mail:
    id: str
    fil: str
    de: str
    a: str
    copie: str
    repondre_a: str
    date: dt.datetime
    objet: str
    texte: str
    message_id: str = ""
    references: str = ""
    pieces: tuple[tuple[str, int], ...] = ()


def decoder(valeur: str) -> str:
    """Un en-tête, encodé ou non (`=?UTF-8?B?…?=`)."""
    try:
        return str(make_header(decode_header(valeur))).strip()
    except (HeaderParseError, LookupError, ValueError):  # mal encodé, jeu de caractères inconnu
        return valeur.strip()


def _entetes(partie: dict[str, Any]) -> dict[str, str]:
    """Les en-têtes d'une partie, sans tenir compte des majuscules ; le premier l'emporte."""
    entetes: dict[str, str] = {}
    for entete in partie.get("headers", []):
        entetes.setdefault(str(entete.get("name", "")).casefold(), str(entete.get("value", "")))
    return entetes


def nom_ou_adresse(valeur: str) -> str:
    nom, adresse = parseaddr(decoder(valeur))
    if nom.startswith("=?") and adresse:  # un nom mal encodé ne se dit pas
        return adresse
    return nom or adresse or decoder(valeur)


def _date(donnees: dict[str, Any], fuseau: dt.tzinfo) -> dt.datetime:
    millisecondes = int(donnees.get("internalDate", 0))
    return dt.datetime.fromtimestamp(millisecondes / 1000, fuseau)


def _charset(partie: dict[str, Any]) -> str:
    genre = _entetes(partie).get("content-type", "")
    for morceau in genre.split(";")[1:]:
        cle, _, valeur = morceau.strip().partition("=")
        if cle.casefold() == "charset":
            return valeur.strip('"') or "utf-8"
    return "utf-8"


def _contenu(partie: dict[str, Any]) -> str:
    donnees = str(partie.get("body", {}).get("data", ""))
    brut = base64.urlsafe_b64decode(donnees + "=" * (-len(donnees) % 4))
    try:
        return brut.decode(_charset(partie), errors="replace")
    except LookupError:  # un jeu de caractères inconnu
        return brut.decode("utf-8", errors="replace")


def _parties(partie: dict[str, Any]) -> list[dict[str, Any]]:
    """Toutes les parties d'un mail, à plat."""
    tout = [partie]
    for enfant in partie.get("parts", []) or []:
        tout += _parties(enfant)
    return tout


class _EnTexte(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.morceaux: list[str] = []
        self._muet = 0
        self._lien: str | None = None

    def handle_starttag(self, balise: str, attributs: list[tuple[str, str | None]]) -> None:
        if balise in _MUETS:
            self._muet += 1
        elif balise in _BLOCS:
            self.morceaux.append("\n")
        elif balise == "a":
            self._lien = dict(attributs).get("href") or None

    def handle_endtag(self, balise: str) -> None:
        if balise in _MUETS:
            self._muet = max(0, self._muet - 1)
        elif balise in _BLOCS:
            self.morceaux.append("\n")
        elif balise == "a" and self._lien:
            if self._lien.startswith(("http://", "https://")):
                self.morceaux.append(f" ({self._lien})")
            self._lien = None

    def handle_data(self, donnees: str) -> None:
        if not self._muet:
            self.morceaux.append(donnees)


def en_texte(source: str) -> str:
    """Du HTML en texte : sans balises ni scripts, un paragraphe par ligne, les liens en clair."""
    lecteur = _EnTexte()
    lecteur.feed(source)
    lignes = (" ".join(ligne.split()) for ligne in "".join(lecteur.morceaux).splitlines())
    texte, vide = [], True
    for ligne in lignes:
        if ligne or not vide:
            texte.append(ligne)
        vide = not ligne
    return "\n".join(texte).strip()


def lire_mail(donnees: dict[str, Any], fuseau: dt.tzinfo) -> Mail:
    """Un mail au format complet de l'API Gmail (`format=full`)."""
    racine = donnees.get("payload", {})
    entetes = _entetes(racine)
    parties = _parties(racine)
    corps = [p for p in parties if not p.get("filename") and "data" in p.get("body", {})]
    texte_brut = next((p for p in corps if p.get("mimeType") == "text/plain"), None)
    en_html = next((p for p in corps if p.get("mimeType") == "text/html"), None)
    if texte_brut is not None:
        texte = _contenu(texte_brut).strip()
    elif en_html is not None:
        texte = en_texte(_contenu(en_html))
    else:
        texte = ""
    if len(texte) > MAX_TEXTE:
        texte = texte[:MAX_TEXTE] + COUPE
    pieces = tuple(
        (str(p["filename"]), int(p.get("body", {}).get("size", 0)))
        for p in parties
        if p.get("filename")
    )
    return Mail(
        id=str(donnees["id"]),
        fil=str(donnees.get("threadId", "")),
        de=decoder(entetes.get("from", "")),
        a=decoder(entetes.get("to", "")),
        copie=decoder(entetes.get("cc", "")),
        repondre_a=decoder(entetes.get("reply-to", "")),
        date=_date(donnees, fuseau),
        objet=decoder(entetes.get("subject", "")) or "(sans objet)",
        texte=texte,
        message_id=entetes.get("message-id", ""),
        references=entetes.get("references", ""),
        pieces=pieces,
    )


def lire_resume(donnees: dict[str, Any], fuseau: dt.tzinfo) -> Resume:
    """Un mail au format réduit de l'API Gmail (`format=metadata`)."""
    racine = donnees.get("payload", {})
    entetes = _entetes(racine)
    libelles = set(donnees.get("labelIds", []))
    extrait = " ".join(html.unescape(str(donnees.get("snippet", ""))).split())
    return Resume(
        id=str(donnees["id"]),
        date=_date(donnees, fuseau),
        expediteur=nom_ou_adresse(entetes.get("from", "")),
        objet=decoder(entetes.get("subject", "")) or "(sans objet)",
        extrait=extrait if len(extrait) <= 100 else extrait[:99].rstrip() + "…",
        non_lu="UNREAD" in libelles,
        important="IMPORTANT" in libelles,
        piece_jointe=racine.get("mimeType") == "multipart/mixed",
    )


def taille(octets: int) -> str:
    """« 850 octets », « 120 Ko », « 2,3 Mo »."""
    if octets < 1000:
        return f"{octets} octets"
    if octets < 1_000_000:
        return f"{round(octets / 1000)} Ko"
    return f"{octets / 1_000_000:.1f} Mo".replace(".", ",")


@dataclass(frozen=True)
class Brouillon:
    """Un mail qu'Atlas écrit : ses adresses, exactes, et, pour une réponse, son fil."""

    a: tuple[str, ...]
    objet: str
    texte: str
    copie: tuple[str, ...] = ()
    fil: str = ""
    en_reponse_a: str = ""
    references: str = ""


def _morceaux(valeur: str) -> list[str]:
    """Une liste d'adresses, coupée aux virgules qui ne sont ni entre guillemets (« "Martin,
    Paul" <…> », comme l'écrit Outlook) ni entre chevrons."""
    morceaux, courant, guillemets, chevrons = [], "", False, False
    for caractere in valeur:
        if caractere == '"':
            guillemets = not guillemets
        elif caractere in "<>" and not guillemets:
            chevrons = caractere == "<"
        elif caractere == "," and not (guillemets or chevrons):
            morceaux.append(courant)
            courant = ""
            continue
        courant += caractere
    return [*morceaux, courant]


def verifier_adresses(valeur: object, cle: str) -> tuple[str, ...]:
    """Des adresses données par Claude (« paul@exemple.fr, Marie <marie@exemple.fr> ») ;
    `ErreurConnecteur` si l'une n'en est pas une."""
    trouvees = []
    for morceau in _morceaux(str(valeur or "")):
        if not (morceau := morceau.strip()):
            continue
        _, adresse = parseaddr(morceau)
        if not _ADRESSE.fullmatch(adresse):
            raise ErreurConnecteur(
                f"{cle} : « {morceau} » n'est pas une adresse mail ; par exemple paul@exemple.fr."
            )
        trouvees.append(adresse)
    return tuple(trouvees)


def en_reponse(mail: Mail, a: tuple[str, ...] = ()) -> Brouillon:
    """Une réponse à `mail`, sans texte encore : aux adresses `a` que Claude donne, sinon à
    l'expéditeur (ou à son adresse de réponse), dans le même fil, l'objet précédé de « Re: »."""
    destinataire = a or verifier_adresses(mail.repondre_a or mail.de, "a")
    objet = mail.objet if mail.objet.casefold().startswith("re:") else f"Re: {mail.objet}"
    references = " ".join(r for r in (mail.references, mail.message_id) if r)
    return Brouillon(
        a=destinataire,
        objet=objet,
        texte="",
        fil=mail.fil,
        en_reponse_a=mail.message_id,
        references=references,
    )


def lire_brouillon(raw: str, fil: str = "") -> Brouillon:
    """Un brouillon tel qu'il est dans Gmail (`format=raw`), que David a pu retoucher : ce qui
    partira. `ErreurConnecteur` s'il porte une copie cachée ou une pièce jointe, qu'Atlas ne lit
    pas à David. `fil` : celui qu'Atlas connaît, quand il a préparé une réponse."""
    brut = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    message = message_from_bytes(brut, policy=policy.default)
    if message["Bcc"] or any(True for _ in message.iter_attachments()):
        raise ErreurConnecteur(EN_GMAIL)
    corps = message.get_body(preferencelist=("plain", "html"))
    texte = "" if corps is None else corps.get_content()
    if corps is not None and corps.get_content_type() == "text/html":
        texte = en_texte(texte)

    def adresses(nom: str) -> tuple[str, ...]:
        entete = message[nom]
        return tuple(adresse.addr_spec for adresse in entete.addresses) if entete else ()

    return Brouillon(
        a=adresses("To"),
        objet=str(message["Subject"] or ""),
        texte=texte.strip(),
        copie=adresses("Cc"),
        fil=fil,
        en_reponse_a=str(message["In-Reply-To"] or ""),
        references=str(message["References"] or ""),
    )


def composer(brouillon: Brouillon) -> str:
    """Le mail au format que l'API Gmail attend (`raw`) : du texte simple en UTF-8, depuis
    l'adresse de David (Gmail la met), sans copie cachée ni pièce jointe."""
    message = EmailMessage()
    message["To"] = ", ".join(brouillon.a)
    if brouillon.copie:
        message["Cc"] = ", ".join(brouillon.copie)
    message["Subject"] = brouillon.objet
    if brouillon.en_reponse_a:
        message["In-Reply-To"] = brouillon.en_reponse_a
        message["References"] = brouillon.references
    message.set_content(brouillon.texte)
    return base64.urlsafe_b64encode(message.as_bytes()).decode()

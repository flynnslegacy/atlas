"""L'API Gmail, dans la doublure de Google (doublure_google.py), comme sa documentation la décrit :
des mails au format de l'API (des parties MIME, leur contenu en base64url, leurs libellés), la
recherche (les mots que les tests emploient : `in:inbox`, `is:unread`, `is:important`,
`category:primary`, `from:`, et du texte libre), et les formats complet et réduit d'un mail.
"""

from __future__ import annotations

import base64
import datetime as dt
from typing import Any

import httpx
from doublure_google import DoublureGoogle, erreur, repondre

HOTE = r"gmail\.googleapis\.com/gmail/v1/users/me"
DAVID = "david@example.com"


def _base64(texte: str | bytes, charset: str = "utf-8") -> str:
    brut = texte.encode(charset) if isinstance(texte, str) else texte
    return base64.urlsafe_b64encode(brut).decode().rstrip("=")


def partie(genre: str, contenu: str, charset: str = "utf-8", nom: str = "") -> dict[str, Any]:
    """Une partie MIME au format de l'API ; avec un `nom`, une pièce jointe."""
    donnees = _base64(contenu, charset)
    entetes = [{"name": "Content-Type", "value": f"{genre}; charset={charset}"}]
    if nom:
        return {
            "mimeType": genre,
            "filename": nom,
            "headers": entetes,
            "body": {"attachmentId": f"pj-{nom}", "size": len(contenu)},
        }
    return {
        "mimeType": genre,
        "filename": "",
        "headers": entetes,
        "body": {"data": donnees, "size": len(contenu)},
    }


class Gmail:
    """`mails` : les mails de la boîte, par identifiant."""

    def __init__(self, doublure: DoublureGoogle) -> None:
        self.mails: dict[str, dict[str, Any]] = {}
        doublure.route("GET", rf"{HOTE}/messages", self._chercher)
        doublure.route("GET", rf"{HOTE}/messages/([^/]+)", self._lire)

    def mail(
        self,
        id_: str,
        de: str,
        objet: str | None,
        texte: str = "",
        *,
        date: dt.datetime,
        a: str = DAVID,
        copie: str = "",
        libelles: tuple[str, ...] = ("INBOX", "UNREAD"),
        html: str = "",
        pieces: tuple[tuple[str, str], ...] = (),
        charset: str = "utf-8",
        entetes: tuple[tuple[str, str], ...] = (),
        fil: str = "",
    ) -> dict[str, Any]:
        """Un mail reçu : du texte, du HTML, ou les deux (une alternative), avec des pièces
        jointes (nom, contenu) : alors un « multipart/mixed ». Sans objet (None), pas d'en-tête
        Subject ; sans texte ni HTML, seulement les pièces jointes."""
        corps = []
        if texte:
            corps.append(partie("text/plain", texte, charset))
        if html:
            corps.append(partie("text/html", html, charset))
        racine: dict[str, Any] = (
            corps[0] if len(corps) == 1 else {"mimeType": "multipart/alternative", "parts": corps}
        )
        if pieces:
            jointes = [partie("application/octet-stream", c, nom=n) for n, c in pieces]
            racine = {
                "mimeType": "multipart/mixed",
                "parts": [racine, *jointes] if corps else jointes,
            }
        en_tetes = [
            ("From", de),
            ("To", a),
            *([("Subject", objet)] if objet is not None else []),
            ("Message-ID", f"<{id_}@exemple.fr>"),
        ]
        if copie:
            en_tetes.append(("Cc", copie))
        racine["headers"] = [
            {"name": n, "value": v} for n, v in [*en_tetes, *entetes]
        ] + racine.get("headers", [])
        extrait = (texte or html)[:120].replace("'", "&#39;")
        message = {
            "id": id_,
            "threadId": fil or f"fil-{id_}",
            "labelIds": list(libelles),
            "snippet": extrait,
            "internalDate": str(int(date.timestamp() * 1000)),
            "payload": racine,
        }
        self.mails[id_] = message
        return message

    def _correspond(self, message: dict[str, Any], requete: str) -> bool:
        libelles = set(message["labelIds"])
        entetes = {e["name"].casefold(): e["value"] for e in message["payload"]["headers"]}
        for mot in requete.split():
            if mot == "in:inbox" and "INBOX" not in libelles:
                return False
            if mot == "is:unread" and "UNREAD" not in libelles:
                return False
            if mot == "is:important" and "IMPORTANT" not in libelles:
                return False
            if mot.startswith("from:") and mot[5:].casefold() not in entetes["from"].casefold():
                return False
            if ":" not in mot:
                objet = entetes.get("subject", "")
                ensemble = f"{objet} {message['snippet']} {entetes['from']}"
                if mot.casefold() not in ensemble.casefold():
                    return False
        return True

    def _chercher(self, requete: httpx.Request) -> httpx.Response:
        params = requete.url.params
        trouves = [m for m in self.mails.values() if self._correspond(m, params.get("q", ""))]
        trouves.sort(key=lambda m: -int(m["internalDate"]))
        taille = int(params.get("maxResults", "100"))
        page: dict[str, Any] = {"resultSizeEstimate": len(trouves)}
        if trouves:
            page["messages"] = [
                {"id": m["id"], "threadId": m["threadId"]} for m in trouves[:taille]
            ]
        if len(trouves) > taille:
            page["nextPageToken"] = "suite"
        return repondre(200, page)

    def _lire(self, requete: httpx.Request, id_: str) -> httpx.Response:
        message = self.mails.get(id_)
        if message is None:
            return erreur(404, "notFound")
        params = requete.url.params
        if params.get("format") != "metadata":
            return repondre(200, message)
        voulus = {n.casefold() for n in params.get_list("metadataHeaders")}
        racine = message["payload"]
        entetes = [e for e in racine["headers"] if e["name"].casefold() in voulus]
        reduit = {k: v for k, v in message.items() if k != "payload"}
        reduit["payload"] = {"mimeType": racine["mimeType"], "headers": entetes}
        return repondre(200, reduit)

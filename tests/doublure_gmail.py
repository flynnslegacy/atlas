"""L'API Gmail, dans la doublure de Google (doublure_google.py), comme sa documentation la décrit :
des mails au format de l'API (des parties MIME, leur contenu en base64url, leurs libellés), la
recherche (les mots que les tests emploient : `in:inbox`, `is:unread`, `is:important`,
`category:primary`, `from:`, et du texte libre), les formats complet et réduit d'un mail, les
brouillons (que David peut retoucher dans Gmail : `retoucher`) et l'envoi (`envoyes` : chaque
mail parti), les libellés et la corbeille.
"""

from __future__ import annotations

import base64
import datetime as dt
from email import message_from_bytes, policy
from email.message import EmailMessage
from typing import Any

import httpx
from doublure_google import DoublureGoogle, corps, erreur, repondre

HOTE = r"gmail\.googleapis\.com/gmail/v1/users/me"
DAVID = "david@example.com"
SYSTEME = ("INBOX", "UNREAD", "IMPORTANT", "SENT", "DRAFT", "TRASH", "SPAM", "STARRED")


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


def lu(message: dict[str, Any]) -> EmailMessage:
    """Un mail écrit par Atlas (`raw`), tel qu'un logiciel de mail le lirait."""
    donnees = message["raw"]
    brut = base64.urlsafe_b64decode(donnees + "=" * (-len(donnees) % 4))
    return message_from_bytes(brut, policy=policy.default)


class Gmail:
    """`mails` : les mails de la boîte, par identifiant ; `brouillons` : ceux qu'Atlas a
    préparés ; `envoyes` : ceux qui sont partis."""

    def __init__(self, doublure: DoublureGoogle) -> None:
        self.mails: dict[str, dict[str, Any]] = {}
        self.brouillons: dict[str, dict[str, Any]] = {}
        self.envoyes: list[dict[str, Any]] = []
        self.libelles: dict[str, str] = {nom: nom for nom in SYSTEME}  # identifiant → nom
        doublure.route("GET", rf"{HOTE}/messages", self._chercher)
        doublure.route("GET", rf"{HOTE}/messages/([^/]+)", self._lire)
        doublure.route("POST", rf"{HOTE}/drafts", self._brouillon)
        doublure.route("POST", rf"{HOTE}/drafts/send", self._envoyer_le_brouillon)
        doublure.route("GET", rf"{HOTE}/drafts/([^/]+)", self._lire_le_brouillon)
        doublure.route("POST", rf"{HOTE}/messages/send", self._envoyer)
        doublure.route("GET", rf"{HOTE}/labels", self._libelles)
        doublure.route("POST", rf"{HOTE}/messages/batchModify", self._changer)
        doublure.route("POST", rf"{HOTE}/messages/([^/]+)/trash", self._corbeille)

    def retoucher(
        self,
        id_: str,
        *,
        texte: str | None = None,
        entetes: tuple[tuple[str, str], ...] = (),
        piece: tuple[str, bytes] | None = None,
    ) -> None:
        """David retouche dans Gmail un brouillon qu'Atlas a préparé : son texte, ses en-têtes
        (une copie, une copie cachée), une pièce jointe."""
        message = self.brouillons[id_]
        ecrit = lu(message)
        for nom, valeur in entetes:
            del ecrit[nom]
            ecrit[nom] = valeur
        if texte is not None:
            ecrit.set_content(texte)
        if piece is not None:
            nom, contenu = piece
            ecrit.add_attachment(contenu, maintype="application", subtype="pdf", filename=nom)
        message["raw"] = base64.urlsafe_b64encode(ecrit.as_bytes()).decode()

    def libelle(self, nom: str) -> str:
        """Un libellé de David ; rend son identifiant (`Label_…`, comme chez Google)."""
        id_ = f"Label_{len(self.libelles) + 1}"
        self.libelles[id_] = nom
        return id_

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
        identifiant: bool = True,
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
            *([("Message-ID", f"<{id_}@exemple.fr>")] if identifiant else []),
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

    def _brouillon(self, requete: httpx.Request) -> httpx.Response:
        id_ = f"brouillon{len(self.brouillons) + 1}"
        self.brouillons[id_] = corps(requete)["message"]
        return repondre(200, {"id": id_, "message": {"id": f"m-{id_}"}})

    def _lire_le_brouillon(self, requete: httpx.Request, id_: str) -> httpx.Response:
        message = self.brouillons.get(id_)
        if message is None:
            return erreur(404, "notFound")
        assert requete.url.params.get("format") == "raw"
        fil = message.get("threadId", f"fil-{id_}")  # Gmail donne un fil à tout brouillon
        return repondre(
            200, {"id": id_, "message": {"id": f"m-{id_}", "threadId": fil, "raw": message["raw"]}}
        )

    def _envoyer_le_brouillon(self, requete: httpx.Request) -> httpx.Response:
        message = self.brouillons.pop(corps(requete)["id"], None)
        if message is None:
            return erreur(404, "notFound")
        self.envoyes.append(message)
        return repondre(200, {"id": f"envoye{len(self.envoyes)}", "labelIds": ["SENT"]})

    def _envoyer(self, requete: httpx.Request) -> httpx.Response:
        self.envoyes.append(corps(requete))
        return repondre(200, {"id": f"envoye{len(self.envoyes)}", "labelIds": ["SENT"]})

    def _libelles(self, requete: httpx.Request) -> httpx.Response:
        liste = [
            {"id": i, "name": n, "type": "system" if i in SYSTEME else "user"}
            for i, n in self.libelles.items()
        ]
        return repondre(200, {"labels": liste})

    def _changer(self, requete: httpx.Request) -> httpx.Response:
        demande = corps(requete)
        inconnus = set(demande.get("addLabelIds", [])) - set(self.libelles)
        if inconnus or any(i not in self.mails for i in demande["ids"]):
            return erreur(400, "invalidArgument")
        for id_ in demande["ids"]:
            libelles = self.mails[id_]["labelIds"]
            retires = demande.get("removeLabelIds", [])
            libelles[:] = [nom for nom in libelles if nom not in retires]
            libelles += [nom for nom in demande.get("addLabelIds", []) if nom not in libelles]
        return repondre(204)

    def _corbeille(self, requete: httpx.Request, id_: str) -> httpx.Response:
        message = self.mails.get(id_)
        if message is None:
            return erreur(404, "notFound")
        message["labelIds"] = [nom for nom in message["labelIds"] if nom != "INBOX"] + ["TRASH"]
        return repondre(200, message)

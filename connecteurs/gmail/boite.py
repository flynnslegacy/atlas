"""Le client de l'API Gmail (spec de Gmail et de Google Agenda, §6) : chercher des mails (la
syntaxe de recherche de Gmail), en lire un, écrire un brouillon, envoyer. Tout est synchrone :
le connecteur l'appelle par `asyncio.to_thread`."""

from __future__ import annotations

import datetime as dt

import httpx

from atlas_core.connecteurs import ErreurConnecteur
from atlas_core.google import Autorisation
from atlas_core.rendez_vous import fuseau_du_mac

from .mails import Brouillon, Mail, Resume, composer, lire_mail, lire_resume

ADRESSE = "https://gmail.googleapis.com/gmail/v1/users/me"
SERVICE = "Gmail"
MAX_MAILS = 20
PLUS_DE_BROUILLON = "Ce brouillon n'est plus dans Gmail : prépare-le de nouveau."


class ErreurGmail(Exception):
    """Une réponse inattendue de Gmail : le Core la note, et Claude apprend l'échec."""


class Boite:
    """La boîte Gmail de David, par son autorisation."""

    def __init__(self, autorisation: Autorisation, *, fuseau: dt.tzinfo | None = None) -> None:
        self._autorisation = autorisation
        self.fuseau = fuseau or fuseau_du_mac()

    def chercher(self, requete: str) -> tuple[list[Resume], bool]:
        """Les mails qui répondent à la recherche, les plus récents d'abord (20 au plus), et
        s'il y en a d'autres."""
        page = self._json("GET", "messages", params={"q": requete, "maxResults": MAX_MAILS})
        resumes = []
        for message in page.get("messages", []):
            donnees = self._json(
                "GET",
                f"messages/{message['id']}",
                params={"format": "metadata", "metadataHeaders": ["From", "Subject", "Date"]},
            )
            resumes.append(lire_resume(donnees, self.fuseau))
        return resumes, bool(page.get("nextPageToken"))

    def lire(self, id_: str) -> Mail:
        return lire_mail(
            self._json("GET", f"messages/{id_}", params={"format": "full"}), self.fuseau
        )

    def brouillon(self, brouillon: Brouillon) -> str:
        """Un brouillon dans Gmail ; rend son identifiant."""
        message = self._message(brouillon)
        return str(self._json("POST", "drafts", json={"message": message})["id"])

    def envoyer(self, brouillon: Brouillon) -> None:
        self._json("POST", "messages/send", json=self._message(brouillon))

    def envoyer_le_brouillon(self, id_: str) -> None:
        reponse = self._appeler("POST", "drafts/send", json={"id": id_})
        if reponse.status_code == 404:  # David l'a supprimé, ou envoyé, entre-temps
            raise ErreurConnecteur(PLUS_DE_BROUILLON)
        if not reponse.is_success:
            raise ErreurGmail(f"POST drafts/send : {reponse.status_code}")

    def _message(self, brouillon: Brouillon) -> dict:
        message = {"raw": composer(brouillon)}
        if brouillon.fil:
            message["threadId"] = brouillon.fil
        return message

    def _json(self, methode: str, chemin: str, **options) -> dict:
        reponse = self._appeler(methode, chemin, **options)
        if not reponse.is_success:
            raise ErreurGmail(f"{methode} {chemin.split('/')[0]} : {reponse.status_code}")
        return reponse.json() if reponse.content else {}

    def _appeler(self, methode: str, chemin: str, **options) -> httpx.Response:
        return self._autorisation.appeler(
            methode, f"{ADRESSE}/{chemin}", service=SERVICE, **options
        )

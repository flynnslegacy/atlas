"""L'autorisation Google d'Atlas (spec de Gmail et de Google Agenda, §4) : le jeton d'accès, tiré
du jeton durable de David et renouvelé toutes les heures ; les requêtes vers les API de Google,
et ce qu'Atlas dit quand elles échouent ; et la connexion par le navigateur de David, qui donne
le jeton durable une fois (`connecter`, que lance `make google` : scripts/google.py).

La connexion suit OAuth pour une application de bureau : Google renvoie le navigateur vers
un petit serveur sur ce Mac (`127.0.0.1`), et deux protections empêchent un autre programme
de détourner la réponse : `state` (une valeur tirée au hasard, que la réponse doit rendre) et
PKCE (le code ne s'échange qu'avec un secret que seule la commande connaît).

Tout est synchrone (httpx) : les connecteurs appellent `Autorisation.appeler` par
`asyncio.to_thread`. Les tests passent leur doublure de Google (`http`).
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import threading
import time
import webbrowser
from collections.abc import Callable, Mapping
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit

import httpx

from .outils import ErreurConnecteur

PERMISSIONS = (
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
)
AUTORISER = "https://accounts.google.com/o/oauth2/v2/auth"
JETON = "https://oauth2.googleapis.com/token"
DELAI_S = 15.0
MARGE_S = 60.0  # un jeton d'accès se renouvelle une minute avant de mourir
ATTENTE_S = 300.0

RETIREE = "Google a retiré l'autorisation d'Atlas : relance make google sur ton Mac."
CLIENT_REFUSE = (
    "Google ne reconnaît pas l'identifiant ou le secret du client : vérifie-les dans Paramètres "
    "› Connecteurs › Réglages."
)
MUET = "Google ne répond pas : réessaie dans un moment."
PERMISSION = "L'autorisation d'Atlas ne couvre pas ça : relance make google sur ton Mac."
SANS_REPONSE = "Pas de réponse de Google en 5 minutes : relance make google."
AUTRE_DEMANDE = "La réponse ne vient pas de cette demande : relance make google."
PAS_AUTORISE = "Tu n'as pas autorisé Atlas : relance make google pour recommencer."
SANS_JETON = (
    "Google n'a pas donné de jeton durable : retire l'accès d'Atlas sur myaccount.google.com "
    "(Sécurité, Accès tiers), puis relance make google."
)
MERCI = "Atlas est autorisé : tu peux fermer cette page."
NON = "Atlas n'est pas autorisé : tu peux fermer cette page."


def pas_active(service: str) -> str:
    return f"L'accès à {service} n'est pas activé dans ton projet Google Cloud."


class ErreurConnexion(Exception):
    """`make google` n'a pas obtenu de jeton : son message dit quoi faire."""


def _raisons(reponse: httpx.Response) -> set[str]:
    """Les raisons d'un refus, telles que les API de Google les écrivent."""
    try:
        erreur = reponse.json().get("error", {})
    except ValueError:
        return set()
    if not isinstance(erreur, dict):
        return set()
    detail = [e.get("reason", "") for e in erreur.get("errors", []) if isinstance(e, dict)]
    detail += [d.get("reason", "") for d in erreur.get("details", []) if isinstance(d, dict)]
    return set(detail)


def _erreur_du_jeton(reponse: httpx.Response) -> str:
    try:
        return str(reponse.json().get("error", ""))
    except ValueError:
        return ""


class Autorisation:
    """Le jeton d'accès de David, pour les API de Google. `http` : le client (les tests
    passent leur doublure) ; `horloge` : pour compter l'heure de vie d'un jeton."""

    def __init__(
        self,
        id_client: str,
        secret_client: str,
        jeton: str,
        *,
        http: httpx.Client | None = None,
        horloge: Callable[[], float] = time.monotonic,
        delai_s: float = DELAI_S,
    ) -> None:
        self._client = {"client_id": id_client, "client_secret": secret_client}
        self._jeton = jeton
        self._http = http or httpx.Client(timeout=delai_s)
        self._horloge = horloge
        self._acces: str | None = None
        self._expire = 0.0
        self._verrou = threading.Lock()

    def appeler(
        self,
        methode: str,
        url: str,
        *,
        service: str,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
        entetes: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        """Une requête vers une API de Google (`service` : « Gmail », « l'Agenda »), avec le
        jeton d'accès, renouvelé une fois si Google le refuse. Les refus que David peut réparer
        deviennent des `ErreurConnecteur` ; les autres réponses reviennent telles quelles."""
        options = {"params": params, "json": json, "entetes": entetes or {}}
        reponse = self._envoyer(methode, url, self._jeton_d_acces(), options)
        if reponse.status_code == 401:
            reponse = self._envoyer(methode, url, self._jeton_d_acces(renouveler=True), options)
            if reponse.status_code == 401:
                raise ErreurConnecteur(RETIREE)
        if reponse.status_code == 403:
            raisons = _raisons(reponse)
            if raisons & {"accessNotConfigured", "SERVICE_DISABLED"}:
                raise ErreurConnecteur(pas_active(service))
            if raisons & {"insufficientPermissions", "ACCESS_TOKEN_SCOPE_INSUFFICIENT"}:
                raise ErreurConnecteur(PERMISSION)
        if reponse.status_code == 429 or reponse.status_code >= 500:
            raise ErreurConnecteur(MUET)
        return reponse

    def _envoyer(
        self, methode: str, url: str, acces: str, options: dict[str, Any]
    ) -> httpx.Response:
        entetes = {"Authorization": f"Bearer {acces}", **options["entetes"]}
        try:
            return self._http.request(
                methode, url, params=options["params"], json=options["json"], headers=entetes
            )
        except httpx.TransportError:  # injoignable, ou muet au-delà du délai
            raise ErreurConnecteur(MUET) from None

    def _jeton_d_acces(self, renouveler: bool = False) -> str:
        with self._verrou:  # deux outils à la fois ne renouvellent qu'une fois
            if renouveler or self._acces is None or self._horloge() >= self._expire - MARGE_S:
                self._renouveler()
            assert self._acces is not None
            return self._acces

    def _renouveler(self) -> None:
        demande = {**self._client, "refresh_token": self._jeton, "grant_type": "refresh_token"}
        try:
            reponse = self._http.post(JETON, data=demande)
        except httpx.TransportError:
            raise ErreurConnecteur(MUET) from None
        if reponse.status_code == 429 or reponse.status_code >= 500:
            raise ErreurConnecteur(MUET)
        erreur = _erreur_du_jeton(reponse)
        if erreur in {"invalid_client", "unauthorized_client"}:
            raise ErreurConnecteur(CLIENT_REFUSE)
        if not reponse.is_success:  # invalid_grant : retiré, expiré, mot de passe changé
            raise ErreurConnecteur(RETIREE)
        donnees = reponse.json()
        self._acces = str(donnees["access_token"])
        self._expire = self._horloge() + float(donnees.get("expires_in", 3600))


def connecter(
    id_client: str,
    secret_client: str,
    *,
    http: httpx.Client | None = None,
    ouvrir: Callable[[str], object] = webbrowser.open,
    attente_s: float = ATTENTE_S,
) -> str:
    """Demande l'accord de David dans son navigateur, et rend le jeton durable."""
    verificateur = secrets.token_urlsafe(64)
    empreinte = hashlib.sha256(verificateur.encode()).digest()
    defi = base64.urlsafe_b64encode(empreinte).rstrip(b"=").decode()
    etat = secrets.token_urlsafe(24)
    recu: dict[str, str] = {}

    class Retour(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 — le nom qu'attend http.server
            morceaux = urlsplit(self.path)
            if morceaux.path != "/":
                self.send_error(404)
                return
            recu.update(parse_qsl(morceaux.query))
            texte = MERCI if "code" in recu else NON
            corps = f"<!doctype html><meta charset=utf-8><title>Atlas</title><p>{texte}</p>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(corps.encode())

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            pass

    serveur = HTTPServer(("127.0.0.1", 0), Retour)
    retour = f"http://127.0.0.1:{serveur.server_port}/"
    demande = {
        "client_id": id_client,
        "redirect_uri": retour,
        "response_type": "code",
        "scope": " ".join(PERMISSIONS),
        "access_type": "offline",
        "prompt": "consent",
        "state": etat,
        "code_challenge": defi,
        "code_challenge_method": "S256",
    }
    ouvrir(f"{AUTORISER}?{urlencode(demande)}")
    fin = time.monotonic() + attente_s
    try:
        while not recu and time.monotonic() < fin:
            serveur.timeout = max(0.05, fin - time.monotonic())
            serveur.handle_request()
    finally:
        serveur.server_close()
    if not recu:
        raise ErreurConnexion(SANS_REPONSE)
    if not secrets.compare_digest(recu.get("state", ""), etat):
        raise ErreurConnexion(AUTRE_DEMANDE)
    if "code" not in recu:
        raise ErreurConnexion(PAS_AUTORISE)
    echange = {
        "client_id": id_client,
        "client_secret": secret_client,
        "code": recu["code"],
        "code_verifier": verificateur,
        "grant_type": "authorization_code",
        "redirect_uri": retour,
    }
    try:
        reponse = (http or httpx.Client(timeout=DELAI_S)).post(JETON, data=echange)
    except httpx.TransportError:
        raise ErreurConnexion(MUET) from None
    if reponse.status_code == 429 or reponse.status_code >= 500:
        raise ErreurConnexion(MUET)
    if _erreur_du_jeton(reponse) in {"invalid_client", "unauthorized_client"}:
        raise ErreurConnexion(CLIENT_REFUSE)
    jeton = reponse.json().get("refresh_token") if reponse.is_success else None
    if not jeton:
        raise ErreurConnexion(SANS_JETON)
    return str(jeton)

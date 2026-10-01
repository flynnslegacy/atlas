"""Une doublure des API de Google pour les tests (spec de Gmail et de Google Agenda, §8).

Il n'existe pas de faux Gmail qu'on puisse lancer comme Radicale : la doublure répond à la place
de Google, dans le client httpx des connecteurs (`http`), comme sa documentation le décrit. Elle
délivre les jetons (le renouvellement, l'échange du code de `make google` avec sa vérification
PKCE), exige un jeton d'accès valable sur chaque requête, sait tomber en panne, et garde trace de
tout ce qu'elle reçoit (`recues`). Les API elles-mêmes s'y branchent par `route`
(`doublure_agenda.py`, `doublure_gmail.py`). Jamais le vrai Google.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import httpx

ID_CLIENT = "atlas-test.apps.googleusercontent.com"
SECRET_CLIENT = "secret-du-client-de-test"
JETON_DURABLE = "jeton-durable-de-test"

Reponse = Callable[..., httpx.Response]


def repondre(statut: int, contenu: Any = None) -> httpx.Response:
    """Une réponse JSON, comme celles de Google (sans contenu : 204)."""
    if contenu is None:
        return httpx.Response(statut)
    return httpx.Response(statut, json=contenu)


def erreur(statut: int, raison: str = "") -> httpx.Response:
    """Un refus au format des API de Google."""
    detail = [{"reason": raison}] if raison else []
    return repondre(statut, {"error": {"code": statut, "message": raison, "errors": detail}})


def corps(requete: httpx.Request) -> Any:
    return json.loads(requete.content or b"null")


class DoublureGoogle:
    def __init__(self) -> None:
        self.jetons_durables = {JETON_DURABLE}
        self.acces_valides: set[str] = set()
        self.jetons_donnes = 0
        self.recues: list[httpx.Request] = []
        self.muette = False  # plus de réponse : le délai du client s'écoule
        self.acces_refuses = False  # Google n'accepte plus aucun jeton d'accès
        self.lenteur_du_jeton = 0.0  # secondes avant de donner un jeton
        self.jeton_en_panne: int | None = None  # le statut que rend alors l'échange de jetons
        self.refus: tuple[int, str] | None = None  # (statut, raison) pour toute requête d'API
        self._defis: dict[str, tuple[str, str]] = {}  # code → (défi PKCE, adresse de retour)
        self._routes: list[tuple[str, re.Pattern[str], Reponse]] = []
        self.http = httpx.Client(transport=httpx.MockTransport(self._repondre))

    def reglages(self, **autres: str) -> dict[str, str]:
        """Les réglages d'un connecteur Google, avec le client et le jeton de la doublure."""
        return {
            "ATLAS_GOOGLE_ID_CLIENT": ID_CLIENT,
            "ATLAS_GOOGLE_SECRET_CLIENT": SECRET_CLIENT,
            "ATLAS_GOOGLE_JETON": JETON_DURABLE,
            **autres,
        }

    def route(self, methode: str, motif: str, reponse: Reponse) -> None:
        """Une API : `motif` couvre l'hôte et le chemin ; ses groupes vont à `reponse`."""
        self._routes.append((methode, re.compile(motif), reponse))

    def accorder(self, adresse: str) -> dict[str, str]:
        """Google, quand David accepte : garde le défi PKCE et l'adresse de retour de la
        demande, et rend ce que la page de Google renverrait au navigateur (l'adresse de retour,
        `code`, `state`)."""
        demande = dict(parse_qsl(urlsplit(adresse).query))
        code = f"code-{len(self._defis) + 1}"
        self._defis[code] = (demande["code_challenge"], demande["redirect_uri"])
        return {"retour": demande["redirect_uri"], "code": code, "state": demande["state"]}

    def retirer_les_acces(self) -> None:
        """Les jetons d'accès ne valent plus : le client doit en redemander un."""
        self.acces_valides.clear()

    def _repondre(self, requete: httpx.Request) -> httpx.Response:
        self.recues.append(requete)
        if self.muette:
            raise httpx.ReadTimeout("Google ne répond plus", request=requete)
        if requete.url.host == "oauth2.googleapis.com":
            return self._jeton(dict(parse_qsl(requete.content.decode())))
        acces = requete.headers.get("authorization", "").removeprefix("Bearer ")
        if acces not in self.acces_valides or self.acces_refuses:
            return erreur(401, "authError")
        if self.refus is not None:
            return erreur(*self.refus)
        adresse = f"{requete.url.host}{requete.url.path}"
        for methode, motif, reponse in self._routes:
            trouve = motif.fullmatch(adresse)
            if requete.method == methode and trouve:
                return reponse(requete, *trouve.groups())
        return erreur(404, "notFound")

    def _jeton(self, demande: dict[str, str]) -> httpx.Response:
        time.sleep(self.lenteur_du_jeton)
        if self.jeton_en_panne is not None:
            return erreur(self.jeton_en_panne, "backendError")
        self.jetons_donnes += 1
        client = (demande.get("client_id"), demande.get("client_secret"))
        if client != (ID_CLIENT, SECRET_CLIENT):
            return repondre(401, {"error": "invalid_client"})
        if demande.get("grant_type") == "refresh_token":
            if demande.get("refresh_token") not in self.jetons_durables:
                return repondre(400, {"error": "invalid_grant"})
            acces = f"acces-{self.jetons_donnes}"
            self.acces_valides.add(acces)
            return repondre(
                200, {"access_token": acces, "expires_in": 3599, "token_type": "Bearer"}
            )
        defi, retour = self._defis.pop(demande.get("code", ""), (None, None))
        empreinte = hashlib.sha256(demande.get("code_verifier", "").encode()).digest()
        attendu = base64.urlsafe_b64encode(empreinte).rstrip(b"=").decode()
        if defi != attendu or demande.get("redirect_uri") != retour:
            return repondre(400, {"error": "invalid_grant"})
        durable = f"jeton-durable-{len(self.jetons_durables) + 1}"
        self.jetons_durables.add(durable)
        return repondre(
            200, {"access_token": "acces-0", "refresh_token": durable, "expires_in": 3599}
        )

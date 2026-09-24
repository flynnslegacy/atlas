"""Serveur du Core : route de santé, WebSocket audio, WebSocket et page web."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from .cerveau import CerveauBouchon
from .config import Config
from .diffuseur import Diffuseur
from .protocole import Erreur, decoder_audio_entrant, decoder_message
from .protocole_web import Authentification, Muet, Saisie, decoder_message_page
from .regie import Regie
from .session import Session, sans_destinataire
from .synthese import ClientSynthese
from .transcription import ClientTranscription
from .web import cle_valide, origine_autorisee, politique_securite

_journal = logging.getLogger(__name__)
_config = Config.depuis_environnement()
_http: httpx.AsyncClient | None = None

RACINE_WEB = Path(__file__).resolve().parent.parent / "atlas_web"
DELAI_AUTHENTIFICATION_S = 5.0
FERMETURE_CLE_ABSENTE = 4000
FERMETURE_NON_AUTORISE = 4401
FERMETURE_ORIGINE = 1008  # « policy violation », avant même d'accepter la connexion


@asynccontextmanager
async def _cycle_de_vie(app: FastAPI):
    global _http
    _http = httpx.AsyncClient()
    try:
        yield
    finally:
        await _http.aclose()
        _http = None


app = FastAPI(title="atlas-core", lifespan=_cycle_de_vie)


def _services() -> dict:
    assert _http is not None, "le cycle de vie de l'application n'a pas démarré"
    return {
        "transcription": ClientTranscription(_config.stt_url, _http),
        "synthese": ClientSynthese(_config.tts_url, _config.tts_voix, _http),
        "cerveau": CerveauBouchon(),
    }


def creer_session(envoyer_json, envoyer_binaire) -> Session:
    return Session(
        envoyer_json=envoyer_json,
        envoyer_binaire=envoyer_binaire,
        diffuseur=_regie.diffuseur,
        avec_voix=_regie.voix_active,
        **_services(),
    )


def creer_session_ecrite() -> Session:
    """Répond aux questions tapées quand aucun client audio n'est connecté : par écrit."""
    return Session(
        envoyer_json=sans_destinataire,
        envoyer_binaire=sans_destinataire,
        diffuseur=_regie.diffuseur,
        avec_voix=lambda: False,
        **_services(),
    )


_regie = Regie(Diffuseur(), lambda: creer_session_ecrite())


@app.middleware("http")
async def _en_tetes_de_securite(request: Request, call_next):
    reponse = await call_next(request)
    reponse.headers["Content-Security-Policy"] = politique_securite(request.headers.get("host", ""))
    reponse.headers["X-Content-Type-Options"] = "nosniff"
    reponse.headers["Referrer-Policy"] = "no-referrer"
    return reponse


@app.get("/sante")
async def sante() -> dict:
    return {"ok": True, "stt": _config.stt_url, "tts": _config.tts_url}


@app.websocket("/ws/audio")
async def ws_audio(ws: WebSocket) -> None:
    await ws.accept()

    async def envoyer_json(msg) -> None:
        await ws.send_text(msg.model_dump_json())

    async def envoyer_binaire(trame: bytes) -> None:
        await ws.send_bytes(trame)

    session = creer_session(envoyer_json, envoyer_binaire)
    _regie.rattacher(session)
    try:
        while True:
            recu = await ws.receive()
            if recu["type"] == "websocket.disconnect":
                break
            if (texte := recu.get("text")) is not None:
                try:
                    await session.sur_message(decoder_message(texte))
                except ValueError as e:
                    await envoyer_json(Erreur(code="message_invalide", message=str(e)))
            elif (binaire := recu.get("bytes")) is not None:
                try:
                    await session.sur_audio(decoder_audio_entrant(binaire))
                except ValueError as e:
                    await envoyer_json(Erreur(code="trame_invalide", message=str(e)))
    except WebSocketDisconnect:
        pass
    finally:
        _regie.detacher(session)
        await session.fermer()


async def _recevoir_texte(ws: WebSocket) -> str | None:
    """Le prochain message texte de la page, ou None si elle s'est déconnectée."""
    while True:
        recu = await ws.receive()
        if recu["type"] == "websocket.disconnect":
            return None
        if (texte := recu.get("text")) is not None:
            return texte


@app.websocket("/ws/web")
async def ws_web(ws: WebSocket) -> None:
    if not origine_autorisee(ws.headers.get("origin"), ws.headers.get("host")):
        await ws.close(code=FERMETURE_ORIGINE)
        return
    await ws.accept()
    if not _config.web_cle:
        message = (
            "La clé d'accès n'est pas configurée : ajoute ATLAS_WEB_CLE dans le .env du Core, "
            "puis redémarre-le."
        )
        await ws.send_text(Erreur(code="cle_absente", message=message).model_dump_json())
        await ws.close(code=FERMETURE_CLE_ABSENTE)
        return

    try:
        premier = await asyncio.wait_for(_recevoir_texte(ws), DELAI_AUTHENTIFICATION_S)
    except TimeoutError:
        premier = ""
    if premier is None:
        return  # la page est déjà partie
    try:
        demande = decoder_message_page(premier)
    except ValueError:
        demande = None
    if not isinstance(demande, Authentification) or not cle_valide(demande.cle, _config.web_cle):
        await ws.close(code=FERMETURE_NON_AUTORISE)
        return

    async def envoyer(msg) -> None:
        await ws.send_text(msg.model_dump_json())

    abonnement = _regie.diffuseur.abonner(envoyer)
    try:
        while (texte := await _recevoir_texte(ws)) is not None:
            try:
                msg = decoder_message_page(texte)
            except ValueError as e:
                abonnement.envoyer_prive(Erreur(code="message_invalide", message=str(e)))
                continue
            if isinstance(msg, Saisie):
                await _regie.saisie(msg.texte)
            elif isinstance(msg, Muet):
                await _regie.basculer_muet(msg.actif)
    except WebSocketDisconnect:
        pass
    finally:
        await abonnement.fermer()


# Toujours en dernier : monté sur « / », il capterait sinon les routes déclarées après lui.
app.mount("/", StaticFiles(directory=RACINE_WEB, html=True), name="web")

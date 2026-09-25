"""Serveur du Core : route de santé, WebSocket audio, WebSocket et page web, et la voix
des pages."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path

import httpx
from claude_agent_sdk import ClaudeSDKClient
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from atlas_audio.client import lire_reglages
from atlas_audio.connexion import PeripheriqueEnPanne

from .cerveau import Cerveau, CerveauBouchon
from .cerveau_claude import CerveauClaude, options_cerveau, purger_cles_api
from .config import Config
from .diffuseur import Diffuseur
from .protocole import Bonjour, Erreur, decoder_audio_entrant, decoder_message
from .protocole_voix import (
    AuthentificationVoix,
    HeyAtlas,
    Parler,
    Pret,
    Reprise,
    decoder_message_voix,
    verifier_bloc_page,
)
from .protocole_web import Authentification, Muet, Saisie, decoder_message_page
from .regie import Regie
from .session import Session, sans_destinataire
from .synthese import ClientSynthese
from .transcription import ClientTranscription
from .voix import charger_modeles, monter_page
from .web import cle_valide, origine_autorisee, politique_securite

_journal = logging.getLogger(__name__)
_config = Config.depuis_environnement()
# Les réglages du client audio du Mac, que le Core applique aussi aux pages.
_reglages = lire_reglages()
_http: httpx.AsyncClient | None = None
_cerveau: Cerveau | None = None

RACINE_WEB = Path(__file__).resolve().parent.parent / "atlas_web"
# Le dossier de travail de Claude : vide, à lui seul, hors de tout projet.
DOSSIER_CERVEAU = Path.home() / ".atlas" / "cerveau"
DELAI_AUTHENTIFICATION_S = 5.0
FERMETURE_CLE_ABSENTE = 4000
FERMETURE_NON_AUTORISE = 4401
FERMETURE_ORIGINE = 1008  # « policy violation », avant même d'accepter la connexion
FERMETURE_PANNE = 1011  # « internal error » : la voix d'une page s'est arrêtée, elle se rebranche


def creer_cerveau(config: Config) -> Cerveau:
    """Le cerveau unique du Core, partagé par la voix et le clavier."""
    if config.cerveau == "bouchon":
        return CerveauBouchon()
    retirees = purger_cles_api(os.environ)
    if retirees:
        _journal.warning("retiré de l'environnement, pour Claude : %s", ", ".join(retirees))

    def fabrique() -> ClaudeSDKClient:
        DOSSIER_CERVEAU.mkdir(parents=True, exist_ok=True)
        return ClaudeSDKClient(options=options_cerveau(config.cerveau_modele, DOSSIER_CERVEAU))

    return CerveauClaude(fabrique, oubli_s=config.cerveau_oubli_min * 60)


@asynccontextmanager
async def _cycle_de_vie(app: FastAPI):
    global _http, _cerveau
    _http = httpx.AsyncClient()
    _cerveau = creer_cerveau(_config)
    try:
        yield
    finally:
        # Le cerveau dans son propre `try` : s'il lève (ou est annulé), le client HTTP se
        # ferme quand même, dans le `finally` qui l'entoure.
        try:
            await _cerveau.fermer()
        finally:
            _cerveau = None
            await _http.aclose()
            _http = None


app = FastAPI(title="atlas-core", lifespan=_cycle_de_vie)


def _services() -> dict:
    assert _http is not None and _cerveau is not None, "le cycle de vie n'a pas démarré"
    return {
        "transcription": ClientTranscription(_config.stt_url, _http),
        "synthese": ClientSynthese(_config.tts_url, _config.tts_voix, _http),
        "cerveau": _cerveau,
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
    # Sans ceci, l'iPad peut mélanger des modules anciens et nouveaux après une mise à
    # jour : le navigateur revalide à chaque fois (l'ETag donne un 304 sur le réseau local).
    reponse.headers["Cache-Control"] = "no-cache"
    return reponse


@app.get("/sante")
async def sante() -> dict:
    return {"ok": True, "stt": _config.stt_url, "tts": _config.tts_url}


@app.websocket("/ws/audio")
async def ws_audio(ws: WebSocket) -> None:
    if ws.headers.get("origin") is not None:
        # Un navigateur envoie toujours un en-tête Origin ; le client audio du Mac n'en
        # envoie jamais.
        await ws.close(code=FERMETURE_ORIGINE)
        return
    await ws.accept()
    if not _config.audio_cle:
        message = (
            "La clé du client audio n'est pas configurée : ajoute ATLAS_AUDIO_CLE dans le .env "
            "du Core, puis redémarre-le."
        )
        await ws.send_text(Erreur(code="cle_absente", message=message).model_dump_json())
        await ws.close(code=FERMETURE_CLE_ABSENTE)
        return
    authentifie = await _client_audio_authentifie(ws)
    if authentifie is None:
        return  # le client est déjà parti
    if not authentifie:
        await ws.close(code=FERMETURE_NON_AUTORISE)
        return

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
    """Le prochain message texte, ou None si l'autre bout s'est déconnecté."""
    while True:
        recu = await ws.receive()
        if recu["type"] == "websocket.disconnect":
            return None
        if (texte := recu.get("text")) is not None:
            return texte


async def _client_audio_authentifie(ws: WebSocket) -> bool | None:
    """Vrai si le premier message est un `Bonjour` portant la bonne clé, reçu à temps ;
    None si le client est parti avant."""
    try:
        premier = await asyncio.wait_for(_recevoir_texte(ws), DELAI_AUTHENTIFICATION_S)
    except TimeoutError:
        return False
    if premier is None:
        return None
    try:
        bonjour = decoder_message(premier)
    except ValueError:
        return False
    return isinstance(bonjour, Bonjour) and cle_valide(bonjour.cle, _config.audio_cle)


async def _ouvrir_page(ws: WebSocket) -> bool:
    """Accepte la connexion d'une page de la bonne origine, si la clé des pages est
    configurée ; sinon la ferme et rend False."""
    if not origine_autorisee(ws.headers.get("origin"), ws.headers.get("host")):
        await ws.close(code=FERMETURE_ORIGINE)
        return False
    await ws.accept()
    if not _config.web_cle:
        message = (
            "La clé d'accès n'est pas configurée : ajoute ATLAS_WEB_CLE dans le .env du Core, "
            "puis redémarre-le."
        )
        await ws.send_text(Erreur(code="cle_absente", message=message).model_dump_json())
        await ws.close(code=FERMETURE_CLE_ABSENTE)
        return False
    return True


async def _page_authentifiee(ws: WebSocket, decoder, attendu: type):
    """Le premier message de la page s'il arrive à temps, du type attendu, avec la clé
    des pages ; sinon la connexion est fermée (4401) et None est rendu."""
    try:
        premier = await asyncio.wait_for(_recevoir_texte(ws), DELAI_AUTHENTIFICATION_S)
    except TimeoutError:
        premier = ""
    if premier is None:
        return None  # la page est déjà partie
    try:
        demande = decoder(premier)
    except ValueError:
        demande = None
    if not isinstance(demande, attendu) or not cle_valide(demande.cle, _config.web_cle):
        await ws.close(code=FERMETURE_NON_AUTORISE)
        return None
    return demande


@app.websocket("/ws/web")
async def ws_web(ws: WebSocket) -> None:
    if not await _ouvrir_page(ws):
        return
    demande = await _page_authentifiee(ws, decoder_message_page, Authentification)
    if demande is None:
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
                await _regie.saisie(msg.texte, demande.page)
            elif isinstance(msg, Muet):
                await _regie.basculer_muet(msg.actif)
    except WebSocketDisconnect:
        pass
    finally:
        await abonnement.fermer()


@app.websocket("/ws/voix")
async def ws_voix(ws: WebSocket) -> None:
    """La voix d'une page qui a allumé son micro : le Core écoute pour elle (voix.py)."""
    if not await _ouvrir_page(ws):
        return
    demande = await _page_authentifiee(ws, decoder_message_voix, AuthentificationVoix)
    if demande is None:
        return

    async def envoyer_json(msg) -> None:
        await ws.send_text(msg.model_dump_json())

    async def envoyer_binaire(pcm: bytes) -> None:
        await ws.send_bytes(pcm)

    try:
        modeles = await asyncio.to_thread(charger_modeles, _reglages.seuil_reveil)
    except FileNotFoundError as e:
        await envoyer_json(Erreur(code="modeles_absents", message=str(e)))
        await ws.close(code=FERMETURE_CLE_ABSENTE)
        return
    page = monter_page(
        envoyer_json,
        envoyer_binaire,
        creer_session,
        modeles,
        replace(_reglages, bargein_dbfs=_config.voix_bargein_dbfs),
        _config.voix_marge_s,
        demande.hey_atlas,
    )
    await envoyer_json(Pret())
    _regie.rattacher(page.session, demande.page)
    service = asyncio.create_task(page.servir())
    try:
        while True:
            if service.done():
                # Le client de la page s'est arrêté. Une panne : la page se rebranche,
                # plutôt que de parler dans le vide. Un envoi qui a échoué : elle est partie.
                if not isinstance(service.exception(), PeripheriqueEnPanne):
                    await ws.close(code=FERMETURE_PANNE)
                break
            recu = await ws.receive()
            if recu["type"] == "websocket.disconnect":
                break
            if (binaire := recu.get("bytes")) is not None:
                try:
                    page.peripherique.recevoir(verifier_bloc_page(binaire))
                except ValueError as e:
                    await envoyer_json(Erreur(code="trame_invalide", message=str(e)))
                continue
            try:
                msg = decoder_message_voix(recu.get("text") or "")
            except ValueError as e:
                await envoyer_json(Erreur(code="message_invalide", message=str(e)))
                continue
            if isinstance(msg, Parler):
                page.client.demander_la_parole()
            elif isinstance(msg, HeyAtlas):
                page.reveilleur.actif = msg.actif
            elif isinstance(msg, Reprise):
                page.client.reamorcer()
    except WebSocketDisconnect:
        pass
    finally:
        service.cancel()
        await asyncio.wait([service])
        erreur = None if service.cancelled() else service.exception()
        if isinstance(erreur, PeripheriqueEnPanne):
            _journal.info("la page est partie pendant qu'Atlas lui parlait")
        elif erreur is not None:
            _journal.error("la voix d'une page s'est arrêtée", exc_info=erreur)
        _regie.detacher(page.session)
        await page.session.fermer()


# Toujours en dernier : monté sur « / », il capterait sinon les routes déclarées après lui.
app.mount("/", StaticFiles(directory=RACINE_WEB, html=True), name="web")

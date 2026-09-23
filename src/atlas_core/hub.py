"""Serveur du Core : route de santé et WebSocket audio."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from .cerveau import CerveauBouchon
from .config import Config
from .protocole import Erreur, decoder_audio_entrant, decoder_message
from .session import Session
from .synthese import ClientSynthese
from .transcription import ClientTranscription

_journal = logging.getLogger(__name__)
_config = Config.depuis_environnement()
_http: httpx.AsyncClient | None = None


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


def creer_session(envoyer_json, envoyer_binaire) -> Session:
    assert _http is not None, "le cycle de vie de l'application n'a pas démarré"
    return Session(
        envoyer_json=envoyer_json,
        envoyer_binaire=envoyer_binaire,
        transcription=ClientTranscription(_config.stt_url, _http),
        synthese=ClientSynthese(_config.tts_url, _config.tts_voix, _http),
        cerveau=CerveauBouchon(),
    )


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
        await session.fermer()

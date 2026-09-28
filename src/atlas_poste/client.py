"""Le poste : se connecter au Core, exécuter ses gestes, lui répondre.

Lancé sur le Mac de David par `make run-poste`. Il ouvre lui-même sa connexion (aucun port
n'est ouvert sur le Mac). Le poste et le Core se prouvent alors l'un à l'autre qu'ils
connaissent `ATLAS_POSTE_CLE`, sans jamais l'envoyer : le poste n'obéit qu'au serveur qui la
prouve. Il exécute ensuite les gestes signés du Core un par un, hors de la boucle, et répond
à chacun. Si le Core disparaît, il se reconnecte, comme le client audio.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import Callable
from typing import Protocol

from atlas_audio.connexion import CleNonProuvee, boucle_de_connexion
from atlas_core.protocole_poste import (
    ActionPoste,
    BonjourPoste,
    DefiPoste,
    PretPoste,
    ReponsePoste,
    ResultatPoste,
    cle_de_session,
    decoder_message_vers_poste,
    est_signe,
    nouveau_nonce,
    preuve_du_core,
    preuve_du_poste,
    preuve_valide,
    signer,
)

_journal = logging.getLogger(__name__)

URL_PAR_DEFAUT = "ws://127.0.0.1:8080/ws/poste"


class Executant(Protocol):
    def executer(self, action: ActionPoste) -> ResultatPoste: ...


def lire_reglages() -> tuple[str, str]:
    """L'adresse du Core et la clé du poste, lues dans l'environnement (le `.env`)."""
    url = os.environ.get("ATLAS_POSTE_URL", "").strip() or URL_PAR_DEFAUT
    cle = os.environ.get("ATLAS_POSTE_CLE", "").strip()
    if not cle:
        raise ValueError(
            "ATLAS_POSTE_CLE manquante : mets dans le .env du poste la même clé que dans celui "
            "du Core"
        )
    return url, cle


def _identifiant(brut: str) -> int | None:
    try:
        identifiant = json.loads(brut).get("id")
    except (ValueError, AttributeError):
        return None
    return identifiant if isinstance(identifiant, int) else None


async def _session(ws, messages, cle: str, nonce: str) -> str:
    """Le poste et le Core se prouvent la clé ; rend la clé de la session, ou lève
    `CleNonProuvee` si le serveur ne la prouve pas (le poste ne lui dit alors rien de plus)."""
    await ws.send(BonjourPoste(nonce=nonce).model_dump_json())
    brut = await anext(messages, None)
    try:
        defi = decoder_message_vers_poste(brut) if isinstance(brut, str) else None
    except ValueError:
        defi = None
    if not isinstance(defi, DefiPoste) or not preuve_valide(
        preuve_du_core(cle, nonce, defi.nonce), defi.preuve
    ):
        raise CleNonProuvee
    await ws.send(ReponsePoste(preuve=preuve_du_poste(cle, nonce, defi.nonce)).model_dump_json())
    return cle_de_session(cle, nonce, defi.nonce)


async def servir(ws, gestes: Executant, cle: str, nonce: Callable[[], str] = nouveau_nonce) -> None:
    """Sert une connexion au Core jusqu'à sa fin : la preuve de la clé, puis un geste signé
    à la fois, dans l'ordre. Une action non signée, ou rejouée, n'est jamais exécutée."""
    messages = aiter(ws)
    session = await _session(ws, messages, cle, nonce())
    dernier = 0  # le dernier geste exécuté : un geste rejoué ne repart pas
    async for brut in messages:
        if not isinstance(brut, str):
            continue
        try:
            message = decoder_message_vers_poste(brut)
        except ValueError as e:
            # Un geste hors de la liste n'est jamais exécuté ; le Core apprend pourquoi.
            _journal.warning("geste refusé : %s", e)
            if (identifiant := _identifiant(brut)) is not None:
                erreur = f"Geste refusé par le poste : {e}"
                refus = ResultatPoste(id=identifiant, ok=False, erreur=erreur)
                await ws.send(signer(session, refus).model_dump_json())
            continue
        if isinstance(message, PretPoste):
            _journal.info("connecté au Core")
            continue
        if not isinstance(message, ActionPoste):
            continue
        if not est_signe(session, message) or message.id <= dernier:
            _journal.warning("action non signée ou rejouée : ignorée (id %s)", message.id)
            continue
        dernier = message.id
        resultat = await asyncio.to_thread(gestes.executer, message)
        await ws.send(signer(session, resultat).model_dump_json())


async def principal() -> None:
    import websockets

    from .gestes import Gestes
    from .quartz import EvenementsQuartz

    logging.basicConfig(level=logging.INFO)
    url, cle = lire_reglages()
    evenements = EvenementsQuartz()
    evenements.demander_les_autorisations()
    gestes = Gestes(evenements=evenements)
    await boucle_de_connexion(
        lambda: websockets.connect(url),
        lambda ws: servir(ws, gestes, cle),
        nom_cle="ATLAS_POSTE_CLE",
    )


if __name__ == "__main__":
    asyncio.run(principal())

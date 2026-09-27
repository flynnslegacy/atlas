"""Le poste : se connecter au Core, exécuter ses gestes, lui répondre.

Lancé sur le Mac de David par `make run-poste`. Il ouvre lui-même sa connexion (aucun port
n'est ouvert sur le Mac), se présente avec `ATLAS_POSTE_CLE`, puis exécute les gestes du
Core un par un, hors de la boucle, et répond à chacun. Si le Core disparaît, il se
reconnecte, comme le client audio.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Protocol

from atlas_audio.connexion import boucle_de_connexion
from atlas_core.protocole_poste import (
    ActionPoste,
    BonjourPoste,
    PretPoste,
    ResultatPoste,
    decoder_message_vers_poste,
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


async def servir(ws, gestes: Executant, cle: str) -> None:
    """Sert une connexion au Core jusqu'à sa fin : un geste à la fois, dans l'ordre."""
    await ws.send(BonjourPoste(cle=cle).model_dump_json())
    async for brut in ws:
        if not isinstance(brut, str):
            continue
        try:
            message = decoder_message_vers_poste(brut)
        except ValueError as e:
            # Un geste hors de la liste n'est jamais exécuté ; le Core apprend pourquoi.
            _journal.warning("geste refusé : %s", e)
            if (identifiant := _identifiant(brut)) is not None:
                erreur = f"Geste refusé par le poste : {e}"
                await ws.send(
                    ResultatPoste(id=identifiant, ok=False, erreur=erreur).model_dump_json()
                )
            continue
        if isinstance(message, PretPoste):
            _journal.info("connecté au Core")
            continue
        resultat = await asyncio.to_thread(gestes.executer, message)
        await ws.send(resultat.model_dump_json())


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

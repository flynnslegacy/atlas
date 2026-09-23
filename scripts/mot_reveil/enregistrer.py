"""Enregistrement guidé de la voix de David pour « Hey Atlas ».

    uv run python -m scripts.mot_reveil.enregistrer

Passe par le vrai chemin du micro d'Atlas (binaire Swift avec annulation d'écho,
ou sounddevice si ATLAS_AUDIO_PERIPHERIQUE=sounddevice). Reprend là où elle
s'était arrêtée : une prise déjà enregistrée n'est pas refaite.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path

import numpy as np

from .audio import ecrire_wav
from .seance import Prise, plan_seance

DOSSIER = Path("donnees/mot_reveil/david")
DUREE_BLOC_S = 0.02


async def attendre_entree(peripherique, message: str, demander: Callable[[str], str]) -> None:
    """Attend Entrée sans laisser déborder la file du micro : le son est lu et jeté."""
    attente = asyncio.create_task(asyncio.to_thread(demander, message))
    while not attente.done():
        try:
            await asyncio.wait_for(peripherique.lire_bloc(), timeout=0.1)
        # Avant Python 3.11, asyncio.TimeoutError est distinct du TimeoutError natif ; ce
        # module doit tourner en 3.10 (contraintes.md), d'où la forme explicite ci-dessous.
        except asyncio.TimeoutError:  # noqa: UP041
            pass
    await attente


async def enregistrer_prise(peripherique, duree_s: float) -> np.ndarray:
    blocs = [await peripherique.lire_bloc() for _ in range(round(duree_s / DUREE_BLOC_S))]
    return np.frombuffer(b"".join(blocs), dtype="<i2").astype(np.float32) / 32768.0


async def seance(
    peripherique, prises: list[Prise], dossier: Path, demander: Callable[[str], str] = input
) -> int:
    faites = 0
    for rang, prise in enumerate(prises, 1):
        chemin = dossier / prise.dossier / f"{prise.nom}.wav"
        if chemin.exists():
            continue
        message = (
            f"\n[{rang}/{len(prises)}] {prise.consigne}\n"
            f"Entrée, puis vas-y ({prise.duree_s:.0f} s)."
        )
        await attendre_entree(peripherique, message, demander)
        ecrire_wav(chemin, await enregistrer_prise(peripherique, prise.duree_s))
        faites += 1
    return faites


async def principal() -> None:
    from atlas_audio.aec import ouvrir_peripherique

    peripherique = await ouvrir_peripherique()
    try:
        n = await seance(peripherique, plan_seance(), DOSSIER)
    finally:
        await peripherique.fermer()
    print(f"\n{n} prises enregistrées dans {DOSSIER}.")


if __name__ == "__main__":
    asyncio.run(principal())

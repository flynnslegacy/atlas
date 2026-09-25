"""Essai réel du cerveau, hors de `make test` : le vrai CLI claude, les options exactes.

Six questions : une présentation, l'heure (la ligne de date), un rappel de la question
précédente (la conversation), une recherche web, une longue réponse coupée en route, puis
une question juste après la coupure (le ménage). Chaque question part de sa propre tâche,
comme les tours de la session.

Il consomme un peu de l'abonnement Claude : à lancer à la main, avec l'accord de David.

    uv run python scripts/essai_cerveau.py
"""

from __future__ import annotations

import asyncio
import os
import re
import tempfile
import time
from pathlib import Path

from claude_agent_sdk import ClaudeSDKClient

from atlas_core.cerveau import RECHERCHE, ErreurCerveau
from atlas_core.cerveau_claude import CerveauClaude, options_cerveau, purger_cles_api
from atlas_core.config import Config

QUESTIONS = [
    ("Bonjour Atlas, présente-toi en une phrase.", None),
    ("Quelle heure est-il, et quel jour sommes-nous ?", None),
    ("Qu'est-ce que je t'ai demandé juste avant ?", None),
    ("Quel temps fait-il à Paris aujourd'hui ?", None),
    ("Raconte-moi en détail l'histoire de la tour Eiffel.", 120),
    ("Pardon, je t'ai coupé : résume-la en une phrase.", None),
]


async def poser(cerveau: CerveauClaude, texte: str, couper_apres: int | None) -> None:
    print(f"\n» {texte}")
    debut = time.monotonic()
    premier: float | None = None
    rendu = 0
    flux = cerveau.repondre(texte)
    try:
        async for fragment in flux:
            if premier is None:
                premier = time.monotonic() - debut
                print(f"  [premier fragment après {premier:.1f} s]")
            if fragment is RECHERCHE:
                print("  [recherche web]")
                continue
            print(fragment, end="", flush=True)
            rendu += len(fragment)
            if couper_apres is not None and rendu >= couper_apres:
                print("\n  [coupé ici, comme par un barge-in]")
                break
    except ErreurCerveau as e:
        print(f"\n  [erreur] {e}")
    finally:
        await flux.aclose()
    print(f"\n  [{time.monotonic() - debut:.1f} s]")


def _transcriptions(dossier: Path) -> list[Path]:
    """Les transcriptions que le CLI aurait écrites pour ce dossier de travail."""
    projets = Path.home() / ".claude" / "projects"
    if not projets.is_dir():
        return []
    # Le CLI range chaque dossier de travail sous un nom où tout ce qui n'est ni lettre ni
    # chiffre devient « - ».
    marque = re.sub(r"[^A-Za-z0-9]", "-", dossier.name)
    return [f for d in projets.iterdir() if marque in d.name for f in d.glob("*.jsonl")]


async def principal() -> None:
    config = Config.depuis_environnement()
    retirees = purger_cles_api(os.environ)
    if retirees:
        print(f"Retiré de l'environnement : {', '.join(retirees)}")
    print(f"Modèle : {config.cerveau_modele}")
    with tempfile.TemporaryDirectory(prefix="atlas-essai-") as nom:
        dossier = Path(nom).resolve()
        cerveau = CerveauClaude(
            lambda: ClaudeSDKClient(options=options_cerveau(config.cerveau_modele, dossier))
        )
        try:
            for texte, couper_apres in QUESTIONS:
                await asyncio.create_task(poser(cerveau, texte, couper_apres))
        finally:
            await cerveau.fermer()
        ecrites = _transcriptions(dossier)
    if ecrites:
        print(f"\nATTENTION : le CLI a écrit {len(ecrites)} transcription(s) sur le disque :")
        for chemin in ecrites:
            print(f"  {chemin}")
    else:
        print("\nAucune transcription écrite sur le disque par le CLI.")


if __name__ == "__main__":
    asyncio.run(principal())

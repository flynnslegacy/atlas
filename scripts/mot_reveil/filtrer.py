"""Garde les extraits synthétisés où Whisper entend ce qu'il faut.

    /opt/piper/bin/python -m scripts.mot_reveil.filtrer
        --clips /travail/clips --retenus /travail/retenus --stt http://localhost:9010

Reprend là où il s'était arrêté, grâce au journal retenus/filtrage.json.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
from pathlib import Path

import httpx

from .phrases import a_garder

SORTES = {"positifs": True, "negatifs": False}


async def transcrire(http: httpx.AsyncClient, url: str, wav: bytes) -> str:
    reponse = await http.post(
        f"{url.rstrip('/')}/transcribe",
        content=wav,
        headers={"Content-Type": "audio/wav"},
        timeout=60.0,
    )
    reponse.raise_for_status()
    return reponse.json()["text"]


def _duree_s(chemin: Path) -> float:
    import soundfile as sf

    return sf.info(str(chemin)).duration


async def filtrer(
    http: httpx.AsyncClient, url: str, clips: Path, retenus: Path, paralleles: int = 4
) -> dict[str, dict[str, int]]:
    chemin_journal = retenus / "filtrage.json"
    journal: dict[str, dict] = (
        json.loads(chemin_journal.read_text()) if chemin_journal.exists() else {}
    )
    limite = asyncio.Semaphore(paralleles)

    async def trancher(source: str, sorte: str, fichier: Path) -> None:
        cle = f"{source}/{sorte}/{fichier.name}"
        if cle not in journal:
            async with limite:
                texte = await transcrire(http, url, fichier.read_bytes())
            journal[cle] = {
                "texte": texte,
                "garde": a_garder(texte, SORTES[sorte], _duree_s(fichier)),
            }
        if journal[cle]["garde"]:
            cible = retenus / sorte / f"{source}_{fichier.name}"
            cible.parent.mkdir(parents=True, exist_ok=True)
            if not cible.exists():
                shutil.copyfile(fichier, cible)

    bilan: dict[str, dict[str, int]] = {}
    try:
        for source in sorted(p.name for p in clips.iterdir() if p.is_dir()):
            for sorte in SORTES:
                fichiers = sorted((clips / source / sorte).glob("*.wav"))
                await asyncio.gather(*(trancher(source, sorte, f) for f in fichiers))
                bilan.setdefault(source, {})[sorte] = sum(
                    journal[f"{source}/{sorte}/{f.name}"]["garde"] for f in fichiers
                )
    finally:
        retenus.mkdir(parents=True, exist_ok=True)
        chemin_journal.write_text(json.dumps(journal, indent=1, ensure_ascii=False))
    return bilan


async def principal(args: argparse.Namespace) -> None:
    async with httpx.AsyncClient() as http:
        bilan = await filtrer(http, args.stt, args.clips, args.retenus)
    for source, sortes in bilan.items():
        print(f"{source} : {sortes['positifs']} positifs et {sortes['negatifs']} négatifs gardés.")


def main(argv: list[str] | None = None) -> None:
    parseur = argparse.ArgumentParser(description=__doc__)
    parseur.add_argument("--clips", type=Path, required=True)
    parseur.add_argument("--retenus", type=Path, required=True)
    parseur.add_argument("--stt", default=os.environ.get("ATLAS_STT_URL", "http://localhost:9010"))
    asyncio.run(principal(parseur.parse_args(argv)))


if __name__ == "__main__":
    main()

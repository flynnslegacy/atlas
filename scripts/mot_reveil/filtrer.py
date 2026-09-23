"""Garde les extraits synthétisés qui ont la bonne forme.

Positifs : jugés à leur durée seule (voir phrases.garder_positif). Négatifs : écartés
si Whisper y entend « hey atlas ». Les dossiers d'essai (<source>/essai/) sont ignorés.

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

from .phrases import garder_negatif, garder_positif

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


def _sauvegarder_journal(chemin_journal: Path, journal: dict) -> None:
    """Écrit le journal atomiquement (fichier temporaire puis renommage) : un `docker stop`
    ou un crash en cours de route ne peut jamais laisser un journal à moitié écrit."""
    chemin_journal.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemin_journal.with_name(chemin_journal.name + ".tmp")
    tmp.write_text(json.dumps(journal, indent=1, ensure_ascii=False))
    os.replace(tmp, chemin_journal)


async def filtrer(
    http: httpx.AsyncClient,
    url: str,
    clips: Path,
    retenus: Path,
    paralleles: int = 4,
    sauvegarde_tous: int = 200,
) -> dict[str, dict[str, int]]:
    chemin_journal = retenus / "filtrage.json"
    journal: dict[str, dict] = (
        json.loads(chemin_journal.read_text()) if chemin_journal.exists() else {}
    )
    limite = asyncio.Semaphore(paralleles)
    decisions = 0

    async def trancher(source: str, sorte: str, fichier: Path) -> None:
        nonlocal decisions
        cle = f"{source}/{sorte}/{fichier.name}"
        if cle not in journal:
            duree = round(_duree_s(fichier), 2)
            if SORTES[sorte]:
                journal[cle] = {"duree_s": duree, "garde": garder_positif(duree)}
            else:
                async with limite:
                    texte = await transcrire(http, url, fichier.read_bytes())
                journal[cle] = {
                    "texte": texte,
                    "duree_s": duree,
                    "garde": garder_negatif(texte, duree),
                }
            decisions += 1
            if decisions % sauvegarde_tous == 0:
                _sauvegarder_journal(chemin_journal, journal)
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
        _sauvegarder_journal(chemin_journal, journal)
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

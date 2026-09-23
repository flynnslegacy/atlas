"""Fait écouter, sur le Mac, quelques extraits par voix d'un essai rapatrié de l'Unraid.

    uv run python -m scripts.mot_reveil.ecouter donnees/mot_reveil/essais/piper --par-voix 3
    uv run python -m scripts.mot_reveil.ecouter donnees/mot_reveil/essais/qwen

Lit <dossier>/positifs/manifeste.json (écrit par generer_piper et generer_qwen), annonce
chaque voix, avec sa description pour une voix Qwen, puis joue ses extraits avec afplay.
C'est le vrai contrôle des positifs : Whisper ne sait pas juger deux mots isolés.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections.abc import Callable
from pathlib import Path

from .generer_qwen import DESCRIPTIONS


def choisir(manifeste: dict[str, dict], par_voix: int) -> list[tuple[str, list[str]]]:
    """Les `par_voix` premiers extraits de chaque voix, voix triées par nom."""
    par_nom: dict[str, list[str]] = {}
    for nom in sorted(manifeste):
        par_nom.setdefault(manifeste[nom]["voix"], []).append(nom)
    return [(voix, noms[:par_voix]) for voix, noms in sorted(par_nom.items())]


def _presenter(voix: str) -> str:
    qwen = re.fullmatch(r"voix_(\d+)", voix)
    if qwen and int(qwen.group(1)) < len(DESCRIPTIONS):
        return f"{voix} : {DESCRIPTIONS[int(qwen.group(1))]}"
    return voix


def _afplay(chemin: Path) -> None:
    subprocess.run(["afplay", str(chemin)], check=False)


def ecouter(dossier: Path, par_voix: int, jouer: Callable[[Path], None] = _afplay) -> None:
    positifs = dossier / "positifs"
    manifeste = json.loads((positifs / "manifeste.json").read_text())
    for voix, noms in choisir(manifeste, par_voix):
        print(f"\n== {_presenter(voix)}")
        for nom in noms:
            print(f"   {nom} : « {manifeste[nom]['texte']} »", flush=True)
            jouer(positifs / f"{nom}.wav")


def main(argv: list[str] | None = None) -> None:
    parseur = argparse.ArgumentParser(description=__doc__)
    parseur.add_argument("dossier", type=Path)
    parseur.add_argument("--par-voix", type=int, default=1)
    args = parseur.parse_args(argv)
    ecouter(args.dossier, args.par_voix)


if __name__ == "__main__":
    main()

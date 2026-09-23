"""Génère les extraits Piper : positifs « Eille Atlasse » et négatifs proches.

Tourne dans le conteneur d'entraînement, avec l'environnement /opt/piper :
    /opt/piper/bin/python -m scripts.mot_reveil.generer_piper
        --voix /travail/voix_piper --sortie /travail/clips/piper
        [--essai] [--exclure fr_FR-gilles-low]

L'essai s'écrit dans <sortie>/essai/, que filtrer.py ignore : on l'écoute, on ne s'en sert pas.
"""

from __future__ import annotations

import argparse
import json
import random
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .audio import couper_silences, ecrire_wav, ramener_16k
from .phrases import NEGATIVES, POSITIVES

# Seules les voix qui disent « Hey Atlas » juste, à l'oreille de David (essais du 24 septembre
# 2026). Écartées : fr_FR-mls-medium et fr_FR-mls_1840-low (2 à 9 s de charabia pour deux
# mots), fr_FR-upmc-medium (durée normale, mais prononciation fausse).
VOIX = ("fr_FR-siwis-medium", "fr_FR-tom-medium", "fr_FR-gilles-low")


@dataclass(frozen=True)
class Tache:
    nom: str
    voix: str
    locuteur: int | None
    texte: str
    vitesse: float
    bruit: float
    bruit_duree: float


def planifier(
    locuteurs: dict[str, int], textes: list[str], nombre: int, prefixe: str, graine: int
) -> list[Tache]:
    """Tire `nombre` combinaisons reproductibles ; chaque locuteur a la même chance."""
    rng = random.Random(graine)
    paires = [
        (voix, locuteur)
        for voix, n in sorted(locuteurs.items())
        for locuteur in (range(n) if n > 1 else [None])
    ]
    taches = []
    for i in range(nombre):
        voix, locuteur = rng.choice(paires)
        taches.append(
            Tache(
                f"{prefixe}_{i:06d}",
                voix,
                locuteur,
                rng.choice(textes),
                round(rng.uniform(0.8, 1.3), 2),
                round(rng.uniform(0.4, 0.9), 2),
                round(rng.uniform(0.6, 1.0), 2),
            )
        )
    return taches


def synthetiser(voix_chargee, tache: Tache, fabrique_config: Callable | None = None):
    if fabrique_config is None:
        from piper import SynthesisConfig as fabrique_config
    config = fabrique_config(
        speaker_id=tache.locuteur,
        length_scale=tache.vitesse,
        noise_scale=tache.bruit,
        noise_w_scale=tache.bruit_duree,
    )
    morceaux = list(voix_chargee.synthesize(tache.texte, syn_config=config))
    if not morceaux:
        return np.zeros(0, dtype=np.float32), voix_chargee.config.sample_rate
    audio = np.concatenate([np.asarray(m.audio_float_array, dtype=np.float32) for m in morceaux])
    return audio, morceaux[0].sample_rate


def produire(
    taches: list[Tache], voix_chargees: dict, dossier: Path, fabrique_config: Callable | None = None
) -> int:
    """Synthétise `taches` dans `dossier`, avec un manifeste.json (nom -> voix, texte, vitesse).

    Sans lui, les fichiers `piper_pos_NNNNNN.wav` ne disent pas quelle voix les a produits :
    impossible de retrouver les extraits d'une voix donnée (par exemple mls) pour les écouter.
    Le manifeste se complète à chaque reprise, sans perdre les entrées déjà écrites.
    """
    chemin_manifeste = dossier / "manifeste.json"
    manifeste: dict[str, dict] = (
        json.loads(chemin_manifeste.read_text()) if chemin_manifeste.exists() else {}
    )
    ecrits = 0
    avant = dict(manifeste)
    for tache in taches:
        chemin = dossier / f"{tache.nom}.wav"
        if chemin.exists():
            # Écrit avant un arrêt brutal, peut-être sans son entrée : le tirage est
            # reproductible, la tâche la redonne.
            manifeste.setdefault(tache.nom, _entree(tache))
            continue
        audio, frequence = synthetiser(voix_chargees[tache.voix], tache, fabrique_config)
        audio = couper_silences(ramener_16k(audio, frequence))
        if audio.size:
            ecrire_wav(chemin, audio)
            manifeste[tache.nom] = _entree(tache)
            ecrits += 1
    if manifeste != avant:
        chemin_manifeste.write_text(json.dumps(manifeste, indent=1, ensure_ascii=False))
    return ecrits


def _entree(tache: Tache) -> dict:
    return {
        "voix": tache.voix,
        "locuteur": tache.locuteur,
        "texte": tache.texte,
        "vitesse": tache.vitesse,
    }


def main(argv: list[str] | None = None) -> None:
    parseur = argparse.ArgumentParser(description=__doc__)
    parseur.add_argument("--voix", type=Path, required=True)
    parseur.add_argument("--sortie", type=Path, required=True)
    parseur.add_argument("--positifs", type=int, default=6000)
    parseur.add_argument("--negatifs", type=int, default=6000)
    parseur.add_argument("--graine", type=int, default=1)
    parseur.add_argument("--exclure", nargs="*", default=[])
    parseur.add_argument("--essai", action="store_true", help="50 positifs et 50 négatifs")
    args = parseur.parse_args(argv)

    from piper import PiperVoice

    voix_chargees = {
        nom: PiperVoice.load(str(args.voix / f"{nom}.onnx"))
        for nom in VOIX
        if nom not in args.exclure and (args.voix / f"{nom}.onnx").exists()
    }
    if not voix_chargees:
        raise SystemExit(f"Aucune voix Piper dans {args.voix} : lance telecharger_donnees.sh.")
    locuteurs = {nom: max(1, v.config.num_speakers) for nom, v in voix_chargees.items()}
    n_pos, n_neg = (50, 50) if args.essai else (args.positifs, args.negatifs)
    dossier = args.sortie / "essai" if args.essai else args.sortie
    for sorte, textes, n, graine in (
        ("positifs", POSITIVES, n_pos, args.graine),
        ("negatifs", NEGATIVES, n_neg, args.graine + 1),
    ):
        taches = planifier(locuteurs, textes, n, f"piper_{sorte[:3]}", graine)
        ecrits = produire(taches, voix_chargees, dossier / sorte)
        print(f"{sorte} : {ecrits} extraits écrits dans {dossier / sorte}.")


if __name__ == "__main__":
    main()

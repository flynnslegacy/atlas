"""Assemble le dossier d'entraînement de train.py à partir de tout ce qui a été produit.

    python -m scripts.mot_reveil.preparer --travail /travail [--essai]

Entrées, sous /travail :
- retenus/{positifs,negatifs}/ : extraits gardés par filtrer.py ;
- david/{positifs,atlas_seul,parole,bureau}/ : enregistrements de David ;
- david/faux_reveils/ : alertes de veiller.py, à partir de la deuxième itération.
Sortie : entrainement/hey_atlas/{positive,negative}_{train,test}/, les traits
négatifs de David, les bruits de son bureau en fond, et entrainement/hey_atlas.yml.
"""

from __future__ import annotations

import argparse
import shutil
from collections.abc import Callable
from pathlib import Path

import numpy as np

from .audio import couper_silences, ecrire_wav, fenetres, lire_wav, ramener_16k
from .configuration import configuration, ecrire
from .repartition import est_test, noms_copies, repartir

UNE_SUR_SYNTHESE = 10
UNE_SUR_DAVID = 3  # identique à evaluer.UNE_SUR_DAVID (un test y veille)
COPIES_DAVID = 30
COPIES_NEGATIFS_DAVID = 10
PAS = 50000
PAS_ESSAI = 500


def _lire_16k(chemin: Path) -> np.ndarray:
    audio, frequence = lire_wav(chemin)
    return ramener_16k(audio, frequence)


def preparer(
    travail: Path, extraire: Callable[[np.ndarray], np.ndarray], essai: bool = False
) -> dict:
    racine = travail / "entrainement" / "hey_atlas"
    for sous in ("positive_train", "positive_test", "negative_train", "negative_test"):
        shutil.rmtree(racine / sous, ignore_errors=True)
        (racine / sous).mkdir(parents=True)

    # 1. Synthèse gardée par Whisper : un extrait sur dix va au test.
    for sorte, prefixe in (("positifs", "positive"), ("negatifs", "negative")):
        dossier = travail / "retenus" / sorte
        noms = sorted(p.name for p in dossier.glob("*.wav"))
        if essai:
            noms = noms[:300]
        entrainement, test = repartir(noms, UNE_SUR_SYNTHESE)
        for partie, liste in (("train", entrainement), ("test", test)):
            for nom in liste:
                shutil.copyfile(dossier / nom, racine / f"{prefixe}_{partie}" / nom)

    # 2. « Hey Atlas » de David : jamais la part de test, et le reste dupliqué pour peser.
    david = travail / "david"
    for sous, prefixe, copies in (
        ("positifs", "positive", COPIES_DAVID),
        ("atlas_seul", "negative", COPIES_NEGATIFS_DAVID),
    ):
        for chemin in sorted((david / sous).glob("*.wav")):
            if est_test(chemin.name, UNE_SUR_DAVID):
                continue
            audio = couper_silences(_lire_16k(chemin))
            if audio.size:
                for copie in noms_copies(f"david_{chemin.name}", copies):
                    ecrire_wav(racine / f"{prefixe}_train" / copie, audio)

    # 3. Faux réveils capturés par la veille : des négatifs précieux.
    for chemin in sorted((david / "faux_reveils").glob("*.wav")):
        for copie in noms_copies(f"faux_{chemin.name}", COPIES_NEGATIFS_DAVID):
            shutil.copyfile(chemin, racine / "negative_train" / copie)

    if not any((racine / "positive_test").glob("*.wav")):
        raise SystemExit("positive_test est vide : train.py ne peut pas calculer sa fenêtre.")

    # 4. Parole et bureau de David (hors test) : traits négatifs, et bruits de fond.
    morceaux = []
    fonds = travail / "donnees" / "fonds" / "bureau_david"
    shutil.rmtree(fonds, ignore_errors=True)  # sinon un fond retiré de la source y resterait
    for sous in ("parole", "bureau"):
        for chemin in sorted((david / sous).glob("*.wav")):
            if est_test(chemin.name, UNE_SUR_DAVID):
                continue
            audio = _lire_16k(chemin)
            morceaux.append(fenetres(audio, 2.0))
            if sous == "bureau":
                ecrire_wav(fonds / chemin.name, audio)
    traits = {
        "ACAV100M_sample": str(
            travail / "donnees" / "openwakeword_features_ACAV100M_2000_hrs_16bit.npy"
        )
    }
    chemin_traits = travail / "donnees" / "traits_david.npy"
    if morceaux:
        chemin_traits.parent.mkdir(parents=True, exist_ok=True)
        np.save(chemin_traits, extraire(np.concatenate(morceaux)).astype(np.float32))
        traits["negatifs_david"] = str(chemin_traits)
    else:
        chemin_traits.unlink(missing_ok=True)  # sinon un traits_david.npy d'avant reste orphelin

    ecrire(
        configuration(travail, traits, PAS_ESSAI if essai else PAS),
        travail / "entrainement" / "hey_atlas.yml",
    )
    return {sous.name: len(list(sous.glob("*.wav"))) for sous in sorted(racine.iterdir())}


def extracteur_openwakeword() -> Callable[[np.ndarray], np.ndarray]:
    """Traits openWakeWord (N, 16, 96) de fenêtres de 2 s, comme les données ACAV100M."""
    from openwakeword.utils import AudioFeatures

    traits = AudioFeatures()

    def extraire(fen: np.ndarray) -> np.ndarray:
        pcm = (np.clip(fen, -1.0, 1.0) * 32767).astype(np.int16)
        return traits.embed_clips(pcm, batch_size=64)

    return extraire


def main(argv: list[str] | None = None) -> None:
    parseur = argparse.ArgumentParser(description=__doc__)
    parseur.add_argument("--travail", type=Path, default=Path("/travail"))
    parseur.add_argument("--essai", action="store_true", help="300 extraits, 500 pas")
    args = parseur.parse_args(argv)
    bilan = preparer(args.travail, extracteur_openwakeword(), essai=args.essai)
    for sous, n in bilan.items():
        print(f"{sous} : {n} extraits")


if __name__ == "__main__":
    main()

"""Mesure un modèle « Hey Atlas » par le chemin exact du client Atlas.

    uv run python -m scripts.mot_reveil.evaluer --modele models/hey_atlas.onnx

Seule la part des enregistrements de David réservée au test est utilisée :
preparer.py ne l'a jamais mise dans l'entraînement.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from .audio import couper_silences, en_blocs, lire_wav, ramener_16k
from .metriques import SEUILS, assembler, detectes, par_heure, reveils, seuil_conseille
from .repartition import est_test

DISTANCES = ("bureau", "m150", "m300")
UNE_SUR_DAVID = 3  # preparer.py réserve exactement la même part au test


def charger(dossier: Path, une_sur: int, couper: bool) -> dict[str, np.ndarray]:
    extraits = {}
    for chemin in sorted(dossier.glob("*.wav")):
        if not est_test(chemin.name, une_sur):
            continue
        audio, frequence = lire_wav(chemin)
        audio = ramener_16k(audio, frequence)
        if couper:
            audio = couper_silences(audio)
        if audio.size:
            extraits[chemin.name] = audio
    return extraits


def scores_flux(modele: str, audio: np.ndarray) -> list[float]:
    from atlas_audio.reveilleur import PredicteurOpenWakeWord

    predicteur = PredicteurOpenWakeWord(modele)  # neuf pour chaque flux : aucun état ne fuit
    return [predicteur.score(bloc) for bloc in en_blocs(audio)]


def _exiger_non_vide(extraits: dict[str, np.ndarray], dossier: Path) -> None:
    """Arrête tout avant de charger un modèle si le dossier de test est absent ou vide."""
    if not extraits:
        raise SystemExit(
            f"Aucun enregistrement de test trouvé dans {dossier} : "
            "evaluer.py attend les enregistrements de David produits par enregistrer.py, "
            "sous le dossier passé à --donnees."
        )


def mesurer(modele: str, donnees: Path) -> list[dict]:
    positifs = charger(donnees / "positifs", UNE_SUR_DAVID, couper=True)
    atlas = charger(donnees / "atlas_seul", UNE_SUR_DAVID, couper=True)
    negatifs = {
        **charger(donnees / "parole", UNE_SUR_DAVID, couper=False),
        **charger(donnees / "bureau", UNE_SUR_DAVID, couper=False),
    }
    # Avant tout chargement du modèle : un dossier absent ou vide donnerait sinon un
    # rapport complet et plausible (0 % de détection, 0 faux réveil) indiscernable
    # d'un modèle parfait.
    _exiger_non_vide(positifs, donnees / "positifs")
    _exiger_non_vide(atlas, donnees / "atlas_seul")
    if not negatifs:
        raise SystemExit(
            f"Aucun enregistrement de test trouvé dans {donnees / 'parole'} "
            f"ni {donnees / 'bureau'} : evaluer.py attend les enregistrements de David "
            "produits par enregistrer.py, sous le dossier passé à --donnees."
        )

    flux_positifs = {}
    for distance in DISTANCES:
        extraits = {n: a for n, a in positifs.items() if n.startswith(f"{distance}_")}
        if extraits:
            audio, segments = assembler(extraits)
            flux_positifs[distance] = (scores_flux(modele, audio), segments)
    scores_atlas = scores_flux(modele, assembler(atlas)[0])
    scores_negatifs = scores_flux(modele, assembler(negatifs)[0])

    lignes = []
    for seuil in SEUILS:
        detection = {}
        trouves = total = 0
        for distance, (scores, segments) in flux_positifs.items():
            n = len(detectes(reveils(scores, seuil), segments))
            detection[distance] = n / len(segments)
            trouves += n
            total += len(segments)
        faux = len(reveils(scores_negatifs, seuil))
        lignes.append(
            {
                "seuil": seuil,
                "detection": detection,
                "global": trouves / total if total else 0.0,
                "atlas_seul": len(reveils(scores_atlas, seuil)),
                "faux": faux,
                "faux_par_heure": par_heure(faux, len(scores_negatifs)),
            }
        )
    return lignes


def formater(lignes: list[dict]) -> str:
    entete = "seuil  bureau  1,5 m   3 m    global  « Atlas » seul  faux réveils"
    rangees = [entete]
    for ligne in lignes:
        d = ligne["detection"]
        cellules = [f"{d.get(x, 0.0):5.0%}" for x in DISTANCES]
        rangees.append(
            f"{ligne['seuil']:4.1f}   {'   '.join(cellules)}   {ligne['global']:5.0%}"
            f"  {ligne['atlas_seul']:14d}  {ligne['faux']:3d} ({ligne['faux_par_heure']:.1f}/h)"
        )
    conseil = seuil_conseille(lignes)
    rangees.append(
        f"\nSeuil conseillé : {conseil}"
        if conseil is not None
        else "\nAucun seuil n'évite tous les faux réveils : il faut une itération de plus."
    )
    return "\n".join(rangees)


def main(argv: list[str] | None = None) -> None:
    parseur = argparse.ArgumentParser(description=__doc__)
    parseur.add_argument("--modele", default="models/hey_atlas.onnx")
    parseur.add_argument("--donnees", type=Path, default=Path("donnees/mot_reveil/david"))
    args = parseur.parse_args(argv)
    print(formater(mesurer(args.modele, args.donnees)))


if __name__ == "__main__":
    main()

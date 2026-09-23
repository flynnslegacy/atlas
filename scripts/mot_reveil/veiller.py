"""Écoute une journée sans rien déclencher, et garde 3 s autour de chaque faux réveil.

    uv run python -m scripts.mot_reveil.veiller --modele models/hey_atlas.onnx

Ne la lance pas en même temps que le client Atlas : les deux voudraient le micro.
Ne dis pas « Hey Atlas » pendant la veille : tout ce qu'elle garde doit être faux.
Seules les fenêtres de 3 s autour des alertes sont enregistrées. Ctrl-C pour finir.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

from .audio import ecrire_wav
from .veille import DUREE_BLOC_S, Veilleur


def seuils_veille(seuil: float, seuil_journal: float | None) -> float:
    """Seuil du journal : par défaut le plus bas entre 0,3 et 0,6 fois le seuil réel.

    Lève SystemExit si `seuil_journal` est donné mais n'est pas strictement en dessous
    de `seuil` : un journal au niveau du seuil réel (ou au-dessus) ne repère plus rien
    avant les vrais réveils.
    """
    if seuil_journal is None:
        return min(0.3, round(0.6 * seuil, 2))
    if not seuil_journal < seuil:
        raise SystemExit(
            f"--seuil-journal ({seuil_journal}) doit être strictement inférieur "
            f"à --seuil ({seuil})."
        )
    return seuil_journal


async def veiller(
    peripherique,
    predicteur,
    veilleur: Veilleur,
    dossier: Path,
    seuil_reel: float,
    blocs_max: int | None = None,
) -> list[dict]:
    dossier.mkdir(parents=True, exist_ok=True)
    alertes: list[dict] = []
    lus = 0
    try:
        while blocs_max is None or lus < blocs_max:
            bloc = await peripherique.lire_bloc()
            lus += 1
            alerte = veilleur.ajouter(bloc, predicteur.score(bloc))
            if alerte is None:
                continue
            nom = f"{dossier.name}_alerte_{len(alertes) + 1:04d}_{alerte.score:.2f}.wav"
            ecrire_wav(dossier / nom, alerte.audio)
            faux = alerte.score >= seuil_reel
            alertes.append(
                {
                    "fichier": nom,
                    "score": round(alerte.score, 3),
                    "instant_s": round(alerte.instant_s, 2),
                    "faux_reveil": faux,
                }
            )
            etat = "FAUX RÉVEIL" if faux else "presque"
            print(f"{time.strftime('%H:%M:%S')}  {etat}  score {alerte.score:.2f}  → {nom}")
    finally:
        heures = lus * DUREE_BLOC_S / 3600
        journal = {
            "heures": round(heures, 2),
            "seuil_reel": seuil_reel,
            "faux_reveils": sum(a["faux_reveil"] for a in alertes),
            "alertes": alertes,
        }
        (dossier / "journal.json").write_text(json.dumps(journal, indent=2, ensure_ascii=False))
    return alertes


async def principal(args: argparse.Namespace) -> None:
    from atlas_audio.aec import ouvrir_peripherique
    from atlas_audio.reveilleur import PredicteurOpenWakeWord

    seuil_reel = args.seuil
    seuil_journal = seuils_veille(seuil_reel, args.seuil_journal)
    dossier = args.dossier / time.strftime("%Y%m%d-%H%M")
    predicteur = PredicteurOpenWakeWord(args.modele)
    peripherique = await ouvrir_peripherique()
    print(f"Veille en cours (seuil réel {seuil_reel}). Ctrl-C pour finir. Alertes : {dossier}")
    try:
        alertes = await veiller(
            peripherique, predicteur, Veilleur(seuil_journal), dossier, seuil_reel
        )
    except (KeyboardInterrupt, asyncio.CancelledError):
        alertes = json.loads((dossier / "journal.json").read_text())["alertes"]
    finally:
        await peripherique.fermer()
    faux = sum(a["faux_reveil"] for a in alertes)
    print(f"\n{faux} faux réveils, {len(alertes) - faux} presque. Journal : {dossier}/journal.json")


def main(argv: list[str] | None = None) -> None:
    from atlas_audio.client import lire_reglages

    parseur = argparse.ArgumentParser(description=__doc__)
    parseur.add_argument("--modele", default="models/hey_atlas.onnx")
    parseur.add_argument("--seuil", type=float, default=lire_reglages().seuil_reveil)
    parseur.add_argument("--seuil-journal", type=float, default=None)
    parseur.add_argument("--dossier", type=Path, default=Path("donnees/mot_reveil/veille"))
    try:
        asyncio.run(principal(parseur.parse_args(argv)))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

"""Génère les extraits Qwen3 : une quinzaine de voix conçues, puis clonées.

Tourne dans un conteneur ponctuel de l'image atlas-tts, qui a torch et qwen-tts.
Arrête d'abord le service atlas-tts, pour libérer la mémoire vidéo :
    python -m scripts.mot_reveil.generer_qwen concevoir --sortie /travail/clips/qwen
    python -m scripts.mot_reveil.generer_qwen cloner --sortie /travail/clips/qwen
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .audio import couper_silences, ecrire_wav, lire_wav, ramener_16k
from .phrases import NEGATIVES, POSITIVES

DESCRIPTIONS = (
    "Voix d'homme d'une trentaine d'années, grave et posée, accent français standard.",
    "Voix de femme d'une trentaine d'années, claire et dynamique, accent français standard.",
    "Voix d'homme âgé d'environ soixante-dix ans, un peu rauque, débit lent.",
    "Voix de femme âgée d'environ soixante-dix ans, douce et chaleureuse.",
    "Voix d'enfant d'environ huit ans, aiguë et enjouée.",
    "Voix d'adolescent d'environ quinze ans, un peu nonchalante.",
    "Voix de femme d'une vingtaine d'années, rapide et souriante.",
    "Voix d'homme d'une cinquantaine d'années, chaleureuse, légèrement nasale.",
    "Voix d'homme jeune, accent du sud de la France, chantante.",
    "Voix de femme, accent québécois, naturelle.",
    "Voix d'homme, accent belge, détendue.",
    "Voix de femme d'une quarantaine d'années, grave et sérieuse.",
    "Voix d'enfant d'environ six ans, timide et douce.",
    "Voix d'homme qui parle vite, un peu essoufflé et pressé.",
    "Voix de femme fatiguée, débit lent, voix basse.",
)
# Le texte doit être EXACTEMENT ce que dit la référence : sinon le clonage commence
# chaque phrase par la fin du texte (leçon du spike S1). On ne coupe donc jamais la référence.
TEXTE_REFERENCE = (
    "Bonjour, je te lis la suite. Tout est prêt de mon côté, on peut commencer quand tu veux."
)
MAX_JETONS = 400  # 8 s d'audio au plus : largement assez pour « Eille Atlasse »


@dataclass(frozen=True)
class TacheQwen:
    nom: str
    voix: int
    texte: str


def planifier_qwen(nb_voix: int, textes: list[str], nombre: int, prefixe: str) -> list[TacheQwen]:
    """Répartit `nombre` extraits à parts égales entre voix et textes."""
    return [
        TacheQwen(f"{prefixe}_{i:06d}", i % nb_voix, textes[(i // nb_voix) % len(textes)])
        for i in range(nombre)
    ]


def charger(nom_modele: str):
    import torch
    from qwen_tts import Qwen3TTSModel

    options = {"device_map": "cuda:0", "dtype": torch.bfloat16}
    try:
        return Qwen3TTSModel.from_pretrained(nom_modele, attn_implementation="sdpa", **options)
    except (TypeError, ValueError):
        return Qwen3TTSModel.from_pretrained(nom_modele, **options)


def concevoir(modele, dossier_references: Path, descriptions=DESCRIPTIONS) -> int:
    import soundfile as sf

    dossier_references.mkdir(parents=True, exist_ok=True)
    faites = 0
    for i, description in enumerate(descriptions):
        chemin = dossier_references / f"voix_{i:02d}.wav"
        if chemin.exists():
            continue
        wavs, frequence = modele.generate_voice_design(
            text=TEXTE_REFERENCE, language="French", instruct=description
        )
        audio = np.asarray(wavs[0], dtype=np.float32)
        sf.write(str(chemin), audio, frequence, subtype="PCM_16")  # fréquence native gardée
        chemin.with_suffix(".txt").write_text(TEXTE_REFERENCE, encoding="utf-8")
        faites += 1
    return faites


def cloner(modele, dossier_references: Path, taches: list[TacheQwen], dossier_sortie: Path) -> int:
    invites: dict[int, object] = {}
    ecrits = 0
    for tache in taches:
        chemin = dossier_sortie / f"{tache.nom}.wav"
        if chemin.exists():
            continue
        if tache.voix not in invites:
            reference = dossier_references / f"voix_{tache.voix:02d}.wav"
            audio_ref, frequence_ref = lire_wav(reference)
            texte_ref = reference.with_suffix(".txt").read_text(encoding="utf-8").strip()
            invites[tache.voix] = modele.create_voice_clone_prompt(
                ref_audio=(audio_ref, frequence_ref), ref_text=texte_ref, x_vector_only_mode=False
            )
        wavs, frequence = modele.generate_voice_clone(
            text=tache.texte,
            language="French",
            voice_clone_prompt=invites[tache.voix],
            max_new_tokens=MAX_JETONS,
        )
        audio = couper_silences(ramener_16k(np.asarray(wavs[0], dtype=np.float32), frequence))
        if audio.size:
            ecrire_wav(chemin, audio)
            ecrits += 1
    return ecrits


def main(argv: list[str] | None = None) -> None:
    parseur = argparse.ArgumentParser(description=__doc__)
    parseur.add_argument("etape", choices=["concevoir", "cloner"])
    parseur.add_argument("--sortie", type=Path, required=True)
    parseur.add_argument("--positifs", type=int, default=8000)
    parseur.add_argument("--negatifs", type=int, default=4000)
    parseur.add_argument("--essai", action="store_true", help="30 positifs et 30 négatifs")
    args = parseur.parse_args(argv)
    references = args.sortie / "references"
    if args.etape == "concevoir":
        n = concevoir(charger("Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign"), references)
        print(f"{n} voix conçues dans {references}. Écoute-les avant de cloner.")
        return
    nb_voix = len(sorted(references.glob("voix_*.wav")))
    if nb_voix == 0:
        raise SystemExit("Aucune voix de référence : lance d'abord l'étape « concevoir ».")
    modele = charger("Qwen/Qwen3-TTS-12Hz-1.7B-Base")
    n_pos, n_neg = (30, 30) if args.essai else (args.positifs, args.negatifs)
    for sorte, textes, n in (("positifs", POSITIVES, n_pos), ("negatifs", NEGATIVES, n_neg)):
        taches = planifier_qwen(nb_voix, textes, n, f"qwen_{sorte[:3]}")
        ecrits = cloner(modele, references, taches, args.sortie / sorte)
        print(f"{sorte} : {ecrits} extraits écrits dans {args.sortie / sorte}.")


if __name__ == "__main__":
    main()

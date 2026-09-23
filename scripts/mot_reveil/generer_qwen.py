"""Génère les extraits Qwen3 : une quarantaine de voix conçues, puis clonées.

Tourne dans un conteneur ponctuel de l'image atlas-tts, qui a torch et qwen-tts.
Arrête d'abord le service atlas-tts, pour libérer la mémoire vidéo :
    python -m scripts.mot_reveil.generer_qwen concevoir --sortie /travail/clips/qwen
    python -m scripts.mot_reveil.generer_qwen cloner --sortie /travail/clips/qwen --essai
    python -m scripts.mot_reveil.generer_qwen cloner --sortie /travail/clips/qwen

L'essai fait dire « Hey Atlas » une fois à chaque voix, dans <sortie>/essai/ (que filtrer.py
ignore). Pour écarter une voix ratée, retire son voix_NN.wav et son voix_NN.txt de
<sortie>/references/ : le clonage n'utilise que les références présentes.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .audio import couper_silences, ecrire_wav, lire_wav, ramener_16k
from .phrases import NEGATIVES_QWEN, POSITIVES_QWEN

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
    "Voix de femme d'une trentaine d'années, accent du sud-ouest, chaleureuse et chantante.",
    "Voix d'homme d'une quarantaine d'années, accent alsacien, posée.",
    "Voix d'homme d'une trentaine d'années, accent québécois, énergique.",
    "Voix de femme d'une cinquantaine d'années, accent belge, souriante.",
    "Voix d'homme d'une soixantaine d'années, accent suisse romand, lent et calme.",
    "Voix de femme d'une trentaine d'années, accent d'Afrique de l'Ouest, claire et assurée.",
    "Voix d'homme d'une quarantaine d'années, accent d'Afrique de l'Ouest, grave et chaleureuse.",
    "Voix d'homme d'une trentaine d'années, accent maghrébin, dynamique.",
    "Voix de femme d'une quarantaine d'années, accent maghrébin, douce.",
    "Voix d'homme d'une trentaine d'années, accent marseillais, enjoué.",
    "Voix de femme d'une vingtaine d'années, accent parisien, un peu traînante.",
    "Voix d'homme d'une vingtaine d'années, aiguë et rapide.",
    "Voix d'adolescente d'environ quatorze ans, vive et claire.",
    "Voix de garçon d'environ dix ans, énergique.",
    "Voix de fillette d'environ sept ans, douce et hésitante.",
    "Voix de femme âgée d'environ quatre-vingts ans, un peu tremblante.",
    "Voix d'homme âgé d'environ quatre-vingts ans, faible et lente.",
    "Voix d'homme d'une cinquantaine d'années, très grave et rauque.",
    "Voix de femme d'une trentaine d'années, grave et voilée.",
    "Voix d'homme d'une trentaine d'années, nasale, débit rapide.",
    "Voix de femme d'une quarantaine d'années, aiguë et énergique.",
    "Voix d'homme d'une quarantaine d'années, très douce, presque chuchotée.",
    "Voix de femme d'une trentaine d'années, enrhumée, un peu nasale.",
    "Voix d'homme d'une vingtaine d'années, accent du nord de la France, détendu.",
    "Voix de femme d'une soixantaine d'années, accent du sud, dynamique.",
)
# Le texte doit être EXACTEMENT ce que dit la référence : sinon le clonage commence
# chaque phrase par la fin du texte (leçon du spike S1). On ne coupe donc jamais la référence.
TEXTE_REFERENCE = (
    "Bonjour, je te lis la suite. Tout est prêt de mon côté, on peut commencer quand tu veux."
)
MAX_JETONS = 400  # 8 s d'audio au plus : largement assez pour « Hey Atlas »
# Qwen lit l'orthographe usuelle ; « Eille Atlasse » est réservé à Piper (espeak).
TEXTES = {"positifs": POSITIVES_QWEN, "negatifs": NEGATIVES_QWEN}


@dataclass(frozen=True)
class TacheQwen:
    nom: str
    voix: str  # nom de la référence, par exemple « voix_07 »
    texte: str


def planifier_qwen(
    voix: list[str], textes: list[str], nombre: int, prefixe: str
) -> list[TacheQwen]:
    """Répartit `nombre` extraits à parts égales entre voix et textes.

    Le nom porte la voix : écarter une voix ne réattribue jamais un fichier déjà écrit.
    """
    n = len(voix)
    taches = []
    for i in range(nombre):
        v, tirage = voix[i % n], i // n
        taches.append(TacheQwen(f"{prefixe}_{v}_{tirage:05d}", v, textes[tirage % len(textes)]))
    return taches


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
    """Clone `taches` dans `dossier_sortie`, avec un manifeste.json (nom -> voix, texte)."""
    chemin_manifeste = dossier_sortie / "manifeste.json"
    manifeste: dict[str, dict] = (
        json.loads(chemin_manifeste.read_text()) if chemin_manifeste.exists() else {}
    )
    invites: dict[str, object] = {}
    ecrits = 0
    avant = dict(manifeste)
    for tache in taches:
        chemin = dossier_sortie / f"{tache.nom}.wav"
        if chemin.exists():
            # Écrit avant un arrêt brutal, peut-être sans son entrée : le tirage est
            # reproductible, la tâche la redonne.
            manifeste.setdefault(tache.nom, {"voix": tache.voix, "texte": tache.texte})
            continue
        if tache.voix not in invites:
            reference = dossier_references / f"{tache.voix}.wav"
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
            manifeste[tache.nom] = {"voix": tache.voix, "texte": tache.texte}
            ecrits += 1
    if manifeste != avant:
        chemin_manifeste.write_text(json.dumps(manifeste, indent=1, ensure_ascii=False))
    return ecrits


def main(argv: list[str] | None = None) -> None:
    parseur = argparse.ArgumentParser(description=__doc__)
    parseur.add_argument("etape", choices=["concevoir", "cloner"])
    parseur.add_argument("--sortie", type=Path, required=True)
    parseur.add_argument("--positifs", type=int, default=12000)
    parseur.add_argument("--negatifs", type=int, default=6000)
    parseur.add_argument("--essai", action="store_true", help="un positif par voix, 30 négatifs")
    args = parseur.parse_args(argv)
    references = args.sortie / "references"
    if args.etape == "concevoir":
        n = concevoir(charger("Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign"), references)
        print(f"{n} voix conçues dans {references}. Écoute-les avant de cloner.")
        return
    voix = sorted(p.stem for p in references.glob("voix_*.wav"))
    if not voix:
        raise SystemExit("Aucune voix de référence : lance d'abord l'étape « concevoir ».")
    modele = charger("Qwen/Qwen3-TTS-12Hz-1.7B-Base")
    n_pos, n_neg = (len(voix), 30) if args.essai else (args.positifs, args.negatifs)
    dossier = args.sortie / "essai" if args.essai else args.sortie
    for sorte, n in (("positifs", n_pos), ("negatifs", n_neg)):
        taches = planifier_qwen(voix, TEXTES[sorte], n, f"qwen_{sorte[:3]}")
        ecrits = cloner(modele, references, taches, dossier / sorte)
        print(f"{sorte} : {ecrits} extraits écrits dans {dossier / sorte}.")


if __name__ == "__main__":
    main()

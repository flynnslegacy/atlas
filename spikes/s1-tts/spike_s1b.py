"""SPIKE S1b — JETABLE. Fixer la voix d'Atlas : la concevoir une fois, puis la cloner.

La voix « décrite » a gagné l'écoute à l'aveugle, avec trois défauts : un écho, des
fins qui partent en silence puis en sons parasites, et une voix réinventée à chaque
appel. Le remède documenté par Qwen : concevoir la voix UNE fois, puis cloner.

Étape 1 — concevoir quatre prises de référence, voix sèche de studio :
    python spike_s1b.py concevoir
Étape 2 — cloner les cinq phrases pièges depuis la prise choisie à l'oreille :
    python spike_s1b.py cloner 3
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf
from spike import FREQUENCE_ATLAS, PHRASES, charger_qwen, ramener_a_atlas

RACINE = Path("/sortie/s1b")
REFERENCES = RACINE / "references"
CLONE = RACINE / "clone"
NB_PRISES = 4

TEXTE_REFERENCE = (
    "Bonjour, je m'appelle Atlas. Je suis là pour t'aider à organiser tes journées, "
    "à suivre tes projets et à répondre à tes questions, calmement et clairement."
)
VOIX_SECHE = (
    "Voix d'homme française d'une quarantaine d'années, grave et posée, diction claire et "
    "naturelle, ton calme et rassurant, accent français standard. Enregistrement de studio, "
    "voix sèche et proche du micro, sans écho, sans réverbération ni bruit de fond."
)
SECONDES_PAR_CARACTERE = 0.07  # débit posé en français : environ 14 caractères par seconde


def duree_attendue(texte: str) -> float:
    return len(texte) * SECONDES_PAR_CARACTERE


def couper_fin(audio: np.ndarray, sr: int, attendu: float) -> tuple[np.ndarray, str]:
    """Coupe ce qui suit la parole : un silence prolongé, puis des sons parasites.

    Passé 60 % de la durée attendue, le premier silence d'au moins 0,6 s marque la fin
    de la phrase ; on garde 0,2 s de queue. À défaut, l'audio est plafonné au double
    de la durée attendue. La règle appliquée est rapportée, pour que l'oreille juge.
    """
    trame = int(0.02 * sr)
    n = len(audio) // trame
    if n == 0:
        return audio, "aucune"
    rms = np.sqrt(np.mean(audio[: n * trame].reshape(n, trame) ** 2, axis=1))
    silencieux = rms < 0.02 * float(rms.max())
    course = 0
    for i in range(int(attendu * 0.6 / 0.02), n):
        course = course + 1 if silencieux[i] else 0
        if course >= 30:
            return audio[: (i - course + 1 + 10) * trame], "silence"
    plafond = int(attendu * 2 * sr)
    if len(audio) > plafond:
        return audio[:plafond], "plafond"
    return audio, "aucune"


def ecrire_json(chemin: Path, donnees: dict) -> None:
    chemin.write_text(json.dumps(donnees, indent=2, ensure_ascii=False), encoding="utf-8")


def concevoir() -> None:
    REFERENCES.mkdir(parents=True, exist_ok=True)
    modele = charger_qwen("Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign")
    attendu = duree_attendue(TEXTE_REFERENCE)
    rapport: dict = {"texte": TEXTE_REFERENCE, "description": VOIX_SECHE, "prises": []}
    for prise in range(1, NB_PRISES + 1):
        debut = time.monotonic()
        wavs, sr = modele.generate_voice_design(
            text=TEXTE_REFERENCE, language="French", instruct=VOIX_SECHE
        )
        calcul = time.monotonic() - debut
        audio = np.asarray(wavs[0], dtype=np.float32)
        brute = len(audio) / sr
        audio, regle = couper_fin(audio, sr, attendu)
        # Fréquence native conservée : c'est la matière première du clonage.
        sf.write(REFERENCES / f"ref_{prise}.wav", audio, sr, subtype="PCM_16")
        rapport["prises"].append(
            {
                "prise": prise,
                "calcul_s": round(calcul, 2),
                "audio_brut_s": round(brute, 2),
                "audio_final_s": round(len(audio) / sr, 2),
                "attendu_s": round(attendu, 2),
                "coupe": regle,
            }
        )
        print(f"prise {prise} : {brute:.1f} s brut, {len(audio) / sr:.1f} s gardé ({regle})")
    ecrire_json(REFERENCES / "references.json", rapport)
    print(f"\nÉcoute les {NB_PRISES} prises dans {REFERENCES} et choisis la meilleure.")


def cloner(prise: int) -> None:
    import torch

    CLONE.mkdir(parents=True, exist_ok=True)
    reference = REFERENCES / f"ref_{prise}.wav"
    audio_ref, sr_ref = sf.read(reference, dtype="float32")
    torch.cuda.reset_peak_memory_stats()
    modele = charger_qwen("Qwen/Qwen3-TTS-12Hz-1.7B-Base")

    debut = time.monotonic()
    invite = modele.create_voice_clone_prompt(
        ref_audio=(audio_ref, sr_ref), ref_text=TEXTE_REFERENCE, x_vector_only_mode=False
    )
    rapport: dict = {
        "reference": reference.name,
        "invite_calculee_en_s": round(time.monotonic() - debut, 2),
        "phrases": [],
    }
    for rang, texte in enumerate(PHRASES, start=1):
        attendu = duree_attendue(texte)
        debut = time.monotonic()
        wavs, sr = modele.generate_voice_clone(
            text=texte, language="French", voice_clone_prompt=invite
        )
        calcul = time.monotonic() - debut
        audio = np.asarray(wavs[0], dtype=np.float32)
        brute = len(audio) / sr
        audio, regle = couper_fin(audio, sr, attendu)
        sf.write(
            CLONE / f"phrase_{rang}.wav",
            ramener_a_atlas(audio, sr),
            FREQUENCE_ATLAS,
            subtype="PCM_16",
        )
        rapport["phrases"].append(
            {
                "phrase": rang,
                "calcul_s": round(calcul, 2),
                "audio_brut_s": round(brute, 2),
                "audio_final_s": round(len(audio) / sr, 2),
                "attendu_s": round(attendu, 2),
                "coupe": regle,
            }
        )
        print(f"phrase {rang} : {calcul:.1f} s de calcul, {brute:.1f} s brut ({regle})")
    rapport["vram_pic_go"] = round(torch.cuda.max_memory_allocated() / 1e9, 2)
    ecrire_json(CLONE / "clone.json", rapport)
    print(f"\nÉcoute les 5 phrases dans {CLONE} : même voix ? écho ? fins propres ?")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "concevoir":
        concevoir()
    elif len(sys.argv) == 3 and sys.argv[1] == "cloner" and sys.argv[2].isdigit():
        cloner(int(sys.argv[2]))
    else:
        sys.exit("usage : spike_s1b.py concevoir | spike_s1b.py cloner <numéro de prise>")

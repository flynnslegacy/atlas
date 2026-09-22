"""SPIKE S1 — JETABLE, à ne pas intégrer tel quel.

Cherche la voix d'Atlas : masculine, fluide, en français. Compare à l'aveugle
Piper Tom (le service atlas-tts déjà lancé) et deux variantes de Qwen3-TTS.

Tout est ramené à 16 kHz et à un volume identique : c'est ce qu'Atlas diffusera,
et ni la bande passante ni le volume ne doivent trahir le moteur.

Produit dans /sortie :
  aveugle/NN.wav  les extraits, dans un ordre mélangé
  grille.txt      la grille à remplir pendant l'écoute
  cles.json       qui est qui — à n'ouvrir QU'APRÈS avoir noté
  mesures.json    temps de calcul, VRAM, API de streaming découverte
"""

from __future__ import annotations

import inspect
import json
import os
import random
import time
import traceback
import urllib.request
from pathlib import Path

import numpy as np
import soundfile as sf
import soxr

SORTIE = Path("/sortie")
AVEUGLE = SORTIE / "aveugle"
URL_PIPER = os.environ.get("ATLAS_TTS_URL", "http://localhost:9011")
FREQUENCE_ATLAS = 16000

# Les cinq phrases pièges : chiffres, guillemets, chemin de fichier, nom propre, question.
PHRASES = [
    "Bonjour David, il est quatorze heures trente-deux.",
    "Le workflow « veille concurrence » a échoué à trois heures du matin : "
    "erreur d'authentification sur l'API.",
    "J'ai noté ça dans projets/atlas.md — tu veux que je te le relise ?",
    "Attention : cette action va envoyer un mail à Paul Durand. Je confirme ?",
    "D'accord. Alors reprenons : tu disais que l'offre devait tenir en une page.",
]

VOIX_DECRITE = (
    "Voix d'homme française d'une quarantaine d'années, grave et posée, diction "
    "claire et naturelle, ton calme et rassurant, accent français standard."
)
CONSIGNE_PRESET = "Parle en français, calmement, sur un ton posé et naturel."

CANDIDATS = [
    {"nom": "piper_tom", "modele": None},
    {"nom": "qwen_preset_uncle_fu", "modele": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"},
    {"nom": "qwen_voix_decrite", "modele": "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign"},
]


def ramener_a_atlas(audio, sr: int) -> np.ndarray:
    """16 kHz, crête à -1 dBFS."""
    audio = np.asarray(audio, dtype=np.float32).flatten()
    if sr != FREQUENCE_ATLAS:
        audio = soxr.resample(audio, sr, FREQUENCE_ATLAS)
    crete = float(np.max(np.abs(audio))) if audio.size else 0.0
    return audio * (0.891 / crete) if crete > 0 else audio


def piper_tom(texte: str) -> tuple[np.ndarray, int]:
    corps = json.dumps({"text": texte, "voice": "fr_FR-tom-medium"}).encode("utf-8")
    requete = urllib.request.Request(
        f"{URL_PIPER}/synthesize", data=corps, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(requete, timeout=120) as reponse:
        brut = reponse.read()
    # WAV en flux : en-tête de 44 octets, puis PCM 16 kHz mono s16le.
    utile = brut[44 : 44 + (len(brut) - 44) // 2 * 2]
    return np.frombuffer(utile, dtype="<i2").astype(np.float32) / 32768.0, 16000


def charger_qwen(nom: str):
    import torch
    from qwen_tts import Qwen3TTSModel

    options = {"device_map": "cuda:0", "dtype": torch.bfloat16}
    try:
        return Qwen3TTSModel.from_pretrained(nom, attn_implementation="sdpa", **options)
    except (TypeError, ValueError):
        return Qwen3TTSModel.from_pretrained(nom, **options)


def api_streaming(modele) -> dict:
    """La doc ne montre aucun streaming en Python : on relève ce que le paquet expose."""
    signatures = {}
    for nom in ("generate_custom_voice", "generate_voice_design"):
        if hasattr(modele, nom):
            signatures[nom] = str(inspect.signature(getattr(modele, nom)))
    return {
        "methodes_contenant_stream": [m for m in dir(modele) if "stream" in m.lower()],
        "signatures": signatures,
    }


def generer(nom: str, modele, texte: str) -> tuple[np.ndarray, int]:
    if nom == "piper_tom":
        return piper_tom(texte)
    if nom == "qwen_preset_uncle_fu":
        wavs, sr = modele.generate_custom_voice(
            text=texte, language="French", speaker="Uncle_Fu", instruct=CONSIGNE_PRESET
        )
    else:
        wavs, sr = modele.generate_voice_design(
            text=texte, language="French", instruct=VOIX_DECRITE
        )
    return np.asarray(wavs[0], dtype=np.float32), int(sr)


def essayer(candidat: dict, extraits: list, mesures: dict) -> None:
    nom = candidat["nom"]
    rapport: dict = {"phrases": []}
    mesures["candidats"][nom] = rapport
    modele = None
    try:
        if candidat["modele"]:
            import torch

            torch.cuda.reset_peak_memory_stats()
            debut = time.monotonic()
            modele = charger_qwen(candidat["modele"])
            rapport["chargement_s"] = round(time.monotonic() - debut, 1)
            rapport["streaming"] = api_streaming(modele)
        for rang, texte in enumerate(PHRASES, start=1):
            debut = time.monotonic()
            audio, sr = generer(nom, modele, texte)
            calcul = time.monotonic() - debut
            duree = len(audio) / sr if sr else 0.0
            rapport["phrases"].append(
                {
                    "phrase": rang,
                    "calcul_s": round(calcul, 2),
                    "audio_s": round(duree, 2),
                    "facteur_temps_reel": round(calcul / duree, 2) if duree else None,
                    "frequence_native_hz": sr,
                }
            )
            extraits.append((nom, rang, ramener_a_atlas(audio, sr)))
            print(f"{nom} phrase {rang} : {calcul:.1f} s de calcul, {duree:.1f} s d'audio")
        if candidat["modele"]:
            import torch

            rapport["vram_pic_go"] = round(torch.cuda.max_memory_allocated() / 1e9, 2)
    except Exception as e:  # un candidat en échec ne doit pas empêcher les autres
        rapport["erreur"] = f"{type(e).__name__}: {e}"
        rapport["trace"] = traceback.format_exc()[-2000:]
        print(f"ÉCHEC {nom} : {rapport['erreur']}")
    finally:
        if modele is not None:
            import torch

            del modele
            torch.cuda.empty_cache()


def ecrire(nom: str, contenu: str) -> None:
    (SORTIE / nom).write_text(contenu, encoding="utf-8")


def principal() -> None:
    AVEUGLE.mkdir(parents=True, exist_ok=True)
    extraits: list = []
    mesures: dict = {"candidats": {}}
    try:
        import torch

        mesures["torch"] = torch.__version__
        mesures["gpu"] = torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
    except Exception as e:
        mesures["gpu"] = f"indisponible : {e}"

    for candidat in CANDIDATS:
        essayer(candidat, extraits, mesures)

    random.shuffle(extraits)
    cles = {}
    lignes = ["N° | masculine | fluide | chiffres | nom propre | sonne français | note /5"]
    for numero, (nom, rang, audio) in enumerate(extraits, start=1):
        fichier = f"{numero:02d}.wav"
        sf.write(AVEUGLE / fichier, audio, FREQUENCE_ATLAS, subtype="PCM_16")
        cles[fichier] = {"candidat": nom, "phrase": rang}
        lignes.append(f"{numero:02d} |" + "   |" * 6)
    ecrire("cles.json", json.dumps(cles, indent=2, ensure_ascii=False))
    ecrire("mesures.json", json.dumps(mesures, indent=2, ensure_ascii=False))
    ecrire("grille.txt", "\n".join(lignes) + "\n")
    print(f"\n{len(extraits)} extraits dans {AVEUGLE}. N'ouvre pas cles.json avant d'avoir noté.")


if __name__ == "__main__":
    principal()

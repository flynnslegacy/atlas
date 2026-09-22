"""Banc de mesure de la chaîne audio.

Les quatre chiffres qui décident des réglages : détection du wake word,
faux positifs, erreurs de transcription, latence. Tout le reste est du ressenti.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
import unicodedata
import wave
from pathlib import Path

import httpx

from helios_audio.vad import DetecteurVoix, Endpointeur
from helios_core.transcription import ClientTranscription

RACINE = Path(__file__).parent
POSITIFS = RACINE / "enregistrements" / "positifs"  # « Hey Helios » prononcé
NEGATIFS = RACINE / "enregistrements" / "negatifs"  # parole normale, sans le mot
PHRASES = RACINE / "enregistrements" / "phrases"  # énoncés à transcrire

_PONCTUATION = re.compile(r"[^\w\s]", re.UNICODE)


def normaliser(texte: str) -> str:
    texte = unicodedata.normalize("NFC", texte.lower())
    return " ".join(_PONCTUATION.sub(" ", texte).split())


def taux_erreur_mots(attendu: str, obtenu: str) -> float:
    a, o = normaliser(attendu).split(), normaliser(obtenu).split()
    if not a:
        return 0.0 if not o else 1.0
    # distance de Levenshtein sur les mots
    precedente = list(range(len(o) + 1))
    for i, mot_a in enumerate(a, 1):
        courante = [i]
        for j, mot_o in enumerate(o, 1):
            courante.append(
                min(
                    precedente[j] + 1,
                    courante[j - 1] + 1,
                    precedente[j - 1] + (mot_a != mot_o),
                )
            )
        precedente = courante
    return precedente[-1] / len(a)


def _blocs(chemin: Path) -> list[bytes]:
    with wave.open(str(chemin), "rb") as f:
        assert f.getframerate() == 16000 and f.getnchannels() == 1
        brut = f.readframes(f.getnframes())
    return [brut[i : i + 640] for i in range(0, len(brut) - 639, 640)]


def mesurer_reveil(seuil: float) -> dict:
    from helios_audio.reveilleur import PredicteurOpenWakeWord, ReveilleurMotCle

    detectes = 0
    fichiers = sorted(POSITIFS.glob("*.wav"))
    for chemin in fichiers:
        r = ReveilleurMotCle(PredicteurOpenWakeWord(), seuil=seuil)
        if any(r.examiner(b) for b in _blocs(chemin)):
            detectes += 1

    faux, minutes = 0, 0.0
    for chemin in sorted(NEGATIFS.glob("*.wav")):
        r = ReveilleurMotCle(PredicteurOpenWakeWord(), seuil=seuil)
        blocs = _blocs(chemin)
        minutes += len(blocs) * 0.02 / 60
        faux += sum(1 for b in blocs if r.examiner(b))

    return {
        "seuil": seuil,
        "detection": detectes / len(fichiers) if fichiers else 0.0,
        "faux_par_heure": faux / minutes * 60 if minutes else 0.0,
    }


def mesurer_endpointage(silence_ms: int) -> dict:
    detecteur = DetecteurVoix()
    fichiers = sorted(PHRASES.glob("*.wav"))
    retards = []
    for chemin in fichiers:
        e = Endpointeur(silence_ms=silence_ms)
        for n, bloc in enumerate(_blocs(chemin)):
            if e.ajouter(detecteur.parle(bloc)) == "fin":
                retards.append(n * 20)
                break
    return {
        "silence_ms": silence_ms,
        "retard_median_ms": sorted(retards)[len(retards) // 2] if retards else 0,
        "fichiers_mesures": len(retards),
        "fichiers_total": len(fichiers),
    }


async def mesurer_transcription() -> dict:
    attendus = json.loads((RACINE / "attendus.json").read_text(encoding="utf-8"))
    taux, latences = [], []
    async with httpx.AsyncClient() as http:
        client = ClientTranscription(
            os.environ.get("HELIOS_STT_URL", "http://unraid.local:9010"), http
        )
        for nom, attendu in attendus.items():
            pcm = b"".join(_blocs(PHRASES / nom))
            debut = time.monotonic()
            obtenu = await client.transcrire(pcm)
            latences.append((time.monotonic() - debut) * 1000)
            taux.append(taux_erreur_mots(attendu, obtenu))
    return {
        "wer_moyen": sum(taux) / len(taux) if taux else 0.0,
        "latence_mediane_ms": sorted(latences)[len(latences) // 2] if latences else 0,
        "fichiers_mesures": len(taux),
        "fichiers_total": len(attendus),
    }


async def principal() -> None:
    resultats = {
        "reveil": [mesurer_reveil(s) for s in (0.3, 0.5, 0.7)],
        "endpointage": [mesurer_endpointage(ms) for ms in (300, 400, 600)],
        "transcription": await mesurer_transcription(),
    }
    print(json.dumps(resultats, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(principal())

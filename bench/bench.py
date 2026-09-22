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

from atlas_audio.vad import CHEMIN_MODELE, DetecteurVoix, Endpointeur
from atlas_core.protocole import DUREE_BLOC_MS
from atlas_core.transcription import ClientTranscription

RACINE = Path(__file__).parent
POSITIFS = RACINE / "enregistrements" / "positifs"  # « Hey Atlas » prononcé
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
    from atlas_audio.reveilleur import PredicteurOpenWakeWord, ReveilleurMotCle

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


def retard_fin_enonce(parole: list[bool], silence_ms: int) -> tuple[int | None, int]:
    """Rend (retard en ms, nombre de fins) pour une suite de verdicts de voix par bloc.

    Le retard sépare le dernier bloc de parole de la PREMIÈRE fin décidée : c'est
    l'attente réelle entre le moment où l'on se tait et celui où Atlas le sait.
    Il vaut None si aucune fin n'est décidée. Chaque enregistrement ne contient
    qu'une phrase : plus d'une fin veut dire que le réglage a coupé la parole.
    """
    endpointeur = Endpointeur(silence_ms=silence_ms)
    retard: int | None = None
    derniere_parole: int | None = None
    fins = 0
    for n, parle in enumerate(parole):
        if parle:
            derniere_parole = n
        if endpointeur.ajouter(parle) == "fin":
            fins += 1
            if retard is None and derniere_parole is not None:
                retard = (n - derniere_parole) * DUREE_BLOC_MS
    return retard, fins


def mesurer_endpointage(silence_ms: int) -> dict:
    fichiers = sorted(PHRASES.glob("*.wav"))
    retards = []
    coupures = 0
    for chemin in fichiers:
        # Un détecteur neuf par fichier : l'état interne de Silero ne doit pas
        # fuir d'un enregistrement à l'autre.
        detecteur = DetecteurVoix()
        parole = [detecteur.parle(bloc) for bloc in _blocs(chemin)]
        retard, fins = retard_fin_enonce(parole, silence_ms)
        if retard is not None:
            retards.append(retard)
        if fins > 1:
            coupures += 1
    return {
        "silence_ms": silence_ms,
        "retard_median_ms": sorted(retards)[len(retards) // 2] if retards else 0,
        "fichiers_mesures": len(retards),
        "fichiers_total": len(fichiers),
        "coupures_prematurees": coupures,
    }


def verifier_modele_vad(chemin: str = CHEMIN_MODELE) -> None:
    """Arrête le banc avec une consigne claire si le modèle Silero manque."""
    if not Path(chemin).is_file():
        raise SystemExit(
            f"Modèle Silero introuvable : {chemin}\n"
            "Le banc en a besoin pour l'endpointage. Télécharge-le depuis la racine du dépôt :\n"
            "  mkdir -p models && curl -L -o models/silero_vad.onnx "
            "https://raw.githubusercontent.com/snakers4/silero-vad/master/src/silero_vad/data/silero_vad.onnx"
        )


async def mesurer_transcription() -> dict:
    attendus = json.loads((RACINE / "attendus.json").read_text(encoding="utf-8"))
    taux, latences = [], []
    async with httpx.AsyncClient() as http:
        client = ClientTranscription(
            os.environ.get("ATLAS_STT_URL", "http://unraid.local:9010"), http
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
    verifier_modele_vad()
    resultats = {
        "reveil": [mesurer_reveil(s) for s in (0.3, 0.5, 0.7)],
        "endpointage": [mesurer_endpointage(ms) for ms in (300, 400, 600)],
        "transcription": await mesurer_transcription(),
    }
    print(json.dumps(resultats, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(principal())

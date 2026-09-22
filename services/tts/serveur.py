"""Service de synthèse vocale, moteur interchangeable.

Rend toujours du PCM 16 kHz mono s16le, quel que soit le moteur : la conversion
de fréquence appartient au service, jamais au reste du pipeline.
"""

from __future__ import annotations

import json
import logging
import os
import struct
import subprocess
import threading
from collections.abc import Callable, Iterator, Mapping
from contextlib import asynccontextmanager
from typing import Any, Protocol

import numpy as np
import soundfile as sf
import soxr
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

# Sous « uvicorn.error » : uvicorn ne configure que ses propres journaux, et un message
# hors de cette branche serait perdu. C'est le seul moyen pour le propriétaire de voir
# que le modèle s'est chargé ou qu'une génération a été coupée au plafond.
_journal = logging.getLogger("uvicorn.error").getChild("atlas_tts")

FREQUENCE_SORTIE = 16000
TAILLE_MORCEAU = 640  # 20 ms


def nom_moteur_choisi(environ: Mapping[str, str] = os.environ) -> str:
    """Le moteur demandé par ATLAS_TTS_MOTEUR ; qwen3 par défaut (spec, décision D6)."""
    return environ.get("ATLAS_TTS_MOTEUR") or "qwen3"


MOTEUR = nom_moteur_choisi()


class MoteurTTS(Protocol):
    nom: str
    voix_defaut: str  # voix utilisée quand ni la requête ni ATLAS_TTS_VOIX n'en donnent

    def synthetiser(self, texte: str, voix: str) -> Iterator[bytes]:
        """Rend des morceaux de PCM 16 kHz mono s16le.

        Appelée par la route avant la réponse HTTP : une exception levée à l'appel
        devient un 503. Un moteur peut donc travailler dès l'appel (Qwen3) ou
        paresseusement, à la lecture des morceaux (Piper).
        """
        ...

    def verifier(self, voix: str) -> None:
        """Lève FileNotFoundError si la voix demandée n'est pas installée."""
        ...


def voix_par_defaut(moteur: MoteurTTS, environ: Mapping[str, str] = os.environ) -> str:
    """ATLAS_TTS_VOIX l'emporte ; vide ou absente, chaque moteur prend sa propre voix."""
    return environ.get("ATLAS_TTS_VOIX") or moteur.voix_defaut


def aligner_sur_echantillons(donnees: bytes) -> tuple[bytes, bytes]:
    """Sépare les octets alignés sur des échantillons de 16 bits du dernier octet orphelin."""
    if len(donnees) % 2:
        return donnees[:-1], donnees[-1:]
    return donnees, b""


def en_blocs(tampon: bytes) -> tuple[list[bytes], bytes]:
    """Découpe en blocs de 20 ms et rend ce qui reste, pour la lecture suivante."""
    blocs = []
    while len(tampon) >= TAILLE_MORCEAU:
        blocs.append(tampon[:TAILLE_MORCEAU])
        tampon = tampon[TAILLE_MORCEAU:]
    return blocs, tampon


class MoteurPiper:
    nom = "piper"
    voix_defaut = "fr_FR-siwis-medium"

    def __init__(self, dossier_modeles: str = "/modeles") -> None:
        self._dossier = dossier_modeles
        self._dernier_processus: subprocess.Popen | None = None

    def _commande(self, modele: str) -> list[str]:
        return ["piper", "--model", modele, "--output_raw"]

    def _modele(self, voix: str) -> str:
        return f"{self._dossier}/{voix or voix_par_defaut(self)}.onnx"

    def _configuration(self, modele: str) -> str:
        return f"{modele}.json"

    def _frequence(self, modele: str) -> int:
        """Fréquence native de la voix, lue dans sa configuration.

        Chaque voix Piper a la sienne (Siwis 22 050 Hz, Tom 44 100 Hz, les voix
        « low » 16 000 Hz). La supposer fixe ralentit ou accélère la parole.
        """
        with open(self._configuration(modele), encoding="utf-8") as fichier:
            return int(json.load(fichier)["audio"]["sample_rate"])

    def verifier(self, voix: str) -> None:
        modele = self._modele(voix)
        if not os.path.isfile(modele):
            raise FileNotFoundError(f"voix Piper introuvable : le fichier {modele} n'existe pas")
        configuration = self._configuration(modele)
        if not os.path.isfile(configuration):
            raise FileNotFoundError(
                f"configuration de voix Piper introuvable : le fichier {configuration} n'existe pas"
            )
        try:
            self._frequence(modele)
        except (KeyError, TypeError, ValueError) as e:
            raise ValueError(
                f"configuration de voix Piper illisible : {configuration} ({e})"
            ) from e

    def synthetiser(self, texte: str, voix: str) -> Iterator[bytes]:
        modele = self._modele(voix)
        frequence = self._frequence(modele)  # lue avant de lancer piper
        proc = subprocess.Popen(
            self._commande(modele),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
        )
        self._dernier_processus = proc
        assert proc.stdin and proc.stdout
        proc.stdin.write(texte.encode("utf-8"))
        proc.stdin.close()

        try:
            # Rééchantillonneur à état : garde son filtre d'une lecture à l'autre pour
            # éviter les discontinuités aux frontières de bloc (soxr.resample le
            # réinitialiserait à chaque appel).
            rechantillonneur = soxr.ResampleStream(frequence, FREQUENCE_SORTIE, 1, dtype="float32")

            orphelin = b""  # octet isolé d'un échantillon coupé par une lecture
            tampon = b""  # PCM rééchantillonné pas encore découpé en blocs
            while True:
                brut = proc.stdout.read(4096)
                if not brut:
                    break
                donnees, orphelin = aligner_sur_echantillons(orphelin + brut)
                if not donnees:
                    continue
                echantillons = np.frombuffer(donnees, dtype="<i2").astype(np.float32)
                ramene = rechantillonneur.resample_chunk(echantillons)
                tampon += np.clip(ramene, -32768, 32767).astype("<i2").tobytes()
                blocs, tampon = en_blocs(tampon)
                yield from blocs
            proc.wait()

            dernier = rechantillonneur.resample_chunk(np.empty(0, dtype=np.float32), last=True)
            tampon += np.clip(dernier, -32768, 32767).astype("<i2").tobytes()
            blocs, tampon = en_blocs(tampon)
            yield from blocs
            if tampon:
                yield tampon + b"\x00" * (TAILLE_MORCEAU - len(tampon))
        finally:
            # Si le générateur est abandonné en cours de route (déconnexion HTTP,
            # GeneratorExit), le sous-processus piper ne doit pas rester orphelin :
            # Atlas coupe des phrases en plein milieu en fonctionnement normal.
            if proc.stdout:
                proc.stdout.close()
            if proc.poll() is None:
                proc.terminate()
            proc.wait()


PLAFOND_MIN_S = 8.0
SECONDES_PAR_CARACTERE = 0.06  # débit de parole mesuré par le spike S1
# 4 et non 2,5 : une phrase chargée en chiffres se dit bien plus lentement que la
# moyenne (0,10 s par caractère pour la phrase 1 du spike).
MARGE_PLAFOND = 4.0
# Borne haute prudente, en attendant de mesurer les jetons générés par seconde d'audio.
JETONS_PAR_SECONDE_MAX = 50


def plafond_duree(texte: str) -> float:
    """Durée au-delà de laquelle une génération est tenue pour emballée.

    Très large (4 fois la durée attendue, 8 s au moins) : elle ne doit jamais toucher
    une phrase normale, seulement arrêter une génération qui boucle.
    """
    return max(PLAFOND_MIN_S, len(texte) * SECONDES_PAR_CARACTERE * MARGE_PLAFOND)


def charger_qwen3(nom_modele: str) -> Any:
    """Charge Qwen3-TTS sur le GPU.

    torch et qwen_tts ne sont importés qu'ici : le service reste importable, et ses
    tests exécutables, sur une machine sans GPU ni ces paquets.
    """
    import torch
    from qwen_tts import Qwen3TTSModel

    options = {"device_map": "cuda:0", "dtype": torch.bfloat16}
    try:
        # sdpa plutôt que flash-attn, dont la compilation prend trop de temps.
        return Qwen3TTSModel.from_pretrained(nom_modele, attn_implementation="sdpa", **options)
    except (TypeError, ValueError):
        return Qwen3TTSModel.from_pretrained(nom_modele, **options)


class MoteurQwen3:
    """Clone la voix d'Atlas avec Qwen3-TTS (verdict du spike S1).

    Une voix V est la paire indissociable V.wav + V.txt, le texte exact de l'audio.
    Qwen3 rend la phrase entière d'un coup : elle est ensuite découpée en blocs de 20 ms
    (exception à la spec §6.4, acceptée).
    """

    nom = "qwen3"
    voix_defaut = "atlas_reference"

    def __init__(
        self,
        dossier_voix: str = "/voix",
        modele: str = "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
        charger: Callable[[str], Any] | None = None,
    ) -> None:
        # Construction bon marché : le modèle ne se charge qu'au premier besoin.
        self._dossier = dossier_voix
        self._nom_modele = modele
        self._charger = charger or charger_qwen3
        self._modele: Any = None
        self._empreintes: dict[str, Any] = {}
        # Un seul verrou, non réentrant : il protège le chargement et le cache des
        # empreintes, et sérialise la génération, car un modèle unique sur le GPU ne
        # doit jamais générer deux phrases à la fois.
        self._verrou = threading.Lock()

    def _fichiers(self, voix: str) -> tuple[str, str]:
        base = f"{self._dossier}/{voix}"
        return f"{base}.wav", f"{base}.txt"

    def verifier(self, voix: str) -> None:
        audio, texte = self._fichiers(voix or voix_par_defaut(self))
        if not os.path.isfile(audio):
            raise FileNotFoundError(
                f"audio de référence de la voix introuvable : le fichier {audio} n'existe pas"
            )
        if not os.path.isfile(texte):
            raise FileNotFoundError(
                f"texte de référence de la voix introuvable : le fichier {texte} n'existe pas"
            )

    def _preparer(self, voix: str) -> tuple[Any, Any]:
        """Rend le modèle et l'empreinte de la voix, calculés une seule fois.

        À n'appeler que sous self._verrou.
        """
        if self._modele is None:
            _journal.info("chargement du modèle %s", self._nom_modele)
            self._modele = self._charger(self._nom_modele)
        if voix not in self._empreintes:
            fichier_audio, fichier_texte = self._fichiers(voix)
            audio, frequence = sf.read(fichier_audio, dtype="float32")
            # Le texte doit être EXACTEMENT ce que dit l'audio : lu dans son fichier, sans
            # autre retouche que les blancs qui l'entourent. S'il en dit plus, le modèle
            # croit la référence inachevée et commence chaque phrase par les mots
            # manquants (bug du spike S1).
            with open(fichier_texte, encoding="utf-8") as fichier:
                texte = fichier.read().strip()
            self._empreintes[voix] = self._modele.create_voice_clone_prompt(
                ref_audio=(audio, frequence), ref_text=texte, x_vector_only_mode=False
            )
        return self._modele, self._empreintes[voix]

    def prechauffer(self, voix: str) -> None:
        """Charge le modèle et l'empreinte, pour épargner 5 à 40 s à la première requête."""
        voix = voix or voix_par_defaut(self)
        with self._verrou:
            self._preparer(voix)

    def synthetiser(self, texte: str, voix: str) -> Iterator[bytes]:
        """Génère toute la phrase dès l'appel, puis rend ses blocs de 20 ms.

        Qwen3 ne rend rien avant la fin de la génération : travailler avant la réponse
        HTTP ne retarde pas le premier son, et un échec (chargement, mémoire GPU,
        génération) devient un 503 au lieu d'un 200 muet. Le verrou est rendu avant
        que le premier bloc ne parte : un client qui se déconnecte ne peut pas le garder.
        """
        voix = voix or voix_par_defaut(self)
        plafond_s = plafond_duree(texte)
        with self._verrou:
            modele, empreinte = self._preparer(voix)
            wavs, frequence = modele.generate_voice_clone(
                text=texte,
                language="French",
                voice_clone_prompt=empreinte,
                max_new_tokens=int(plafond_s * JETONS_PAR_SECONDE_MAX),
            )

        audio = np.asarray(wavs[0], dtype=np.float32).reshape(-1)
        # Seule coupe permise : le plafond de durée. Jamais sur un silence, qui a amputé
        # de vraie parole 3 fois sur 11 pendant le spike S1.
        limite = int(plafond_s * frequence)
        if len(audio) > limite:
            _journal.warning(
                "génération Qwen3 coupée au plafond : %.1f s produites, %.1f s permises "
                "pour %d caractères",
                len(audio) / frequence,
                plafond_s,
                len(texte),
            )
            audio = audio[:limite]

        # L'audio est complet : un rééchantillonnage d'un seul tenant suffit.
        ramene = soxr.resample(audio, frequence, FREQUENCE_SORTIE)
        pcm = (np.clip(ramene, -1.0, 1.0) * 32767).astype("<i2").tobytes()
        blocs, reste = en_blocs(pcm)
        if reste:
            blocs.append(reste + b"\x00" * (TAILLE_MORCEAU - len(reste)))
        return iter(blocs)


_moteurs: dict[str, MoteurTTS] = {"piper": MoteurPiper(), "qwen3": MoteurQwen3()}


def obtenir_moteur() -> MoteurTTS:
    if MOTEUR not in _moteurs:
        raise HTTPException(status_code=500, detail=f"moteur inconnu : {MOTEUR}")
    return _moteurs[MOTEUR]


def entete_wav_streaming() -> bytes:
    """En-tête WAV pour un flux de longueur inconnue.

    Les tailles sont mises au maximum : c'est la convention pour un WAV streamé,
    et tous les lecteurs de flux l'acceptent.
    """
    return (
        b"RIFF"
        + struct.pack("<I", 0xFFFFFFFF)
        + b"WAVE"
        + b"fmt "
        + struct.pack("<IHHIIHH", 16, 1, 1, FREQUENCE_SORTIE, FREQUENCE_SORTIE * 2, 2, 16)
        + b"data"
        + struct.pack("<I", 0xFFFFFFFF)
    )


class DemandeSynthese(BaseModel):
    # Le plafond de durée, max_new_tokens et le temps passé sous le verrou grossissent
    # avec le texte : 1 000 caractères, environ une minute de parole, bien au-delà d'une
    # phrase envoyée par le Core. Le texte vide ou blanc reste refusé par la route (400).
    text: str = Field(max_length=1000)
    # Le nom de voix devient un chemin de fichier : ni « / », ni « . », ni « \ », pour
    # qu'il ne sorte jamais du dossier des voix. Vide : la voix par défaut du moteur.
    voice: str = Field("", max_length=64, pattern=r"^[A-Za-z0-9_-]*$")


def demarrer_prechauffage(moteur: MoteurTTS | None) -> threading.Thread | None:
    """Préchauffe le moteur dans un fil démon, si le moteur sait le faire.

    Le serveur démarre sans attendre. Un échec est journalisé, jamais fatal : la
    première requête retentera le chargement et rendra sa propre erreur.
    """
    prechauffer = getattr(moteur, "prechauffer", None)
    if moteur is None or prechauffer is None:
        return None
    voix = voix_par_defaut(moteur)

    def prechauffer_sans_planter() -> None:
        try:
            prechauffer(voix)
        except Exception:
            _journal.exception(
                "préchauffage du moteur %s en échec pour la voix %s : "
                "la première requête retentera le chargement",
                moteur.nom,
                voix,
            )
        else:
            _journal.info("moteur %s préchauffé pour la voix %s", moteur.nom, voix)

    fil = threading.Thread(target=prechauffer_sans_planter, name="prechauffage-tts", daemon=True)
    fil.start()
    return fil


@asynccontextmanager
async def _cycle_de_vie(app: FastAPI):
    demarrer_prechauffage(_moteurs.get(MOTEUR))
    yield


app = FastAPI(title="atlas-tts", lifespan=_cycle_de_vie)


@app.post("/synthesize")
def synthetiser(
    demande: DemandeSynthese,
    moteur: MoteurTTS = Depends(obtenir_moteur),  # noqa: B008
) -> StreamingResponse:
    if not demande.text.strip():
        raise HTTPException(status_code=400, detail="texte vide")
    voix = demande.voice or voix_par_defaut(moteur)
    # Vérifié AVANT le flux : une fois le 200 et l'en-tête WAV partis, le code de
    # statut ne peut plus changer, et une voix absente rendrait un Atlas muet.
    try:
        moteur.verifier(voix)
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    # Appelé AVANT le flux, pour la même raison : un moteur qui travaille dès l'appel
    # (Qwen3) peut encore échouer avec un vrai code d'erreur.
    try:
        blocs = moteur.synthetiser(demande.text, voix)
    except Exception as e:
        _journal.exception("synthèse impossible avec le moteur %s", moteur.nom)
        raise HTTPException(status_code=503, detail=f"moteur de voix indisponible : {e}") from e

    def flux() -> Iterator[bytes]:
        yield entete_wav_streaming()
        yield from blocs

    return StreamingResponse(flux(), media_type="audio/wav")


@app.get("/sante")
def sante() -> dict:
    return {"ok": True, "moteur": MOTEUR}

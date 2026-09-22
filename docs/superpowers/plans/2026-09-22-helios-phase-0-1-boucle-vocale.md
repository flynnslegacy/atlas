# Helios — Phases 0 et 1 : la boucle vocale

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Obtenir une boucle vocale française complète — « Hey Helios, quelle heure est-il » donne une réponse parlée, et David peut couper Helios en pleine phrase.

**Architecture:** Trois étages. Le M5 porte `helios-audio` (capture, annulation d'écho, wake word, VAD, lecture) ; le MacBook néo headless porte `helios-core` (hub WebSocket, machine à états, segmentation, cerveau) ; l'Unraid porte `helios-stt` et `helios-tts` en Docker sur GPU. En phase 1 le cerveau est un **bouchon** aux réponses figées : Claude n'arrive qu'en phase 2, pour que la chaîne audio soit validée seule.

**Tech Stack:** Python 3.12 + `uv` · FastAPI + uvicorn + websockets · pydantic v2 · faster-whisper (CUDA) · Qwen3-TTS ou Piper FR · openWakeWord · Silero VAD (ONNX) · sounddevice · un binaire Swift pour l'AEC macOS · pytest + pytest-asyncio · ruff · Docker.

**Spec:** `docs/superpowers/specs/2026-09-22-helios-design.md`

## Global Constraints

Ces contraintes valent pour **toutes** les tâches du plan. Chaque tâche les hérite implicitement.

- **Python 3.12 minimum.** Gestionnaire de paquets : `uv`. Jamais `pip install` direct.
- **Format audio unique dans tout le système : PCM 16 kHz, mono, signé 16 bits, petit-boutiste (`s16le`).** Un bloc = 20 ms = 320 échantillons = 640 octets. Toute conversion se fait aux frontières (carte son, modèle), jamais au milieu du pipeline.
- **Tout ce que l'utilisateur voit ou entend est en français** : messages vocaux, messages d'erreur remontés au client, libellés du front. Les noms de code, de variables et de fonctions restent en français eux aussi, conformément à la spec et au projet de référence (`@outil`, `niveau`).
- **Ports fixes :** `helios-core` 8080 · `helios-stt` 9010 · `helios-tts` 9011 · Ollama 11434 · Hermes (port de ton instance).
- **Les services GPU ne sont jamais exposés hors du LAN.** Seul `helios-core` passe par le reverse proxy.
- **Aucun secret dans le dépôt.** Les clés vivent en variables d'environnement ; `.env` est dans `.gitignore` ; `.env.example` documente les noms attendus, jamais les valeurs.
- **Aucun appel à la vraie API Claude dans les tests.** Le cerveau est derrière une interface, toujours mocké.
- **Helios ne saisit jamais d'identifiant ni de mot de passe, et n'exécute aucune action financière.** Ces interdits ne sont pas configurables et ne doivent apparaître dans aucun outil.
- **Objectifs de latence** (seuils du banc de mesure, tâche 15) : fin de phrase détectée ≤ 400 ms · transcription ≤ 600 ms · premier morceau audio TTS ≤ 300 ms · bout en bout avec le cerveau bouchon ≤ 1,2 s.
- **Commit après chaque tâche**, jamais au milieu. Message en français, à l'impératif.

---

## Structure des fichiers

Ce que chaque fichier porte, décidé avant les tâches. Un fichier = une responsabilité.

```
pyproject.toml               dépendances, extras core/audio/dev, config ruff et pytest
Makefile                     test, lint, bench, run-core, run-audio
.env.example                 noms des variables d'environnement attendues

src/helios_core/
  protocole.py               types de messages WebSocket (pydantic) + codec binaire
  etat.py                    machine à états : repos → écoute → réflexion → parole
  hub.py                     serveur FastAPI, route /ws/audio, gestion des connexions
  transcription.py           client HTTP vers helios-stt, assemblage des trames
  synthese.py                client HTTP vers helios-tts, streaming par morceaux
  phrases.py                 découpage d'un flux de texte français en phrases
  cerveau.py                 interface Cerveau + CerveauBouchon (phase 1)
  session.py                 orchestration d'un tour de parole, gestion du barge-in
  config.py                  chargement de la configuration depuis l'environnement

src/helios_audio/
  aec.py                     pilote du binaire Swift (pipes stdin/stdout)
  vad.py                     Silero VAD + machine d'endpointing
  reveil.py                  openWakeWord, chargement du modèle « Hey Helios »
  client.py                  daemon : boucle WebSocket, capture, lecture, barge-in
  raccourci.py               push-to-talk (phase 1 avant le wake word)

src/helios_aec/              paquet Swift
  Package.swift
  Sources/helios-aec/main.swift   capture + lecture avec Voice Processing d'Apple

services/stt/
  Dockerfile
  serveur.py                 FastAPI, route /transcribe, faster-whisper
services/tts/
  Dockerfile
  serveur.py                 FastAPI, route /synthesize, moteur configurable

tests/
  test_protocole.py  test_phrases.py  test_etat.py  test_session.py
  test_transcription.py  test_synthese.py  test_vad.py  test_aec_protocole.py

bench/
  enregistrements/           jeu de référence (hors dépôt, voir .gitignore)
  bench.py                   mesures : wake word, faux positifs, WER, latences
  attendus.json              transcriptions attendues du jeu de référence

docs/superpowers/spikes/     verdicts de la phase 0
```

---

# Phase 0 — Les trois spikes

Ces trois tâches ne produisent **pas** de code conservé : leur livrable est une réponse
écrite et une décision. Tout code écrit ici est jetable et doit être annoncé comme tel.
Elles bloquent la phase 1 parce qu'elles en changent des choix.

### Spike S1 : Qwen3-TTS tient-il en français sur le 4070 Ti ?

**Files:**
- Create: `docs/superpowers/spikes/2026-09-22-s1-tts-francais.md`
- Jetable : tout ce qui est écrit sous `/tmp/spike-tts/`

**Interfaces:**
- Consumes: rien.
- Produces: la décision du moteur TTS, consommée par la tâche 4. Valeurs possibles :
  `qwen3` ou `piper` ou `kokoro`. Le nom retenu devient la valeur par défaut de la
  variable d'environnement `HELIOS_TTS_MOTEUR`.

- [ ] **Étape 1 : Réunir les phrases de test**

Cinq phrases françaises couvrant les pièges réels de l'usage d'Helios :

```
1. Bonjour David, il est quatorze heures trente-deux.
2. Le workflow « veille concurrence » a échoué à trois heures du matin : erreur d'authentification sur l'API.
3. J'ai noté ça dans projets/helios.md — tu veux que je te le relise ?
4. Attention : cette action va envoyer un mail à Paul Durand. Je confirme ?
5. D'accord. Alors reprenons : tu disais que l'offre devait tenir en une page.
```

Elles contiennent des chiffres à dire en toutes lettres, des guillemets, un chemin de
fichier, un nom propre et une question — c'est-à-dire tout ce qui casse un TTS français.

- [ ] **Étape 2 : Synthétiser avec Qwen3-TTS sur l'Unraid et mesurer**

Sur l'Unraid, mesurer pour chaque phrase, avec ComfyUI **arrêté** puis **en cours de
génération**, trois grandeurs : la VRAM occupée (`nvidia-smi --query-gpu=memory.used
--format=csv -l 1`), le délai jusqu'au premier morceau audio, et le délai total.

- [ ] **Étape 3 : Synthétiser les mêmes phrases avec Piper FR comme point de comparaison**

Piper est le repli. Sans point de comparaison, « la voix de Qwen3 est correcte » ne veut
rien dire.

- [ ] **Étape 4 : Écouter en aveugle et trancher**

Écouter les dix fichiers dans un ordre aléatoire, sans savoir lequel est lequel, et noter
chacun sur trois critères : les chiffres sont-ils dits correctement, le nom propre est-il
prononcé correctement, la phrase sonne-t-elle française.

- [ ] **Étape 5 : Écrire le verdict**

Le document doit répondre à quatre questions, sans langue de bois : quel moteur est retenu ;
quelle est la latence du premier morceau ; combien de VRAM il consomme et s'il cohabite
avec ComfyUI ; et si le moteur retenu **sait streamer par morceaux** — c'est une exigence
de la spec, pas un confort, et un moteur qui ne rend que le fichier complet est disqualifié
quelle que soit sa qualité de voix.

- [ ] **Étape 6 : Commit**

```bash
git add docs/superpowers/spikes/2026-09-22-s1-tts-francais.md
git commit -m "spike S1 : verdict sur le moteur TTS français"
```

---

### Spike S2 : l'AEC d'Apple rend-il le barge-in utilisable sur enceintes ?

**Files:**
- Create: `docs/superpowers/spikes/2026-09-22-s2-aec-macos.md`
- Jetable : `/tmp/spike-aec/` (projet Swift minimal)

**Interfaces:**
- Consumes: rien.
- Produces: la décision `aec_systeme` (on écrit le binaire Swift, tâche 10) ou `casque`
  (la tâche 10 se réduit à une capture `sounddevice` simple). Produit aussi la valeur
  mesurée du **seuil de barge-in en dB** consommée par la tâche 13.

- [ ] **Étape 1 : Écrire un binaire Swift minimal**

Un exécutable en ligne de commande qui active le Voice Processing d'Apple, joue un fichier
WAV sur la sortie par défaut et écrit le signal capturé sur la sortie standard :

```swift
import AVFoundation

let engine = AVAudioEngine()
try engine.inputNode.setVoiceProcessingEnabled(true)
try engine.outputNode.setVoiceProcessingEnabled(true)

let player = AVAudioPlayerNode()
engine.attach(player)
engine.connect(player, to: engine.mainMixerNode, format: nil)

let entree = engine.inputNode
let format = entree.outputFormat(forBus: 0)
entree.installTap(onBus: 0, bufferSize: 320, format: format) { buffer, _ in
    guard let canal = buffer.floatChannelData?[0] else { return }
    var pcm = [Int16](repeating: 0, count: Int(buffer.frameLength))
    for i in 0..<Int(buffer.frameLength) {
        pcm[i] = Int16(max(-1.0, min(1.0, canal[i])) * 32767.0)
    }
    pcm.withUnsafeBufferPointer { FileHandle.standardOutput.write(Data(buffer: $0)) }
}

try engine.start()
// lecture du WAV passé en argument, puis RunLoop.main.run()
```

- [ ] **Étape 2 : Mesurer l'atténuation d'écho**

Jouer une phrase TTS sur les enceintes du M5, dans la pièce de travail réelle, sans parler.
Mesurer l'énergie RMS du signal capturé avec Voice Processing **activé** puis **désactivé**.
Le rapport des deux est l'atténuation, en dB.

```bash
# atténuation = 20 * log10(rms_sans_aec / rms_avec_aec)
```

- [ ] **Étape 3 : Mesurer ce qui compte vraiment — les faux barge-in**

L'atténuation est un chiffre intermédiaire ; le vrai critère est opérationnel. Faire jouer
cinq minutes de parole d'Helios, sans parler du tout, en faisant tourner le VAD sur le
signal capturé. **Compter les déclenchements.** Le seuil d'acceptation est zéro faux
barge-in sur cinq minutes.

- [ ] **Étape 4 : Vérifier le vrai barge-in**

Rejouer la même chose, mais parler par-dessus à dix reprises, à volume de conversation
normale, à trois mètres du micro. Compter les interruptions correctement détectées. Le
seuil est dix sur dix.

- [ ] **Étape 5 : Écrire le verdict**

Trois réponses : atténuation obtenue en dB ; nombre de faux barge-in sur cinq minutes ;
nombre de vraies interruptions détectées sur dix. Puis la décision — `aec_systeme` si les
seuils sont tenus, `casque` sinon — et le **seuil d'énergie en dB** qu'on retiendra pour le
VAD pendant la lecture.

- [ ] **Étape 6 : Commit**

```bash
git add docs/superpowers/spikes/2026-09-22-s2-aec-macos.md
git commit -m "spike S2 : verdict sur l'annulation d'écho macOS"
```

---

### Spike S3 : un skill Hermes peut-il appeler un endpoint HTTP externe ?

**Files:**
- Create: `docs/superpowers/spikes/2026-09-22-s3-hermes-http.md`
- Jetable : le skill de test dans Hermes, à supprimer après le spike.

**Interfaces:**
- Consumes: rien.
- Produces: la décision `hermes` ou `pwa` pour l'accès distant. N'affecte aucune tâche de
  la phase 1 — ce spike est fait maintenant parce qu'il est court et qu'il conditionne la
  phase 4, pas parce qu'il bloque la boucle vocale.

- [ ] **Étape 1 : Monter un endpoint d'écho local**

Trois lignes qui renvoient ce qu'on leur envoie, pour ne tester que le transport :

```python
from fastapi import FastAPI
app = FastAPI()

@app.post("/echo")
async def echo(corps: dict) -> dict:
    return {"reponse": f"Reçu : {corps.get('texte', '')}"}
```

L'exposer temporairement via le reverse proxy Unraid, sous un chemin non deviné.

- [ ] **Étape 2 : Créer un skill Hermes qui l'appelle**

Suivre la documentation de `agentskills.io` telle qu'Hermes la supporte. Le skill prend le
texte du message entrant, le POSTe sur l'endpoint, et rend la réponse.

- [ ] **Étape 3 : Tester depuis Telegram, en texte puis en vocal**

Le test vocal est le plus important : la spec compte sur la transcription vocale intégrée
d'Hermes. Envoyer un message vocal en français et vérifier que le texte transcrit arrive
bien dans l'appel HTTP.

- [ ] **Étape 4 : Écrire le verdict et retirer le skill de test**

Répondre à trois questions : le skill peut-il appeler un HTTP externe ; la transcription
vocale française est-elle exploitable ; quelle latence bout en bout. Puis **supprimer le
skill de test et fermer l'exposition de l'endpoint d'écho** — c'est une route ouverte sur
Internet, elle ne survit pas au spike.

- [ ] **Étape 5 : Commit**

```bash
git add docs/superpowers/spikes/2026-09-22-s3-hermes-http.md
git commit -m "spike S3 : verdict sur Hermes comme porte d'entrée distante"
```

---

# Phase 1 — La boucle vocale

**Note sur les noms de l'API HTTP.** Les routes `/transcribe` et `/synthesize` gardent les
noms de champs de la spec (`text`, `language`, `duration_ms`, `voice`) : ce sont des clés de
protocole, pas du code métier, et elles doivent rester identiques à la spec pour que le
repli TTS soit un simple changement de conteneur. Tout le reste du code est en français.

### Tâche 1 : Squelette du dépôt et outillage

**Files:**
- Create: `pyproject.toml`, `Makefile`, `.env.example`
- Create: `src/helios_core/__init__.py`, `src/helios_audio/__init__.py`
- Test: `tests/test_fumee.py`

**Interfaces:**
- Consumes: rien.
- Produces: `make test`, `make lint`, `make format`. Toutes les tâches suivantes lancent
  leurs tests avec `uv run pytest`.

- [ ] **Étape 1 : Écrire le test de fumée**

```python
# tests/test_fumee.py
def test_le_paquet_core_est_importable():
    import helios_core
    assert helios_core.__version__ == "0.1.0"
```

- [ ] **Étape 2 : Lancer le test pour vérifier qu'il échoue**

Run: `uv run pytest tests/test_fumee.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'helios_core'`

- [ ] **Étape 3 : Écrire `pyproject.toml`**

```toml
[project]
name = "helios"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["pydantic>=2.9", "httpx>=0.27"]

[project.optional-dependencies]
core  = ["fastapi>=0.115", "uvicorn[standard]>=0.32", "websockets>=13"]
audio = ["sounddevice>=0.5", "numpy>=2.1", "onnxruntime>=1.20", "openwakeword>=0.6"]
dev   = ["pytest>=8.3", "pytest-asyncio>=0.24", "ruff>=0.7"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/helios_core", "src/helios_audio"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
```

- [ ] **Étape 4 : Créer les paquets**

```python
# src/helios_core/__init__.py
__version__ = "0.1.0"
```

```python
# src/helios_audio/__init__.py
__version__ = "0.1.0"
```

- [ ] **Étape 5 : Écrire le Makefile**

```make
.PHONY: install test lint format bench run-core run-audio

install:
	uv sync --extra core --extra audio --extra dev

test:
	uv run pytest -v

lint:
	uv run ruff check . && uv run ruff format --check .

format:
	uv run ruff format .

bench:
	uv run python bench/bench.py

run-core:
	uv run uvicorn helios_core.hub:app --host 0.0.0.0 --port 8080

run-audio:
	uv run python -m helios_audio.client
```

- [ ] **Étape 6 : Écrire `.env.example`**

```bash
# Adresses des services — jamais de secret dans ce fichier, seulement des noms
HELIOS_CORE_URL=ws://neo.local:8080/ws/audio
HELIOS_STT_URL=http://unraid.local:9010
HELIOS_TTS_URL=http://unraid.local:9011

# Moteur TTS : valeur décidée par le spike S1 (qwen3 | piper | kokoro)
HELIOS_TTS_MOTEUR=piper
HELIOS_TTS_VOIX=fr_FR-siwis-medium

# Modèle de transcription
HELIOS_STT_MODELE=large-v3
HELIOS_STT_DECHARGEMENT_S=300
```

- [ ] **Étape 7 : Installer et lancer les tests**

Run: `make install && make test`
Expected: PASS, 1 test.

- [ ] **Étape 8 : Commit**

```bash
git add pyproject.toml Makefile .env.example src/ tests/
git commit -m "Ajoute le squelette du dépôt et l'outillage"
```

---

### Tâche 2 : Protocole de messages et codec binaire

**Files:**
- Create: `src/helios_core/protocole.py`
- Test: `tests/test_protocole.py`

**Interfaces:**
- Consumes: rien.
- Produces:
  - Modèles pydantic : `Bonjour`, `Reveil`, `FinEnonce`, `Interruption`,
    `ReponseConfirmation` (client vers core) ; `Etat`, `Transcription`, `Dire`,
    `StopAudio`, `Confirmation`, `Erreur` (core vers client).
  - `MessageClient` et `MessageCore` : unions discriminées sur le champ `type`.
  - `decoder_message(brut: str) -> MessageClient`
  - `encoder_audio_entrant(pcm: bytes) -> bytes`
  - `decoder_audio_entrant(trame: bytes) -> bytes`
  - `encoder_audio_sortant(id_enonce: int, pcm: bytes) -> bytes`
  - `decoder_audio_sortant(trame: bytes) -> tuple[int, bytes]`
  - Constantes : `TAILLE_BLOC_OCTETS = 640`, `FREQUENCE_HZ = 16000`

- [ ] **Étape 1 : Écrire les tests qui échouent**

```python
# tests/test_protocole.py
import pytest
from helios_core.protocole import (
    TAILLE_BLOC_OCTETS, Etat, decoder_message,
    encoder_audio_entrant, decoder_audio_entrant,
    encoder_audio_sortant, decoder_audio_sortant,
)

def test_decoder_un_message_bonjour():
    msg = decoder_message('{"type":"bonjour","client":"m5","frequence":16000,'
                          '"capacites":["aec","vad"]}')
    assert msg.client == "m5"
    assert "aec" in msg.capacites

def test_un_type_inconnu_est_refuse():
    with pytest.raises(ValueError):
        decoder_message('{"type":"nimporte_quoi"}')

def test_un_etat_invalide_est_refuse():
    with pytest.raises(ValueError):
        Etat(valeur="en_train_de_cuire")

def test_aller_retour_audio_entrant():
    pcm = b"\x01\x02" * 320
    assert decoder_audio_entrant(encoder_audio_entrant(pcm)) == pcm

def test_aller_retour_audio_sortant_preserve_l_identifiant():
    pcm = b"\x03\x04" * 320
    id_lu, pcm_lu = decoder_audio_sortant(encoder_audio_sortant(4242, pcm))
    assert id_lu == 4242
    assert pcm_lu == pcm

def test_un_bloc_de_mauvaise_taille_est_refuse():
    with pytest.raises(ValueError):
        encoder_audio_entrant(b"\x00" * 639)

def test_une_trame_sortante_lue_comme_entrante_est_refusee():
    with pytest.raises(ValueError):
        decoder_audio_entrant(encoder_audio_sortant(1, b"\x00" * TAILLE_BLOC_OCTETS))
```

Le dernier test est le plus important : il garantit qu'une trame sortante ne peut pas être
confondue avec une trame entrante. Sans lui, un bug de routage produit du bruit blanc dans
les oreilles de David au lieu d'une erreur.

- [ ] **Étape 2 : Lancer les tests pour vérifier qu'ils échouent**

Run: `uv run pytest tests/test_protocole.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'helios_core.protocole'`

- [ ] **Étape 3 : Écrire le protocole**

```python
# src/helios_core/protocole.py
"""Messages échangés entre le client audio et le Core.

Deux canaux sur la même WebSocket : les messages de contrôle en JSON texte,
l'audio en trames binaires préfixées d'un octet de type.
"""

from __future__ import annotations

import struct
from typing import Annotated, Literal

from pydantic import BaseModel, Field, TypeAdapter, ValidationError

FREQUENCE_HZ = 16000
DUREE_BLOC_MS = 20
TAILLE_BLOC_OCTETS = FREQUENCE_HZ * DUREE_BLOC_MS // 1000 * 2  # 640

_TYPE_AUDIO_ENTRANT = 0x01
_TYPE_AUDIO_SORTANT = 0x02


# --- client vers core ---------------------------------------------------

class Bonjour(BaseModel):
    type: Literal["bonjour"] = "bonjour"
    client: str
    frequence: int = FREQUENCE_HZ
    capacites: list[str] = Field(default_factory=list)


class Reveil(BaseModel):
    type: Literal["reveil"] = "reveil"
    confiance: float
    horodatage: float


class FinEnonce(BaseModel):
    type: Literal["fin_enonce"] = "fin_enonce"
    duree_ms: int


class Interruption(BaseModel):
    type: Literal["interruption"] = "interruption"
    horodatage: float


class ReponseConfirmation(BaseModel):
    type: Literal["reponse_confirmation"] = "reponse_confirmation"
    id_demande: str
    acceptee: bool


MessageClient = Annotated[
    Bonjour | Reveil | FinEnonce | Interruption | ReponseConfirmation,
    Field(discriminator="type"),
]
_adaptateur_client = TypeAdapter(MessageClient)


# --- core vers client ---------------------------------------------------

class Etat(BaseModel):
    type: Literal["etat"] = "etat"
    valeur: Literal["repos", "ecoute", "reflexion", "parole"]


class Transcription(BaseModel):
    type: Literal["transcription"] = "transcription"
    texte: str
    finale: bool


class Dire(BaseModel):
    type: Literal["dire"] = "dire"
    id_enonce: int
    rang: int
    texte: str


class StopAudio(BaseModel):
    type: Literal["stop_audio"] = "stop_audio"
    id_enonce: int


class Confirmation(BaseModel):
    type: Literal["confirmation"] = "confirmation"
    id_demande: str
    action: str
    niveau: int
    expiration_s: int


class Erreur(BaseModel):
    type: Literal["erreur"] = "erreur"
    code: str
    message: str


MessageCore = Etat | Transcription | Dire | StopAudio | Confirmation | Erreur


def decoder_message(brut: str) -> MessageClient:
    """Décode un message de contrôle venant du client.

    Lève ValueError sur tout ce qui n'est pas un message connu et valide.
    """
    try:
        return _adaptateur_client.validate_json(brut)
    except ValidationError as e:
        raise ValueError(f"message client invalide : {e}") from e


# --- trames binaires ----------------------------------------------------

def _verifier_bloc(pcm: bytes) -> None:
    if len(pcm) != TAILLE_BLOC_OCTETS:
        raise ValueError(
            f"bloc de {len(pcm)} octets, attendu {TAILLE_BLOC_OCTETS} "
            f"({DUREE_BLOC_MS} ms à {FREQUENCE_HZ} Hz en s16le)"
        )


def encoder_audio_entrant(pcm: bytes) -> bytes:
    _verifier_bloc(pcm)
    return bytes([_TYPE_AUDIO_ENTRANT]) + pcm


def decoder_audio_entrant(trame: bytes) -> bytes:
    if not trame or trame[0] != _TYPE_AUDIO_ENTRANT:
        raise ValueError("trame audio entrante attendue")
    pcm = trame[1:]
    _verifier_bloc(pcm)
    return pcm


def encoder_audio_sortant(id_enonce: int, pcm: bytes) -> bytes:
    _verifier_bloc(pcm)
    return bytes([_TYPE_AUDIO_SORTANT]) + struct.pack(">I", id_enonce) + pcm


def decoder_audio_sortant(trame: bytes) -> tuple[int, bytes]:
    if not trame or trame[0] != _TYPE_AUDIO_SORTANT:
        raise ValueError("trame audio sortante attendue")
    (id_enonce,) = struct.unpack(">I", trame[1:5])
    pcm = trame[5:]
    _verifier_bloc(pcm)
    return id_enonce, pcm
```

- [ ] **Étape 4 : Lancer les tests pour vérifier qu'ils passent**

Run: `uv run pytest tests/test_protocole.py -v`
Expected: PASS, 7 tests.

- [ ] **Étape 5 : Commit**

```bash
git add src/helios_core/protocole.py tests/test_protocole.py
git commit -m "Ajoute le protocole de messages et le codec de trames audio"
```

---

### Tâche 3 : Découpage d'un flux de texte français en phrases

**Files:**
- Create: `src/helios_core/phrases.py`
- Test: `tests/test_phrases.py`

**Interfaces:**
- Consumes: rien.
- Produces: `DecoupeurPhrases` avec deux méthodes :
  - `ajouter(fragment: str) -> list[str]` — rend les phrases devenues complètes
  - `vider() -> list[str]` — rend ce qui reste en fin de génération

C'est la pièce qui permet de commencer à parler avant que le cerveau ait fini d'écrire.
Elle est purement logique, donc entièrement testable — et c'est là que se cachent les bugs
les plus agaçants à l'usage.

- [ ] **Étape 1 : Écrire les tests qui échouent**

```python
# tests/test_phrases.py
from helios_core.phrases import DecoupeurPhrases

def test_une_phrase_complete_sort_immediatement():
    d = DecoupeurPhrases()
    assert d.ajouter("Bonjour David.") == ["Bonjour David."]

def test_une_phrase_incomplete_est_retenue():
    d = DecoupeurPhrases()
    assert d.ajouter("Bonjour ") == []
    assert d.ajouter("David.") == ["Bonjour David."]

def test_deux_phrases_dans_un_fragment():
    d = DecoupeurPhrases()
    assert d.ajouter("Il est midi. Tu déjeunes ?") == ["Il est midi.", "Tu déjeunes ?"]

def test_une_abreviation_ne_coupe_pas():
    d = DecoupeurPhrases()
    assert d.ajouter("M. Durand est arrivé.") == ["M. Durand est arrivé."]

def test_une_decimale_ne_coupe_pas():
    d = DecoupeurPhrases()
    assert d.ajouter("Il fait 3.5 degrés dehors.") == ["Il fait 3.5 degrés dehors."]

def test_les_points_de_suspension_ne_coupent_pas_trois_fois():
    d = DecoupeurPhrases()
    assert d.ajouter("Attends... je réfléchis.") == ["Attends... je réfléchis."]

def test_le_flux_caractere_par_caractere_donne_le_meme_resultat():
    d = DecoupeurPhrases()
    sorties = []
    for c in "Il est midi. Tu déjeunes ?":
        sorties.extend(d.ajouter(c))
    sorties.extend(d.vider())
    assert sorties == ["Il est midi.", "Tu déjeunes ?"]

def test_vider_rend_une_phrase_sans_ponctuation_finale():
    d = DecoupeurPhrases()
    d.ajouter("Bon, on verra")
    assert d.vider() == ["Bon, on verra"]

def test_vider_deux_fois_ne_repete_rien():
    d = DecoupeurPhrases()
    d.ajouter("Bon")
    assert d.vider() == ["Bon"]
    assert d.vider() == []
```

- [ ] **Étape 2 : Lancer les tests pour vérifier qu'ils échouent**

Run: `uv run pytest tests/test_phrases.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'helios_core.phrases'`

- [ ] **Étape 3 : Écrire le découpeur**

```python
# src/helios_core/phrases.py
"""Découpage d'un flux de texte français en phrases prononçables.

Le cerveau écrit au fil de l'eau ; on veut envoyer chaque phrase au TTS dès
qu'elle est complète, sans couper au milieu d'une abréviation ou d'un nombre.
"""

from __future__ import annotations

import re

_FINS = ".!?"

# Abréviations françaises courantes après lesquelles un point ne finit pas la phrase.
_ABREVIATIONS = {
    "m", "mm", "mme", "mlle", "dr", "pr", "st", "ste", "av", "bd",
    "cf", "ex", "etc", "env", "art", "fig", "p", "pp", "vol", "no", "n°",
}

_MOT_FINAL = re.compile(r"([A-Za-zÀ-ÿ°]+)\.$")


class DecoupeurPhrases:
    """Accumule du texte et rend les phrases au fur et à mesure."""

    def __init__(self) -> None:
        self._tampon = ""

    def ajouter(self, fragment: str) -> list[str]:
        self._tampon += fragment
        phrases: list[str] = []
        while True:
            coupe = self._trouver_coupe()
            if coupe is None:
                break
            phrases.append(self._tampon[:coupe].strip())
            self._tampon = self._tampon[coupe:].lstrip()
        return [p for p in phrases if p]

    def vider(self) -> list[str]:
        reste = self._tampon.strip()
        self._tampon = ""
        return [reste] if reste else []

    def _trouver_coupe(self) -> int | None:
        """Position juste après la ponctuation finale, ou None."""
        for i, c in enumerate(self._tampon):
            if c not in _FINS:
                continue
            fin = i + 1
            # Points de suspension : avaler la série et ne couper qu'après.
            while fin < len(self._tampon) and self._tampon[fin] == c == ".":
                fin += 1
            if fin - i > 1:
                # « ... » au milieu d'une phrase : ce n'est une fin que si un
                # espace et une majuscule suivent.
                if not self._suit_une_nouvelle_phrase(fin):
                    continue
                return fin
            if self._est_une_decimale(i):
                continue
            if self._est_une_abreviation(fin):
                continue
            if fin < len(self._tampon) and not self._tampon[fin].isspace():
                continue  # ponctuation collée à la suite : on attend
            if fin == len(self._tampon):
                return fin
            return fin
        return None

    def _est_une_decimale(self, i: int) -> bool:
        avant = self._tampon[i - 1] if i > 0 else ""
        apres = self._tampon[i + 1] if i + 1 < len(self._tampon) else ""
        return avant.isdigit() and apres.isdigit()

    def _est_une_abreviation(self, fin: int) -> bool:
        m = _MOT_FINAL.search(self._tampon[:fin])
        return bool(m) and m.group(1).lower() in _ABREVIATIONS

    def _suit_une_nouvelle_phrase(self, fin: int) -> bool:
        reste = self._tampon[fin:]
        if not reste:
            return True
        if not reste[0].isspace():
            return False
        suite = reste.lstrip()
        return bool(suite) and suite[0].isupper()
```

- [ ] **Étape 4 : Lancer les tests pour vérifier qu'ils passent**

Run: `uv run pytest tests/test_phrases.py -v`
Expected: PASS, 9 tests.

- [ ] **Étape 5 : Commit**

```bash
git add src/helios_core/phrases.py tests/test_phrases.py
git commit -m "Ajoute le découpage en phrases françaises au fil du flux"
```

---

### Tâche 4 : Service de transcription `helios-stt`

**Files:**
- Create: `services/stt/serveur.py`, `services/stt/Dockerfile`, `services/stt/requirements.txt`
- Test: `tests/test_stt_serveur.py`

**Interfaces:**
- Consumes: rien.
- Produces: la route HTTP consommée par la tâche 6.
  ```
  POST /transcribe   Content-Type: audio/wav   corps : WAV 16 kHz mono
                     → 200 {"text": str, "language": str, "duration_ms": int}
                     → 400 {"detail": str} si le corps n'est pas un WAV lisible
  GET  /sante        → {"ok": true, "modele": str, "charge": bool}
  ```
  Et le protocole `Transcripteur` avec `transcrire(wav: bytes) -> tuple[str, str, int]`,
  qui permet de tester le service sans GPU.

- [ ] **Étape 1 : Écrire les tests qui échouent**

Le service se teste sans carte graphique en injectant un faux moteur — c'est tout l'intérêt
de faire passer le moteur par une dépendance.

```python
# tests/test_stt_serveur.py
import io
import wave

import pytest
from fastapi.testclient import TestClient

from services.stt.serveur import app, obtenir_transcripteur


class FauxTranscripteur:
    def __init__(self) -> None:
        self.appels: list[bytes] = []

    def transcrire(self, wav: bytes) -> tuple[str, str, int]:
        self.appels.append(wav)
        return ("il est quatorze heures", "fr", 1500)


def _wav_silencieux(ms: int = 1000) -> bytes:
    tampon = io.BytesIO()
    with wave.open(tampon, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(16000)
        f.writeframes(b"\x00\x00" * (16 * ms))
    return tampon.getvalue()


@pytest.fixture
def client():
    faux = FauxTranscripteur()
    app.dependency_overrides[obtenir_transcripteur] = lambda: faux
    yield TestClient(app), faux
    app.dependency_overrides.clear()


def test_transcrire_rend_le_texte(client):
    c, _ = client
    r = c.post("/transcribe", content=_wav_silencieux(),
               headers={"Content-Type": "audio/wav"})
    assert r.status_code == 200
    assert r.json() == {"text": "il est quatorze heures",
                        "language": "fr", "duration_ms": 1500}


def test_un_corps_qui_n_est_pas_un_wav_est_refuse(client):
    c, _ = client
    r = c.post("/transcribe", content=b"ceci n'est pas un wav",
               headers={"Content-Type": "audio/wav"})
    assert r.status_code == 400


def test_un_corps_vide_est_refuse(client):
    c, _ = client
    r = c.post("/transcribe", content=b"", headers={"Content-Type": "audio/wav"})
    assert r.status_code == 400


def test_la_route_de_sante_repond(client):
    c, _ = client
    r = c.get("/sante")
    assert r.status_code == 200
    assert r.json()["ok"] is True
```

- [ ] **Étape 2 : Lancer les tests pour vérifier qu'ils échouent**

Run: `uv run pytest tests/test_stt_serveur.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'services.stt.serveur'`

- [ ] **Étape 3 : Écrire le serveur**

```python
# services/stt/serveur.py
"""Service de transcription : faster-whisper derrière une route HTTP.

Le modèle se charge à la demande et se décharge après inactivité, parce que les
12 Go de VRAM sont partagés avec ComfyUI. Ce comportement disparaîtra avec la 3090.
"""

from __future__ import annotations

import io
import os
import threading
import time
import wave
from typing import Protocol

from fastapi import Body, Depends, FastAPI, HTTPException

MODELE = os.environ.get("HELIOS_STT_MODELE", "large-v3")
DECHARGEMENT_S = int(os.environ.get("HELIOS_STT_DECHARGEMENT_S", "300"))


class Transcripteur(Protocol):
    def transcrire(self, wav: bytes) -> tuple[str, str, int]:
        """Rend (texte, langue, durée en millisecondes)."""
        ...


class MoteurWhisper:
    """Charge le modèle à la demande, le décharge après inactivité."""

    def __init__(self, modele: str, dechargement_s: int) -> None:
        self._nom = modele
        self._dechargement_s = dechargement_s
        self._modele = None
        self._dernier_usage = 0.0
        self._verrou = threading.Lock()

    @property
    def charge(self) -> bool:
        return self._modele is not None

    def _obtenir(self):
        from faster_whisper import WhisperModel

        with self._verrou:
            if self._modele is None:
                self._modele = WhisperModel(
                    self._nom, device="cuda", compute_type="float16"
                )
            self._dernier_usage = time.monotonic()
            return self._modele

    def decharger_si_inactif(self) -> None:
        with self._verrou:
            if (
                self._modele is not None
                and time.monotonic() - self._dernier_usage > self._dechargement_s
            ):
                self._modele = None

    def transcrire(self, wav: bytes) -> tuple[str, str, int]:
        modele = self._obtenir()
        segments, info = modele.transcribe(
            io.BytesIO(wav), language="fr", vad_filter=False
        )
        texte = "".join(s.text for s in segments).strip()
        return texte, info.language, int(info.duration * 1000)


_moteur = MoteurWhisper(MODELE, DECHARGEMENT_S)


def obtenir_transcripteur() -> Transcripteur:
    return _moteur


app = FastAPI(title="helios-stt")


def _verifier_wav(corps: bytes) -> None:
    if not corps:
        raise HTTPException(status_code=400, detail="corps vide")
    try:
        with wave.open(io.BytesIO(corps), "rb") as f:
            if f.getnchannels() != 1 or f.getsampwidth() != 2:
                raise HTTPException(
                    status_code=400, detail="attendu : WAV mono 16 bits"
                )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"WAV illisible : {e}") from e


@app.post("/transcribe")
def transcrire(
    corps: bytes = Body(..., media_type="audio/wav"),
    transcripteur: Transcripteur = Depends(obtenir_transcripteur),
) -> dict:
    _verifier_wav(corps)
    texte, langue, duree_ms = transcripteur.transcrire(corps)
    return {"text": texte, "language": langue, "duration_ms": duree_ms}


@app.get("/sante")
def sante() -> dict:
    return {"ok": True, "modele": MODELE, "charge": _moteur.charge}
```

- [ ] **Étape 4 : Lancer les tests pour vérifier qu'ils passent**

Run: `uv run pytest tests/test_stt_serveur.py -v`
Expected: PASS, 4 tests.

- [ ] **Étape 5 : Écrire le Dockerfile**

```dockerfile
# services/stt/Dockerfile
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.12 python3-pip && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt
COPY serveur.py .

EXPOSE 9010
CMD ["python3", "-m", "uvicorn", "serveur:app", "--host", "0.0.0.0", "--port", "9010"]
```

```
# services/stt/requirements.txt
faster-whisper>=1.2.1
fastapi>=0.115
uvicorn[standard]>=0.32
```

- [ ] **Étape 6 : Construire et vérifier sur l'Unraid**

```bash
docker build -t helios-stt services/stt/
docker run -d --name helios-stt --gpus all -p 9010:9010 \
  -e HELIOS_STT_MODELE=large-v3 -v helios-modeles:/root/.cache helios-stt
curl -s http://unraid.local:9010/sante
```
Expected: `{"ok":true,"modele":"large-v3","charge":false}`

- [ ] **Étape 7 : Vérifier une vraie transcription française**

Enregistrer une phrase française en WAV 16 kHz mono, puis :

```bash
curl -s -X POST http://unraid.local:9010/transcribe \
  -H 'Content-Type: audio/wav' --data-binary @phrase.wav
```
Expected: le texte français correct, `"language":"fr"`.

- [ ] **Étape 8 : Commit**

```bash
git add services/stt/ tests/test_stt_serveur.py
git commit -m "Ajoute le service de transcription faster-whisper"
```

---

### Tâche 5 : Service de synthèse `helios-tts`

**Files:**
- Create: `services/tts/serveur.py`, `services/tts/Dockerfile`, `services/tts/requirements.txt`
- Test: `tests/test_tts_serveur.py`

**Interfaces:**
- Consumes: la décision de moteur du spike S1.
- Produces: la route HTTP consommée par la tâche 6.
  ```
  POST /synthesize   corps : {"text": str, "voice": str}
                     → 200 audio/wav en streaming (en-tête puis morceaux PCM 16 kHz)
                     → 400 si "text" est vide
  GET  /sante        → {"ok": true, "moteur": str}
  ```
  Et le protocole `MoteurTTS` avec `synthetiser(texte: str, voix: str) -> Iterator[bytes]`,
  qui rend des morceaux de PCM 16 kHz mono s16le.

Le streaming par morceaux est une **exigence**, pas un confort : c'est ce qui permet à
Helios de commencer à parler avant d'avoir fini de synthétiser. Un moteur qui ne rend que
le fichier complet est disqualifié.

- [ ] **Étape 1 : Écrire les tests qui échouent**

```python
# tests/test_tts_serveur.py
import pytest
from fastapi.testclient import TestClient

from services.tts.serveur import app, obtenir_moteur


class FauxMoteur:
    nom = "faux"

    def synthetiser(self, texte: str, voix: str):
        # trois morceaux de 20 ms, pour vérifier que le streaming passe bien
        for _ in range(3):
            yield b"\x00\x01" * 320


@pytest.fixture
def client():
    app.dependency_overrides[obtenir_moteur] = lambda: FauxMoteur()
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_synthetiser_rend_un_wav_avec_les_morceaux(client):
    r = client.post("/synthesize", json={"text": "Bonjour David.", "voice": "fr"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("audio/wav")
    assert r.content[:4] == b"RIFF"
    assert r.content[8:12] == b"WAVE"
    assert len(r.content) == 44 + 3 * 640


def test_un_texte_vide_est_refuse(client):
    assert client.post("/synthesize", json={"text": "", "voice": "fr"}).status_code == 400


def test_un_texte_uniquement_blanc_est_refuse(client):
    assert client.post("/synthesize", json={"text": "   ", "voice": "fr"}).status_code == 400


def test_la_route_de_sante_repond(client):
    r = client.get("/sante")
    assert r.status_code == 200
    assert r.json()["ok"] is True
```

- [ ] **Étape 2 : Lancer les tests pour vérifier qu'ils échouent**

Run: `uv run pytest tests/test_tts_serveur.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'services.tts.serveur'`

- [ ] **Étape 3 : Écrire le serveur avec le moteur Piper**

Piper est écrit en premier parce qu'il est le repli garanti de la spec et qu'il sert de
mètre étalon au banc de mesure, quel que soit le verdict de S1.

```python
# services/tts/serveur.py
"""Service de synthèse vocale, moteur interchangeable.

Rend toujours du PCM 16 kHz mono s16le, quel que soit le moteur : la conversion
de fréquence appartient au service, jamais au reste du pipeline.
"""

from __future__ import annotations

import os
import struct
import subprocess
from collections.abc import Iterator
from typing import Protocol

import numpy as np
import soxr
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

MOTEUR = os.environ.get("HELIOS_TTS_MOTEUR", "piper")
VOIX_DEFAUT = os.environ.get("HELIOS_TTS_VOIX", "fr_FR-siwis-medium")
FREQUENCE_SORTIE = 16000
TAILLE_MORCEAU = 640  # 20 ms


class MoteurTTS(Protocol):
    nom: str

    def synthetiser(self, texte: str, voix: str) -> Iterator[bytes]:
        """Rend des morceaux de PCM 16 kHz mono s16le."""
        ...


class MoteurPiper:
    nom = "piper"

    def __init__(self, dossier_modeles: str = "/modeles") -> None:
        self._dossier = dossier_modeles

    def synthetiser(self, texte: str, voix: str) -> Iterator[bytes]:
        modele = f"{self._dossier}/{voix or VOIX_DEFAUT}.onnx"
        proc = subprocess.Popen(
            ["piper", "--model", modele, "--output_raw"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        )
        assert proc.stdin and proc.stdout
        proc.stdin.write(texte.encode("utf-8"))
        proc.stdin.close()

        reste = b""
        while True:
            brut = proc.stdout.read(4096)
            if not brut:
                break
            # Piper sort du 22050 Hz : on ramène à 16 kHz ici, une fois pour toutes.
            echantillons = np.frombuffer(reste + brut, dtype="<i2")
            reste = b""
            if echantillons.size == 0:
                continue
            ramene = soxr.resample(echantillons.astype(np.float32), 22050, FREQUENCE_SORTIE)
            pcm = np.clip(ramene, -32768, 32767).astype("<i2").tobytes()
            for i in range(0, len(pcm) - TAILLE_MORCEAU + 1, TAILLE_MORCEAU):
                yield pcm[i : i + TAILLE_MORCEAU]
        proc.wait()


_moteurs: dict[str, MoteurTTS] = {"piper": MoteurPiper()}


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
        b"RIFF" + struct.pack("<I", 0xFFFFFFFF) + b"WAVE"
        + b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, FREQUENCE_SORTIE,
                                FREQUENCE_SORTIE * 2, 2, 16)
        + b"data" + struct.pack("<I", 0xFFFFFFFF)
    )


class DemandeSynthese(BaseModel):
    text: str
    voice: str = ""


app = FastAPI(title="helios-tts")


@app.post("/synthesize")
def synthetiser(
    demande: DemandeSynthese, moteur: MoteurTTS = Depends(obtenir_moteur)
) -> StreamingResponse:
    if not demande.text.strip():
        raise HTTPException(status_code=400, detail="texte vide")

    def flux() -> Iterator[bytes]:
        yield entete_wav_streaming()
        yield from moteur.synthetiser(demande.text, demande.voice or VOIX_DEFAUT)

    return StreamingResponse(flux(), media_type="audio/wav")


@app.get("/sante")
def sante() -> dict:
    return {"ok": True, "moteur": MOTEUR}
```

- [ ] **Étape 4 : Lancer les tests pour vérifier qu'ils passent**

Run: `uv run pytest tests/test_tts_serveur.py -v`
Expected: PASS, 4 tests.

- [ ] **Étape 5 : Écrire le Dockerfile**

```dockerfile
# services/tts/Dockerfile
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.12 python3-pip && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt
COPY serveur.py .

EXPOSE 9011
CMD ["python3", "-m", "uvicorn", "serveur:app", "--host", "0.0.0.0", "--port", "9011"]
```

```
# services/tts/requirements.txt
piper-tts>=1.3.0
numpy>=2.1
soxr>=0.5
fastapi>=0.115
uvicorn[standard]>=0.32
```

- [ ] **Étape 6 : Déployer et vérifier une vraie synthèse française**

```bash
docker build -t helios-tts services/tts/
docker run -d --name helios-tts --gpus all -p 9011:9011 \
  -v helios-voix:/modeles helios-tts
curl -s -X POST http://unraid.local:9011/synthesize \
  -H 'Content-Type: application/json' \
  -d '{"text":"Bonjour David, il est quatorze heures trente-deux.","voice":""}' \
  --output /tmp/test.wav
afplay /tmp/test.wav
```
Expected: une phrase française intelligible, les chiffres dits en toutes lettres.

- [ ] **Étape 7 : Ajouter le moteur retenu par S1, si ce n'est pas Piper**

Si le verdict de S1 a retenu Qwen3 ou Kokoro, écrire une classe de plus dans le même
fichier, **derrière le même protocole `MoteurTTS`**, en suivant l'API relevée dans
`docs/superpowers/spikes/2026-09-22-s1-tts-francais.md`, et l'enregistrer dans le
dictionnaire `_moteurs`. Les quatre tests de l'étape 1 s'appliquent tels quels : ils
testent la route, pas le moteur. Ajouter un test de plus, qui vérifie que le nouveau
moteur rend bien son **premier morceau en moins de 300 ms** — c'est la seule propriété
du moteur qui engage l'architecture.

Si S1 a retenu Piper, sauter cette étape.

- [ ] **Étape 8 : Commit**

```bash
git add services/tts/ tests/test_tts_serveur.py
git commit -m "Ajoute le service de synthèse vocale avec streaming par morceaux"
```

---

### Tâche 6 : Configuration et clients HTTP vers les services GPU

**Files:**
- Create: `src/helios_core/config.py`, `src/helios_core/transcription.py`,
  `src/helios_core/synthese.py`
- Test: `tests/test_transcription.py`, `tests/test_synthese.py`

**Interfaces:**
- Consumes: les routes HTTP des tâches 4 et 5.
- Produces:
  - `Config.depuis_environnement() -> Config` avec les champs `stt_url`, `tts_url`,
    `tts_voix`, `port_core`
  - `pcm_vers_wav(pcm: bytes, frequence: int = 16000) -> bytes`
  - `ClientTranscription.transcrire(pcm: bytes) -> str` (coroutine)
  - `ClientSynthese.synthetiser(texte: str) -> AsyncIterator[bytes]` rendant des blocs
    de 640 octets, **en-tête WAV déjà retiré**

- [ ] **Étape 1 : Écrire les tests qui échouent**

Les deux clients se testent sans réseau grâce au transport simulé de `httpx`.

```python
# tests/test_transcription.py
import httpx
import pytest

from helios_core.protocole import TAILLE_BLOC_OCTETS
from helios_core.transcription import ClientTranscription, pcm_vers_wav


def test_pcm_vers_wav_produit_un_entete_lisible():
    wav = pcm_vers_wav(b"\x00\x00" * 320)
    assert wav[:4] == b"RIFF" and wav[8:12] == b"WAVE"
    assert len(wav) == 44 + 640


async def test_transcrire_rend_le_texte():
    recus: list[bytes] = []

    def repondre(requete: httpx.Request) -> httpx.Response:
        recus.append(requete.content)
        return httpx.Response(200, json={"text": "il est midi",
                                         "language": "fr", "duration_ms": 900})

    transport = httpx.MockTransport(repondre)
    async with httpx.AsyncClient(transport=transport) as http:
        client = ClientTranscription("http://stt", http)
        assert await client.transcrire(b"\x00\x00" * 320) == "il est midi"
    assert recus[0][:4] == b"RIFF"


async def test_une_erreur_du_service_remonte_une_exception():
    transport = httpx.MockTransport(lambda r: httpx.Response(500, text="boum"))
    async with httpx.AsyncClient(transport=transport) as http:
        client = ClientTranscription("http://stt", http)
        with pytest.raises(RuntimeError, match="transcription"):
            await client.transcrire(b"\x00\x00" * TAILLE_BLOC_OCTETS)
```

```python
# tests/test_synthese.py
import httpx
import pytest

from helios_core.synthese import ClientSynthese

_ENTETE = b"RIFF" + b"\xff" * 4 + b"WAVE" + b"fmt " + b"\x00" * 20 + b"data" + b"\xff" * 4


async def _collecter(client: ClientSynthese, texte: str) -> list[bytes]:
    return [bloc async for bloc in client.synthetiser(texte)]


async def test_les_blocs_sortent_sans_l_entete():
    corps = _ENTETE + b"\x01\x02" * 320 * 3

    def repondre(requete: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=corps)

    async with httpx.AsyncClient(transport=httpx.MockTransport(repondre)) as http:
        blocs = await _collecter(ClientSynthese("http://tts", "fr", http), "Bonjour.")
    assert len(blocs) == 3
    assert all(len(b) == 640 for b in blocs)
    assert b"RIFF" not in b"".join(blocs)


async def test_un_reste_partiel_est_complete_par_du_silence():
    corps = _ENTETE + b"\x01\x02" * 400  # 800 octets : un bloc plein + 160 octets
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=corps))
    ) as http:
        blocs = await _collecter(ClientSynthese("http://tts", "fr", http), "Bonjour.")
    assert len(blocs) == 2
    assert all(len(b) == 640 for b in blocs)
    assert blocs[1].endswith(b"\x00" * 480)


async def test_une_erreur_du_service_remonte_une_exception():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(503, text="occupé"))
    ) as http:
        with pytest.raises(RuntimeError, match="synthèse"):
            await _collecter(ClientSynthese("http://tts", "fr", http), "Bonjour.")
```

Le test du reste partiel est celui qui compte : un moteur TTS ne finit presque jamais sur
un multiple exact de 20 ms, et un bloc incomplet envoyé à la carte son produit un clic.

- [ ] **Étape 2 : Lancer les tests pour vérifier qu'ils échouent**

Run: `uv run pytest tests/test_transcription.py tests/test_synthese.py -v`
Expected: FAIL avec `ModuleNotFoundError`

- [ ] **Étape 3 : Écrire la configuration**

```python
# src/helios_core/config.py
"""Configuration lue dans l'environnement. Aucun secret, seulement des adresses."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    stt_url: str
    tts_url: str
    tts_voix: str
    port_core: int

    @staticmethod
    def depuis_environnement() -> Config:
        return Config(
            stt_url=os.environ.get("HELIOS_STT_URL", "http://unraid.local:9010"),
            tts_url=os.environ.get("HELIOS_TTS_URL", "http://unraid.local:9011"),
            tts_voix=os.environ.get("HELIOS_TTS_VOIX", "fr_FR-siwis-medium"),
            port_core=int(os.environ.get("HELIOS_CORE_PORT", "8080")),
        )
```

- [ ] **Étape 4 : Écrire le client de transcription**

```python
# src/helios_core/transcription.py
"""Client du service helios-stt."""

from __future__ import annotations

import io
import wave

import httpx

from .protocole import FREQUENCE_HZ


def pcm_vers_wav(pcm: bytes, frequence: int = FREQUENCE_HZ) -> bytes:
    """Emballe du PCM s16le mono dans un WAV, pour que le service reste testable au curl."""
    tampon = io.BytesIO()
    with wave.open(tampon, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(frequence)
        f.writeframes(pcm)
    return tampon.getvalue()


class ClientTranscription:
    def __init__(self, base_url: str, http: httpx.AsyncClient) -> None:
        self._base = base_url.rstrip("/")
        self._http = http

    async def transcrire(self, pcm: bytes) -> str:
        reponse = await self._http.post(
            f"{self._base}/transcribe",
            content=pcm_vers_wav(pcm),
            headers={"Content-Type": "audio/wav"},
            timeout=30.0,
        )
        if reponse.status_code != 200:
            raise RuntimeError(
                f"transcription en échec ({reponse.status_code}) : {reponse.text[:200]}"
            )
        return reponse.json()["text"]
```

- [ ] **Étape 5 : Écrire le client de synthèse**

```python
# src/helios_core/synthese.py
"""Client du service helios-tts, en flux."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx

from .protocole import TAILLE_BLOC_OCTETS

_TAILLE_ENTETE_WAV = 44


class ClientSynthese:
    def __init__(self, base_url: str, voix: str, http: httpx.AsyncClient) -> None:
        self._base = base_url.rstrip("/")
        self._voix = voix
        self._http = http

    async def synthetiser(self, texte: str) -> AsyncIterator[bytes]:
        """Rend des blocs de 20 ms, en-tête WAV retiré, dernier bloc complété au silence."""
        a_sauter = _TAILLE_ENTETE_WAV
        reste = b""
        async with self._http.stream(
            "POST",
            f"{self._base}/synthesize",
            json={"text": texte, "voice": self._voix},
            timeout=60.0,
        ) as reponse:
            if reponse.status_code != 200:
                corps = await reponse.aread()
                raise RuntimeError(
                    f"synthèse en échec ({reponse.status_code}) : {corps[:200]!r}"
                )
            async for morceau in reponse.aiter_bytes():
                if a_sauter:
                    saut = min(a_sauter, len(morceau))
                    morceau = morceau[saut:]
                    a_sauter -= saut
                    if not morceau:
                        continue
                reste += morceau
                while len(reste) >= TAILLE_BLOC_OCTETS:
                    yield reste[:TAILLE_BLOC_OCTETS]
                    reste = reste[TAILLE_BLOC_OCTETS:]
        if reste:
            yield reste + b"\x00" * (TAILLE_BLOC_OCTETS - len(reste))
```

- [ ] **Étape 6 : Lancer les tests pour vérifier qu'ils passent**

Run: `uv run pytest tests/test_transcription.py tests/test_synthese.py -v`
Expected: PASS, 6 tests.

- [ ] **Étape 7 : Commit**

```bash
git add src/helios_core/config.py src/helios_core/transcription.py \
        src/helios_core/synthese.py tests/test_transcription.py tests/test_synthese.py
git commit -m "Ajoute la configuration et les clients des services GPU"
```

---

### Tâche 7 : Machine à états et cerveau bouchon

**Files:**
- Create: `src/helios_core/etat.py`, `src/helios_core/cerveau.py`
- Test: `tests/test_etat.py`, `tests/test_cerveau.py`

**Interfaces:**
- Consumes: rien.
- Produces:
  - `MachineEtat` avec `.valeur` (`"repos" | "ecoute" | "reflexion" | "parole"`),
    `.aller_vers(valeur)` qui lève `TransitionInterdite` sur un enchaînement impossible,
    et `.peut_aller_vers(valeur) -> bool`
  - `TransitionInterdite(Exception)`
  - Protocole `Cerveau` avec `repondre(texte: str) -> AsyncIterator[str]`
  - `CerveauBouchon` — les réponses figées de la phase 1

La machine à états existe pour une raison précise : sans elle, une trame audio qui arrive
pendant que le cerveau réfléchit se mélange à l'énoncé suivant, et on passe des heures à
chercher pourquoi Helios répond à la phrase d'avant.

- [ ] **Étape 1 : Écrire les tests qui échouent**

```python
# tests/test_etat.py
import pytest

from helios_core.etat import MachineEtat, TransitionInterdite


def test_l_etat_de_depart_est_le_repos():
    assert MachineEtat().valeur == "repos"


@pytest.mark.parametrize(
    "depart,arrivee",
    [("repos", "ecoute"), ("ecoute", "reflexion"), ("reflexion", "parole"),
     ("parole", "repos"), ("parole", "ecoute"), ("ecoute", "repos")],
)
def test_les_transitions_permises_passent(depart, arrivee):
    m = MachineEtat()
    m._valeur = depart  # positionnement direct pour le test
    m.aller_vers(arrivee)
    assert m.valeur == arrivee


@pytest.mark.parametrize(
    "depart,arrivee",
    [("repos", "parole"), ("repos", "reflexion"), ("ecoute", "parole"),
     ("reflexion", "ecoute")],
)
def test_les_transitions_interdites_levent(depart, arrivee):
    m = MachineEtat()
    m._valeur = depart
    with pytest.raises(TransitionInterdite):
        m.aller_vers(arrivee)


def test_peut_aller_vers_ne_leve_pas():
    m = MachineEtat()
    assert m.peut_aller_vers("ecoute") is True
    assert m.peut_aller_vers("parole") is False
    assert m.valeur == "repos"
```

```python
# tests/test_cerveau.py
from helios_core.cerveau import CerveauBouchon


async def _texte(cerveau, demande: str) -> str:
    return "".join([f async for f in cerveau.repondre(demande)])


async def test_il_donne_l_heure():
    reponse = await _texte(CerveauBouchon(heure=lambda: (14, 32)), "quelle heure est-il")
    assert "quatorze heures trente-deux" in reponse


async def test_il_repond_bonjour():
    assert "Bonjour" in await _texte(CerveauBouchon(), "bonjour Helios")


async def test_il_assume_de_ne_pas_savoir():
    reponse = await _texte(CerveauBouchon(), "explique-moi la mécanique quantique")
    assert "phase un" in reponse


async def test_il_rend_plusieurs_fragments():
    fragments = [f async for f in CerveauBouchon().repondre("bonjour")]
    assert len(fragments) > 1, "le cerveau doit streamer, sinon on ne teste pas le découpage"
```

- [ ] **Étape 2 : Lancer les tests pour vérifier qu'ils échouent**

Run: `uv run pytest tests/test_etat.py tests/test_cerveau.py -v`
Expected: FAIL avec `ModuleNotFoundError`

- [ ] **Étape 3 : Écrire la machine à états**

```python
# src/helios_core/etat.py
"""Machine à états d'un tour de parole."""

from __future__ import annotations

from typing import Literal

Valeur = Literal["repos", "ecoute", "reflexion", "parole"]

_PERMISES: dict[Valeur, set[Valeur]] = {
    "repos": {"ecoute"},
    "ecoute": {"reflexion", "repos"},
    "reflexion": {"parole", "repos"},
    "parole": {"repos", "ecoute"},  # « ecoute » est le chemin de l'interruption
}


class TransitionInterdite(Exception):
    pass


class MachineEtat:
    def __init__(self) -> None:
        self._valeur: Valeur = "repos"

    @property
    def valeur(self) -> Valeur:
        return self._valeur

    def peut_aller_vers(self, valeur: Valeur) -> bool:
        return valeur in _PERMISES[self._valeur]

    def aller_vers(self, valeur: Valeur) -> None:
        if not self.peut_aller_vers(valeur):
            raise TransitionInterdite(f"{self._valeur} ne mène pas à {valeur}")
        self._valeur = valeur
```

- [ ] **Étape 4 : Écrire le cerveau bouchon**

```python
# src/helios_core/cerveau.py
"""Le cerveau de la phase 1 : des réponses figées.

Claude arrive en phase 2. Ce bouchon existe pour valider la chaîne audio seule —
si la voix ne marche pas, on veut le savoir sans avoir à déboguer un LLM en même temps.
"""

from __future__ import annotations

import asyncio
import datetime as dt
from collections.abc import AsyncIterator, Callable
from typing import Protocol

_UNITES = {
    0: "zéro", 1: "une", 2: "deux", 3: "trois", 4: "quatre", 5: "cinq",
    6: "six", 7: "sept", 8: "huit", 9: "neuf", 10: "dix", 11: "onze",
    12: "douze", 13: "treize", 14: "quatorze", 15: "quinze", 16: "seize",
    17: "dix-sept", 18: "dix-huit", 19: "dix-neuf", 20: "vingt",
    30: "trente", 40: "quarante", 50: "cinquante",
}


def en_lettres(n: int) -> str:
    """Nombres de 0 à 59 en toutes lettres — le TTS lit mieux les mots que les chiffres."""
    if n in _UNITES:
        return _UNITES[n]
    dizaine, unite = divmod(n, 10)
    base = _UNITES[dizaine * 10]
    if unite == 1:
        return f"{base} et une"
    return f"{base}-{_UNITES[unite]}"


class Cerveau(Protocol):
    def repondre(self, texte: str) -> AsyncIterator[str]:
        """Rend la réponse en fragments, au fil de l'eau."""
        ...


class CerveauBouchon:
    def __init__(self, heure: Callable[[], tuple[int, int]] | None = None) -> None:
        self._heure = heure or (lambda: (dt.datetime.now().hour,
                                         dt.datetime.now().minute))

    async def repondre(self, texte: str) -> AsyncIterator[str]:
        demande = texte.lower()
        if "heure" in demande:
            h, m = self._heure()
            phrase = f"Il est {en_lettres(h)} heures {en_lettres(m)}."
        elif "bonjour" in demande or "salut" in demande:
            phrase = "Bonjour David. Je t'écoute."
        else:
            phrase = ("Je n'ai pas encore de cerveau, on est en phase un. "
                      "Demande-moi l'heure, pour voir.")

        # On rend mot à mot pour que le découpage en phrases soit réellement exercé.
        for mot in phrase.split(" "):
            yield mot + " "
            await asyncio.sleep(0)
```

- [ ] **Étape 5 : Lancer les tests pour vérifier qu'ils passent**

Run: `uv run pytest tests/test_etat.py tests/test_cerveau.py -v`
Expected: PASS, 15 tests.

- [ ] **Étape 6 : Commit**

```bash
git add src/helios_core/etat.py src/helios_core/cerveau.py \
        tests/test_etat.py tests/test_cerveau.py
git commit -m "Ajoute la machine à états et le cerveau bouchon de la phase 1"
```

---

### Tâche 8 : Orchestration d'un tour de parole et interruption

**Files:**
- Create: `src/helios_core/session.py`
- Test: `tests/test_session.py`

**Interfaces:**
- Consumes: `MachineEtat` (tâche 7), `Cerveau` (tâche 7), `DecoupeurPhrases` (tâche 3),
  `ClientTranscription` et `ClientSynthese` (tâche 6), le protocole (tâche 2).
- Produces:
  ```python
  Session(envoyer_json, envoyer_binaire, transcription, synthese, cerveau)
  await session.sur_message(msg: MessageClient) -> None
  await session.sur_audio(pcm: bytes) -> None
  await session.fermer() -> None
  ```
  `envoyer_json` a la signature `(MessageCore) -> Awaitable[None]`, `envoyer_binaire`
  la signature `(bytes) -> Awaitable[None]`.

C'est le cœur de la phase 1, et la seule tâche où vit une vraie difficulté : l'interruption
doit annuler la génération **et** vider ce qui est déjà en vol, sans laisser la machine à
états dans un entre-deux.

- [ ] **Étape 1 : Écrire les tests qui échouent**

```python
# tests/test_session.py
import asyncio
from collections.abc import AsyncIterator

from helios_core.protocole import (
    Dire, Etat, FinEnonce, Interruption, Reveil, StopAudio,
    Transcription, decoder_audio_sortant,
)
from helios_core.session import Session


class Collecteur:
    def __init__(self) -> None:
        self.json: list = []
        self.binaire: list[bytes] = []

    async def envoyer_json(self, msg) -> None:
        self.json.append(msg)

    async def envoyer_binaire(self, trame: bytes) -> None:
        self.binaire.append(trame)

    def types(self) -> list[str]:
        return [m.type for m in self.json]

    def premier(self, classe):
        return next(m for m in self.json if isinstance(m, classe))


class FausseTranscription:
    def __init__(self, texte: str) -> None:
        self.texte = texte

    async def transcrire(self, pcm: bytes) -> str:
        return self.texte


class FausseSynthese:
    def __init__(self, blocs: int = 3, lenteur: float = 0.0) -> None:
        self.blocs, self.lenteur = blocs, lenteur

    async def synthetiser(self, texte: str) -> AsyncIterator[bytes]:
        for _ in range(self.blocs):
            if self.lenteur:
                await asyncio.sleep(self.lenteur)
            yield b"\x00" * 640


class CerveauFixe:
    def __init__(self, phrase: str = "Il est midi. Tu déjeunes ?") -> None:
        self.phrase = phrase

    async def repondre(self, texte: str) -> AsyncIterator[str]:
        for mot in self.phrase.split(" "):
            yield mot + " "
            await asyncio.sleep(0)


class CerveauLent:
    async def repondre(self, texte: str) -> AsyncIterator[str]:
        for i in range(50):
            yield f"phrase numéro {i}. "
            await asyncio.sleep(0.02)


def _session(collecteur, cerveau=None, synthese=None, texte="quelle heure est-il"):
    return Session(
        envoyer_json=collecteur.envoyer_json,
        envoyer_binaire=collecteur.envoyer_binaire,
        transcription=FausseTranscription(texte),
        synthese=synthese or FausseSynthese(),
        cerveau=cerveau or CerveauFixe(),
    )


async def _tour(session, collecteur, blocs: int = 5) -> None:
    await session.sur_message(Reveil(confiance=0.9, horodatage=0.0))
    for _ in range(blocs):
        await session.sur_audio(b"\x00" * 640)
    await session.sur_message(FinEnonce(duree_ms=blocs * 20))


async def test_un_tour_complet_dit_les_deux_phrases():
    c = Collecteur()
    s = _session(c)
    await _tour(s, c)
    await s.fermer()

    dires = [m for m in c.json if isinstance(m, Dire)]
    assert [d.texte for d in dires] == ["Il est midi.", "Tu déjeunes ?"]
    assert c.premier(Transcription).texte == "quelle heure est-il"
    assert c.types()[-1] == "etat" and c.json[-1].valeur == "repos"


async def test_les_trames_audio_portent_l_identifiant_de_l_enonce():
    c = Collecteur()
    s = _session(c)
    await _tour(s, c)
    await s.fermer()

    identifiants = {decoder_audio_sortant(t)[0] for t in c.binaire}
    assert identifiants == {1}
    assert len(c.binaire) == 2 * 3  # deux phrases, trois blocs chacune


async def test_un_enonce_vide_ne_fait_pas_parler():
    c = Collecteur()
    s = _session(c, texte="   ")
    await _tour(s, c)
    await s.fermer()

    assert not [m for m in c.json if isinstance(m, Dire)]
    assert c.binaire == []
    assert c.json[-1].valeur == "repos"


async def test_l_audio_recu_hors_ecoute_est_ignore():
    c = Collecteur()
    s = _session(c)
    await s.sur_audio(b"\x00" * 640)  # aucun réveil : on est au repos
    await s.sur_message(FinEnonce(duree_ms=20))
    await s.fermer()
    assert not [m for m in c.json if isinstance(m, Dire)]


async def test_l_interruption_envoie_stop_audio_et_repasse_en_ecoute():
    c = Collecteur()
    s = _session(c, cerveau=CerveauLent(), synthese=FausseSynthese(blocs=2, lenteur=0.01))
    await _tour(s, c)
    await asyncio.sleep(0.15)

    avant = len(c.binaire)
    await s.sur_message(Interruption(horodatage=1.0))
    await asyncio.sleep(0.15)

    assert any(isinstance(m, StopAudio) for m in c.json)
    assert len(c.binaire) == avant, "plus aucune trame ne doit partir après l'interruption"
    assert [m for m in c.json if isinstance(m, Etat)][-1].valeur == "ecoute"
    await s.fermer()


async def test_un_reveil_pendant_la_parole_interrompt():
    c = Collecteur()
    s = _session(c, cerveau=CerveauLent(), synthese=FausseSynthese(blocs=2, lenteur=0.01))
    await _tour(s, c)
    await asyncio.sleep(0.15)

    await s.sur_message(Reveil(confiance=0.9, horodatage=2.0))
    await asyncio.sleep(0.05)
    assert any(isinstance(m, StopAudio) for m in c.json)
    await s.fermer()


async def test_deux_tours_incrementent_l_identifiant():
    c = Collecteur()
    s = _session(c)
    await _tour(s, c)
    await _tour(s, c)
    await s.fermer()
    assert {decoder_audio_sortant(t)[0] for t in c.binaire} == {1, 2}
```

- [ ] **Étape 2 : Lancer les tests pour vérifier qu'ils échouent**

Run: `uv run pytest tests/test_session.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'helios_core.session'`

- [ ] **Étape 3 : Écrire la session**

```python
# src/helios_core/session.py
"""Orchestration d'un tour de parole, pour une connexion cliente.

Une Session par client audio. Elle ne connaît ni le réseau ni le transport :
elle reçoit des messages décodés et appelle deux fonctions d'envoi. C'est ce qui
la rend testable sans WebSocket.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable

from .cerveau import Cerveau
from .etat import MachineEtat
from .phrases import DecoupeurPhrases
from .protocole import (
    Dire, Erreur, Etat, FinEnonce, Interruption, MessageClient, MessageCore,
    Reveil, StopAudio, Transcription, encoder_audio_sortant,
)

_journal = logging.getLogger(__name__)

EnvoyerJson = Callable[[MessageCore], Awaitable[None]]
EnvoyerBinaire = Callable[[bytes], Awaitable[None]]


class Session:
    def __init__(
        self,
        envoyer_json: EnvoyerJson,
        envoyer_binaire: EnvoyerBinaire,
        transcription,
        synthese,
        cerveau: Cerveau,
    ) -> None:
        self._envoyer_json = envoyer_json
        self._envoyer_binaire = envoyer_binaire
        self._transcription = transcription
        self._synthese = synthese
        self._cerveau = cerveau
        self._machine = MachineEtat()
        self._tampon: list[bytes] = []
        self._tache: asyncio.Task | None = None
        self._id_enonce = 0

    # --- entrées ---------------------------------------------------------

    async def sur_message(self, msg: MessageClient) -> None:
        if isinstance(msg, Reveil):
            await self._reveiller()
        elif isinstance(msg, FinEnonce):
            await self._fin_enonce()
        elif isinstance(msg, Interruption):
            await self._interrompre()

    async def sur_audio(self, pcm: bytes) -> None:
        if self._machine.valeur == "ecoute":
            self._tampon.append(pcm)

    async def fermer(self) -> None:
        await self._annuler_tache()

    # --- transitions -----------------------------------------------------

    async def _reveiller(self) -> None:
        if self._machine.valeur in ("parole", "reflexion"):
            await self._interrompre()
        if self._machine.valeur == "repos":
            self._machine.aller_vers("ecoute")
        self._tampon.clear()
        await self._etat("ecoute")

    async def _fin_enonce(self) -> None:
        if self._machine.valeur != "ecoute":
            return
        self._machine.aller_vers("reflexion")
        await self._etat("reflexion")
        self._tache = asyncio.create_task(self._tour())

    async def _interrompre(self) -> None:
        await self._annuler_tache()
        await self._envoyer_json(StopAudio(id_enonce=self._id_enonce))
        if self._machine.valeur == "parole":
            self._machine.aller_vers("ecoute")
            self._tampon.clear()
            await self._etat("ecoute")
        elif self._machine.valeur == "reflexion":
            self._machine.aller_vers("repos")
            await self._etat("repos")

    async def _annuler_tache(self) -> None:
        if self._tache and not self._tache.done():
            self._tache.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._tache
        self._tache = None

    # --- le tour lui-même ------------------------------------------------

    async def _tour(self) -> None:
        try:
            pcm = b"".join(self._tampon)
            self._tampon.clear()

            texte = await self._transcription.transcrire(pcm)
            await self._envoyer_json(Transcription(texte=texte, finale=True))

            if not texte.strip():
                self._machine.aller_vers("repos")
                await self._etat("repos")
                return

            self._machine.aller_vers("parole")
            await self._etat("parole")
            self._id_enonce += 1
            identifiant = self._id_enonce

            decoupeur = DecoupeurPhrases()
            rang = 0
            async for fragment in self._cerveau.repondre(texte):
                for phrase in decoupeur.ajouter(fragment):
                    rang += 1
                    await self._dire(identifiant, rang, phrase)
            for phrase in decoupeur.vider():
                rang += 1
                await self._dire(identifiant, rang, phrase)

            self._machine.aller_vers("repos")
            await self._etat("repos")
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 — on ne laisse jamais mourir la session
            _journal.exception("échec du tour de parole")
            await self._envoyer_json(
                Erreur(code="tour", message=f"Je n'ai pas pu répondre : {e}")
            )
            if self._machine.peut_aller_vers("repos"):
                self._machine.aller_vers("repos")
                await self._etat("repos")

    async def _dire(self, identifiant: int, rang: int, phrase: str) -> None:
        await self._envoyer_json(Dire(id_enonce=identifiant, rang=rang, texte=phrase))
        async for bloc in self._synthese.synthetiser(phrase):
            await self._envoyer_binaire(encoder_audio_sortant(identifiant, bloc))

    async def _etat(self, valeur) -> None:
        await self._envoyer_json(Etat(valeur=valeur))
```

- [ ] **Étape 4 : Lancer les tests pour vérifier qu'ils passent**

Run: `uv run pytest tests/test_session.py -v`
Expected: PASS, 7 tests.

- [ ] **Étape 5 : Commit**

```bash
git add src/helios_core/session.py tests/test_session.py
git commit -m "Ajoute l'orchestration d'un tour de parole et l'interruption"
```

---

### Tâche 9 : Hub WebSocket

**Files:**
- Create: `src/helios_core/hub.py`
- Test: `tests/test_hub.py`

**Interfaces:**
- Consumes: `Session` (tâche 8), `Config` et les deux clients (tâche 6),
  `CerveauBouchon` (tâche 7), le protocole (tâche 2).
- Produces: l'application FastAPI `app`, la route `GET /sante` et la WebSocket
  `/ws/audio`. Point d'entrée de `make run-core`.
  Expose aussi `creer_session(envoyer_json, envoyer_binaire) -> Session`, qu'on
  remplace dans les tests.

- [ ] **Étape 1 : Écrire les tests qui échouent**

```python
# tests/test_hub.py
import json

from fastapi.testclient import TestClient

from helios_core import hub
from helios_core.protocole import Bonjour, TAILLE_BLOC_OCTETS, encoder_audio_entrant


class SessionEspionne:
    def __init__(self, envoyer_json, envoyer_binaire) -> None:
        self.envoyer_json = envoyer_json
        self.messages: list = []
        self.audio: list[bytes] = []

    async def sur_message(self, msg) -> None:
        self.messages.append(msg)

    async def sur_audio(self, pcm: bytes) -> None:
        self.audio.append(pcm)

    async def fermer(self) -> None:
        pass


def test_la_route_de_sante_repond():
    with TestClient(hub.app) as client:
        r = client.get("/sante")
        assert r.status_code == 200 and r.json()["ok"] is True


def test_un_bonjour_arrive_jusqu_a_la_session(monkeypatch):
    espionnes: list[SessionEspionne] = []

    def fabrique(envoyer_json, envoyer_binaire):
        s = SessionEspionne(envoyer_json, envoyer_binaire)
        espionnes.append(s)
        return s

    monkeypatch.setattr(hub, "creer_session", fabrique)
    with TestClient(hub.app) as client, client.websocket_connect("/ws/audio") as ws:
        ws.send_text(Bonjour(client="test").model_dump_json())
        ws.send_bytes(encoder_audio_entrant(b"\x00" * TAILLE_BLOC_OCTETS))
        ws.close()

    assert isinstance(espionnes[0].messages[0], Bonjour)
    assert espionnes[0].audio == [b"\x00" * TAILLE_BLOC_OCTETS]


def test_un_message_invalide_renvoie_une_erreur_sans_couper(monkeypatch):
    monkeypatch.setattr(hub, "creer_session", SessionEspionne)
    with TestClient(hub.app) as client, client.websocket_connect("/ws/audio") as ws:
        ws.send_text('{"type":"nimporte_quoi"}')
        recu = json.loads(ws.receive_text())
        assert recu["type"] == "erreur"
        assert recu["code"] == "message_invalide"
        ws.close()
```

Le troisième test compte : un client qui envoie une bêtise ne doit pas faire tomber la
connexion, sinon la moindre incompatibilité de version rend Helios muet.

- [ ] **Étape 2 : Lancer les tests pour vérifier qu'ils échouent**

Run: `uv run pytest tests/test_hub.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'helios_core.hub'`

- [ ] **Étape 3 : Écrire le hub**

```python
# src/helios_core/hub.py
"""Serveur du Core : route de santé et WebSocket audio."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from .cerveau import CerveauBouchon
from .config import Config
from .protocole import Erreur, decoder_audio_entrant, decoder_message
from .session import Session
from .synthese import ClientSynthese
from .transcription import ClientTranscription

_journal = logging.getLogger(__name__)
_config = Config.depuis_environnement()
_http: httpx.AsyncClient | None = None


@asynccontextmanager
async def _cycle_de_vie(app: FastAPI):
    global _http
    _http = httpx.AsyncClient()
    try:
        yield
    finally:
        await _http.aclose()
        _http = None


app = FastAPI(title="helios-core", lifespan=_cycle_de_vie)


def creer_session(envoyer_json, envoyer_binaire) -> Session:
    assert _http is not None, "le cycle de vie de l'application n'a pas démarré"
    return Session(
        envoyer_json=envoyer_json,
        envoyer_binaire=envoyer_binaire,
        transcription=ClientTranscription(_config.stt_url, _http),
        synthese=ClientSynthese(_config.tts_url, _config.tts_voix, _http),
        cerveau=CerveauBouchon(),
    )


@app.get("/sante")
async def sante() -> dict:
    return {"ok": True, "stt": _config.stt_url, "tts": _config.tts_url}


@app.websocket("/ws/audio")
async def ws_audio(ws: WebSocket) -> None:
    await ws.accept()

    async def envoyer_json(msg) -> None:
        await ws.send_text(msg.model_dump_json())

    async def envoyer_binaire(trame: bytes) -> None:
        await ws.send_bytes(trame)

    session = creer_session(envoyer_json, envoyer_binaire)
    try:
        while True:
            recu = await ws.receive()
            if recu["type"] == "websocket.disconnect":
                break
            if (texte := recu.get("text")) is not None:
                try:
                    await session.sur_message(decoder_message(texte))
                except ValueError as e:
                    await envoyer_json(
                        Erreur(code="message_invalide", message=str(e))
                    )
            elif (binaire := recu.get("bytes")) is not None:
                try:
                    await session.sur_audio(decoder_audio_entrant(binaire))
                except ValueError as e:
                    await envoyer_json(Erreur(code="trame_invalide", message=str(e)))
    except WebSocketDisconnect:
        pass
    finally:
        await session.fermer()
```

- [ ] **Étape 4 : Lancer toute la suite**

Run: `uv run pytest -v`
Expected: PASS, tous les tests des tâches 1 à 9.

- [ ] **Étape 5 : Vérifier le Core en vrai, sans client audio**

```bash
make run-core &
curl -s http://127.0.0.1:8080/sante
```
Expected: `{"ok":true,"stt":"http://unraid.local:9010","tts":"http://unraid.local:9011"}`

- [ ] **Étape 6 : Commit**

```bash
git add src/helios_core/hub.py tests/test_hub.py
git commit -m "Ajoute le hub WebSocket du Core"
```

---

### Tâche 10 : Entrée/sortie audio du M5, avec annulation d'écho

**Files:**
- Create: `src/helios_aec/Package.swift`, `src/helios_aec/Sources/helios-aec/main.swift`
- Create: `src/helios_audio/aec.py`
- Test: `tests/test_aec_protocole.py`

**Interfaces:**
- Consumes: le verdict du spike S2.
- Produces: le protocole `PeripheriqueAudio`, avec deux implémentations :
  ```python
  class PeripheriqueAudio(Protocol):
      async def lire_bloc(self) -> bytes        # 640 octets capturés
      async def jouer(self, pcm: bytes) -> None # 640 octets à sortir
      async def vider(self) -> None             # jette la lecture en attente
      async def fermer(self) -> None
  ```
  `PeripheriqueAec` (binaire Swift, si S2 a conclu `aec_systeme`) et
  `PeripheriqueSounddevice` (repli casque). Le choix se fait par la variable
  `HELIOS_AUDIO_PERIPHERIQUE` (`aec` ou `sounddevice`).
  Plus le codec du tube : `trame_lecture(pcm) -> bytes`, `trame_vidage() -> bytes`.

**Pourquoi un binaire séparé.** L'annulation d'écho d'Apple n'agit que si le **même**
moteur audio possède la capture *et* la lecture — c'est ainsi qu'il connaît le signal à
soustraire. Python n'a pas accès à cette API, donc le binaire Swift possède les deux bouts
et Python le pilote par des tubes.

- [ ] **Étape 1 : Écrire le test du codec du tube**

```python
# tests/test_aec_protocole.py
import struct

import pytest

from helios_audio.aec import TAILLE_BLOC, trame_lecture, trame_vidage


def test_une_trame_de_lecture_porte_son_bloc():
    pcm = b"\x01\x02" * 320
    trame = trame_lecture(pcm)
    assert trame[0] == 0x01
    assert struct.unpack(">I", trame[1:5])[0] == TAILLE_BLOC
    assert trame[5:] == pcm


def test_une_trame_de_vidage_est_vide():
    trame = trame_vidage()
    assert trame[0] == 0x02
    assert struct.unpack(">I", trame[1:5])[0] == 0
    assert len(trame) == 5


def test_un_bloc_de_mauvaise_taille_est_refuse():
    with pytest.raises(ValueError):
        trame_lecture(b"\x00" * 100)
```

- [ ] **Étape 2 : Lancer le test pour vérifier qu'il échoue**

Run: `uv run pytest tests/test_aec_protocole.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'helios_audio.aec'`

- [ ] **Étape 3 : Écrire le binaire Swift**

```swift
// src/helios_aec/Package.swift
// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "helios-aec",
    platforms: [.macOS(.v14)],
    targets: [.executableTarget(name: "helios-aec")]
)
```

```swift
// src/helios_aec/Sources/helios-aec/main.swift
//
// Capture et lecture audio avec le Voice Processing d'Apple.
// stdin  : [0x01][taille:4 BE][pcm]  joue le bloc
//          [0x02][0:4]               vide la file de lecture (barge-in)
// stdout : flux continu de PCM 16 kHz mono s16le capturé, écho retiré.

import AVFoundation
import Foundation

let frequence = 16000.0
let tailleBloc = 640

let moteur = AVAudioEngine()
let lecteur = AVAudioPlayerNode()
let fileLecture = DispatchQueue(label: "helios.lecture")

let format = AVAudioFormat(commonFormat: .pcmFormatFloat32,
                           sampleRate: frequence, channels: 1, interleaved: false)!

try moteur.inputNode.setVoiceProcessingEnabled(true)
try moteur.outputNode.setVoiceProcessingEnabled(true)
moteur.attach(lecteur)
moteur.connect(lecteur, to: moteur.mainMixerNode, format: format)

// --- capture : on écrit sur stdout au fil de l'eau ---
var tampon = Data()
moteur.inputNode.installTap(onBus: 0, bufferSize: 320,
                            format: moteur.inputNode.outputFormat(forBus: 0)) { buf, _ in
    guard let canal = buf.floatChannelData?[0] else { return }
    var pcm = Data(capacity: Int(buf.frameLength) * 2)
    for i in 0..<Int(buf.frameLength) {
        let v = Int16(max(-1.0, min(1.0, canal[i])) * 32767.0)
        withUnsafeBytes(of: v.littleEndian) { pcm.append(contentsOf: $0) }
    }
    tampon.append(pcm)
    while tampon.count >= tailleBloc {
        FileHandle.standardOutput.write(tampon.prefix(tailleBloc))
        tampon.removeFirst(tailleBloc)
    }
}

try moteur.start()
lecteur.play()

// --- commandes sur stdin ---
func lireExactement(_ n: Int) -> Data? {
    var reste = n, accu = Data()
    while reste > 0 {
        guard let bout = try? FileHandle.standardInput.read(upToCount: reste),
              !bout.isEmpty else { return nil }
        accu.append(bout); reste -= bout.count
    }
    return accu
}

func jouer(_ pcm: Data) {
    let cadre = AVAudioFrameCount(pcm.count / 2)
    guard let buf = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: cadre) else { return }
    buf.frameLength = cadre
    pcm.withUnsafeBytes { brut in
        let source = brut.bindMemory(to: Int16.self)
        for i in 0..<Int(cadre) {
            buf.floatChannelData![0][i] = Float(Int16(littleEndian: source[i])) / 32767.0
        }
    }
    lecteur.scheduleBuffer(buf, completionHandler: nil)
}

while true {
    guard let entete = lireExactement(5) else { break }
    let type = entete[entete.startIndex]
    let taille = entete.subdata(in: entete.startIndex+1..<entete.startIndex+5)
        .withUnsafeBytes { $0.load(as: UInt32.self).bigEndian }
    if type == 0x02 {
        fileLecture.sync { lecteur.stop(); lecteur.play() }   // vidage immédiat
        continue
    }
    guard let pcm = lireExactement(Int(taille)) else { break }
    jouer(pcm)
}
moteur.stop()
```

- [ ] **Étape 4 : Compiler le binaire**

```bash
cd src/helios_aec && swift build -c release
```
Expected: `.build/release/helios-aec` existe.

- [ ] **Étape 5 : Écrire le pilote Python et le repli**

```python
# src/helios_audio/aec.py
"""Accès au périphérique audio du M5.

Deux implémentations derrière le même protocole : le binaire Swift avec
annulation d'écho, et un repli sounddevice pour l'usage au casque.
"""

from __future__ import annotations

import asyncio
import os
import struct
from typing import Protocol

from helios_core.protocole import FREQUENCE_HZ as FREQUENCE
from helios_core.protocole import TAILLE_BLOC_OCTETS as TAILLE_BLOC

_TYPE_LECTURE = 0x01
_TYPE_VIDAGE = 0x02

CHEMIN_BINAIRE = os.environ.get(
    "HELIOS_AEC_BINAIRE", "src/helios_aec/.build/release/helios-aec"
)


def trame_lecture(pcm: bytes) -> bytes:
    if len(pcm) != TAILLE_BLOC:
        raise ValueError(f"bloc de {len(pcm)} octets, attendu {TAILLE_BLOC}")
    return bytes([_TYPE_LECTURE]) + struct.pack(">I", len(pcm)) + pcm


def trame_vidage() -> bytes:
    return bytes([_TYPE_VIDAGE]) + struct.pack(">I", 0)


class PeripheriqueAudio(Protocol):
    async def lire_bloc(self) -> bytes: ...
    async def jouer(self, pcm: bytes) -> None: ...
    async def vider(self) -> None: ...
    async def fermer(self) -> None: ...


class PeripheriqueAec:
    """Pilote le binaire Swift. À utiliser dès que le son sort sur des enceintes."""

    def __init__(self, chemin: str = CHEMIN_BINAIRE) -> None:
        self._chemin = chemin
        self._proc: asyncio.subprocess.Process | None = None

    async def demarrer(self) -> None:
        self._proc = await asyncio.create_subprocess_exec(
            self._chemin,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
        )

    async def lire_bloc(self) -> bytes:
        assert self._proc and self._proc.stdout
        return await self._proc.stdout.readexactly(TAILLE_BLOC)

    async def jouer(self, pcm: bytes) -> None:
        assert self._proc and self._proc.stdin
        self._proc.stdin.write(trame_lecture(pcm))
        await self._proc.stdin.drain()

    async def vider(self) -> None:
        assert self._proc and self._proc.stdin
        self._proc.stdin.write(trame_vidage())
        await self._proc.stdin.drain()

    async def fermer(self) -> None:
        if self._proc:
            self._proc.terminate()
            await self._proc.wait()
            self._proc = None


class PeripheriqueSounddevice:
    """Repli sans annulation d'écho : ne convient qu'au casque."""

    def __init__(self) -> None:
        import sounddevice as sd

        self._file_capture: asyncio.Queue[bytes] = asyncio.Queue(maxsize=100)
        self._file_lecture: asyncio.Queue[bytes] = asyncio.Queue(maxsize=200)
        self._boucle = asyncio.get_running_loop()

        def sur_entree(donnees, cadres, temps, etat) -> None:
            self._boucle.call_soon_threadsafe(
                self._file_capture.put_nowait, bytes(donnees)
            )

        def sur_sortie(sortie, cadres, temps, etat) -> None:
            try:
                sortie[:] = self._file_lecture.get_nowait()
            except asyncio.QueueEmpty:
                sortie[:] = b"\x00" * len(sortie)

        self._entree = sd.RawInputStream(
            samplerate=FREQUENCE, channels=1, dtype="int16",
            blocksize=TAILLE_BLOC // 2, callback=sur_entree,
        )
        self._sortie = sd.RawOutputStream(
            samplerate=FREQUENCE, channels=1, dtype="int16",
            blocksize=TAILLE_BLOC // 2, callback=sur_sortie,
        )
        self._entree.start()
        self._sortie.start()

    async def lire_bloc(self) -> bytes:
        return await self._file_capture.get()

    async def jouer(self, pcm: bytes) -> None:
        await self._file_lecture.put(pcm)

    async def vider(self) -> None:
        while not self._file_lecture.empty():
            self._file_lecture.get_nowait()

    async def fermer(self) -> None:
        self._entree.stop()
        self._sortie.stop()


async def ouvrir_peripherique() -> PeripheriqueAudio:
    if os.environ.get("HELIOS_AUDIO_PERIPHERIQUE", "aec") == "sounddevice":
        return PeripheriqueSounddevice()
    peripherique = PeripheriqueAec()
    await peripherique.demarrer()
    return peripherique
```

- [ ] **Étape 6 : Lancer le test pour vérifier qu'il passe**

Run: `uv run pytest tests/test_aec_protocole.py -v`
Expected: PASS, 3 tests.

- [ ] **Étape 7 : Vérifier le binaire à la main**

Jouer un WAV de test à travers le binaire et enregistrer ce qu'il capture :

```bash
ffmpeg -i /tmp/test.wav -f s16le -ar 16000 -ac 1 - \
  | python3 -c "
import sys, struct
d = sys.stdin.buffer.read()
for i in range(0, len(d)-639, 640):
    sys.stdout.buffer.write(bytes([1]) + struct.pack('>I', 640) + d[i:i+640])
" | src/helios_aec/.build/release/helios-aec > /tmp/capture.raw
```
Expected: le son sort par les enceintes, et `/tmp/capture.raw` grossit.

- [ ] **Étape 8 : Commit**

```bash
git add src/helios_aec/ src/helios_audio/aec.py tests/test_aec_protocole.py
git commit -m "Ajoute l'entrée/sortie audio du M5 avec annulation d'écho"
```

---

### Tâche 11 : Détection de voix et fin de phrase

**Files:**
- Create: `src/helios_audio/vad.py`
- Test: `tests/test_vad.py`

**Interfaces:**
- Consumes: `TAILLE_BLOC` (tâche 10).
- Produces:
  - `DetecteurVoix(seuil: float = 0.5)` avec `probabilite(bloc: bytes) -> float`
    et `parle(bloc: bytes) -> bool` — c'est `parle` que le client appelle
  - `Endpointeur(silence_ms=400, parole_min_ms=200)` avec
    `ajouter(parle: bool) -> Literal["rien", "debut", "fin"]` et `reinitialiser()`

L'endpointeur est de la logique pure : c'est lui qui décide quand David a fini de parler,
et c'est le réglage qu'on va passer le plus de temps à ajuster. Il est donc séparé du
modèle, et testé exhaustivement.

- [ ] **Étape 1 : Écrire les tests qui échouent**

```python
# tests/test_vad.py
from helios_audio.vad import Endpointeur

BLOC_MS = 20


def _jouer(e: Endpointeur, motif: list[tuple[bool, int]]) -> list[str]:
    """Joue une suite de (parle, durée_ms) et rend les événements non vides."""
    evenements = []
    for parle, duree in motif:
        for _ in range(duree // BLOC_MS):
            ev = e.ajouter(parle)
            if ev != "rien":
                evenements.append(ev)
    return evenements


def test_un_silence_continu_ne_produit_rien():
    assert _jouer(Endpointeur(), [(False, 2000)]) == []


def test_une_parole_assez_longue_produit_un_debut():
    assert _jouer(Endpointeur(), [(True, 300)]) == ["debut"]


def test_une_parole_trop_courte_est_ignoree():
    assert _jouer(Endpointeur(parole_min_ms=200), [(True, 100), (False, 1000)]) == []


def test_un_silence_apres_la_parole_produit_une_fin():
    assert _jouer(Endpointeur(), [(True, 300), (False, 500)]) == ["debut", "fin"]


def test_un_silence_trop_court_ne_coupe_pas():
    motif = [(True, 300), (False, 200), (True, 300), (False, 500)]
    assert _jouer(Endpointeur(silence_ms=400), motif) == ["debut", "fin"]


def test_deux_phrases_separees_produisent_deux_cycles():
    motif = [(True, 300), (False, 500), (True, 300), (False, 500)]
    assert _jouer(Endpointeur(), motif) == ["debut", "fin", "debut", "fin"]


def test_reinitialiser_oublie_l_etat():
    e = Endpointeur()
    _jouer(e, [(True, 300)])
    e.reinitialiser()
    assert _jouer(e, [(False, 1000)]) == []
```

- [ ] **Étape 2 : Lancer les tests pour vérifier qu'ils échouent**

Run: `uv run pytest tests/test_vad.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'helios_audio.vad'`

- [ ] **Étape 3 : Écrire le VAD et l'endpointeur**

```python
# src/helios_audio/vad.py
"""Détection de voix (Silero) et décision de fin de phrase.

Le modèle et la décision sont séparés : le premier est une boîte noire qu'on
ne teste pas, le second est de la logique pure qu'on teste exhaustivement.
"""

from __future__ import annotations

import os
from typing import Literal

import numpy as np

from .aec import TAILLE_BLOC

DUREE_BLOC_MS = 20
_FENETRE_SILERO = 512  # échantillons attendus par le modèle v5 à 16 kHz

CHEMIN_MODELE = os.environ.get("HELIOS_VAD_MODELE", "models/silero_vad.onnx")


class DetecteurVoix:
    """Enveloppe Silero. Accumule jusqu'à la fenêtre attendue par le modèle."""

    def __init__(self, seuil: float = 0.5, chemin: str = CHEMIN_MODELE) -> None:
        import onnxruntime

        self.seuil = seuil
        self._session = onnxruntime.InferenceSession(
            chemin, providers=["CPUExecutionProvider"]
        )
        self._etat = np.zeros((2, 1, 128), dtype=np.float32)
        self._reste = np.zeros(0, dtype=np.float32)
        self._derniere = 0.0

    def probabilite(self, bloc: bytes) -> float:
        echantillons = np.frombuffer(bloc, dtype="<i2").astype(np.float32) / 32768.0
        self._reste = np.concatenate([self._reste, echantillons])
        while self._reste.size >= _FENETRE_SILERO:
            fenetre = self._reste[:_FENETRE_SILERO]
            self._reste = self._reste[_FENETRE_SILERO:]
            sortie, self._etat = self._session.run(
                None,
                {
                    "input": fenetre.reshape(1, -1),
                    "state": self._etat,
                    "sr": np.array(16000, dtype=np.int64),
                },
            )
            self._derniere = float(sortie[0][0])
        return self._derniere

    def parle(self, bloc: bytes) -> bool:
        return self.probabilite(bloc) >= self.seuil


class Endpointeur:
    """Décide du début et de la fin d'un énoncé à partir d'un flux de booléens."""

    def __init__(self, silence_ms: int = 400, parole_min_ms: int = 200) -> None:
        self._blocs_silence = max(1, silence_ms // DUREE_BLOC_MS)
        self._blocs_parole_min = max(1, parole_min_ms // DUREE_BLOC_MS)
        self.reinitialiser()

    def reinitialiser(self) -> None:
        self._en_cours = False
        self._parole = 0
        self._silence = 0

    def ajouter(self, parle: bool) -> Literal["rien", "debut", "fin"]:
        if parle:
            self._silence = 0
            self._parole += 1
            if not self._en_cours and self._parole >= self._blocs_parole_min:
                self._en_cours = True
                return "debut"
            return "rien"

        if not self._en_cours:
            self._parole = 0
            return "rien"

        self._silence += 1
        if self._silence >= self._blocs_silence:
            self.reinitialiser()
            return "fin"
        return "rien"
```

- [ ] **Étape 4 : Lancer les tests pour vérifier qu'ils passent**

Run: `uv run pytest tests/test_vad.py -v`
Expected: PASS, 7 tests.

- [ ] **Étape 5 : Télécharger le modèle Silero**

```bash
mkdir -p models
curl -L -o models/silero_vad.onnx \
  https://raw.githubusercontent.com/snakers4/silero-vad/master/src/silero_vad/data/silero_vad.onnx
```

`models/` est déjà dans `.gitignore` : le modèle ne part pas dans le dépôt.

- [ ] **Étape 6 : Commit**

```bash
git add src/helios_audio/vad.py tests/test_vad.py
git commit -m "Ajoute la détection de voix et la décision de fin de phrase"
```

---

### Tâche 12 : Le client audio, du push-to-talk à l'interruption

**Files:**
- Create: `src/helios_audio/client.py`, `src/helios_audio/reveilleur.py`
- Test: `tests/test_client_audio.py`

**Interfaces:**
- Consumes: `PeripheriqueAudio` (tâche 10), `DetecteurVoix` et `Endpointeur` (tâche 11),
  le protocole (tâche 2).
- Produces:
  - Protocole `Reveilleur` avec `examiner(bloc: bytes) -> bool`
  - `ReveilleurTouche` — on appuie sur Entrée pour parler (phase 1)
  - Protocole `Transport` avec `envoyer_json`, `envoyer_binaire`, `recevoir`
  - `TransportWebSocket(url)` — l'implémentation réelle
  - `ClientAudio(transport, peripherique, detecteur, endpointeur, reveilleur)` avec
    `executer()` et `sur_message(msg)`
  - `python -m helios_audio.client` comme point d'entrée

- [ ] **Étape 1 : Écrire les tests qui échouent**

```python
# tests/test_client_audio.py
import asyncio

from helios_audio.client import ClientAudio
from helios_core.protocole import (
    Dire, Etat, FinEnonce, Interruption, Reveil, StopAudio,
    decoder_audio_entrant, encoder_audio_sortant,
)

BLOC = b"\x00" * 640


class FauxTransport:
    def __init__(self) -> None:
        self.json: list = []
        self.binaire: list[bytes] = []

    async def envoyer_json(self, msg) -> None:
        self.json.append(msg)

    async def envoyer_binaire(self, trame: bytes) -> None:
        self.binaire.append(trame)

    def types(self) -> list[str]:
        return [m.type for m in self.json]


class FauxPeripherique:
    def __init__(self, blocs: list[bytes]) -> None:
        self._blocs = list(blocs)
        self.joues: list[bytes] = []
        self.vidages = 0

    async def lire_bloc(self) -> bytes:
        if not self._blocs:
            raise asyncio.CancelledError
        return self._blocs.pop(0)

    async def jouer(self, pcm: bytes) -> None:
        self.joues.append(pcm)

    async def vider(self) -> None:
        self.vidages += 1

    async def fermer(self) -> None:
        pass


class DetecteurScript:
    """Rend les valeurs d'une liste, puis False."""

    def __init__(self, suite: list[bool]) -> None:
        self._suite = list(suite)

    def parle(self, bloc: bytes) -> bool:
        return self._suite.pop(0) if self._suite else False


class ReveilleurScript:
    def __init__(self, a_declencher_au_bloc: int | None = 0) -> None:
        self._cible = a_declencher_au_bloc
        self._n = -1

    def examiner(self, bloc: bytes) -> bool:
        self._n += 1
        return self._n == self._cible


def _client(transport, peripherique, parole: list[bool], reveil_au=0):
    from helios_audio.vad import Endpointeur

    return ClientAudio(
        transport=transport,
        peripherique=peripherique,
        detecteur=DetecteurScript(parole),
        endpointeur=Endpointeur(silence_ms=60, parole_min_ms=40),
        reveilleur=ReveilleurScript(reveil_au),
    )


async def test_le_reveil_est_annonce_puis_l_audio_part():
    t, p = FauxTransport(), FauxPeripherique([BLOC] * 6)
    c = _client(t, p, parole=[True] * 6)
    await c.boucle_capture()

    assert t.types()[0] == "reveil"
    assert len(t.binaire) == 5, "le bloc du réveil n'est pas envoyé, les suivants oui"
    assert decoder_audio_entrant(t.binaire[0]) == BLOC


async def test_le_silence_declenche_la_fin_d_enonce():
    t, p = FauxTransport(), FauxPeripherique([BLOC] * 10)
    c = _client(t, p, parole=[True] * 4 + [False] * 6)
    await c.boucle_capture()

    assert any(isinstance(m, FinEnonce) for m in t.json)


async def test_avant_le_reveil_rien_ne_part():
    t, p = FauxTransport(), FauxPeripherique([BLOC] * 4)
    c = _client(t, p, parole=[True] * 4, reveil_au=None)
    await c.boucle_capture()

    assert t.json == [] and t.binaire == []


async def test_l_audio_recu_est_joue():
    t, p = FauxTransport(), FauxPeripherique([])
    c = _client(t, p, parole=[])
    await c.sur_message(Dire(id_enonce=1, rang=1, texte="Bonjour."))
    await c.sur_trame(encoder_audio_sortant(1, BLOC))
    assert p.joues == [BLOC]


async def test_un_stop_audio_vide_le_peripherique():
    t, p = FauxTransport(), FauxPeripherique([])
    c = _client(t, p, parole=[])
    await c.sur_message(StopAudio(id_enonce=1))
    assert p.vidages == 1


async def test_une_trame_perimee_n_est_pas_jouee():
    t, p = FauxTransport(), FauxPeripherique([])
    c = _client(t, p, parole=[])
    await c.sur_message(Dire(id_enonce=2, rang=1, texte="Deux."))
    await c.sur_trame(encoder_audio_sortant(1, BLOC))  # énoncé précédent
    assert p.joues == []


async def test_parler_pendant_la_parole_declenche_l_interruption():
    t, p = FauxTransport(), FauxPeripherique([BLOC] * 6)
    c = _client(t, p, parole=[True] * 6, reveil_au=None)
    await c.sur_message(Etat(valeur="parole"))
    await c.boucle_capture()

    assert any(isinstance(m, Interruption) for m in t.json)
    assert p.vidages >= 1
```

Le dernier test est le garde-fou de tout l'édifice : sans lui, une régression sur le
barge-in ne se voit qu'à l'usage, et elle rend Helios pénible sans qu'on sache pourquoi.

- [ ] **Étape 2 : Lancer les tests pour vérifier qu'ils échouent**

Run: `uv run pytest tests/test_client_audio.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'helios_audio.client'`

- [ ] **Étape 3 : Écrire le réveilleur au clavier**

```python
# src/helios_audio/reveilleur.py
"""Ce qui décide qu'on veut parler à Helios.

En phase 1 c'est la touche Entrée : zéro faux déclenchement pendant qu'on met au
point le reste. Le wake word arrive en tâche 13, derrière le même protocole.
"""

from __future__ import annotations

import sys
import threading
from typing import Protocol


class Reveilleur(Protocol):
    def examiner(self, bloc: bytes) -> bool:
        """Rend True une seule fois, au moment où il faut se réveiller."""
        ...


class ReveilleurTouche:
    """Appuyer sur Entrée pour parler."""

    def __init__(self) -> None:
        self._arme = False
        self._verrou = threading.Lock()
        fil = threading.Thread(target=self._ecouter, daemon=True)
        fil.start()
        print("Appuie sur Entrée pour parler à Helios.", file=sys.stderr)

    def _ecouter(self) -> None:
        for _ in sys.stdin:
            with self._verrou:
                self._arme = True

    def examiner(self, bloc: bytes) -> bool:
        with self._verrou:
            if self._arme:
                self._arme = False
                return True
        return False
```

- [ ] **Étape 4 : Écrire le client**

```python
# src/helios_audio/client.py
"""Le daemon audio du M5.

Deux boucles concurrentes : l'une lit le micro et parle au Core, l'autre reçoit
du Core et joue le son. Le client ne décide de rien d'autre que du barge-in —
il le décide localement parce que 200 ms d'aller-retour réseau rendraient
l'interruption molle.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time
from typing import Protocol

from helios_core.protocole import (
    Bonjour, Dire, Etat, FinEnonce, Interruption, Reveil, StopAudio,
    decoder_audio_sortant, encoder_audio_entrant,
)

from .aec import ouvrir_peripherique
from .reveilleur import ReveilleurTouche
from .vad import DetecteurVoix, Endpointeur

_journal = logging.getLogger(__name__)

URL_CORE = os.environ.get("HELIOS_CORE_URL", "ws://127.0.0.1:8080/ws/audio")


class Transport(Protocol):
    async def envoyer_json(self, msg) -> None: ...
    async def envoyer_binaire(self, trame: bytes) -> None: ...


class ClientAudio:
    def __init__(self, transport, peripherique, detecteur, endpointeur, reveilleur) -> None:
        self._transport = transport
        self._peripherique = peripherique
        self._detecteur = detecteur
        self._endpointeur = endpointeur
        self._reveilleur = reveilleur
        self._capture = False
        self._helios_parle = False
        self._id_courant = 0
        self._bargein = Endpointeur(silence_ms=400, parole_min_ms=300)

    # --- micro vers Core --------------------------------------------------

    async def boucle_capture(self) -> None:
        with contextlib.suppress(asyncio.CancelledError, asyncio.IncompleteReadError):
            while True:
                bloc = await self._peripherique.lire_bloc()
                await self._traiter_bloc(bloc)

    async def _traiter_bloc(self, bloc: bytes) -> None:
        if self._helios_parle:
            await self._surveiller_bargein(bloc)
            return

        if not self._capture:
            if self._reveilleur.examiner(bloc):
                self._capture = True
                self._endpointeur.reinitialiser()
                await self._transport.envoyer_json(
                    Reveil(confiance=1.0, horodatage=time.time())
                )
            return

        await self._transport.envoyer_binaire(encoder_audio_entrant(bloc))
        if self._endpointeur.ajouter(self._detecteur.parle(bloc)) == "fin":
            self._capture = False
            await self._transport.envoyer_json(FinEnonce(duree_ms=0))

    async def _surveiller_bargein(self, bloc: bytes) -> None:
        if self._bargein.ajouter(self._detecteur.parle(bloc)) != "debut":
            return
        _journal.info("interruption détectée")
        self._helios_parle = False
        await self._peripherique.vider()
        await self._transport.envoyer_json(Interruption(horodatage=time.time()))
        self._capture = True
        self._endpointeur.reinitialiser()

    # --- Core vers haut-parleur -------------------------------------------

    async def sur_message(self, msg) -> None:
        if isinstance(msg, Dire):
            self._id_courant = msg.id_enonce
            self._helios_parle = True
            self._bargein.reinitialiser()
        elif isinstance(msg, StopAudio):
            self._helios_parle = False
            await self._peripherique.vider()
        elif isinstance(msg, Etat):
            if msg.valeur == "parole":
                self._helios_parle = True
                self._bargein.reinitialiser()
            elif msg.valeur in ("repos", "ecoute"):
                self._helios_parle = False

    async def sur_trame(self, trame: bytes) -> None:
        identifiant, pcm = decoder_audio_sortant(trame)
        if identifiant != self._id_courant:
            return  # trame d'un énoncé interrompu : on la jette
        await self._peripherique.jouer(pcm)


class TransportWebSocket:
    def __init__(self, ws) -> None:
        self._ws = ws

    async def envoyer_json(self, msg) -> None:
        await self._ws.send(msg.model_dump_json())

    async def envoyer_binaire(self, trame: bytes) -> None:
        await self._ws.send(trame)


async def principal() -> None:
    import json

    import websockets
    from pydantic import TypeAdapter

    from helios_core.protocole import MessageCore

    adaptateur = TypeAdapter(MessageCore)
    logging.basicConfig(level=logging.INFO)
    peripherique = await ouvrir_peripherique()

    async with websockets.connect(URL_CORE) as ws:
        transport = TransportWebSocket(ws)
        client = ClientAudio(
            transport=transport,
            peripherique=peripherique,
            detecteur=DetecteurVoix(),
            endpointeur=Endpointeur(),
            reveilleur=ReveilleurTouche(),
        )
        await transport.envoyer_json(Bonjour(client="m5", capacites=["aec", "vad"]))
        capture = asyncio.create_task(client.boucle_capture())
        try:
            async for recu in ws:
                if isinstance(recu, bytes):
                    await client.sur_trame(recu)
                else:
                    await client.sur_message(adaptateur.validate_python(json.loads(recu)))
        finally:
            capture.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await capture
            await peripherique.fermer()


if __name__ == "__main__":
    asyncio.run(principal())
```

- [ ] **Étape 5 : Lancer les tests pour vérifier qu'ils passent**

Run: `uv run pytest tests/test_client_audio.py -v`
Expected: PASS, 7 tests.

- [ ] **Étape 6 : Le premier vrai tour de parole**

C'est le moment qui compte. Les quatre services doivent tourner : `helios-stt` et
`helios-tts` sur l'Unraid, `make run-core` sur le néo (ou en local pour l'essai),
`make run-audio` sur le M5. Puis : appuyer sur Entrée, dire « quelle heure est-il »,
se taire.

Expected: Helios répond l'heure à voix haute, en français.

- [ ] **Étape 7 : Vérifier l'interruption**

Appuyer sur Entrée, poser une question dont la réponse est longue, et **parler par-dessus**
pendant qu'Helios répond.

Expected: il se tait en moins de 400 ms et se remet à écouter.

- [ ] **Étape 8 : Commit**

```bash
git add src/helios_audio/client.py src/helios_audio/reveilleur.py \
        tests/test_client_audio.py
git commit -m "Ajoute le client audio du M5 avec push-to-talk et interruption"
```

---

### Tâche 13 : Le wake word « Hey Helios »

**Files:**
- Modify: `src/helios_audio/reveilleur.py` (ajout de `ReveilleurMotCle`)
- Modify: `src/helios_audio/client.py:principal` (choix du réveilleur par l'environnement)
- Create: `scripts/entrainer_mot_reveil.md`
- Test: `tests/test_reveilleur.py`

**Interfaces:**
- Consumes: le protocole `Reveilleur` (tâche 12).
- Produces: `ReveilleurMotCle(predicteur, seuil=0.5, refractaire_ms=2000)` et la variable
  d'environnement `HELIOS_REVEILLEUR` (`touche` ou `motcle`).

**Le point qui fait rater cet entraînement.** « Hey Helios » se prononce en **français**.
Le générateur d'échantillons d'openWakeWord utilise une voix anglaise par défaut, et un
modèle entraîné sur « hey hee-lee-ohs » ne réagira jamais à « eille élios ». Les
échantillons positifs doivent être synthétisés avec des voix Piper **françaises**.

- [ ] **Étape 1 : Écrire les tests qui échouent**

```python
# tests/test_reveilleur.py
from helios_audio.reveilleur import ReveilleurMotCle

BLOC = b"\x00" * 640


class PredicteurScript:
    def __init__(self, scores: list[float]) -> None:
        self._scores = list(scores)

    def score(self, bloc: bytes) -> float:
        return self._scores.pop(0) if self._scores else 0.0


def _compter(r: ReveilleurMotCle, n: int) -> int:
    return sum(1 for _ in range(n) if r.examiner(BLOC))


def test_un_score_au_dessus_du_seuil_reveille():
    r = ReveilleurMotCle(PredicteurScript([0.9]), seuil=0.5)
    assert r.examiner(BLOC) is True


def test_un_score_sous_le_seuil_ne_reveille_pas():
    r = ReveilleurMotCle(PredicteurScript([0.3]), seuil=0.5)
    assert r.examiner(BLOC) is False


def test_la_periode_refractaire_evite_le_double_declenchement():
    # 2000 ms de refractaire = 100 blocs de 20 ms
    r = ReveilleurMotCle(PredicteurScript([0.9] * 50), seuil=0.5, refractaire_ms=2000)
    assert _compter(r, 50) == 1


def test_apres_la_periode_refractaire_il_reveille_de_nouveau():
    scores = [0.9] + [0.0] * 100 + [0.9]
    r = ReveilleurMotCle(PredicteurScript(scores), seuil=0.5, refractaire_ms=2000)
    assert _compter(r, 102) == 2
```

- [ ] **Étape 2 : Lancer les tests pour vérifier qu'ils échouent**

Run: `uv run pytest tests/test_reveilleur.py -v`
Expected: FAIL avec `ImportError: cannot import name 'ReveilleurMotCle'`

- [ ] **Étape 3 : Écrire le réveilleur par mot-clé**

Ajouter à `src/helios_audio/reveilleur.py` :

```python
import os
from typing import Protocol as _Protocol

DUREE_BLOC_MS = 20


class Predicteur(_Protocol):
    def score(self, bloc: bytes) -> float:
        """Rend la probabilité que le mot de réveil vienne d'être prononcé."""
        ...


class PredicteurOpenWakeWord:
    def __init__(self, chemin: str | None = None) -> None:
        import openwakeword
        import numpy as np

        self._np = np
        chemin = chemin or os.environ.get(
            "HELIOS_MOT_REVEIL", "models/hey_helios.onnx"
        )
        self._modele = openwakeword.Model(
            wakeword_models=[chemin], inference_framework="onnx"
        )
        self._nom = list(self._modele.models.keys())[0]

    def score(self, bloc: bytes) -> float:
        echantillons = self._np.frombuffer(bloc, dtype="<i2")
        return float(self._modele.predict(echantillons)[self._nom])


class ReveilleurMotCle:
    """Réveille sur le mot-clé, avec une période réfractaire.

    Sans réfractaire, une seule prononciation déclenche une dizaine de réveils :
    le score reste au-dessus du seuil pendant toute la durée du mot.
    """

    def __init__(
        self, predicteur: Predicteur, seuil: float = 0.5, refractaire_ms: int = 2000
    ) -> None:
        self._predicteur = predicteur
        self._seuil = seuil
        self._blocs_refractaires = refractaire_ms // DUREE_BLOC_MS
        self._attente = 0

    def examiner(self, bloc: bytes) -> bool:
        if self._attente > 0:
            self._attente -= 1
            self._predicteur.score(bloc)  # on consomme quand même le bloc
            return False
        if self._predicteur.score(bloc) >= self._seuil:
            self._attente = self._blocs_refractaires
            return True
        return False
```

Et dans `client.py`, remplacer la construction du réveilleur :

```python
    from .reveilleur import PredicteurOpenWakeWord, ReveilleurMotCle, ReveilleurTouche

    if os.environ.get("HELIOS_REVEILLEUR", "touche") == "motcle":
        reveilleur = ReveilleurMotCle(PredicteurOpenWakeWord())
    else:
        reveilleur = ReveilleurTouche()
```

- [ ] **Étape 4 : Lancer les tests pour vérifier qu'ils passent**

Run: `uv run pytest tests/test_reveilleur.py -v`
Expected: PASS, 4 tests.

- [ ] **Étape 5 : Écrire la procédure d'entraînement**

Créer `scripts/entrainer_mot_reveil.md` avec la marche à suivre, exécutée **sur l'Unraid**
pour profiter du GPU :

```bash
# 1. Outils
git clone https://github.com/dscripka/openWakeWord && cd openWakeWord
pip install -e '.[full]'
git clone https://github.com/rhasspy/piper-sample-generator

# 2. Voix FRANÇAISES pour la génération — l'étape que tout le monde rate
#    Récupérer plusieurs voix fr_FR de Piper (siwis, upmc, gilles, mls) et les
#    passer au générateur, afin que le modèle entende « eille élios » et non
#    une prononciation anglaise.

# 3. Environ 30 000 positifs « hey helios », avec variation de vitesse,
#    de hauteur et de réverbération, plus les négatifs d'usage
#    (AudioSet, FMA, et surtout des enregistrements de David qui parle
#    normalement sans dire le mot).

# 4. Entraînement, puis export ONNX vers models/hey_helios.onnx
```

- [ ] **Étape 6 : Entraîner et rapatrier le modèle**

```bash
scp unraid:/chemin/hey_helios.onnx models/hey_helios.onnx
```

- [ ] **Étape 7 : Essayer en vrai**

```bash
HELIOS_REVEILLEUR=motcle make run-audio
```
Dire « Hey Helios, quelle heure est-il ». Puis **parler normalement pendant dix minutes
sans jamais dire le mot**, et compter les faux réveils. Le réglage du seuil se fait au banc
de mesure (tâche 14), pas à l'oreille.

- [ ] **Étape 8 : Commit**

```bash
git add src/helios_audio/reveilleur.py src/helios_audio/client.py \
        scripts/entrainer_mot_reveil.md tests/test_reveilleur.py
git commit -m "Ajoute le wake word « Hey Helios »"
```

---

### Tâche 14 : Le banc de mesure

**Files:**
- Create: `bench/bench.py`, `bench/attendus.json`, `bench/LISEZMOI.md`
- Test: `tests/test_bench.py`

**Interfaces:**
- Consumes: `DetecteurVoix` et `Endpointeur` (tâche 11), `ReveilleurMotCle` (tâche 13),
  `ClientTranscription` (tâche 6).
- Produces: `make bench`, et les fonctions pures `taux_erreur_mots(attendu, obtenu)` et
  `normaliser(texte)`.

Sans ce banc, le seuil du wake word et la durée de silence se règlent à l'impression, et
chaque correction en casse une autre sans qu'on s'en aperçoive. C'est le seul moyen de
savoir si une modification améliore vraiment les choses.

- [ ] **Étape 1 : Écrire les tests des fonctions pures**

```python
# tests/test_bench.py
from bench.bench import normaliser, taux_erreur_mots


def test_normaliser_enleve_la_ponctuation_et_la_casse():
    assert normaliser("Il est Midi, non ?") == "il est midi non"


def test_normaliser_ecrase_les_espaces():
    assert normaliser("  il   est   midi  ") == "il est midi"


def test_un_texte_identique_donne_zero():
    assert taux_erreur_mots("il est midi", "Il est midi.") == 0.0


def test_un_mot_faux_sur_trois():
    assert taux_erreur_mots("il est midi", "il est minuit") == 1 / 3


def test_un_mot_manquant_compte():
    assert taux_erreur_mots("il est bien midi", "il est midi") == 1 / 4


def test_un_attendu_vide_donne_zero_si_obtenu_vide():
    assert taux_erreur_mots("", "") == 0.0
```

- [ ] **Étape 2 : Lancer les tests pour vérifier qu'ils échouent**

Run: `uv run pytest tests/test_bench.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'bench.bench'`

- [ ] **Étape 3 : Écrire le banc**

```python
# bench/bench.py
"""Banc de mesure de la chaîne audio.

Les quatre chiffres qui décident des réglages : détection du wake word,
faux positifs, erreurs de transcription, latence. Tout le reste est du ressenti.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import unicodedata
import wave
from pathlib import Path

import httpx

from helios_audio.vad import DetecteurVoix, Endpointeur
from helios_core.transcription import ClientTranscription

RACINE = Path(__file__).parent
POSITIFS = RACINE / "enregistrements" / "positifs"      # « Hey Helios » prononcé
NEGATIFS = RACINE / "enregistrements" / "negatifs"      # parole normale, sans le mot
PHRASES = RACINE / "enregistrements" / "phrases"        # énoncés à transcrire

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
                min(precedente[j] + 1, courante[j - 1] + 1,
                    precedente[j - 1] + (mot_a != mot_o))
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
    retards = []
    for chemin in sorted(PHRASES.glob("*.wav")):
        e = Endpointeur(silence_ms=silence_ms)
        for n, bloc in enumerate(_blocs(chemin)):
            if e.ajouter(detecteur.parle(bloc)) == "fin":
                retards.append(n * 20)
                break
    return {"silence_ms": silence_ms, "retard_median_ms": sorted(retards)[len(retards) // 2]
            if retards else 0}


async def mesurer_transcription() -> dict:
    attendus = json.loads((RACINE / "attendus.json").read_text(encoding="utf-8"))
    taux, latences = [], []
    async with httpx.AsyncClient() as http:
        import os

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
```

- [ ] **Étape 4 : Lancer les tests pour vérifier qu'ils passent**

Run: `uv run pytest tests/test_bench.py -v`
Expected: PASS, 6 tests.

- [ ] **Étape 5 : Constituer le jeu d'enregistrements**

C'est une tâche pour David, et elle ne se délègue pas : le banc ne vaut que si les
enregistrements sont les siens, dans ses conditions réelles.

- `bench/enregistrements/positifs/` — **30 prises de « Hey Helios »** : au micro, à un
  mètre, à trois mètres, avec de la musique de fond, en parlant vite, en parlant bas.
- `bench/enregistrements/negatifs/` — **une heure de parole normale** sans jamais
  prononcer le mot. Une réunion, un appel, une vidéo qui tourne : ce qui compte est que
  ce soit du français, dans la même pièce.
- `bench/enregistrements/phrases/` — **20 énoncés** représentatifs de ce qu'il dira
  vraiment à Helios, avec leur transcription exacte dans `attendus.json`.

Tout en WAV 16 kHz mono. `bench/audio/` est dans `.gitignore` ; le dossier
`enregistrements/` doit y être ajouté aussi — ces fichiers ne partent pas dans le dépôt.

```json
// bench/attendus.json — exemple de format
{
  "phrase01.wav": "quelle heure est-il",
  "phrase02.wav": "lance la veille concurrence",
  "phrase03.wav": "note ça dans le projet Helios"
}
```

- [ ] **Étape 6 : Lancer le banc et figer les réglages**

```bash
make bench
```

Retenir le seuil de réveil qui donne **plus de 95 % de détection avec moins d'un faux
positif par heure**, et la durée de silence dont le retard médian reste **sous 400 ms**.
Reporter ces deux valeurs dans `.env.example` et dans `bench/LISEZMOI.md`, avec la date et
les chiffres obtenus — c'est la référence contre laquelle on comparera les versions
suivantes.

- [ ] **Étape 7 : Commit**

```bash
echo "bench/enregistrements/" >> .gitignore
git add bench/bench.py bench/attendus.json bench/LISEZMOI.md \
        tests/test_bench.py .gitignore .env.example
git commit -m "Ajoute le banc de mesure de la chaîne audio"
```

---

## Ce que la phase 1 livre, et ce qu'elle ne livre pas

À la fin de la tâche 14, Helios écoute « Hey Helios », comprend le français, répond d'une
vraie voix et se tait quand on lui coupe la parole. Les chiffres du banc sont connus et
les réglages sont justifiés.

Il ne sait rien faire d'autre. Pas de mémoire, pas d'outils, pas de Claude, pas d'interface
web — le cerveau est un bouchon qui donne l'heure. **C'est voulu :** si la voix ne marche
pas, on veut le savoir sans avoir un LLM, une base vectorielle et un registre d'outils à
déboguer en même temps.

La phase 2 remplace `CerveauBouchon` par le process `claude -p` persistant, derrière le
même protocole `Cerveau`. C'est la seule chose qu'elle change dans le code existant — et
c'est la raison pour laquelle le cerveau est derrière une interface depuis la tâche 7.

---

## Couverture de la spec

Vérification section par section, pour ce que les phases 0 et 1 doivent porter.

| Section de la spec | Où elle est traitée |
|---|---|
| §5 Flux d'un tour de parole | Tâches 8 et 12 |
| §5 Interruption en pleine phrase | Tâche 8 (côté Core), tâche 12 (côté client) |
| §5 Budget de latence | Contraintes globales, mesuré en tâche 14 |
| §6.1 `helios-audio` | Tâches 10, 11, 12, 13 |
| §6.2 `helios-core` (hub, états, segmentation) | Tâches 2, 3, 7, 8, 9 |
| §6.2 Brain `claude -p`, rotation de contexte | **Phase 2** — remplace `CerveauBouchon` derrière le protocole `Cerveau` posé en tâche 7 |
| §6.3 `helios-stt` | Tâche 4 |
| §6.4 `helios-tts` | Tâche 5 |
| §6.5 `helios-web` | **Phase 4** |
| §6.6 Protocole client/Core | Tâche 2 |
| §13 Secrets et exposition réseau | Contraintes globales, tâches 1 et 4 à 6 |
| §14 Spikes S1, S2, S3 | Phase 0 |
| §16 Tests unitaires du cœur logique | Tâches 2, 3, 7, 8, 11, 13, 14 |
| §16 Mesure de la chaîne audio | Tâche 14 |
| §16 Pas d'appel à la vraie API Claude | Tâche 7 (cerveau bouchon, aucune dépendance réseau) |

**Un écart assumé.** Les messages `Confirmation` et `ReponseConfirmation` du §6.6 sont
définis en tâche 2 mais la `Session` les ignore : les permissions N1/N2/N3 arrivent en
phase 2, avec les outils. Ils sont posés dès maintenant pour que le protocole n'ait pas à
changer de version quand la phase 2 les activera — un client audio déjà déployé sur le M5
continuera de fonctionner.

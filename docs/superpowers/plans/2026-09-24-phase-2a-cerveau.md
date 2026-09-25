# Phase 2a : le cerveau branché — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Claude devient le cerveau d'Atlas, à la voix comme au clavier, dans une conversation qui se souvient ; la boucle vocale dit ses longues réponses phrase par phrase, se laisse couper à tout moment et survit à la disparition du Core ; le Core est prêt à partir sur le néo.

**Architecture:** Un seul `CerveauClaude` pour tout le Core pilote le CLI `claude` par le SDK Agent (`claude-agent-sdk`) : le client SDK démarre à la première question, une question à la fois, une réponse abandonnée est interrompue et vidée par une tâche de ménage que la question suivante attend. La session reçoit du cerveau du texte au fil des mots et un marqueur `RECHERCHE` : elle dit « Je regarde ça. », repasse en réflexion pendant la recherche, dit les erreurs du cerveau à voix haute, nettoie chaque phrase et ignore les fantômes de Whisper. Côté client audio, le barge-in reste armé entre deux phrases, la lecture est cadencée par sa propre tâche (5 s d'avance au plus) et la connexion se rétablit seule ; `/ws/audio` exige une clé.

**Tech Stack:** Python 3.12+ (la venv du dépôt est en 3.13), FastAPI/Starlette, pydantic v2, `claude-agent-sdk` ≥ 0.2.140 (0.2.159 verrouillé), websockets 17, pytest (asyncio auto) ; bash et launchd pour le néo.

**Spec:** `docs/superpowers/specs/2026-09-24-phase-2a-cerveau-design.md` (à lire avec ce plan : elle fait foi en cas de doute).

## Global Constraints

- Code, identifiants, messages et commentaires en français, comme le reste du dépôt ; lignes de 100 caractères au plus (ruff).
- Une seule nouvelle dépendance : `claude-agent-sdk>=0.2.140`, dans les dépendances `core`. Aucune autre.
- Claude enfermé dans son rôle : `tools=["WebSearch"]`, `allowed_tools=["WebSearch"]`, `setting_sources=[]`, `mcp_servers={}`, `strict_mcp_config=True`, `include_partial_messages=True`, `system_prompt=CONSIGNES`, un dossier de travail vide qui lui est réservé (`~/.atlas/cerveau`), `env={"CLAUDE_CODE_SKIP_PROMPT_HISTORY": "1"}`. Jamais `WebFetch`, jamais d'autre outil.
- L'abonnement, jamais une clé d'API : les variables `ANTHROPIC_*` sont retirées de l'environnement du Core avant de lancer Claude ; `CLAUDE_CODE_OAUTH_TOKEN` est transmis.
- Réglages : `ATLAS_CERVEAU` (`claude` ou `bouchon`, `claude` par défaut), `ATLAS_CERVEAU_MODELE` (`claude-sonnet-5` par défaut), `ATLAS_CERVEAU_OUBLI_MIN` (30), `ATLAS_AUDIO_CLE`.
- `/ws/audio` : le premier message est un `Bonjour` portant `cle`, reçu dans les 5 s, comparé en temps constant ; sinon fermeture `4401`. Sans clé configurée : message `cle_absente` puis fermeture `4000`. Tout en-tête `Origin` : fermeture `1008` avant acceptation.
- Phrases dites : 250 caractères au plus. Phrase d'attente : « Je regarde ça. ». Après une conversation perdue : « Je reprends de zéro, j'ai perdu le fil. ». Messages d'erreur : ceux du §6.4 de la spec, mot pour mot (constantes de `cerveau_claude.py`, Task 5).
- Ligne de date devant chaque question : `[jeudi 24 septembre 2026, 21 h 50]` (jour, « 1er » pour le premier du mois, mois, année, heure, minutes sur deux chiffres).
- Client audio : 5 s d'avance au plus confiées au haut-parleur ; reconnexion après 1, 2, 4, 8, 16 puis 30 s.
- Jamais d'appel au vrai Claude dans `make test` : les tests passent par une doublure du client SDK. Le script `scripts/essai_cerveau.py` (Task 11) consomme l'abonnement de David : **aucun exécutant ne le lance**, seul David le fait (section finale).
- Ne jamais lancer ce qui ouvre le micro (`make run-audio`, `scripts/mot_reveil/enregistrer.py`, `veiller.py`) ni le binaire Swift : c'est David qui le fait.
- Dépôt public : aucune adresse IP, aucun domaine, nom ou courriel privé, aucun jeton dans ce qui est commité. `.env` n'est jamais commité ; le jeton `CLAUDE_CODE_OAUTH_TOKEN` ne va que dans le `.env` du néo.
- Git : ajouter les fichiers par leur chemin, jamais `git add -A` (le dossier `spikes/` n'est pas suivi et reste privé). Messages de commit en français, terminés par la ligne `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Avant chaque commit : `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .`, `node --test "tests/web/*.test.mjs"`. Si `ruff format --check` échoue, lancer `uv run ruff format <fichiers>` : la mise en forme fait foi.
- Fichiers de moins de 500 lignes, sauf `src/atlas_core/session.py`, qui passe à 516 (décision 12 ci-dessous).
- Le code de ce plan a été vérifié tel quel avant d'être écrit ici : appliquées dans l'ordre, les 11 tâches donnent 564 tests Python (et 3 ignorés, comme aujourd'hui) et 72 tests JavaScript qui passent, un lint propre, et chaque tâche laisse la suite entière au vert. Les tests ont en outre été mis à l'épreuve par mutations : chaque comportement clé, retiré du code, fait échouer au moins un test. Un écart entre le plan et ce que vous observez est donc à signaler, pas à contourner.

## Décisions prises en écrivant le plan

La spec fait foi ; voici ce qu'elle laissait ouvert et ce que le plan en a fait.

1. **Le barge-in s'arme sur `Dire`, pas sur l'état « parole ».** Le client reste à l'affût tant qu'un `Dire` est arrivé et qu'aucun état autre que « parole » ne l'a suivi. Une réponse muette (aucun `Dire`) n'arme donc rien : parler dans la pièce pendant qu'on lit une réponse écrite ne la coupe pas. La réflexion d'une recherche désarme aussi : « Hey Atlas » reprend alors la main (spec §4.3).
2. **Le ménage d'une réponse abandonnée tourne en tâche de fond.** Fermer le flux du cerveau rend la main tout de suite (la session coupe la voix sans attendre) ; `interrupt()` et la lecture jusqu'au message de fin se font dans une tâche que la question suivante attend (15 s au plus, sinon conversation neuve et « Je reprends de zéro… »).
3. **Une question qui arrive d'une autre session interrompt la réponse en cours**, qui se termine alors sans erreur, écourtée.
4. **Les erreurs du cerveau sont dites** comme une dernière phrase et affichées en rouge (`Erreur(code="cerveau")`), après ce que Claude avait déjà commencé à dire. Les autres pannes (synthèse, transcription) restent traitées comme aujourd'hui.
5. **La connexion du client audio vit dans `src/atlas_audio/connexion.py`**, pour garder `client.py` sous 500 lignes ; `python -m atlas_audio.client` (et `make run-audio`) ne change pas.
6. **Un `ClientAudio` neuf à chaque connexion** : la nouvelle session du Core numérote ses énoncés à partir de 1, que les repères de l'ancien client jetteraient.
7. **Une clé refusée (4401, 4000) ne remet pas l'attente de reconnexion à zéro**, pour ne pas marteler le Core toutes les secondes.
8. **Le service du néo est un LaunchDaemon avec `UserName`** (il démarre avec la machine, sans session ouverte), installé par un script qui a aussi un mode `--apercu`.
9. **Le dossier de travail de Claude est `~/.atlas/cerveau`**, créé à la première question seulement.
10. **`cli_path=shutil.which("claude")`** : le CLI installé ; à défaut (PATH réduit), celui que le SDK embarque, qui lit la même connexion.
11. **Le 24 septembre 2026 est un jeudi** : la spec donnait « mercredi » dans son exemple de ligne de date ; le plan écrit « jeudi » et corrige la spec (Task 11).
12. **`session.py` passe à 516 lignes.** La spec le modifie sans le découper ; en extraire « la parole d'une réponse » est laissé au backlog. Coût si c'est un tort : un découpage plus tard, sans changement de comportement.
13. **Découpeur :** une série mêlée (« ?! ») se traite comme « ... » (coupe seulement devant une majuscule) ; « 1. » en début de ligne numérote une liste et ne coupe pas.
14. **`CLAUDE_CODE_OAUTH_TOKEN` est commenté dans `.env.example`** : exporté vide par `make` sur le M5, il pourrait masquer la connexion du trousseau.
15. **Le SDK s'utilise d'une tâche à l'autre.** Sa version 0.2.159 lit les messages dans des tâches détachées (plus de groupe de tâches lié à la tâche qui s'est connectée) ; l'avertissement contraire de sa documentation date d'avant. L'essai réel (Task 11) pose chaque question depuis sa propre tâche pour le vérifier.
16. **L'essai réel vérifie aussi qu'aucune transcription n'est écrite** sur le disque par le CLI (spec §7), dans un dossier de travail temporaire.

## Carte des fichiers

| Fichier | Tâche | Rôle |
|---|---|---|
| `pyproject.toml`, `uv.lock` | 1 | `claude-agent-sdk>=0.2.140` dans `core` |
| `src/atlas_core/config.py`, `.env.example` | 1 | `cerveau`, `cerveau_modele`, `cerveau_oubli_min`, `audio_cle` |
| `src/atlas_core/phrases.py` | 2 | Découpeur au fil des mots, plafond de 250 caractères |
| `src/atlas_core/mise_en_voix.py` | 3 | `nettoyer`, `est_hallucination` |
| `src/atlas_core/consignes.py` | 4 | `CONSIGNES`, `ligne_de_date` |
| `src/atlas_core/cerveau.py` | 5 | `Recherche`, `RECHERCHE`, `ErreurCerveau`, `Cerveau.fermer` |
| `src/atlas_core/cerveau_claude.py` | 5 | `CerveauClaude`, `options_cerveau`, `purger_cles_api` |
| `src/atlas_core/etat.py`, `src/atlas_core/session.py` | 6 | Parole → réflexion ; phrase d'attente, erreurs dites, mise en voix, fantômes |
| `src/atlas_core/protocole.py`, `src/atlas_core/hub.py` | 7 | `Bonjour.cle` ; un seul cerveau ; clé de `/ws/audio` |
| `src/atlas_audio/client.py` | 8, 9 | Barge-in entre deux phrases, `Interruption` d'abord, clé ; lecture cadencée, `principal` qui se reconnecte |
| `src/atlas_audio/connexion.py` | 9 | `servir_connexion`, `boucle_de_connexion` |
| `scripts/neo/LISEZMOI.md`, `fr.atlas.core.plist`, `installer_service.sh` | 10 | Déploiement du Core sur le néo |
| `scripts/essai_cerveau.py`, specs | 11 | Essai réel (lancé par David) ; spec parente et spec 2a amendées |
| `tests/test_config.py`, `test_phrases.py`, `test_mise_en_voix.py`, `test_consignes.py`, `test_cerveau.py`, `test_cerveau_claude.py`, `test_etat.py`, `test_session_cerveau.py`, `test_protocole.py`, `test_hub.py`, `test_hub_web.py`, `test_client_parole.py`, `test_client_audio.py`, `test_client_connexion.py`, `test_neo.py` | 1–10 | Tests |

---

### Task 1: La dépendance au SDK et les réglages du cerveau

**Files:**
- Modify: `pyproject.toml`, `uv.lock` (par `uv add`)
- Replace: `src/atlas_core/config.py` (contenu complet ci-dessous)
- Modify: `.env.example` (fin du fichier)
- Replace: `tests/test_config.py` (contenu complet ci-dessous)

**Interfaces:**
- Consumes: rien de neuf.
- Produces: `Config` gagne quatre champs avec valeurs par défaut : `cerveau: str = "claude"`, `cerveau_modele: str = "claude-sonnet-5"`, `cerveau_oubli_min: float = 30.0`, `audio_cle: str = ""`, lus par `Config.depuis_environnement()` dans `ATLAS_CERVEAU`, `ATLAS_CERVEAU_MODELE`, `ATLAS_CERVEAU_OUBLI_MIN`, `ATLAS_AUDIO_CLE`. Constantes `CERVEAUX = ("claude", "bouchon")` et `MODELE_PAR_DEFAUT`. Une valeur invalide lève `ValueError` dont le message nomme la variable. Le paquet `claude_agent_sdk` devient importable.

- [ ] **Step 1: Ajouter la dépendance**

```bash
uv add --optional core "claude-agent-sdk>=0.2.140"
make install
```

`uv add` réécrit la liste `core` de `pyproject.toml` sur plusieurs lignes et ajoute le SDK à `uv.lock` (0.2.159 au moment d'écrire ce plan ; une version plus récente résolue par `uv` convient, le test de la ligne de commande de la Task 5 dira si l'intérieur du SDK a changé). Le résultat attendu dans `pyproject.toml` :

```diff
@@ -10,7 +10,12 @@ dependencies = ["pydantic>=2.9", "httpx>=0.27"]
 environments = ["sys_platform == 'darwin'"]
 
 [project.optional-dependencies]
-core  = ["fastapi>=0.115", "uvicorn[standard]>=0.32", "websockets>=13"]
+core  = [
+    "claude-agent-sdk>=0.2.140",
+    "fastapi>=0.115",
+    "uvicorn[standard]>=0.32",
+    "websockets>=13",
+]
 audio = ["sounddevice>=0.5", "numpy>=2.1", "onnxruntime>=1.20", "openwakeword>=0.6"]
 # Avertissement anyio 4.15.1 sur BlockingPortal (v max publiée); httpx2 élimine StarletteDeprecationWarning.
 dev   = ["pytest>=8.3", "pytest-asyncio>=0.24", "ruff>=0.7", "numpy>=2.1", "soxr>=0.5", "soundfile>=0.12", "httpx2", "starlette>=1.6", "anyio>=4.15"]
```

Vérifier : `uv run python -c "import claude_agent_sdk; print(claude_agent_sdk.__version__)"` affiche une version ≥ 0.2.140.

- [ ] **Step 2: Écrire les tests qui échouent**

Remplacer tout `tests/test_config.py` par :

```python
import pytest

from atlas_core.config import Config


def test_la_cle_web_vient_de_l_environnement(monkeypatch):
    monkeypatch.setenv("ATLAS_WEB_CLE", "  cle-secrete  ")
    assert Config.depuis_environnement().web_cle == "cle-secrete"


def test_sans_cle_web_la_valeur_est_vide(monkeypatch):
    monkeypatch.delenv("ATLAS_WEB_CLE", raising=False)
    assert Config.depuis_environnement().web_cle == ""


def test_les_reglages_du_cerveau_ont_des_valeurs_par_defaut(monkeypatch):
    for nom in ("ATLAS_CERVEAU", "ATLAS_CERVEAU_MODELE", "ATLAS_CERVEAU_OUBLI_MIN"):
        monkeypatch.delenv(nom, raising=False)
    config = Config.depuis_environnement()
    assert config.cerveau == "claude"
    assert config.cerveau_modele == "claude-sonnet-5"
    assert config.cerveau_oubli_min == 30.0


def test_les_reglages_du_cerveau_viennent_de_l_environnement(monkeypatch):
    monkeypatch.setenv("ATLAS_CERVEAU", " Bouchon ")
    monkeypatch.setenv("ATLAS_CERVEAU_MODELE", "claude-opus-5-5")
    monkeypatch.setenv("ATLAS_CERVEAU_OUBLI_MIN", "12.5")
    config = Config.depuis_environnement()
    assert config.cerveau == "bouchon"
    assert config.cerveau_modele == "claude-opus-5-5"
    assert config.cerveau_oubli_min == 12.5


def test_un_modele_vide_reprend_le_modele_par_defaut(monkeypatch):
    monkeypatch.setenv("ATLAS_CERVEAU_MODELE", "  ")
    assert Config.depuis_environnement().cerveau_modele == "claude-sonnet-5"


def test_un_cerveau_inconnu_est_refuse(monkeypatch):
    monkeypatch.setenv("ATLAS_CERVEAU", "gpt")
    with pytest.raises(ValueError, match="ATLAS_CERVEAU"):
        Config.depuis_environnement()


@pytest.mark.parametrize("brute", ["pas-un-nombre", "0", "-5", "nan", "inf"])
def test_un_delai_d_oubli_invalide_est_refuse(monkeypatch, brute):
    monkeypatch.setenv("ATLAS_CERVEAU_OUBLI_MIN", brute)
    with pytest.raises(ValueError, match="ATLAS_CERVEAU_OUBLI_MIN"):
        Config.depuis_environnement()


def test_la_cle_audio_vient_de_l_environnement(monkeypatch):
    monkeypatch.setenv("ATLAS_AUDIO_CLE", "  cle-audio  ")
    assert Config.depuis_environnement().audio_cle == "cle-audio"


def test_sans_cle_audio_la_valeur_est_vide(monkeypatch):
    monkeypatch.delenv("ATLAS_AUDIO_CLE", raising=False)
    assert Config.depuis_environnement().audio_cle == ""
```

- [ ] **Step 3: Vérifier qu'ils échouent**

Run: `uv run pytest tests/test_config.py -q`
Expected: FAIL — 11 échecs, 2 réussites (`AttributeError: 'Config' object has no attribute 'cerveau'`, et `DID NOT RAISE` pour les valeurs invalides).

- [ ] **Step 4: Écrire la configuration**

Remplacer tout `src/atlas_core/config.py` par :

```python
"""Configuration lue dans l'environnement.

Des adresses, des réglages, et les clés d'accès des pages web et du client audio :
jamais écrites dans le code, elles ne viennent que du .env du Core.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass

CERVEAUX = ("claude", "bouchon")
MODELE_PAR_DEFAUT = "claude-sonnet-5"


@dataclass(frozen=True)
class Config:
    stt_url: str
    tts_url: str
    tts_voix: str  # vide : le service TTS prend la voix par défaut de son moteur
    port_core: int
    web_cle: str  # vide : la page web reste fermée
    cerveau: str = "claude"  # « claude », ou « bouchon » pour faire tourner Atlas sans Claude
    cerveau_modele: str = MODELE_PAR_DEFAUT
    cerveau_oubli_min: float = 30.0  # au-delà, sans échange, la conversation repart de zéro
    audio_cle: str = ""  # vide : /ws/audio refuse tout client audio

    @staticmethod
    def depuis_environnement() -> Config:
        return Config(
            stt_url=os.environ.get("ATLAS_STT_URL", "http://unraid.local:9010"),
            tts_url=os.environ.get("ATLAS_TTS_URL", "http://unraid.local:9011"),
            tts_voix=os.environ.get("ATLAS_TTS_VOIX", ""),
            port_core=int(os.environ.get("ATLAS_CORE_PORT", "8080")),
            web_cle=os.environ.get("ATLAS_WEB_CLE", "").strip(),
            cerveau=_lire_cerveau(),
            cerveau_modele=os.environ.get("ATLAS_CERVEAU_MODELE", "").strip() or MODELE_PAR_DEFAUT,
            cerveau_oubli_min=_lire_oubli_min(),
            audio_cle=os.environ.get("ATLAS_AUDIO_CLE", "").strip(),
        )


def _lire_cerveau() -> str:
    brute = os.environ.get("ATLAS_CERVEAU", "claude")
    valeur = brute.strip().lower()
    if valeur not in CERVEAUX:
        raise ValueError(f"ATLAS_CERVEAU invalide : {brute!r} (claude ou bouchon)")
    return valeur


def _lire_oubli_min() -> float:
    brute = os.environ.get("ATLAS_CERVEAU_OUBLI_MIN", "30")
    try:
        valeur = float(brute)
    except ValueError as erreur:
        raise ValueError(
            f"ATLAS_CERVEAU_OUBLI_MIN invalide : {brute!r} n'est pas un nombre"
        ) from erreur
    if not math.isfinite(valeur) or valeur <= 0:
        raise ValueError(
            f"ATLAS_CERVEAU_OUBLI_MIN invalide : {brute!r} doit être un nombre de minutes positif"
        )
    return valeur
```

Puis, à la fin de `.env.example` :

Remplacer :

```text
ATLAS_WEB_CLE=
```

par :

```text
ATLAS_WEB_CLE=

# Le cerveau d'Atlas. « claude » : Claude, par le SDK Agent et le CLI claude connecté à
# l'abonnement. « bouchon » : les réponses figées de la phase 1, pour faire tourner Atlas
# sans Claude.
ATLAS_CERVEAU=claude
# Modèle de Claude. Vide : claude-sonnet-5.
ATLAS_CERVEAU_MODELE=claude-sonnet-5
# Au-delà de ce nombre de minutes sans échange, la question suivante ouvre une
# conversation neuve.
ATLAS_CERVEAU_OUBLI_MIN=30
# Sur le néo seulement (voir scripts/neo/LISEZMOI.md) : le jeton d'abonnement que donne
# « claude setup-token », à décommenter là-bas. C'est un secret : la vraie valeur ne va
# que dans le .env du néo, jamais dans ce fichier.
# CLAUDE_CODE_OAUTH_TOKEN=

# Clé du client audio : la même dans le .env du Core et dans celui du client audio.
# Vide côté Core : /ws/audio refuse tout client. À générer avec :
# python3 -c "import secrets; print(secrets.token_urlsafe(24))"
ATLAS_AUDIO_CLE=
```

- [ ] **Step 5: Vérifier que tout passe**

Run: `uv run pytest tests/test_config.py -q && uv run pytest -q && uv run ruff check . && uv run ruff format --check . && node --test "tests/web/*.test.mjs"`
Expected: 13 tests de configuration passent ; toute la suite passe (421 tests, 3 ignorés) ; ruff ne dit rien.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock src/atlas_core/config.py tests/test_config.py .env.example
git commit -F - <<'MSG'
Ajoute le SDK Agent de Claude et les réglages du cerveau

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

### Task 2: Le découpeur de phrases, au fil des mots

**Files:**
- Replace: `src/atlas_core/phrases.py` (contenu complet ci-dessous)
- Replace: `tests/test_phrases.py` (contenu complet ci-dessous)

**Interfaces:**
- Consumes: rien.
- Produces: `LIMITE = 250` ; `DecoupeurPhrases(limite: int = LIMITE)` avec `ajouter(fragment: str) -> list[str]` et `vider() -> list[str]` (mêmes noms qu'avant). Changement de comportement : une ponctuation finale qui termine le texte reçu ne coupe plus (on attend le caractère suivant, sauf dans `vider`) ; jamais de coupe entre deux chiffres ; « 1. » en début de ligne ne coupe pas ; une phrase de plus de `limite` caractères est coupée sur la dernière virgule, le dernier point-virgule ou deux-points suivis d'une espace, sinon sur le dernier espace, sinon net à la limite. Les cerveaux existants (bouchon, doublures des tests de session) rendent des mots suivis d'une espace : leurs tests passent sans changement.

- [ ] **Step 1: Écrire les tests qui échouent**

Remplacer tout `tests/test_phrases.py` par (les deux premiers tests d'avant changent : « Bonjour David. » ne sort plus avant le caractère suivant) :

```python
"""Tests pour le découpage en phrases françaises."""

import pytest

from atlas_core.phrases import LIMITE, DecoupeurPhrases


def _mot_par_mot(texte: str) -> list[str]:
    """Nourrit le découpeur comme le fait Claude : un mot (et son espace) à la fois."""
    d = DecoupeurPhrases()
    sorties: list[str] = []
    for mot in texte.split(" "):
        sorties.extend(d.ajouter(mot + " "))
    sorties.extend(d.vider())
    return sorties


def test_une_phrase_complete_sort_des_que_le_caractere_suivant_arrive():
    d = DecoupeurPhrases()
    assert d.ajouter("Bonjour David.") == [], "« David. » pourrait encore devenir « David.fr »"
    assert d.ajouter(" ") == ["Bonjour David."]


def test_une_phrase_incomplete_est_retenue():
    d = DecoupeurPhrases()
    assert d.ajouter("Bonjour ") == []
    assert d.ajouter("David. ") == ["Bonjour David."]


def test_vider_rend_la_derniere_phrase_ponctuee():
    d = DecoupeurPhrases()
    assert d.ajouter("Bonjour David.") == []
    assert d.vider() == ["Bonjour David."]


def test_deux_phrases_dans_un_fragment():
    d = DecoupeurPhrases()
    assert d.ajouter("Il est midi. Tu déjeunes ? ") == ["Il est midi.", "Tu déjeunes ?"]


def test_une_abreviation_ne_coupe_pas():
    d = DecoupeurPhrases()
    assert d.ajouter("M. Durand est arrivé. ") == ["M. Durand est arrivé."]


def test_une_decimale_ne_coupe_pas():
    d = DecoupeurPhrases()
    assert d.ajouter("Il fait 3.5 degrés dehors. ") == ["Il fait 3.5 degrés dehors."]


def test_un_nombre_coupe_en_deux_fragments_reste_entier():
    d = DecoupeurPhrases()
    assert d.ajouter("Ça coûte 3.") == []
    assert d.ajouter("5 euros. ") == ["Ça coûte 3.5 euros."]


def test_une_abreviation_coupee_en_deux_fragments_ne_coupe_pas():
    d = DecoupeurPhrases()
    assert d.ajouter("Demande à M.") == []
    assert d.ajouter(" Dupont. ") == ["Demande à M. Dupont."]


def test_un_nom_de_site_ne_coupe_pas():
    d = DecoupeurPhrases()
    assert d.ajouter("Selon meteo.") == []
    assert d.ajouter("fr il pleut. ") == ["Selon meteo.fr il pleut."]


def test_les_points_de_suspension_ne_coupent_pas_trois_fois():
    d = DecoupeurPhrases()
    assert d.ajouter("Attends... je réfléchis. ") == ["Attends... je réfléchis."]


def test_des_points_de_suspension_en_fin_de_texte_attendent_la_suite():
    d = DecoupeurPhrases()
    assert d.ajouter("Attends... ") == []
    assert d.ajouter("Voilà. ") == ["Attends...", "Voilà."]


def test_le_caractere_points_de_suspension_est_une_serie():
    d = DecoupeurPhrases()
    assert d.ajouter("Bon… je vois. Oui… Et toi ? ") == ["Bon… je vois.", "Oui…", "Et toi ?"]


def test_un_numero_de_liste_ne_coupe_pas():
    d = DecoupeurPhrases()
    phrases = d.ajouter("Deux idées :\n1. Aller au parc.\n2. Lire un livre.\n")
    assert phrases == ["Deux idées :\n1. Aller au parc.", "2. Lire un livre."]


def test_une_annee_en_fin_de_phrase_coupe():
    d = DecoupeurPhrases()
    assert d.ajouter("C'était en 2026. Puis ") == ["C'était en 2026."]


def test_le_flux_caractere_par_caractere_donne_le_meme_resultat():
    d = DecoupeurPhrases()
    sorties = []
    for c in "Il est midi. Tu déjeunes ?":
        sorties.extend(d.ajouter(c))
    sorties.extend(d.vider())
    assert sorties == ["Il est midi.", "Tu déjeunes ?"]


def test_le_flux_mot_par_mot_garde_nombres_et_abreviations():
    texte = "Il fait 3.5 degrés. M. Dupont dit 3,5. Pas mal !"
    assert _mot_par_mot(texte) == ["Il fait 3.5 degrés.", "M. Dupont dit 3,5.", "Pas mal !"]


def test_vider_rend_une_phrase_sans_ponctuation_finale():
    d = DecoupeurPhrases()
    d.ajouter("Bon, on verra")
    assert d.vider() == ["Bon, on verra"]


def test_vider_deux_fois_ne_repete_rien():
    d = DecoupeurPhrases()
    d.ajouter("Bon")
    assert d.vider() == ["Bon"]
    assert d.vider() == []


def test_une_phrase_trop_longue_est_coupee_sur_la_derniere_virgule():
    d = DecoupeurPhrases()
    phrases = d.ajouter("a" * 200 + ", puis " + "b" * 30 + ", enfin " + "c" * 30 + " fin. ")
    assert phrases == ["a" * 200 + ", puis " + "b" * 30 + ",", "enfin " + "c" * 30 + " fin."]


def test_une_phrase_trop_longue_sans_virgule_est_coupee_sur_un_espace():
    d = DecoupeurPhrases()
    phrases = d.ajouter("mot " * 80)  # 320 caractères, aucune ponctuation
    assert phrases == [" ".join(["mot"] * 62)], "au-delà de la limite, on n'attend plus"
    assert len(phrases[0]) <= LIMITE


def test_la_coupe_forcee_ne_separe_pas_les_chiffres_d_une_decimale():
    texte = "x" * 240 + " 3,5 " + "y" * 20
    d = DecoupeurPhrases()
    phrases = d.ajouter(texte)
    assert phrases == ["x" * 240 + " 3,5"]


def test_un_mot_sans_espace_plus_long_que_la_limite_est_coupe_net():
    d = DecoupeurPhrases()
    assert d.ajouter("z" * (LIMITE + 10)) == ["z" * LIMITE]
    assert d.vider() == ["z" * 10]


@pytest.mark.parametrize("longueur", [LIMITE - 1, LIMITE])
def test_une_phrase_a_la_limite_n_est_pas_coupee(longueur):
    phrase = "a" * (longueur - 1) + "."
    d = DecoupeurPhrases()
    assert d.ajouter(phrase + " ") == [phrase]
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `uv run pytest tests/test_phrases.py -q`
Expected: FAIL — `ImportError: cannot import name 'LIMITE' from 'atlas_core.phrases'`.

- [ ] **Step 3: Écrire le découpeur**

Remplacer tout `src/atlas_core/phrases.py` par :

```python
"""Découpage d'un flux de texte français en phrases prononçables.

Le cerveau écrit au fil des mots ; on veut envoyer chaque phrase au TTS dès qu'elle
est complète, sans couper au milieu d'une abréviation ou d'un nombre. Une ponctuation
qui termine le texte reçu ne suffit pas : « 3. » peut devenir « 3.5 », « M. » devenir
« M. Dupont ». On attend donc le caractère suivant, sauf quand le flux est fini
(`vider`). Une phrase trop longue est coupée avant la limite : le premier son arrive
plus vite, et la synthèse n'est jamais débordée.
"""

from __future__ import annotations

import re

_FINS = ".!?…"
LIMITE = 250  # caractères au plus par phrase envoyée au TTS (qui en accepte 1 000)

# Abréviations françaises courantes après lesquelles un point ne finit pas la phrase.
_ABREVIATIONS = {
    "m",
    "mm",
    "mme",
    "mlle",
    "dr",
    "pr",
    "st",
    "ste",
    "av",
    "bd",
    "cf",
    "ex",
    "etc",
    "env",
    "art",
    "fig",
    "p",
    "pp",
    "vol",
    "no",
    "n°",
}

_MOT_FINAL = re.compile(r"([A-Za-zÀ-ÿ°]+)\.$")
# Une coupe douce, pour une phrase trop longue : virgule, point-virgule ou deux-points
# suivis d'une espace (« 3,5 » n'en est pas une).
_COUPE_DOUCE = re.compile(r"[,;:](?=\s)")
_ESPACE = re.compile(r"\s")


class DecoupeurPhrases:
    """Accumule du texte et rend les phrases au fur et à mesure."""

    def __init__(self, limite: int = LIMITE) -> None:
        self._tampon = ""
        self._limite = limite

    def ajouter(self, fragment: str) -> list[str]:
        """Ajoute un fragment et rend les phrases devenues complètes."""
        self._tampon += fragment
        return self._extraire(final=False)

    def vider(self) -> list[str]:
        """Rend ce qui reste en fin de génération."""
        phrases = self._extraire(final=True)
        reste = self._tampon.strip()
        self._tampon = ""
        if reste:
            phrases.append(reste)
        return phrases

    def _extraire(self, final: bool) -> list[str]:
        phrases: list[str] = []
        while (coupe := self._trouver_coupe(final)) is not None:
            phrase = self._tampon[:coupe].strip()
            self._tampon = self._tampon[coupe:].lstrip()
            if phrase:
                phrases.append(phrase)
        return phrases

    def _trouver_coupe(self, final: bool) -> int | None:
        fin = self._fin_de_phrase(final)
        if fin is not None and fin <= self._limite:
            return fin
        if fin is not None or len(self._tampon) > self._limite:
            return self._coupe_forcee()
        return None

    def _fin_de_phrase(self, final: bool) -> int | None:
        """Position juste après la première ponctuation finale, ou None.

        Une boucle indexée saute d'un coup les séries de ponctuation (« ... », « ?! »).
        """
        texte = self._tampon
        i, n = 0, len(texte)
        while i < n:
            c = texte[i]
            if c not in _FINS:
                i += 1
                continue
            fin = i + 1
            while fin < n and texte[fin] in _FINS:
                fin += 1
            if fin == n and not final:
                return None  # le caractère suivant peut encore tout changer : on attend
            if fin - i > 1 or c == "…":  # série : « ... », « !! », « ?! »
                suite = self._suit_une_nouvelle_phrase(fin, final)
                if suite is None:
                    return None
                if suite:
                    return fin
                i = fin
                continue
            if self._est_une_decimale(i) or self._est_une_abreviation(fin):
                i = fin
                continue
            if self._est_un_numero_de_liste(i):
                i = fin
                continue
            if fin < n and not texte[fin].isspace():
                i = fin
                continue  # ponctuation collée à la suite (« amara.org ») : pas une fin
            return fin
        return None

    def _coupe_forcee(self) -> int:
        """Coupe d'une phrase trop longue : la dernière virgule, le dernier point-virgule
        ou deux-points avant la limite, sinon le dernier espace, sinon la limite."""
        fenetre = self._tampon[: self._limite + 1]
        douces = list(_COUPE_DOUCE.finditer(fenetre))
        if douces:
            return douces[-1].end()
        espaces = [m.start() for m in _ESPACE.finditer(fenetre) if m.start() > 0]
        if espaces:
            return espaces[-1]
        return self._limite

    def _est_une_decimale(self, i: int) -> bool:
        """Le point est-il entre deux chiffres (« 3.5 ») ?"""
        avant = self._tampon[i - 1] if i > 0 else ""
        apres = self._tampon[i + 1] if i + 1 < len(self._tampon) else ""
        return avant.isdigit() and apres.isdigit()

    def _est_une_abreviation(self, fin: int) -> bool:
        """Le mot avant le point est-il une abréviation connue ?"""
        m = _MOT_FINAL.search(self._tampon[:fin])
        return bool(m) and m.group(1).lower() in _ABREVIATIONS

    def _est_un_numero_de_liste(self, i: int) -> bool:
        """« 1. » en début de ligne numérote une liste : ce n'est pas une fin de phrase."""
        debut = i
        while debut > 0 and self._tampon[debut - 1].isdigit():
            debut -= 1
        if not 1 <= i - debut <= 2:
            return False
        avant = self._tampon[:debut].rstrip(" \t")
        return avant == "" or avant.endswith("\n")

    def _suit_une_nouvelle_phrase(self, fin: int, final: bool) -> bool | None:
        """Après une série, une majuscule ouvre une nouvelle phrase. None : on ne sait
        pas encore, le texte reçu s'arrête avant."""
        reste = self._tampon[fin:]
        if reste and not reste[0].isspace():
            return False
        suite = reste.lstrip()
        if not suite:
            return True if final else None
        return suite[0].isupper()
```

- [ ] **Step 4: Vérifier que tout passe**

Run: `uv run pytest tests/test_phrases.py -q && uv run pytest -q && uv run ruff check . && uv run ruff format --check .`
Expected: 24 tests du découpeur passent ; toute la suite passe (436 tests, 3 ignorés), dont `tests/test_session.py`, `tests/test_session_web.py` et `tests/test_integration_boucle.py` sans modification.

- [ ] **Step 5: Commit**

```bash
git add src/atlas_core/phrases.py tests/test_phrases.py
git commit -F - <<'MSG'
Découpe les phrases au fil des mots, jamais au-delà de 250 caractères

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

### Task 3: La mise en voix et les fantômes de Whisper

**Files:**
- Create: `src/atlas_core/mise_en_voix.py`
- Test: `tests/test_mise_en_voix.py`

**Interfaces:**
- Consumes: rien.
- Produces: `nettoyer(texte: str) -> str` (sans astérisques, dièses de titre, puces, accents graves ; lien Markdown `[texte](adresse)` → `texte` ; toute adresse web → « un lien », sans avaler la ponctuation qui la suit ; blancs réduits à une espace ; peut rendre `""`) ; `est_hallucination(texte: str) -> bool` (vrai pour un texte vide, sans lettres, ou une phrase fantôme connue, comparée après normalisation : minuscules, apostrophes droites, ponctuation retirée).

- [ ] **Step 1: Écrire les tests qui échouent**

`tests/test_mise_en_voix.py` :

```python
import pytest

from atlas_core.mise_en_voix import est_hallucination, nettoyer


@pytest.mark.parametrize(
    ("brut", "attendu"),
    [
        ("Il fait **beau** à Paris.", "Il fait beau à Paris."),
        ("C'est *vraiment* simple.", "C'est vraiment simple."),
        ("## Le résumé\nTout va bien.", "Le résumé Tout va bien."),
        ("Deux idées :\n- aller au parc ;\n- lire.", "Deux idées : aller au parc ; lire."),
        ("Voici :\n1. Aller au parc.", "Voici : Aller au parc."),
        ("• Premier point.", "Premier point."),
        ("Tape `make test` pour voir.", "Tape make test pour voir."),
        ("Regarde https://meteo.fr/paris demain.", "Regarde un lien demain."),
        ("Va sur www.example.org pour ça.", "Va sur un lien pour ça."),
        ("Tout est sur https://x.fr.", "Tout est sur un lien."),
        (
            "D'après [Météo-France](https://meteofrance.com), il pleut.",
            "D'après Météo-France, il pleut.",
        ),
        ("Une   phrase\n\ttrop  espacée. ", "Une phrase trop espacée."),
        ("Il fait 3,5 degrés, soit -2 de moins.", "Il fait 3,5 degrés, soit -2 de moins."),
    ],
)
def test_nettoyer_rend_un_texte_prononcable(brut, attendu):
    assert nettoyer(brut) == attendu


def test_un_texte_deja_propre_ne_change_pas():
    phrase = "Bonjour David, il est midi dix. Tu déjeunes ?"
    assert nettoyer(phrase) == phrase


def test_une_phrase_faite_de_mise_en_forme_devient_vide():
    assert nettoyer("**") == ""
    assert nettoyer("- ") == ""


@pytest.mark.parametrize(
    "fantome",
    [
        "Merci.",
        " merci ! ",
        "Merci beaucoup.",
        "Sous-titres réalisés par la communauté d'Amara.org",
        "Sous-titrage ST' 501",
        "Merci d’avoir regardé cette vidéo !",
        "Abonnez-vous à la chaîne !",
        "[Musique]",
        "♪",
        "...",
        "",
    ],
)
def test_les_phrases_fantomes_de_whisper_sont_reconnues(fantome):
    assert est_hallucination(fantome)


@pytest.mark.parametrize(
    "vraie",
    [
        "Quelle heure est-il ?",
        "Merci pour la météo, et demain ?",
        "Musique classique, tu connais ?",
        "Bonjour Atlas.",
    ],
)
def test_une_vraie_question_n_est_pas_un_fantome(vraie):
    assert not est_hallucination(vraie)
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `uv run pytest tests/test_mise_en_voix.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'atlas_core.mise_en_voix'`.

- [ ] **Step 3: Écrire le module**

`src/atlas_core/mise_en_voix.py` :

```python
"""Rendre un texte prononçable, et reconnaître ce que Whisper invente.

Tout ce qu'Atlas écrit est dit à voix haute : les consignes interdisent déjà la mise en
forme, ce filtre est un filet. Et sur un bruit bref, Whisper produit parfois une phrase
fantôme (« Merci. », « Sous-titres réalisés par… ») : mieux vaut ne rien entendre que
répondre à un fantôme.
"""

from __future__ import annotations

import re

_LIEN_MARKDOWN = re.compile(r"\[([^\]]+)\]\([^)\s]*\)")
# Une adresse finit sur autre chose qu'une ponctuation : le point de la phrase reste.
_ADRESSE_WEB = re.compile(r"(?:https?://|www\.)\S*[^\s.,;:!?)»]", re.IGNORECASE)
_TITRE = re.compile(r"^[ \t]*#{1,6}[ \t]*", re.MULTILINE)
_PUCE = re.compile(r"^[ \t]*(?:[-*•+–]|\d{1,2}[.)])[ \t]+", re.MULTILINE)
_BLANCS = re.compile(r"\s+")


def nettoyer(texte: str) -> str:
    """Le texte sans mise en forme : ni astérisques, ni dièses de titre, ni puces, ni
    accents graves, et toute adresse web devient « un lien »."""
    texte = _LIEN_MARKDOWN.sub(r"\1", texte)
    texte = _ADRESSE_WEB.sub("un lien", texte)
    texte = _TITRE.sub("", texte)
    texte = _PUCE.sub("", texte)
    texte = texte.replace("*", "").replace("`", "")
    return _BLANCS.sub(" ", texte).strip()


# Phrases fantômes connues de Whisper, une fois normalisées (voir `_normaliser`).
_FANTOMES = {
    "",
    "merci",
    "merci beaucoup",
    "merci à tous",
    "merci de votre attention",
    "musique",
    "applaudissements",
    "rires",
}
_DEBUTS_FANTOMES = (
    "sous-titres réalisés par",
    "sous-titrage",
    "sous-titres par",
    "merci d'avoir regardé",
    "abonnez-vous",
    "n'oubliez pas de vous abonner",
)
_PONCTUATION = re.compile(r"[^\w\s'-]")


def _normaliser(texte: str) -> str:
    texte = texte.lower().replace("’", "'")
    texte = _PONCTUATION.sub(" ", texte)
    return _BLANCS.sub(" ", texte).strip()


def est_hallucination(texte: str) -> bool:
    """Vrai si la transcription n'est qu'une phrase fantôme de Whisper (ou rien du tout)."""
    normal = _normaliser(texte)
    return normal in _FANTOMES or normal.startswith(_DEBUTS_FANTOMES)
```

- [ ] **Step 4: Vérifier que tout passe**

Run: `uv run pytest tests/test_mise_en_voix.py -q && uv run pytest -q && uv run ruff check . && uv run ruff format --check .`
Expected: 30 tests passent ; toute la suite passe (466 tests, 3 ignorés).

- [ ] **Step 5: Commit**

```bash
git add src/atlas_core/mise_en_voix.py tests/test_mise_en_voix.py
git commit -F - <<'MSG'
Rend les phrases prononçables et reconnaît les fantômes de Whisper

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

### Task 4: Les consignes d'Atlas et la ligne de date

**Files:**
- Create: `src/atlas_core/consignes.py`
- Test: `tests/test_consignes.py`

**Interfaces:**
- Consumes: rien.
- Produces: `CONSIGNES: str` (l'invite système, spec §6.1) ; `ligne_de_date(maintenant: datetime.datetime) -> str`, par exemple `"[jeudi 24 septembre 2026, 21 h 50]"`.

- [ ] **Step 1: Écrire les tests qui échouent**

`tests/test_consignes.py` :

```python
import datetime as dt

import pytest

from atlas_core.consignes import CONSIGNES, ligne_de_date


@pytest.mark.parametrize(
    ("moment", "attendu"),
    [
        (dt.datetime(2026, 9, 24, 21, 50), "[jeudi 24 septembre 2026, 21 h 50]"),
        (dt.datetime(2026, 6, 1, 9, 5), "[lundi 1er juin 2026, 9 h 05]"),
        (dt.datetime(2027, 2, 14, 0, 0), "[dimanche 14 février 2027, 0 h 00]"),
        (dt.datetime(2026, 8, 15, 12, 30), "[samedi 15 août 2026, 12 h 30]"),
    ],
)
def test_la_ligne_de_date_est_en_francais(moment, attendu):
    assert ligne_de_date(moment) == attendu


def test_les_consignes_tiennent_les_decisions_de_la_spec():
    texte = CONSIGNES.lower()
    for attendu in (
        "atlas",
        "david",
        "tutoies",
        "voix haute",
        "deux à quatre phrases",
        "cite le site par son nom",
        "ne prétends jamais",
    ):
        assert attendu in texte, attendu


def test_les_consignes_ne_revelent_rien_de_prive():
    for interdit in ("@", "http", "192.168"):
        assert interdit not in CONSIGNES.lower(), interdit
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `uv run pytest tests/test_consignes.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'atlas_core.consignes'`.

- [ ] **Step 3: Écrire le module**

`src/atlas_core/consignes.py` :

```python
"""Les consignes d'Atlas (l'invite système de Claude) et la ligne de date.

Claude ne sait pas l'heure qu'il est : chaque question part précédée d'une ligne de
contexte, « [jeudi 24 septembre 2026, 21 h 50] ».
"""

from __future__ import annotations

import datetime as dt

CONSIGNES = """\
Tu es Atlas, l'assistant vocal de David. Tu parles français et tu tutoies David.

Tout ce que tu écris est lu à voix haute par une synthèse vocale. Écris donc seulement \
des phrases simples, comme on parle : ni listes, ni titres, ni gras, ni tableaux, ni \
code, ni émojis, ni adresses web. Écris les nombres, les heures et les dates en toutes \
lettres, comme tu les dirais.

Réponds en deux à quatre phrases, la conclusion d'abord. Si le sujet mérite plus, \
propose d'aller plus loin plutôt que de tout dire d'un coup.

Chaque question commence par une ligne entre crochets qui donne la date et l'heure du \
moment. Sers-t'en quand on te les demande ou quand elles comptent, sans en parler sinon.

La question vient d'une transcription de la voix de David : si elle semble coupée ou \
n'a pas de sens, demande-lui de répéter plutôt que de deviner.

Tu peux chercher sur le web, quand la question porte sur l'actualité, la météo, des \
horaires ou un fait dont tu n'es pas sûr. N'annonce pas ta recherche : Atlas prévient \
David pour toi. Quand tu t'appuies sur une page, cite le site par son nom, par exemple \
« d'après Météo-France », jamais par son adresse.

Tu ne peux rien faire d'autre que réfléchir et chercher sur le web. Ne prétends jamais \
avoir fait une action, comme envoyer un message, régler un minuteur ou allumer une \
lumière : si on te le demande, dis simplement que tu ne sais pas encore le faire. Si tu \
ne sais pas quelque chose, dis-le.
"""

_JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
_MOIS = (
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
)


def ligne_de_date(maintenant: dt.datetime) -> str:
    """« [jeudi 24 septembre 2026, 21 h 50] », « [lundi 1er juin 2026, 9 h 05] »."""
    jour = "1er" if maintenant.day == 1 else str(maintenant.day)
    return (
        f"[{_JOURS[maintenant.weekday()]} {jour} {_MOIS[maintenant.month - 1]} "
        f"{maintenant.year}, {maintenant.hour} h {maintenant.minute:02d}]"
    )
```

- [ ] **Step 4: Vérifier que tout passe**

Run: `uv run pytest tests/test_consignes.py -q && uv run pytest -q && uv run ruff check . && uv run ruff format --check .`
Expected: 6 tests passent ; toute la suite passe (472 tests, 3 ignorés).

- [ ] **Step 5: Commit**

```bash
git add src/atlas_core/consignes.py tests/test_consignes.py
git commit -F - <<'MSG'
Écrit les consignes d'Atlas et la ligne de date

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

### Task 5: Le cerveau Claude

**Files:**
- Modify: `src/atlas_core/cerveau.py` (l'interface : marqueur de recherche, erreur, `fermer`)
- Create: `src/atlas_core/cerveau_claude.py`
- Modify: `tests/test_cerveau.py` (un test ajouté à la fin)
- Test: `tests/test_cerveau_claude.py` (nouveau)

**Interfaces:**
- Consumes: `CONSIGNES`, `ligne_de_date` (Task 4) ; du SDK : `ClaudeAgentOptions`, `ClaudeSDKError`, `CLIConnectionError`, `CLINotFoundError`, `AssistantMessage`, `RateLimitEvent`, `ResultMessage`, `StreamEvent`, `TextBlock`, `ToolUseBlock`.
- Produces, dans `atlas_core.cerveau` : `Recherche` (dataclass figée, sans champ) et l'instance `RECHERCHE` ; `ErreurCerveau(Exception)` dont le message est une phrase française prête à être dite ; le protocole `Cerveau` avec `repondre(texte: str) -> AsyncIterator[str | Recherche]` et `async fermer() -> None` ; `CerveauBouchon.fermer()` (ne fait rien).
- Produces, dans `atlas_core.cerveau_claude` : constantes `OUTIL_RECHERCHE = "WebSearch"`, `DELAI_MENAGE_S = 15.0`, `PHRASE_FIL_PERDU`, `ABSENT`, `DECONNECTE`, `LIMITE`, `INJOIGNABLE`, `ARRET` ; `options_cerveau(modele: str, dossier: Path) -> ClaudeAgentOptions` ; `purger_cles_api(environnement: MutableMapping[str, str]) -> list[str]` (retire les `ANTHROPIC_*`, rend leurs noms triés) ; le protocole `ClientClaude` (`connect()`, `query(prompt)`, `receive_response()`, `interrupt()`, `disconnect()`, que `ClaudeSDKClient` satisfait) ; `CerveauClaude(fabrique: Callable[[], ClientClaude], oubli_s: float = 1800, horloge: Callable[[], float] = time.monotonic, maintenant: Callable[[], datetime] = datetime.now)` avec `repondre(texte)` (générateur asynchrone : texte au fil des mots, `RECHERCHE` à chaque nouvel appel `WebSearch`, `ErreurCerveau` en cas d'échec ; le fermer avant la fin abandonne la réponse) et `async fermer()`. L'attribut `_fabrique` est lu par un test du hub (Task 7).

- [ ] **Step 1: Écrire les tests qui échouent**

À la fin de `tests/test_cerveau.py` :

Remplacer :

```python
    assert len(fragments) > 1, "le cerveau doit streamer, sinon on ne teste pas le découpage"
```

par :

```python
    assert len(fragments) > 1, "le cerveau doit streamer, sinon on ne teste pas le découpage"


async def test_le_bouchon_se_ferme_sans_rien_faire():
    await CerveauBouchon().fermer()
```

Puis `tests/test_cerveau_claude.py` (la doublure `FauxClientClaude` rejoue un tour de messages du SDK par question ; `BLOQUE` y fait attendre jusqu'à une interruption) :

```python
"""Le cerveau Claude, sans appeler Claude : une doublure du client SDK rejoue des
messages réalistes (deltas de texte, appel à la recherche web, message de fin, erreurs)."""

import asyncio
import contextlib
import dataclasses
import datetime as dt

import pytest
from claude_agent_sdk import (
    AssistantMessage,
    CLIConnectionError,
    CLINotFoundError,
    ProcessError,
    RateLimitEvent,
    ResultMessage,
    StreamEvent,
    TextBlock,
    ToolUseBlock,
)
from claude_agent_sdk.types import RateLimitInfo

from atlas_core import cerveau_claude
from atlas_core.cerveau import RECHERCHE, ErreurCerveau
from atlas_core.cerveau_claude import (
    ABSENT,
    ARRET,
    DECONNECTE,
    INJOIGNABLE,
    LIMITE,
    PHRASE_FIL_PERDU,
    CerveauClaude,
    options_cerveau,
    purger_cles_api,
)
from atlas_core.consignes import CONSIGNES

MOMENT = dt.datetime(2026, 9, 24, 21, 50)

# --- messages du SDK --------------------------------------------------------


def _evenement(event: dict, parent: str | None = None) -> StreamEvent:
    return StreamEvent(uuid="u", session_id="s", event=event, parent_tool_use_id=parent)


def debut_texte() -> StreamEvent:
    return _evenement({"type": "content_block_start", "content_block": {"type": "text"}})


def delta(texte: str, parent: str | None = None) -> StreamEvent:
    return _evenement(
        {"type": "content_block_delta", "delta": {"type": "text_delta", "text": texte}}, parent
    )


def debut_recherche(identifiant: str = "t1") -> StreamEvent:
    bloc = {"type": "tool_use", "name": "WebSearch", "id": identifiant, "input": {}}
    return _evenement({"type": "content_block_start", "content_block": bloc})


def appel_recherche(identifiant: str = "t1") -> AssistantMessage:
    bloc = ToolUseBlock(id=identifiant, name="WebSearch", input={"query": "météo"})
    return AssistantMessage(content=[bloc], model="claude-sonnet-5")


def erreur_assistant(code: str, texte: str = "API Error") -> AssistantMessage:
    return AssistantMessage(content=[TextBlock(text=texte)], model="claude-sonnet-5", error=code)


def limite(statut: str) -> RateLimitEvent:
    return RateLimitEvent(rate_limit_info=RateLimitInfo(status=statut), uuid="u", session_id="s")


def fin(**champs) -> ResultMessage:
    valeurs = dict(
        subtype="success",
        duration_ms=1,
        duration_api_ms=1,
        is_error=False,
        num_turns=1,
        session_id="s",
    )
    valeurs.update(champs)
    return ResultMessage(**valeurs)


def reponse(*morceaux: str) -> list:
    return [debut_texte(), *(delta(m) for m in morceaux), fin()]


BLOQUE = object()  # Claude réfléchit encore : plus rien n'arrive avant une interruption


# --- la doublure du client SDK -------------------------------------------------


class FauxClientClaude:
    """Rejoue un tour de messages par question posée."""

    def __init__(self, *tours: list, journal: list | None = None) -> None:
        self.tours = list(tours)
        self.questions: list[str] = []
        self.journal = journal if journal is not None else []
        self.connexions = 0
        self.interruptions = 0
        self.deconnexions = 0
        self.echec_connexion: BaseException | None = None
        self.echec_question: BaseException | None = None
        self.interruption_sans_effet = False
        self._tour: list = []
        self._reveil = asyncio.Event()

    async def connect(self) -> None:
        if self.echec_connexion is not None:
            raise self.echec_connexion
        self.connexions += 1
        self.journal.append("connexion")

    async def query(self, prompt: str) -> None:
        if self.echec_question is not None:
            raise self.echec_question
        self.questions.append(prompt)
        self.journal.append("question")
        self._tour = list(self.tours.pop(0))
        self._reveil = asyncio.Event()

    async def receive_response(self):
        while self._tour:
            message = self._tour.pop(0)
            if message is BLOQUE:
                await self._reveil.wait()
                continue
            if isinstance(message, BaseException):
                raise message
            yield message
            if isinstance(message, ResultMessage):
                return
            await asyncio.sleep(0)

    async def interrupt(self) -> None:
        self.interruptions += 1
        self.journal.append("interruption")
        if self.interruption_sans_effet:
            return
        if self._tour:
            # Comme le CLI : le tour s'arrête, et son message de fin arrive quand même.
            self._tour = [fin(subtype="error_during_execution", is_error=True)]
        self._reveil.set()

    async def disconnect(self) -> None:
        self.deconnexions += 1
        self.journal.append("deconnexion")


class Fabrique:
    def __init__(self, *clients: FauxClientClaude) -> None:
        self.clients = list(clients)
        self.creations = 0

    def __call__(self) -> FauxClientClaude:
        self.creations += 1
        return self.clients.pop(0)


class Temps:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def _cerveau(*clients: FauxClientClaude, temps: Temps | None = None) -> CerveauClaude:
    return CerveauClaude(
        Fabrique(*clients), oubli_s=30 * 60, horloge=temps or Temps(), maintenant=lambda: MOMENT
    )


async def _tout(cerveau: CerveauClaude, texte: str) -> list:
    async def lire() -> list:
        return [f async for f in cerveau.repondre(texte)]

    # Garde-fou : un cerveau qui attend à tort échoue au lieu de bloquer la suite.
    return await asyncio.wait_for(lire(), timeout=2)


# --- le texte ----------------------------------------------------------------


async def test_le_texte_arrive_au_fil_des_mots():
    cerveau = _cerveau(FauxClientClaude(reponse("Il est ", "midi ", "dix.")))
    assert await _tout(cerveau, "Quelle heure est-il ?") == ["Il est ", "midi ", "dix."]


async def test_chaque_question_part_avec_la_ligne_de_date():
    client = FauxClientClaude(reponse("Oui."))
    await _tout(_cerveau(client), "Tu m'entends ?")
    assert client.questions == ["[jeudi 24 septembre 2026, 21 h 50]\nTu m'entends ?"]


async def test_le_client_ne_demarre_qu_a_la_premiere_question_puis_reste_allume():
    client = FauxClientClaude(reponse("Un."), reponse("Deux."))
    fabrique = Fabrique(client)
    cerveau = CerveauClaude(fabrique, maintenant=lambda: MOMENT)
    assert fabrique.creations == 0, "un Core sans Claude doit démarrer quand même"

    assert await _tout(cerveau, "un") == ["Un."]
    assert await _tout(cerveau, "deux") == ["Deux."]
    assert (fabrique.creations, client.connexions) == (1, 1)


async def test_les_evenements_d_un_sous_agent_sont_ignores():
    client = FauxClientClaude([debut_texte(), delta("caché", parent="t9"), delta("Vu."), fin()])
    assert await _tout(_cerveau(client), "q") == ["Vu."]


async def test_deux_blocs_de_texte_sont_separes_par_une_espace():
    tour = [debut_texte(), delta("Voyons."), debut_texte(), delta("D'après Météo-France."), fin()]
    fragments = await _tout(_cerveau(FauxClientClaude(tour)), "q")
    assert "".join(fragments) == "Voyons. D'après Météo-France."


# --- la recherche web ----------------------------------------------------------


async def test_une_recherche_web_est_signalee_une_seule_fois():
    tour = [debut_recherche("t1"), appel_recherche("t1"), debut_texte(), delta("Il pleut."), fin()]
    assert await _tout(_cerveau(FauxClientClaude(tour)), "Il pleut ?") == [RECHERCHE, "Il pleut."]


async def test_deux_recherches_distinctes_sont_signalees_deux_fois():
    tour = [debut_recherche("t1"), debut_recherche("t2"), debut_texte(), delta("Oui."), fin()]
    fragments = await _tout(_cerveau(FauxClientClaude(tour)), "q")
    assert fragments.count(RECHERCHE) == 2


async def test_une_recherche_vue_seulement_dans_le_message_complet_est_signalee():
    tour = [appel_recherche("t1"), debut_texte(), delta("Oui."), fin()]
    assert await _tout(_cerveau(FauxClientClaude(tour)), "q") == [RECHERCHE, "Oui."]


# --- l'interruption --------------------------------------------------------------


async def test_une_reponse_abandonnee_est_interrompue_et_videe_avant_la_suivante():
    journal: list = []
    client = FauxClientClaude(
        [debut_texte(), delta("Une très longue "), BLOQUE, delta("jamais lu"), fin()],
        reponse("Oui ?"),
        journal=journal,
    )
    cerveau = _cerveau(client)

    flux = cerveau.repondre("Raconte.")
    assert await anext(flux) == "Une très longue "
    await flux.aclose()  # la session lâche la réponse (barge-in, question tapée…)

    assert await _tout(cerveau, "Attends.") == ["Oui ?"]
    assert journal == ["connexion", "question", "interruption", "question"]


async def test_la_session_n_attend_pas_le_menage_pour_lacher_la_reponse(monkeypatch):
    monkeypatch.setattr(cerveau_claude, "DELAI_MENAGE_S", 0.05)
    client = FauxClientClaude([debut_texte(), delta("Long "), BLOQUE], reponse("Oui."))
    client.interruption_sans_effet = True  # Claude tarde à finir le tour
    cerveau = _cerveau(client)

    flux = cerveau.repondre("Raconte.")
    await anext(flux)
    await asyncio.wait_for(flux.aclose(), timeout=0.5)  # rend la main tout de suite
    await cerveau.fermer()


async def test_une_question_a_la_fois_la_nouvelle_coupe_l_ancienne():
    client = FauxClientClaude(
        [debut_texte(), delta("Première "), BLOQUE, delta("jamais"), fin()],
        reponse("Seconde."),
    )
    cerveau = _cerveau(client)
    premiere: list = []

    async def lire_la_premiere() -> None:
        async for f in cerveau.repondre("une"):
            premiere.append(f)

    tache = asyncio.create_task(lire_la_premiere())
    while not premiere:
        await asyncio.sleep(0)

    assert await _tout(cerveau, "deux") == ["Seconde."]
    await tache  # finie sans erreur : l'interruption n'est pas un échec
    assert premiere == ["Première "]
    assert client.interruptions == 1


async def test_un_menage_qui_ne_finit_pas_repart_de_zero(monkeypatch):
    monkeypatch.setattr(cerveau_claude, "DELAI_MENAGE_S", 0.05)
    bloque = FauxClientClaude([debut_texte(), delta("Long "), BLOQUE])
    bloque.interruption_sans_effet = True
    neuf = FauxClientClaude(reponse("Me revoilà."))
    cerveau = _cerveau(bloque, neuf)

    flux = cerveau.repondre("Raconte.")
    await anext(flux)
    await flux.aclose()

    assert await _tout(cerveau, "Tu es là ?") == [PHRASE_FIL_PERDU + " ", "Me revoilà."]
    assert bloque.deconnexions == 1


# --- l'oubli et le plantage -------------------------------------------------------


async def test_l_oubli_ouvre_une_conversation_neuve_sans_rien_en_dire():
    temps = Temps()
    ancien = FauxClientClaude(reponse("Un."), reponse("Deux."))
    neuf = FauxClientClaude(reponse("Trois."))
    cerveau = _cerveau(ancien, neuf, temps=temps)

    await _tout(cerveau, "un")
    temps.t += 29 * 60
    assert await _tout(cerveau, "deux") == ["Deux."], "moins de trente minutes : on se souvient"
    temps.t += 30 * 60
    assert await _tout(cerveau, "trois") == ["Trois."]
    assert ancien.deconnexions == 1


async def test_apres_un_plantage_en_pleine_reponse_la_suivante_repart_de_zero():
    mort = FauxClientClaude([debut_texte(), delta("Je "), ProcessError("exit code 1")])
    neuf = FauxClientClaude(reponse("Me revoilà."))
    cerveau = _cerveau(mort, neuf)

    with pytest.raises(ErreurCerveau):
        await _tout(cerveau, "un")
    assert await _tout(cerveau, "deux") == [PHRASE_FIL_PERDU + " ", "Me revoilà."]
    assert mort.deconnexions == 1


async def test_un_flux_qui_se_tarit_sans_message_de_fin_est_un_plantage():
    mort = FauxClientClaude([debut_texte(), delta("Je ")])
    neuf = FauxClientClaude(reponse("Me revoilà."))
    cerveau = _cerveau(mort, neuf)

    with pytest.raises(ErreurCerveau, match=ARRET):
        await _tout(cerveau, "un")
    assert (await _tout(cerveau, "deux"))[0] == PHRASE_FIL_PERDU + " "


async def test_un_processus_mort_entre_deux_questions_est_relance():
    mort = FauxClientClaude(reponse("Un."))
    neuf = FauxClientClaude(reponse("Deux."))
    cerveau = _cerveau(mort, neuf)
    await _tout(cerveau, "un")
    mort.echec_question = CLIConnectionError("ProcessTransport is not ready for writing")

    assert await _tout(cerveau, "deux") == [PHRASE_FIL_PERDU + " ", "Deux."]
    assert neuf.questions[0].endswith("\ndeux")


async def test_fermer_deconnecte_le_client():
    client = FauxClientClaude(reponse("Un."))
    cerveau = _cerveau(client)
    await _tout(cerveau, "un")
    await cerveau.fermer()
    assert client.deconnexions == 1


# --- les erreurs ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("exception", "message"),
    [
        (CLINotFoundError("Claude Code not found"), ABSENT),
        (CLIConnectionError("Failed to start Claude Code"), INJOIGNABLE),
    ],
)
async def test_un_client_qui_ne_demarre_pas_donne_une_erreur_claire(exception, message):
    client = FauxClientClaude()
    client.echec_connexion = exception
    with pytest.raises(ErreurCerveau) as erreur:
        await _tout(_cerveau(client), "q")
    assert str(erreur.value) == message


@pytest.mark.parametrize(
    ("message_sdk", "attendu"),
    [
        (erreur_assistant("authentication_failed"), DECONNECTE),
        (erreur_assistant("rate_limit"), LIMITE),
        (erreur_assistant("server_error"), INJOIGNABLE),
        (erreur_assistant("billing_error", "API Error: facturation"), "API Error: facturation"),
        (limite("rejected"), LIMITE),
        (fin(is_error=True, api_error_status=429), LIMITE),
        (fin(is_error=True, api_error_status=401), DECONNECTE),
        (fin(is_error=True, api_error_status=529), INJOIGNABLE),
        (fin(is_error=True, errors=["boum"]), "boum"),
    ],
)
async def test_les_erreurs_de_claude_sont_traduites(message_sdk, attendu):
    tour = [debut_texte(), message_sdk, fin()]
    with pytest.raises(ErreurCerveau) as erreur:
        await _tout(_cerveau(FauxClientClaude(tour, reponse("Ok."))), "q")
    assert str(erreur.value) == attendu


async def test_un_avertissement_de_limite_n_est_pas_une_erreur():
    tour = [limite("allowed_warning"), debut_texte(), delta("Oui."), fin()]
    assert await _tout(_cerveau(FauxClientClaude(tour)), "q") == ["Oui."]


async def test_apres_une_erreur_la_conversation_continue():
    client = FauxClientClaude(
        [debut_texte(), erreur_assistant("rate_limit"), fin()], reponse("Ok.")
    )
    cerveau = _cerveau(client)
    with pytest.raises(ErreurCerveau):
        await _tout(cerveau, "un")
    assert await _tout(cerveau, "deux") == ["Ok."], "une limite n'est pas un plantage"
    assert client.connexions == 1


# --- la sécurité ---------------------------------------------------------------------


def test_les_options_enferment_claude_dans_son_role(tmp_path):
    options = options_cerveau("claude-sonnet-5", tmp_path)
    assert options.tools == ["WebSearch"]
    assert options.allowed_tools == ["WebSearch"]
    assert options.setting_sources == []
    assert options.mcp_servers == {}
    assert options.strict_mcp_config is True
    assert options.include_partial_messages is True
    assert options.model == "claude-sonnet-5"
    assert options.cwd == tmp_path
    assert options.system_prompt == CONSIGNES
    assert options.env == {"CLAUDE_CODE_SKIP_PROMPT_HISTORY": "1"}


def test_la_ligne_de_commande_du_cli_porte_ces_limites(tmp_path):
    # Volontairement branché sur l'intérieur du SDK : si une mise à jour change la façon
    # dont les options deviennent des arguments, ce test doit être revu, pas supprimé.
    from claude_agent_sdk._internal.transport.subprocess_cli import SubprocessCLITransport

    options = dataclasses.replace(options_cerveau("claude-sonnet-5", tmp_path), cli_path="claude")
    commande = SubprocessCLITransport(prompt=None, options=options)._build_command()

    def valeur(drapeau: str) -> str:
        return commande[commande.index(drapeau) + 1]

    assert valeur("--tools") == "WebSearch"
    assert valeur("--allowedTools") == "WebSearch"
    assert valeur("--model") == "claude-sonnet-5"
    assert "--setting-sources=" in commande
    assert "--strict-mcp-config" in commande
    assert "--include-partial-messages" in commande
    assert "--mcp-config" not in commande
    assert "WebFetch" not in " ".join(commande)


def test_les_cles_d_api_sont_retirees_mais_pas_le_jeton_d_abonnement():
    environnement = {
        "ANTHROPIC_API_KEY": "sk-secret",
        "ANTHROPIC_BASE_URL": "https://ailleurs",
        "CLAUDE_CODE_OAUTH_TOKEN": "jeton",
        "PATH": "/usr/bin",
    }
    assert purger_cles_api(environnement) == ["ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL"]
    assert environnement == {"CLAUDE_CODE_OAUTH_TOKEN": "jeton", "PATH": "/usr/bin"}


async def test_une_question_annulee_en_attendant_le_menage_ne_l_annule_pas():
    client = FauxClientClaude([debut_texte(), delta("Long "), BLOQUE], reponse("Oui."))
    client.interruption_sans_effet = True
    cerveau = _cerveau(client)
    flux = cerveau.repondre("Raconte.")
    await anext(flux)
    await flux.aclose()
    menage = cerveau._menage

    tache = asyncio.create_task(_tout(cerveau, "Et alors ?"))
    await asyncio.sleep(0.01)
    tache.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await tache
    assert menage is not None and not menage.cancelled()
    menage.cancel()
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `uv run pytest tests/test_cerveau.py tests/test_cerveau_claude.py -q`
Expected: FAIL — `ImportError: cannot import name 'cerveau_claude' from 'atlas_core'`.

- [ ] **Step 3: Étendre l'interface du cerveau**

Dans `src/atlas_core/cerveau.py` :

1. Remplacer :

```python
"""Le cerveau de la phase 1 : des réponses figées.

Claude arrive en phase 2. Ce bouchon existe pour valider la chaîne audio seule —
si la voix ne marche pas, on veut le savoir sans avoir à déboguer un LLM en même temps.
```

par :

```python
"""L'interface du cerveau, et le cerveau de la phase 1 : des réponses figées.

Claude est branché en phase 2 (`cerveau_claude.py`). Le bouchon reste : il valide la
chaîne audio seule — si la voix ne marche pas, on veut le savoir sans avoir à déboguer
un LLM en même temps — et fait tourner Atlas sans Claude (`ATLAS_CERVEAU=bouchon`).
```

2. Remplacer :

```python
from collections.abc import AsyncIterator, Callable
```

par :

```python
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
```

3. Remplacer :

```python
class Cerveau(Protocol):
    def repondre(self, texte: str) -> AsyncIterator[str]:
        """Rend la réponse en fragments, au fil de l'eau."""
```

par :

```python
@dataclass(frozen=True)
class Recherche:
    """Dans le flux d'une réponse : le cerveau commence une recherche sur le web."""


RECHERCHE = Recherche()


class ErreurCerveau(Exception):
    """Le cerveau n'a pas pu répondre. Le message est en français, prêt à être dit."""


class Cerveau(Protocol):
    def repondre(self, texte: str) -> AsyncIterator[str | Recherche]:
        """Rend la réponse en fragments de texte, au fil de l'eau, et signale une recherche
        sur le web par `RECHERCHE`. Lève `ErreurCerveau` si la réponse est impossible.

        Fermer le flux avant la fin (`aclose`) abandonne la réponse."""
        ...

    async def fermer(self) -> None:
        """Arrêt du Core : le cerveau libère ce qu'il tient."""
```

4. Remplacer :

```python
            await asyncio.sleep(0)
```

par :

```python
            await asyncio.sleep(0)

    async def fermer(self) -> None:
        """Rien à libérer."""
```

- [ ] **Step 4: Écrire le cerveau Claude**

`src/atlas_core/cerveau_claude.py` :

```python
"""Le cerveau de la phase 2 : Claude, piloté par le SDK Agent.

Un seul `CerveauClaude` pour tout le Core : la voix et le clavier nourrissent la même
conversation. Le client SDK — et derrière lui le CLI `claude`, connecté à l'abonnement
de David — ne démarre qu'à la première question : un Core sans Claude démarre quand
même, et l'erreur ne paraît qu'au moment de répondre.

Une question à la fois. Une réponse abandonnée en route (interruption, question tapée,
réveil) laisse un tour ouvert chez Claude : une tâche de ménage l'interrompt et en vide
les derniers messages, et la question suivante attend ce ménage avant de partir. La
session, elle, n'attend rien : sa voix se tait tout de suite.
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
import logging
import shutil
import time
from collections.abc import AsyncIterator, Callable, MutableMapping
from pathlib import Path
from typing import Any, Protocol

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKError,
    CLIConnectionError,
    CLINotFoundError,
    RateLimitEvent,
    ResultMessage,
    StreamEvent,
    TextBlock,
    ToolUseBlock,
)

from .cerveau import RECHERCHE, ErreurCerveau, Recherche
from .consignes import CONSIGNES, ligne_de_date

_journal = logging.getLogger(__name__)

OUTIL_RECHERCHE = "WebSearch"  # le seul outil de Claude en 2a (pas de WebFetch : spec D3)
DELAI_MENAGE_S = 15.0
PHRASE_FIL_PERDU = "Je reprends de zéro, j'ai perdu le fil."

ABSENT = "Claude Code n'est pas installé sur cette machine."
DECONNECTE = "Claude n'est plus connecté : il faut renouveler sa connexion."
LIMITE = "J'ai atteint la limite de l'abonnement Claude pour le moment."
INJOIGNABLE = "Je n'arrive pas à joindre Claude : vérifie le réseau."
ARRET = "Claude s'est arrêté en pleine réponse."

_ERREURS_ASSISTANT = {
    "authentication_failed": DECONNECTE,
    "rate_limit": LIMITE,
    "server_error": INJOIGNABLE,
}


def options_cerveau(modele: str, dossier: Path) -> ClaudeAgentOptions:
    """Claude enfermé dans son rôle : la recherche web pour seul outil, aucun réglage ni
    `CLAUDE.md` de la machine, aucun serveur MCP, un dossier de travail vide."""
    return ClaudeAgentOptions(
        tools=[OUTIL_RECHERCHE],
        allowed_tools=[OUTIL_RECHERCHE],
        system_prompt=CONSIGNES,
        setting_sources=[],
        mcp_servers={},
        strict_mcp_config=True,
        include_partial_messages=True,
        model=modele,
        cwd=dossier,
        # Le CLI installé et connecté à l'abonnement ; sans lui (PATH réduit d'un service
        # launchd), le SDK prend le CLI qu'il embarque, qui lit la même connexion.
        cli_path=shutil.which("claude"),
        # Aucune transcription de conversation écrite sur le disque par le CLI.
        env={"CLAUDE_CODE_SKIP_PROMPT_HISTORY": "1"},
    )


def purger_cles_api(environnement: MutableMapping[str, str]) -> list[str]:
    """Retire les variables `ANTHROPIC_*` : le SDK passe tout l'environnement du Core au
    CLI, et une clé d'API y ferait payer à l'usage au lieu de l'abonnement. Rend les
    noms retirés (jamais les valeurs). `CLAUDE_CODE_OAUTH_TOKEN`, lui, reste."""
    retirees = sorted(nom for nom in environnement if nom.startswith("ANTHROPIC_"))
    for nom in retirees:
        del environnement[nom]
    return retirees


def _message_exception(e: BaseException) -> str:
    if isinstance(e, CLINotFoundError):
        return ABSENT
    if isinstance(e, CLIConnectionError):
        return INJOIGNABLE
    return str(e) or type(e).__name__


class ClientClaude(Protocol):
    """Ce que le cerveau utilise de `ClaudeSDKClient` (une doublure le remplace en test)."""

    async def connect(self) -> None: ...
    async def query(self, prompt: str) -> None: ...
    def receive_response(self) -> AsyncIterator[Any]: ...
    async def interrupt(self) -> None: ...
    async def disconnect(self) -> None: ...


class CerveauClaude:
    def __init__(
        self,
        fabrique: Callable[[], ClientClaude],
        oubli_s: float = 30 * 60,
        horloge: Callable[[], float] = time.monotonic,
        maintenant: Callable[[], dt.datetime] = dt.datetime.now,
    ) -> None:
        self._fabrique = fabrique
        self._oubli_s = oubli_s
        self._horloge = horloge
        self._maintenant = maintenant
        self._verrou = asyncio.Lock()
        self._client: ClientClaude | None = None
        self._dernier_echange: float | None = None
        self._tour_ouvert = False  # une question est partie, son message de fin pas encore lu
        self._interrompu = False  # le tour en cours a été coupé par une autre question
        self._fil_perdu = False  # la conversation a été perdue : la réponse suivante le dit
        self._menage: asyncio.Task | None = None

    async def repondre(self, texte: str) -> AsyncIterator[str | Recherche]:
        if self._verrou.locked():
            # Une question à la fois : celle-ci, d'où qu'elle vienne, coupe celle en cours.
            await self._interrompre_le_tour()
        async with self._verrou:
            await self._attendre_le_menage()
            self._interrompu = False
            question = f"{ligne_de_date(self._maintenant())}\n{texte}"
            try:
                client = await self._poser(question)
                if self._fil_perdu:
                    self._fil_perdu = False
                    yield PHRASE_FIL_PERDU + " "
                async with contextlib.aclosing(self._lire_le_tour(client)) as fragments:
                    async for fragment in fragments:
                        yield fragment
            finally:
                self._dernier_echange = self._horloge()
                if self._tour_ouvert and self._client is not None:
                    # Réponse lâchée en route (ou coupée par une erreur) : le tour doit
                    # finir chez Claude avant la question suivante, sans retenir la session.
                    self._menage = asyncio.create_task(self._vider_le_tour(self._client))

    async def fermer(self) -> None:
        menage, self._menage = self._menage, None
        if menage is not None:
            with contextlib.suppress(Exception):
                await menage
        await self._jeter_le_client()

    # --- le client SDK -------------------------------------------------------

    async def _poser(self, question: str) -> ClientClaude:
        """Envoie la question ; un processus mort depuis la dernière est relancé."""
        try:
            client = await self._client_pret()
            try:
                await self._envoyer(client, question)
            except (ClaudeSDKError, OSError) as e:
                _journal.warning("Claude ne répond plus (%s) : on le relance", type(e).__name__)
                await self._jeter_le_client()
                self._fil_perdu = True
                client = await self._client_pret()
                await self._envoyer(client, question)
        except (ClaudeSDKError, OSError) as e:
            raise ErreurCerveau(_message_exception(e)) from e
        return client

    async def _envoyer(self, client: ClientClaude, question: str) -> None:
        # Ouvert avant l'envoi : une question annulée pendant l'écriture laisse peut-être
        # un tour en route chez Claude, que le ménage doit alors refermer.
        self._tour_ouvert = True
        try:
            await client.query(question)
        except Exception:
            self._tour_ouvert = False
            raise

    async def _client_pret(self) -> ClientClaude:
        dernier = self._dernier_echange
        if dernier is not None and self._horloge() - dernier >= self._oubli_s:
            # L'oubli est voulu : la conversation repart de zéro sans rien en dire.
            _journal.info("longtemps sans échange : nouvelle conversation")
            self._fil_perdu = False
            await self._jeter_le_client()
        if self._client is None:
            client = self._fabrique()
            try:
                await client.connect()
            except BaseException:
                with contextlib.suppress(Exception):
                    await client.disconnect()
                raise
            self._client = client
        return self._client

    async def _jeter_le_client(self) -> None:
        client, self._client = self._client, None
        self._tour_ouvert = False
        if client is not None:
            with contextlib.suppress(Exception):
                await client.disconnect()

    # --- un tour de conversation ---------------------------------------------

    async def _lire_le_tour(self, client: ClientClaude) -> AsyncIterator[str | Recherche]:
        recherches: set[str] = set()
        texte_rendu = False
        separer = False
        try:
            async with contextlib.aclosing(client.receive_response()) as messages:
                async for message in messages:
                    if isinstance(message, StreamEvent):
                        if message.parent_tool_use_id is not None:
                            continue  # un sous-agent : pas la réponse d'Atlas
                        evenement = message.event
                        if evenement.get("type") == "content_block_start":
                            bloc = evenement.get("content_block") or {}
                            if bloc.get("type") == "text":
                                # Deux blocs de texte (avant et après une recherche) : sans
                                # espace, « …vérifier.D'après… » ne se couperait jamais.
                                separer = texte_rendu
                            elif self._est_une_recherche(bloc, recherches):
                                yield RECHERCHE
                        elif evenement.get("type") == "content_block_delta":
                            delta = evenement.get("delta") or {}
                            morceau = delta.get("text") if delta.get("type") == "text_delta" else ""
                            if morceau:
                                if separer:
                                    morceau, separer = " " + morceau, False
                                texte_rendu = True
                                yield morceau
                    elif isinstance(message, AssistantMessage):
                        if message.error is not None:
                            raise ErreurCerveau(self._message_assistant(message))
                        for bloc in message.content:
                            if isinstance(bloc, ToolUseBlock) and self._est_une_recherche(
                                {"type": "tool_use", "name": bloc.name, "id": bloc.id}, recherches
                            ):
                                yield RECHERCHE
                    elif isinstance(message, RateLimitEvent):
                        if message.rate_limit_info.status == "rejected":
                            raise ErreurCerveau(LIMITE)
                    elif isinstance(message, ResultMessage):
                        self._tour_ouvert = False
                        if message.is_error and not self._interrompu:
                            raise ErreurCerveau(self._message_resultat(message))
        except ErreurCerveau:
            raise
        except Exception as e:  # noqa: BLE001 — le SDK ne sait plus où il en est
            await self._perdre_le_fil(type(e).__name__)
            raise ErreurCerveau(_message_exception(e)) from e
        if self._tour_ouvert:
            # Le flux s'est tari sans message de fin : le processus Claude s'est arrêté.
            await self._perdre_le_fil("fin du flux")
            raise ErreurCerveau(ARRET)

    @staticmethod
    def _est_une_recherche(bloc: dict, deja_vues: set[str]) -> bool:
        """Un appel à la recherche web, signalé une seule fois (l'événement partiel et le
        message complet décrivent le même appel)."""
        if bloc.get("type") != "tool_use" or bloc.get("name") != OUTIL_RECHERCHE:
            return False
        identifiant = bloc.get("id") or ""
        if identifiant in deja_vues:
            return False
        deja_vues.add(identifiant)
        return True

    @staticmethod
    def _message_assistant(message: AssistantMessage) -> str:
        if message.error in _ERREURS_ASSISTANT:
            return _ERREURS_ASSISTANT[message.error]
        texte = " ".join(b.text for b in message.content if isinstance(b, TextBlock)).strip()
        return texte or f"Claude a signalé une erreur ({message.error})."

    @staticmethod
    def _message_resultat(message: ResultMessage) -> str:
        statut = message.api_error_status
        if statut == 429:
            return LIMITE
        if statut in (401, 403):
            return DECONNECTE
        if statut is not None and statut >= 500:
            return INJOIGNABLE
        if message.errors:
            return " ; ".join(message.errors)
        return message.result or f"Claude n'a pas pu répondre ({message.subtype})."

    async def _perdre_le_fil(self, cause: str) -> None:
        """La conversation est perdue : Claude sera relancé à la question suivante, qui
        commencera par le dire."""
        _journal.warning("conversation avec Claude perdue (%s)", cause)
        await self._jeter_le_client()
        self._fil_perdu = True

    # --- l'interruption --------------------------------------------------------

    async def _interrompre_le_tour(self) -> None:
        """Une autre question arrive : la réponse en cours se termine, sans erreur."""
        client = self._client
        if client is None or not self._tour_ouvert:
            return
        self._interrompu = True
        try:
            await client.interrupt()
        except Exception as e:  # noqa: BLE001 — au pire, la nouvelle question attend la fin
            _journal.warning("interruption de Claude impossible (%s)", type(e).__name__)

    async def _vider_le_tour(self, client: ClientClaude) -> None:
        """Interrompt le tour abandonné et consomme ses derniers messages jusqu'au message
        de fin : la question suivante part d'un état propre. Si Claude ne finit pas le
        tour à temps, la conversation est perdue : on repartira de zéro."""
        try:
            async with asyncio.timeout(DELAI_MENAGE_S):
                await client.interrupt()
                async with contextlib.aclosing(client.receive_response()) as reste:
                    async for _message in reste:
                        pass
            self._tour_ouvert = False
        except Exception as e:  # noqa: BLE001 — TimeoutError compris
            await self._perdre_le_fil(f"tour interrompu mal refermé : {type(e).__name__}")

    async def _attendre_le_menage(self) -> None:
        menage = self._menage
        if menage is None:
            return
        # Protégé : une question elle-même annulée ne doit pas annuler le ménage.
        await asyncio.shield(menage)
        if self._menage is menage:
            self._menage = None
```

- [ ] **Step 5: Vérifier que tout passe**

Run: `uv run pytest tests/test_cerveau.py tests/test_cerveau_claude.py -q && uv run pytest -q && uv run ruff check . && uv run ruff format --check .`
Expected: 44 tests passent (10 + 34), en moins d'une seconde ; toute la suite passe (507 tests, 3 ignorés).

- [ ] **Step 6: Commit**

```bash
git add src/atlas_core/cerveau.py src/atlas_core/cerveau_claude.py tests/test_cerveau.py tests/test_cerveau_claude.py
git commit -F - <<'MSG'
Branche Claude comme cerveau, par le SDK Agent

Une seule conversation, une question à la fois ; une réponse abandonnée est
interrompue et vidée en tâche de fond ; oubli après trente minutes, relance
après plantage, erreurs traduites en français.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

### Task 6: La session face au vrai cerveau

**Files:**
- Modify: `src/atlas_core/etat.py` (transition parole → réflexion)
- Modify: `src/atlas_core/session.py` (13 remplacements ci-dessous)
- Modify: `tests/test_etat.py` (une transition permise de plus)
- Test: `tests/test_session_cerveau.py` (nouveau) ; `tests/test_session.py`, `tests/test_session_web.py` et `tests/test_integration_boucle.py` doivent passer **sans modification**

**Interfaces:**
- Consumes: `DecoupeurPhrases` (Task 2) ; `nettoyer`, `est_hallucination` (Task 3) ; `Recherche`, `ErreurCerveau` (Task 5).
- Produces: `PHRASE_ATTENTE = "Je regarde ça."` dans `atlas_core.session`. Comportements : à un `Recherche` du cerveau, la session dit la phrase d'attente (une fois par question), puis, quand ce qui a été dit a fini de jouer, repasse en « reflexion » (machine, client et pages) jusqu'à la phrase suivante, qui reprend la parole sous le même `id_enonce` ; chaque phrase est nettoyée avant d'être dite et affichée (une phrase vide ne compte pas) ; une `ErreurCerveau` est dite comme dernière phrase et publiée en `Erreur(code="cerveau", message=…)` (au client tout de suite, aux pages quand sa voix commence) ; une transcription fantôme mène au repos sans appeler le cerveau. Le muet n'interrompt pas le cerveau. `_dire` prend un paramètre `affichage: Reponse | Erreur | None = None`.

- [ ] **Step 1: Écrire les tests qui échouent**

Dans `tests/test_etat.py`, ajouter la transition parole → réflexion :

Remplacer :

```python
        ("parole", "ecoute"),
```

par :

```python
        ("parole", "ecoute"),
        ("parole", "reflexion"),
```

Puis `tests/test_session_cerveau.py` (il réutilise les doublures de `tests/test_session_web.py`) :

```python
"""La session face au vrai cerveau : recherche web, erreurs dites, mise en voix, fantômes."""

import asyncio
from collections.abc import AsyncIterator

from test_session_web import (
    Collecteur,
    DiffuseurEspion,
    FausseSynthese,
    FausseTranscription,
    FauxPlanificateur,
)

from atlas_core.cerveau import RECHERCHE, ErreurCerveau
from atlas_core.protocole import Dire, Erreur, Etat, FinEnonce, Interruption, Reveil
from atlas_core.protocole_web import Reponse
from atlas_core.session import PHRASE_ATTENTE, Session


class CerveauScript:
    """Rejoue une suite : du texte, `RECHERCHE`, un `asyncio.Event` qui fait attendre
    jusqu'à ce que le test le mette, ou une exception à lever."""

    def __init__(self, *suite) -> None:
        self.suite = suite
        self.questions: list[str] = []
        self.ferme = False  # le flux est fermé, jusqu'au bout ou abandonné en route
        self.complet = False  # le flux est allé jusqu'au bout

    async def repondre(self, texte: str) -> AsyncIterator:
        self.questions.append(texte)
        try:
            for element in self.suite:
                if isinstance(element, asyncio.Event):
                    await element.wait()
                elif isinstance(element, BaseException):
                    raise element
                else:
                    yield element
                    await asyncio.sleep(0)
            self.complet = True
        finally:
            self.ferme = True

    async def fermer(self) -> None:
        pass


class CollecteurQuiRetientLaReflexion(Collecteur):
    """L'envoi de « reflexion » reste suspendu jusqu'à ce que le test le libère."""

    def __init__(self) -> None:
        super().__init__()
        self.liberer = asyncio.Event()

    async def envoyer_json(self, msg) -> None:
        if isinstance(msg, Etat) and msg.valeur == "reflexion" and "parole" in self.etats():
            await self.liberer.wait()
        self.json.append(msg)


def _session(collecteur, diffuseur, cerveau, **options) -> Session:
    return Session(
        envoyer_json=collecteur.envoyer_json,
        envoyer_binaire=collecteur.envoyer_binaire,
        transcription=options.pop("transcription", FausseTranscription()),
        synthese=FausseSynthese(),
        cerveau=cerveau,
        diffuseur=diffuseur,
        planifier=options.pop("planifier", FauxPlanificateur()),
        **options,
    )


async def _attendre(condition, message: str = "") -> None:
    for _ in range(1000):
        if condition():
            return
        await asyncio.sleep(0)
    raise AssertionError(message or "la condition n'est jamais devenue vraie")


def _dits(c: Collecteur) -> list[str]:
    return [m.texte for m in c.de(Dire)]


# --- la recherche web -----------------------------------------------------------


async def test_une_recherche_dit_la_phrase_d_attente_puis_repasse_en_reflexion():
    c, d, plan = Collecteur(), DiffuseurEspion(), FauxPlanificateur()
    resultats = asyncio.Event()
    s = _session(c, d, CerveauScript(RECHERCHE, resultats, "Il pleut. "), planifier=plan)

    await s.sur_saisie("Il pleut à Paris ?")
    await _attendre(lambda: _dits(c) == [PHRASE_ATTENTE])
    assert c.etats() == ["reflexion", "parole"]

    plan.jouer()  # la phrase d'attente a fini de jouer
    await _attendre(lambda: c.etats()[-1] == "reflexion", "l'orbe doit repasser en réflexion")
    assert d.de(Etat)[-1].valeur == "reflexion"

    resultats.set()
    await _attendre(lambda: c.etats()[-1] == "repos")
    assert c.etats() == ["reflexion", "parole", "reflexion", "parole", "repos"]
    assert _dits(c) == [PHRASE_ATTENTE, "Il pleut."]
    assert [m.rang for m in c.de(Dire)] == [1, 2]
    assert len({m.id_enonce for m in c.de(Dire)}) == 1, "une seule réponse, un seul énoncé"
    await s.fermer()


async def test_la_reflexion_part_au_client_avant_la_reprise_de_la_parole():
    c, d, plan = CollecteurQuiRetientLaReflexion(), DiffuseurEspion(), FauxPlanificateur()
    resultats = asyncio.Event()
    s = _session(c, d, CerveauScript(RECHERCHE, resultats, "Il pleut. "), planifier=plan)
    await s.sur_saisie("Il pleut ?")
    await _attendre(lambda: _dits(c) == [PHRASE_ATTENTE])
    plan.jouer()
    resultats.set()
    await asyncio.sleep(0.01)
    assert c.etats() == ["reflexion", "parole"], "« parole » ne double pas « reflexion »"

    c.liberer.set()
    await _attendre(lambda: c.etats()[-1:] == ["repos"])
    assert c.etats() == ["reflexion", "parole", "reflexion", "parole", "repos"]
    await s.fermer()


async def test_la_phrase_d_attente_n_est_dite_qu_une_fois_par_question():
    c, d, plan = Collecteur(), DiffuseurEspion(), FauxPlanificateur()
    cerveau = CerveauScript(RECHERCHE, "Voyons. ", RECHERCHE, "Il pleut. ")
    s = _session(c, d, cerveau, planifier=plan)

    await s.sur_saisie("Il pleut ?")
    await _attendre(lambda: c.etats()[-1:] == ["repos"])
    assert _dits(c) == [PHRASE_ATTENTE, "Voyons.", "Il pleut."]

    await s.sur_saisie("Et demain ?")
    await _attendre(lambda: len(_dits(c)) == 6)
    assert _dits(c)[3] == PHRASE_ATTENTE, "chaque question a sa phrase d'attente"
    await s.fermer()


async def test_une_reponse_arrivee_avant_la_fin_de_l_attente_reste_en_parole():
    c, d, plan = Collecteur(), DiffuseurEspion(), FauxPlanificateur()
    suite = asyncio.Event()
    cerveau = CerveauScript(RECHERCHE, "Il pleut. ", suite, "Et demain aussi. ")
    s = _session(c, d, cerveau, planifier=plan)
    await s.sur_saisie("Il pleut ?")
    await _attendre(lambda: _dits(c) == [PHRASE_ATTENTE, "Il pleut."])

    plan.jouer()  # l'attente finit de jouer alors qu'Atlas a déjà repris la parole
    await asyncio.sleep(0.01)
    assert c.etats() == ["reflexion", "parole"], "pas de réflexion en pleine réponse"

    suite.set()
    await _attendre(lambda: c.etats()[-1:] == ["repos"])
    assert c.etats() == ["reflexion", "parole", "repos"]
    await s.fermer()


async def test_sans_voix_la_recherche_passe_aussi_en_reflexion():
    c, d = Collecteur(), DiffuseurEspion()
    resultats = asyncio.Event()
    s = _session(c, d, CerveauScript(RECHERCHE, resultats, "Il pleut. "), avec_voix=lambda: False)
    await s.sur_saisie("Il pleut ?")
    await _attendre(lambda: [e.valeur for e in d.de(Etat)] == ["reflexion", "parole", "reflexion"])
    assert [r.texte for r in d.de(Reponse)] == [PHRASE_ATTENTE]

    resultats.set()
    await _attendre(lambda: [e.valeur for e in d.de(Etat)][-1:] == ["repos"])
    assert [e.valeur for e in d.de(Etat)] == ["reflexion", "parole", "reflexion", "parole", "repos"]
    await s.fermer()


async def test_hey_atlas_pendant_la_recherche_abandonne_la_reponse():
    c, d, plan = Collecteur(), DiffuseurEspion(), FauxPlanificateur()
    cerveau = CerveauScript(RECHERCHE, asyncio.Event(), "jamais dit. ")
    s = _session(c, d, cerveau, planifier=plan)
    await s.sur_saisie("Il pleut ?")
    await _attendre(lambda: _dits(c) == [PHRASE_ATTENTE])
    plan.jouer()
    await _attendre(lambda: c.etats()[-1] == "reflexion")

    await s.sur_message(Reveil(confiance=0.9, horodatage=0.0))

    assert c.etats()[-2:] == ["repos", "ecoute"]
    assert cerveau.ferme, "le flux du cerveau est fermé : Claude sera interrompu"
    await s.fermer()


async def test_couper_la_phrase_d_attente_annule_le_retour_en_reflexion():
    c, d, plan = Collecteur(), DiffuseurEspion(), FauxPlanificateur()
    s = _session(c, d, CerveauScript(RECHERCHE, asyncio.Event()), planifier=plan)
    await s.sur_saisie("Il pleut ?")
    await _attendre(lambda: _dits(c) == [PHRASE_ATTENTE])

    await s.sur_message(Interruption(horodatage=0.0))  # barge-in pendant l'attente
    plan.jouer()
    await asyncio.sleep(0.01)

    assert c.etats() == ["reflexion", "parole", "ecoute"]
    await s.fermer()


async def test_le_muet_n_interrompt_pas_claude():
    c, d, plan = Collecteur(), DiffuseurEspion(), FauxPlanificateur()
    suite = asyncio.Event()
    cerveau = CerveauScript("Un. ", suite, "Deux. ")
    s = _session(c, d, cerveau, planifier=plan)
    await s.sur_saisie("Compte.")
    await _attendre(lambda: _dits(c) == ["Un."])

    await s.taire()
    suite.set()
    await _attendre(lambda: [e.valeur for e in d.de(Etat)][-1:] == ["repos"])

    assert cerveau.complet, "la réponse va jusqu'au bout, en texte seulement"
    assert [r.texte for r in d.de(Reponse)] == ["Un.", "Deux."]
    assert _dits(c) == ["Un."]
    await s.fermer()


# --- les erreurs du cerveau ------------------------------------------------------------


async def test_une_erreur_du_cerveau_est_dite_puis_affichee_en_rouge():
    c, d, plan = Collecteur(), DiffuseurEspion(), FauxPlanificateur()
    limite = "J'ai atteint la limite de l'abonnement Claude pour le moment."
    s = _session(c, d, CerveauScript("Je commence. ", ErreurCerveau(limite)), planifier=plan)
    await s.sur_saisie("Raconte.")
    await _attendre(lambda: c.etats()[-1:] == ["repos"])
    plan.jouer()

    assert _dits(c) == ["Je commence.", limite], "ce qui était commencé, puis l'erreur"
    assert c.de(Erreur) == [Erreur(code="cerveau", message=limite)]
    assert [r.texte for r in d.de(Reponse)] == ["Je commence."]
    assert d.de(Erreur) == [Erreur(code="cerveau", message=limite)]
    assert c.etats() == ["reflexion", "parole", "repos"]
    await s.fermer()


async def test_sans_voix_une_erreur_du_cerveau_s_affiche_tout_de_suite():
    c, d = Collecteur(), DiffuseurEspion()
    s = _session(
        c,
        d,
        CerveauScript(ErreurCerveau("Je n'arrive pas à joindre Claude.")),
        avec_voix=lambda: False,
    )
    await s.sur_saisie("Bonjour")
    await _attendre(lambda: [e.valeur for e in d.de(Etat)][-1:] == ["repos"])
    assert [e.message for e in d.de(Erreur)] == ["Je n'arrive pas à joindre Claude."]
    await s.fermer()


# --- la mise en voix et les fantômes de Whisper -------------------------------------


async def test_les_phrases_sont_nettoyees_avant_d_etre_dites_et_affichees():
    c, d, plan = Collecteur(), DiffuseurEspion(), FauxPlanificateur()
    cerveau = CerveauScript("Il fait **beau**. ", "** ", "Tout est sur https://x.fr. ")
    s = _session(c, d, cerveau, planifier=plan)
    await s.sur_saisie("Quel temps ?")
    await _attendre(lambda: c.etats()[-1:] == ["repos"])
    plan.jouer()

    assert _dits(c) == ["Il fait beau.", "Tout est sur un lien."]
    assert [r.texte for r in d.de(Reponse)] == ["Il fait beau.", "Tout est sur un lien."]
    assert [m.rang for m in c.de(Dire)] == [1, 2], "une phrase vide ne compte pas"
    await s.fermer()


async def test_une_phrase_fantome_de_whisper_ne_derange_pas_le_cerveau():
    c, d = Collecteur(), DiffuseurEspion()
    cerveau = CerveauScript("Jamais. ")
    s = _session(c, d, cerveau, transcription=FausseTranscription("Merci."))
    await s.sur_message(Reveil(confiance=0.9, horodatage=0.0))
    await s.sur_audio(b"\x00" * 640)
    await s.sur_message(FinEnonce(duree_ms=20))
    await _attendre(lambda: c.etats()[-1:] == ["repos"])

    assert cerveau.questions == []
    assert c.etats() == ["ecoute", "reflexion", "repos"]
    await s.fermer()
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `uv run pytest tests/test_etat.py tests/test_session_cerveau.py -q`
Expected: FAIL — `ImportError: cannot import name 'PHRASE_ATTENTE' from 'atlas_core.session'`.

- [ ] **Step 3: Permettre le retour en réflexion**

Dans `src/atlas_core/etat.py` :

Remplacer :

```python
    "parole": {"repos", "ecoute"},  # « ecoute » est le chemin de l'interruption
```

par :

```python
    # « ecoute » est le chemin de l'interruption ; « reflexion », celui d'une recherche web
    # qui commence après la phrase d'attente.
    "parole": {"repos", "ecoute", "reflexion"},
```

- [ ] **Step 4: Adapter la session**

Dans `src/atlas_core/session.py`, ces remplacements, dans l'ordre (chaque texte à remplacer ne s'y trouve qu'une fois). `_repondre` et `_dire` changent en profondeur ; l'ancienne `_entrer_en_parole` laisse place à `_phrase`, `_chercher`, `_finir_envoi_differe` et une nouvelle `_entrer_en_parole` :

1. Remplacer :

```python
from .cerveau import Cerveau
from .diffuseur import Diffuseur
from .etat import MachineEtat, Valeur
```

par :

```python
from .cerveau import Cerveau, ErreurCerveau, Recherche
from .diffuseur import Diffuseur
from .etat import MachineEtat, Valeur
from .mise_en_voix import est_hallucination, nettoyer
```

2. Remplacer :

```python
EnvoyerBinaire = Callable[[bytes], Awaitable[None]]
```

par :

```python
EnvoyerBinaire = Callable[[bytes], Awaitable[None]]

PHRASE_ATTENTE = "Je regarde ça."  # dite une fois par question, quand Claude cherche sur le web
```

3. Remplacer :

```python
        self._textes_en_attente: list[Reponse] = []
```

par :

```python
        self._textes_en_attente: list[Reponse | Erreur] = []
        # La réponse en cours : son énoncé, le rang de sa dernière phrase, la phrase d'attente.
        self._identifiant = 0
        self._rang = 0
        self._attente_dite = False
        # « reflexion » envoyé au client depuis un rappel du calendrier (qui ne peut pas
        # attendre) : tout état suivant attend qu'il soit parti, pour garder l'ordre.
        self._envoi_differe: asyncio.Task | None = None
```

4. Remplacer :

```python
    def _programmer_texte(self, reponse: Reponse) -> None:
```

par :

```python
    def _programmer_texte(self, reponse: Reponse | Erreur) -> None:
```

5. Remplacer :

```python
            if not texte.strip():
```

par :

```python
            if est_hallucination(texte):
                # Rien entendu, ou une phrase fantôme de Whisper (« Merci. ») : Claude
                # n'est pas dérangé pour si peu.
```

6. Remplacer :

```python
        reflexion_ms: int | None = None
        debut = self._horloge()
        identifiant = self._id_enonce + 1
        rang = 0

        decoupeur = DecoupeurPhrases()
        async with contextlib.aclosing(self._cerveau.repondre(texte)) as fragments:
            async for fragment in fragments:
                if reflexion_ms is None:
                    reflexion_ms = _ms(self._horloge() - debut)
                for phrase in decoupeur.ajouter(fragment):
                    if rang == 0:
                        await self._entrer_en_parole(identifiant)
                    rang += 1
                    await self._dire(identifiant, rang, phrase)
        for phrase in decoupeur.vider():
            if rang == 0:
                await self._entrer_en_parole(identifiant)
            rang += 1
            await self._dire(identifiant, rang, phrase)
```

par :

```python
        self._identifiant = self._id_enonce + 1
        self._rang = 0
        self._attente_dite = False
        reflexion_ms: int | None = None
        debut = self._horloge()
        erreur: ErreurCerveau | None = None

        decoupeur = DecoupeurPhrases()
        try:
            async with contextlib.aclosing(self._cerveau.repondre(texte)) as fragments:
                async for fragment in fragments:
                    if reflexion_ms is None:
                        reflexion_ms = _ms(self._horloge() - debut)
                    if isinstance(fragment, Recherche):
                        await self._chercher()
                        continue
                    for phrase in decoupeur.ajouter(fragment):
                        await self._phrase(phrase)
        except ErreurCerveau as e:
            erreur = e
        for phrase in decoupeur.vider():
            await self._phrase(phrase)
        if erreur is not None:
            # Ce que Claude avait commencé à dire est dit ; puis l'erreur, à voix haute et
            # en rouge pour les pages.
            _journal.warning("le cerveau n'a pas pu répondre : %s", erreur)
            message = Erreur(code="cerveau", message=str(erreur))
            await self._au_client(message)
            await self._phrase(str(erreur), affichage=message)
```

7. Remplacer :

```python
        )
        if rang == 0:
            # Le cerveau n'a produit aucune phrase : « reflexion » va droit au repos.
```

par :

```python
        )
        if self._rang == 0:
            # Le cerveau n'a produit aucune phrase : « reflexion » va droit au repos.
```

8. Remplacer :

```python
            return
        self._machine.aller_vers("repos")
        await self._au_client(Etat(valeur="repos"))
```

par :

```python
            return
        self._machine.aller_vers("repos")
        await self._finir_envoi_differe()
        await self._au_client(Etat(valeur="repos"))
```

9. Remplacer :

```python
    async def _entrer_en_parole(self, identifiant: int) -> None:
        """La première phrase de la réponse : « reflexion » dure jusque-là, pas au-delà."""
```

par :

```python
    async def _phrase(self, phrase: str, affichage: Reponse | Erreur | None = None) -> None:
        """Dit (et affiche) la phrase suivante de la réponse, rendue prononçable."""
        phrase = nettoyer(phrase)
        if not phrase:
            return
        # Le rang avance d'abord : un retour en réflexion programmé après la phrase
        # d'attente voit ainsi que la réponse a repris.
        self._rang += 1
        if self._machine.valeur != "parole":
            await self._entrer_en_parole(self._identifiant)
        await self._dire(self._identifiant, self._rang, phrase, affichage)

    async def _chercher(self) -> None:
        """Claude cherche sur le web : « Je regarde ça. », une fois par question ; puis,
        quand ce qui a été dit a fini de jouer, l'orbe repasse en réflexion jusqu'à la
        réponse (machine, client et pages)."""
        if not self._attente_dite:
            self._attente_dite = True
            await self._phrase(PHRASE_ATTENTE)
        if self._machine.valeur != "parole":
            return
        rang = self._rang

        def revenir_en_reflexion() -> None:
            if self._rang != rang or self._machine.valeur != "parole":
                return  # la réponse a repris entre-temps, ou le tour est fini
            self._machine.aller_vers("reflexion")
            self._publier_etat("reflexion")
            self._envoi_differe = asyncio.get_running_loop().create_task(
                self._au_client(Etat(valeur="reflexion"))
            )

        self._niveaux.apres_lecture(revenir_en_reflexion)

    async def _finir_envoi_differe(self) -> None:
        envoi, self._envoi_differe = self._envoi_differe, None
        if envoi is not None:
            await envoi

    async def _entrer_en_parole(self, identifiant: int) -> None:
        """La réponse prend (ou reprend) la parole : « reflexion » dure jusque-là."""
```

10. Remplacer :

```python
    async def _dire(self, identifiant: int, rang: int, phrase: str) -> None:
        reponse = Reponse(texte=phrase)
        if not self._voix_active():
            self._diffuseur.publier(reponse)
```

par :

```python
    async def _dire(
        self, identifiant: int, rang: int, phrase: str, affichage: Reponse | Erreur | None = None
    ) -> None:
        affichage = affichage if affichage is not None else Reponse(texte=phrase)
        if not self._voix_active():
            self._diffuseur.publier(affichage)
```

11. Remplacer :

```python
                    self._programmer_texte(reponse)
```

par :

```python
                    self._programmer_texte(affichage)
```

12. Remplacer :

```python
            # Muet avant le premier morceau, ou synthèse muette : le texte part tel quel.
            self._diffuseur.publier(reponse)
            if self._voix_active() and phrase.strip():
```

par :

```python
            # Muet avant le premier morceau, ou synthèse muette : le texte part tel quel.
            self._diffuseur.publier(affichage)
            if self._voix_active() and phrase.strip():
```

13. Remplacer :

```python
        self._publier_etat(valeur)
```

par :

```python
        self._publier_etat(valeur)
        await self._finir_envoi_differe()
```

- [ ] **Step 5: Vérifier que tout passe**

Run: `uv run pytest tests/test_etat.py tests/test_session_cerveau.py tests/test_session.py tests/test_session_web.py tests/test_integration_boucle.py -q && uv run pytest -q && uv run ruff check . && uv run ruff format --check .`
Expected: tout passe, dont les 12 tests de `test_session_cerveau.py` ; toute la suite passe (520 tests, 3 ignorés).

- [ ] **Step 6: Commit**

```bash
git add src/atlas_core/etat.py src/atlas_core/session.py tests/test_etat.py tests/test_session_cerveau.py
git commit -F - <<'MSG'
Dit « Je regarde ça » pendant une recherche, et les erreurs du cerveau à voix haute

Pendant la recherche, l'orbe repasse en réflexion ; chaque phrase est rendue
prononçable ; les phrases fantômes de Whisper ne dérangent plus le cerveau.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

### Task 7: Un seul cerveau pour le Core, et la clé de `/ws/audio`

**Files:**
- Modify: `src/atlas_core/protocole.py` (`Bonjour.cle`)
- Modify: `src/atlas_core/hub.py` (8 remplacements ci-dessous)
- Modify: `tests/test_protocole.py`, `tests/test_hub_web.py`
- Replace: `tests/test_hub.py` (contenu complet ci-dessous)

**Interfaces:**
- Consumes: `Config.cerveau`, `cerveau_modele`, `cerveau_oubli_min`, `audio_cle` (Task 1) ; `Cerveau`, `CerveauBouchon` (Task 5) ; `CerveauClaude`, `options_cerveau`, `purger_cles_api` (Task 5) ; `cle_valide` (existant, `web.py`).
- Produces: `Bonjour.cle: str = ""` ; dans `atlas_core.hub` : `creer_cerveau(config: Config) -> Cerveau` (le bouchon, ou un `CerveauClaude` dont la fabrique crée `DOSSIER_CERVEAU` puis un `ClaudeSDKClient` ; retire les `ANTHROPIC_*` de `os.environ`), `DOSSIER_CERVEAU = Path.home() / ".atlas" / "cerveau"`, le cerveau partagé `_cerveau` (créé au démarrage de l'application, fermé à son arrêt, passé à toutes les sessions par `_services()`), `_client_audio_authentifie(ws) -> bool | None`.

- [ ] **Step 1: Écrire les tests qui échouent**

Dans `tests/test_protocole.py` :

Remplacer :

```python
    assert "aec" in msg.capacites
```

par :

```python
    assert "aec" in msg.capacites


def test_le_bonjour_porte_la_cle_du_client_audio():
    msg = decoder_message('{"type":"bonjour","client":"m5","cle":"secret"}')
    assert msg.cle == "secret"
    assert decoder_message('{"type":"bonjour","client":"m5"}').cle == ""
```

Remplacer tout `tests/test_hub.py` par :

```python
import json
import os
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from atlas_core import hub
from atlas_core.cerveau import CerveauBouchon
from atlas_core.cerveau_claude import CerveauClaude
from atlas_core.protocole import (
    TAILLE_BLOC_OCTETS,
    Bonjour,
    Reveil,
    encoder_audio_entrant,
)

CLE_AUDIO = "cle-audio-de-test"


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


@pytest.fixture
def cle_audio(monkeypatch) -> str:
    monkeypatch.setattr(hub, "_config", replace(hub._config, audio_cle=CLE_AUDIO))
    return CLE_AUDIO


def _bonjour(cle: str = CLE_AUDIO) -> str:
    return Bonjour(client="test", cle=cle).model_dump_json()


def test_la_route_de_sante_repond():
    with TestClient(hub.app) as client:
        r = client.get("/sante")
        assert r.status_code == 200 and r.json()["ok"] is True


def test_apres_le_bonjour_les_messages_arrivent_a_la_session(monkeypatch, cle_audio):
    espionnes: list[SessionEspionne] = []

    def fabrique(envoyer_json, envoyer_binaire):
        s = SessionEspionne(envoyer_json, envoyer_binaire)
        espionnes.append(s)
        return s

    monkeypatch.setattr(hub, "creer_session", fabrique)
    with TestClient(hub.app) as client, client.websocket_connect("/ws/audio") as ws:
        ws.send_text(_bonjour())
        ws.send_text(Reveil(confiance=1.0, horodatage=0.0).model_dump_json())
        ws.send_bytes(encoder_audio_entrant(b"\x00" * TAILLE_BLOC_OCTETS))
        ws.close()

    assert [type(m) for m in espionnes[0].messages] == [Reveil], "le bonjour reste au hub"
    assert espionnes[0].audio == [b"\x00" * TAILLE_BLOC_OCTETS]


def test_un_message_invalide_renvoie_une_erreur_sans_couper(monkeypatch, cle_audio):
    monkeypatch.setattr(hub, "creer_session", SessionEspionne)
    with TestClient(hub.app) as client, client.websocket_connect("/ws/audio") as ws:
        ws.send_text(_bonjour())
        ws.send_text('{"type":"nimporte_quoi"}')
        recu = json.loads(ws.receive_text())
        assert recu["type"] == "erreur"
        assert recu["code"] == "message_invalide"
        ws.close()


@pytest.mark.parametrize(
    "premier",
    [
        Bonjour(client="test", cle="pas-la-bonne").model_dump_json(),
        Bonjour(client="test").model_dump_json(),
        Reveil(confiance=1.0, horodatage=0.0).model_dump_json(),
        "pas du json",
    ],
)
def test_sans_la_bonne_cle_ws_audio_se_ferme(monkeypatch, cle_audio, premier):
    espionnes: list = []
    monkeypatch.setattr(hub, "creer_session", lambda j, b: espionnes.append(1))
    with TestClient(hub.app) as client, client.websocket_connect("/ws/audio") as ws:
        ws.send_text(premier)
        with pytest.raises(WebSocketDisconnect) as fermeture:
            ws.receive_text()
    assert fermeture.value.code == hub.FERMETURE_NON_AUTORISE
    assert espionnes == [], "aucune session pour un client refusé"


def test_sans_bonjour_a_temps_ws_audio_se_ferme(monkeypatch, cle_audio):
    monkeypatch.setattr(hub, "DELAI_AUTHENTIFICATION_S", 0.05)
    with TestClient(hub.app) as client, client.websocket_connect("/ws/audio") as ws:
        with pytest.raises(WebSocketDisconnect) as fermeture:
            ws.receive_text()
    assert fermeture.value.code == hub.FERMETURE_NON_AUTORISE


def test_sans_cle_configuree_ws_audio_refuse_tout(monkeypatch):
    monkeypatch.setattr(hub, "_config", replace(hub._config, audio_cle=""))
    with TestClient(hub.app) as client, client.websocket_connect("/ws/audio") as ws:
        erreur = json.loads(ws.receive_text())
        with pytest.raises(WebSocketDisconnect) as fermeture:
            ws.receive_text()
    assert erreur["code"] == "cle_absente" and "ATLAS_AUDIO_CLE" in erreur["message"]
    assert fermeture.value.code == hub.FERMETURE_CLE_ABSENTE


# --- le cerveau ------------------------------------------------------------------


def test_le_bouchon_se_choisit_par_la_configuration():
    assert isinstance(hub.creer_cerveau(replace(hub._config, cerveau="bouchon")), CerveauBouchon)


def test_le_cerveau_claude_ne_demarre_rien_avant_la_premiere_question(monkeypatch, tmp_path):
    dossier = tmp_path / "cerveau"
    monkeypatch.setattr(hub, "DOSSIER_CERVEAU", dossier)
    config = replace(hub._config, cerveau="claude", cerveau_modele="claude-sonnet-5")

    cerveau = hub.creer_cerveau(config)

    assert isinstance(cerveau, CerveauClaude)
    assert not dossier.exists(), "rien sur le disque tant que personne n'a rien demandé"
    client = cerveau._fabrique()  # ce que fera la première question
    assert dossier.is_dir()
    assert client.options.cwd == dossier and client.options.model == "claude-sonnet-5"


def test_les_cles_d_api_sont_retirees_de_l_environnement_du_core(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ne-doit-pas-servir")
    hub.creer_cerveau(replace(hub._config, cerveau="claude"))
    assert "ANTHROPIC_API_KEY" not in os.environ


def test_la_voix_et_le_clavier_partagent_le_meme_cerveau(monkeypatch):
    monkeypatch.setattr(hub, "_config", replace(hub._config, cerveau="bouchon"))

    async def rien(_):
        pass

    with TestClient(hub.app):
        voix = hub.creer_session(rien, rien)
        ecrite = hub.creer_session_ecrite()
        assert voix._cerveau is ecrite._cerveau is hub._cerveau


def test_le_cerveau_est_ferme_a_l_arret_du_core(monkeypatch):
    class CerveauEspion(CerveauBouchon):
        ferme = False

        async def fermer(self) -> None:
            CerveauEspion.ferme = True

    monkeypatch.setattr(hub, "creer_cerveau", lambda config: CerveauEspion())
    with TestClient(hub.app):
        assert not CerveauEspion.ferme
    assert CerveauEspion.ferme
```

Dans `tests/test_hub_web.py` (le client audio doit maintenant présenter sa clé ; l'aller-retour d'un message invalide prouve qu'il a passé l'authentification) :

1. Remplacer :

```python
from atlas_core.diffuseur import Diffuseur
```

par :

```python
from atlas_core.diffuseur import Diffuseur
from atlas_core.protocole import Bonjour
```

2. Remplacer :

```python
    with TestClient(hub.app) as client, client.websocket_connect("/ws/audio") as ws:
```

par :

```python
    monkeypatch.setattr(hub, "_config", replace(hub._config, audio_cle="cle-audio"))
    with TestClient(hub.app) as client, client.websocket_connect("/ws/audio") as ws:
        ws.send_text(Bonjour(client="test", cle="cle-audio").model_dump_json())
        ws.send_text('{"type":"nimporte_quoi"}')
        assert ws.receive_json()["code"] == "message_invalide"  # la boucle est atteinte
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `uv run pytest tests/test_protocole.py -q -k cle; uv run pytest tests/test_hub.py -q -k "cerveau or bouchon or partagent"`
Expected: FAIL — 1 échec (`AttributeError: 'Bonjour' object has no attribute 'cle'`), puis 4 échecs (`module 'atlas_core.hub' has no attribute 'creer_cerveau'`, `'_cerveau'`, `'DOSSIER_CERVEAU'`).

Ne lancez pas encore tout `tests/test_hub.py` : l'ancien hub, qui n'attend aucune clé, laisse les tests de clé attendre sans fin.

- [ ] **Step 3: Ajouter la clé au `Bonjour`**

Dans `src/atlas_core/protocole.py` :

1. Remplacer :

```python
class Bonjour(BaseModel):
```

par :

```python
class Bonjour(BaseModel):
    """Le premier message du client audio : il porte `ATLAS_AUDIO_CLE`, sans laquelle le
    Core ferme la connexion."""

```

2. Remplacer :

```python
    capacites: list[str] = Field(default_factory=list)
```

par :

```python
    capacites: list[str] = Field(default_factory=list)
    cle: str = ""
```

- [ ] **Step 4: Adapter le hub**

Dans `src/atlas_core/hub.py` :

1. Remplacer :

```python
import logging
```

par :

```python
import logging
import os
```

2. Remplacer :

```python
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from .cerveau import CerveauBouchon
from .config import Config
from .diffuseur import Diffuseur
from .protocole import Erreur, decoder_audio_entrant, decoder_message
```

par :

```python
from claude_agent_sdk import ClaudeSDKClient
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from .cerveau import Cerveau, CerveauBouchon
from .cerveau_claude import CerveauClaude, options_cerveau, purger_cles_api
from .config import Config
from .diffuseur import Diffuseur
from .protocole import Bonjour, Erreur, decoder_audio_entrant, decoder_message
```

3. Remplacer :

```python

RACINE_WEB = Path(__file__).resolve().parent.parent / "atlas_web"
```

par :

```python
_cerveau: Cerveau | None = None

RACINE_WEB = Path(__file__).resolve().parent.parent / "atlas_web"
# Le dossier de travail de Claude : vide, à lui seul, hors de tout projet.
DOSSIER_CERVEAU = Path.home() / ".atlas" / "cerveau"
```

4. Remplacer :

```python
@asynccontextmanager
async def _cycle_de_vie(app: FastAPI):
    global _http
    _http = httpx.AsyncClient()
    try:
        yield
    finally:
```

par :

```python
def creer_cerveau(config: Config) -> Cerveau:
    """Le cerveau unique du Core, partagé par la voix et le clavier."""
    if config.cerveau == "bouchon":
        return CerveauBouchon()
    retirees = purger_cles_api(os.environ)
    if retirees:
        _journal.warning("retiré de l'environnement, pour Claude : %s", ", ".join(retirees))

    def fabrique() -> ClaudeSDKClient:
        DOSSIER_CERVEAU.mkdir(parents=True, exist_ok=True)
        return ClaudeSDKClient(options=options_cerveau(config.cerveau_modele, DOSSIER_CERVEAU))

    return CerveauClaude(fabrique, oubli_s=config.cerveau_oubli_min * 60)


@asynccontextmanager
async def _cycle_de_vie(app: FastAPI):
    global _http, _cerveau
    _http = httpx.AsyncClient()
    _cerveau = creer_cerveau(_config)
    try:
        yield
    finally:
        await _cerveau.fermer()
        _cerveau = None
```

5. Remplacer :

```python
    assert _http is not None, "le cycle de vie de l'application n'a pas démarré"
    return {
        "transcription": ClientTranscription(_config.stt_url, _http),
        "synthese": ClientSynthese(_config.tts_url, _config.tts_voix, _http),
        "cerveau": CerveauBouchon(),
```

par :

```python
    assert _http is not None and _cerveau is not None, "le cycle de vie n'a pas démarré"
    return {
        "transcription": ClientTranscription(_config.stt_url, _http),
        "synthese": ClientSynthese(_config.tts_url, _config.tts_voix, _http),
        "cerveau": _cerveau,
```

6. Remplacer :

```python
        # un navigateur envoie toujours un en-tête Origin ; le client audio du Mac n'en
        # envoie jamais ; la clé de /ws/audio reste prévue avant la phase 2.
        await ws.close(code=FERMETURE_ORIGINE)
        return
    await ws.accept()
```

par :

```python
        # Un navigateur envoie toujours un en-tête Origin ; le client audio du Mac n'en
        # envoie jamais.
        await ws.close(code=FERMETURE_ORIGINE)
        return
    await ws.accept()
    if not _config.audio_cle:
        message = (
            "La clé du client audio n'est pas configurée : ajoute ATLAS_AUDIO_CLE dans le .env "
            "du Core, puis redémarre-le."
        )
        await ws.send_text(Erreur(code="cle_absente", message=message).model_dump_json())
        await ws.close(code=FERMETURE_CLE_ABSENTE)
        return
    authentifie = await _client_audio_authentifie(ws)
    if authentifie is None:
        return  # le client est déjà parti
    if not authentifie:
        await ws.close(code=FERMETURE_NON_AUTORISE)
        return
```

7. Remplacer :

```python
    """Le prochain message texte de la page, ou None si elle s'est déconnectée."""
```

par :

```python
    """Le prochain message texte, ou None si l'autre bout s'est déconnecté."""
```

8. Remplacer :

```python
            return texte
```

par :

```python
            return texte


async def _client_audio_authentifie(ws: WebSocket) -> bool | None:
    """Vrai si le premier message est un `Bonjour` portant la bonne clé, reçu à temps ;
    None si le client est parti avant."""
    try:
        premier = await asyncio.wait_for(_recevoir_texte(ws), DELAI_AUTHENTIFICATION_S)
    except TimeoutError:
        return False
    if premier is None:
        return None
    try:
        bonjour = decoder_message(premier)
    except ValueError:
        return False
    return isinstance(bonjour, Bonjour) and cle_valide(bonjour.cle, _config.audio_cle)
```

- [ ] **Step 5: Vérifier que tout passe**

Run: `uv run pytest tests/test_protocole.py tests/test_hub.py tests/test_hub_web.py -q && uv run pytest -q && uv run ruff check . && uv run ruff format --check .`
Expected: tout passe ; toute la suite passe (532 tests, 3 ignorés). Les tests du hub créent un `CerveauClaude` au démarrage de l'application (sans rien lancer : le client SDK ne démarre qu'à la première question) et retirent les `ANTHROPIC_*` de l'environnement du processus de test, ce qui est voulu.

- [ ] **Step 6: Commit**

```bash
git add src/atlas_core/protocole.py src/atlas_core/hub.py tests/test_protocole.py tests/test_hub.py tests/test_hub_web.py
git commit -F - <<'MSG'
Partage un seul cerveau et protège /ws/audio par une clé

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

### Task 8: Le barge-in entre deux phrases, l'interruption d'abord, la clé du client

**Files:**
- Modify: `src/atlas_audio/client.py` (7 remplacements ci-dessous)
- Test: `tests/test_client_parole.py` (nouveau, il réutilise les doublures de `tests/test_client_audio.py`)

**Interfaces:**
- Consumes: `Bonjour.cle` (Task 7, utilisé à la Task 9).
- Produces: `lire_cle_audio() -> str` dans `atlas_audio.client` (lit `ATLAS_AUDIO_CLE`, sans espaces de bord ; `ValueError` nommant la variable si elle est vide ou absente). Dans `ClientAudio` : l'attribut `_core_parle`, posé par un `Dire` qui n'est pas périmé, retiré par tout `Etat` autre que « parole » et par `_couper()` ; `_atlas_parle_encore()` vaut `_core_parle` ou l'horloge de lecture ; au barge-in, `Interruption` part au Core avant le vidage du son.

- [ ] **Step 1: Écrire les tests qui échouent**

`tests/test_client_parole.py` :

```python
"""Le client audio pendant une réponse de Claude : barge-in entre deux phrases, ordre de
l'interruption, clé du Core."""

import pytest
from test_client_audio import (
    BLOC_FORT,
    FausseHorloge,
    FauxPeripherique,
    FauxTransport,
    _client,
    _jouer,
)

from atlas_audio.client import lire_cle_audio
from atlas_core.protocole import Etat, Interruption, Reveil, StopAudio


def _interrompu(t: FauxTransport) -> bool:
    return any(isinstance(m, Interruption) for m in t.json)


async def test_le_bargein_reste_arme_dans_un_blanc_entre_deux_phrases():
    h = FausseHorloge()
    t, p = FauxTransport(), FauxPeripherique([BLOC_FORT] * 6)
    c = _client(t, p, parole=[True] * 6, reveil_au=None, horloge=h)
    await c.sur_message(Etat(valeur="parole"))
    await _jouer(c, id_enonce=1, blocs=1)
    h.avancer(2.0)  # la phrase suivante tarde : plus aucun son ne joue

    await c.boucle_capture()

    assert _interrompu(t), "« attends » dans le blanc entre deux phrases coupe Atlas"


async def test_une_reponse_muette_n_arme_pas_le_bargein():
    h = FausseHorloge()
    t, p = FauxTransport(), FauxPeripherique([BLOC_FORT] * 6)
    c = _client(t, p, parole=[True] * 6, reveil_au=0, horloge=h)
    await c.sur_message(Etat(valeur="parole"))  # muet : aucune phrase n'est dite

    await c.boucle_capture()

    assert not _interrompu(t)
    assert isinstance(t.json[0], Reveil), "le mot de réveil reste écouté"


async def test_la_reflexion_d_une_recherche_desarme_le_bargein():
    h = FausseHorloge()
    t, p = FauxTransport(), FauxPeripherique([BLOC_FORT] * 6)
    c = _client(t, p, parole=[True] * 6, reveil_au=0, horloge=h)
    await c.sur_message(Etat(valeur="parole"))
    await _jouer(c, id_enonce=1, blocs=1)  # « Je regarde ça. »
    await c.sur_message(Etat(valeur="reflexion"))
    h.avancer(2.0)

    await c.boucle_capture()

    assert not _interrompu(t)
    assert isinstance(t.json[0], Reveil), "pendant la recherche, « Hey Atlas » reprend la main"


async def test_la_fin_de_la_reponse_desarme_le_bargein_une_fois_le_son_joue():
    h = FausseHorloge()
    t, p = FauxTransport(), FauxPeripherique([BLOC_FORT] * 6)
    c = _client(t, p, parole=[True] * 6, reveil_au=None, horloge=h)
    await _jouer(c, id_enonce=1, blocs=1)
    await c.sur_message(Etat(valeur="repos"))
    h.avancer(2.0)

    await c.boucle_capture()

    assert not _interrompu(t)


async def test_une_phrase_en_vol_d_une_reponse_coupee_n_arme_pas_le_bargein():
    h = FausseHorloge()
    t, p = FauxTransport(), FauxPeripherique([BLOC_FORT] * 6)
    c = _client(t, p, parole=[True] * 6, reveil_au=0, horloge=h)
    await _jouer(c, id_enonce=1, blocs=1)
    await c.sur_message(StopAudio(id_enonce=1))  # une question tapée coupe la réponse
    await _jouer(c, id_enonce=1, blocs=1, rang=2)  # sa phrase suivante était en vol
    h.avancer(2.0)

    await c.boucle_capture()

    assert isinstance(t.json[0], Reveil), "le micro est rendu au mot de réveil"


class PeripheriqueQuiNote(FauxPeripherique):
    def __init__(self, blocs, journal: list) -> None:
        super().__init__(blocs)
        self.journal = journal

    async def vider(self) -> None:
        await super().vider()
        self.journal.append("vider")


async def test_l_interruption_part_au_core_avant_le_vidage_du_son():
    t = FauxTransport()
    p = PeripheriqueQuiNote([BLOC_FORT] * 6, t.flux)
    c = _client(t, p, parole=[True] * 6, reveil_au=None)
    await _jouer(c, id_enonce=1, blocs=1)

    await c.boucle_capture()

    ordre = [x for x in t.flux if x in ("interruption", "vider")]
    assert ordre[:2] == ["interruption", "vider"]


def test_la_cle_du_client_vient_de_l_environnement(monkeypatch):
    monkeypatch.setenv("ATLAS_AUDIO_CLE", "  cle-audio  ")
    assert lire_cle_audio() == "cle-audio"


@pytest.mark.parametrize("valeur", [None, "", "   "])
def test_sans_cle_le_client_refuse_de_demarrer(monkeypatch, valeur):
    if valeur is None:
        monkeypatch.delenv("ATLAS_AUDIO_CLE", raising=False)
    else:
        monkeypatch.setenv("ATLAS_AUDIO_CLE", valeur)
    with pytest.raises(ValueError, match="ATLAS_AUDIO_CLE"):
        lire_cle_audio()
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `uv run pytest tests/test_client_parole.py -q`
Expected: FAIL — `ImportError: cannot import name 'lire_cle_audio' from 'atlas_audio.client'`.

- [ ] **Step 3: Adapter le client**

Dans `src/atlas_audio/client.py` :

1. Remplacer :

```python


def _lire_relance_s() -> float:
```

par :

```python


def lire_cle_audio() -> str:
    """La clé que le client présente au Core dans son `Bonjour` : la même des deux côtés."""
    cle = os.environ.get("ATLAS_AUDIO_CLE", "").strip()
    if not cle:
        raise ValueError(
            "ATLAS_AUDIO_CLE manquante : mets dans le .env du client la même clé que dans "
            "celui du Core"
        )
    return cle


def _lire_relance_s() -> float:
```

2. Remplacer :

```python
        # haut-parleur. Le Core finit d'ENVOYER bien avant que le son finisse de jouer.
        self._fin_lecture = 0.0
        # Derniers blocs entendus pendant la surveillance du barge-in, avec leur
```

par :

```python
        # haut-parleur. Le Core finit d'ENVOYER bien avant que le son finisse de jouer.
        self._fin_lecture = 0.0
        # Le Core dit une réponse à voix haute : un « Dire » est arrivé, et aucun état
        # autre que « parole » ne l'a encore suivi. Le barge-in reste armé même dans un
        # blanc entre deux phrases, quand plus aucun son ne joue.
        self._core_parle = False
        # Derniers blocs entendus pendant la surveillance du barge-in, avec leur
```

3. Remplacer :

```python
        # Une échéance expire d'elle-même : le micro ne peut jamais rester sourd.
        return self._horloge() < self._fin_lecture + MARGE_SORTIE_S
```

par :

```python
        # Une échéance expire d'elle-même, et tout état autre que « parole » désarme le
        # Core : le micro ne peut jamais rester sourd.
        return self._core_parle or self._horloge() < self._fin_lecture + MARGE_SORTIE_S
```

4. Remplacer :

```python
        await self._peripherique.vider()
        await self._transport.envoyer_json(Interruption(horodatage=time.time()))
```

par :

```python
        # Le Core d'abord : il arrête la synthèse et Claude pendant que le son se vide.
        await self._transport.envoyer_json(Interruption(horodatage=time.time()))
        await self._peripherique.vider()
```

5. Remplacer :

```python
        self._id_courant = 0
        self._fin_lecture = 0.0
        self._pre_roulement.clear()
```

par :

```python
        self._id_courant = 0
        self._fin_lecture = 0.0
        self._core_parle = False
        self._pre_roulement.clear()
```

6. Remplacer :

```python
                return  # phrase en vol d'une réponse coupée : on l'ignore
```

par :

```python
                return  # phrase en vol d'une réponse coupée : on l'ignore
            self._core_parle = True
```

7. Remplacer :

```python
            # « repos » dit que le Core a fini d'ENVOYER, pas que le son est joué : il
            # n'arme ni ne désarme le barge-in, que seule l'horloge de lecture tranche.
            # Il arme en revanche la relance, qui attendra que le son se taise. Sans ce
            # signal, un blanc entre deux phrases relancerait l'écoute en pleine réponse.
```

par :

```python
            # « repos » dit que le Core a fini d'ENVOYER, pas que le son est joué : le
            # barge-in reste armé tant que l'horloge de lecture court. Mais tout état autre
            # que « parole » (repos, réflexion d'une recherche web…) dit que le Core ne
            # parle plus : le blanc qui suit n'est plus gardé. « repos » arme aussi la
            # relance, qui attendra que le son se taise ; sans ce signal, un blanc entre
            # deux phrases relancerait l'écoute en pleine réponse.
            if msg.valeur != "parole":
                self._core_parle = False
```

- [ ] **Step 4: Vérifier que tout passe**

Run: `uv run pytest tests/test_client_parole.py tests/test_client_audio.py tests/test_integration_boucle.py -q && uv run pytest -q && uv run ruff check . && uv run ruff format --check .`
Expected: tout passe, dont les 10 tests de `test_client_parole.py` ; toute la suite passe (542 tests, 3 ignorés).

- [ ] **Step 5: Commit**

```bash
git add src/atlas_audio/client.py tests/test_client_parole.py
git commit -F - <<'MSG'
Garde le barge-in armé entre deux phrases, et prévient le Core avant de vider le son

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

### Task 9: La lecture cadencée et la reconnexion

**Files:**
- Create: `src/atlas_audio/connexion.py`
- Modify: `src/atlas_audio/client.py` (10 remplacements ci-dessous, dont `principal` réécrit)
- Modify: `tests/test_client_audio.py` (l'aide `_client` transmet `attendre`)
- Test: `tests/test_client_connexion.py` (nouveau)

**Interfaces:**
- Consumes: `lire_cle_audio` (Task 8) ; `Bonjour.cle` (Task 7) ; `MessageCore` (existant).
- Produces, dans `atlas_audio.client` : `AVANCE_MAX_S = 5.0` ; `ClientAudio(..., attendre: Callable[[float], Awaitable[None]] | None = None)` (par défaut `asyncio.sleep`) ; `sur_trame` n'écrit une trame que si l'avance, cette trame comprise, reste sous `AVANCE_MAX_S` (à une demi-trame près), sinon attend, et revérifie l'énoncé après chaque attente et après l'écriture ; `async arreter()` (coupe et vide le son, sans lever si le périphérique est mort) ; `principal()` crée un `ClientAudio` neuf par connexion, envoie `Bonjour(client="m5", capacites=["aec", "vad"], cle=…)` et confie le reste à `boucle_de_connexion`.
- Produces, dans `atlas_audio.connexion` : `DELAIS_RECONNEXION_S = (1, 2, 4, 8, 16, 30)`, `FERMETURE_CLE_ABSENTE = 4000`, `FERMETURE_NON_AUTORISE = 4401`, le protocole `ClientConnecte`, `async servir_connexion(ws, client)` (trames binaires dans une file jouée par sa propre tâche, messages JSON traités aussitôt, message illisible journalisé puis ignoré ; à la fin, tâches annulées et `client.arreter()`), `async boucle_de_connexion(ouvrir, servir, attendre=asyncio.sleep, delais=DELAIS_RECONNEXION_S)` (ne rend jamais la main : délai croissant entre les tentatives, remis à zéro par une connexion acceptée, sauf si le Core a fermé en 4401 ou 4000, ce que le journal explique).

- [ ] **Step 1: Écrire les tests qui échouent**

Dans `tests/test_client_audio.py`, l'aide `_client` transmet un `attendre` :

1. Remplacer :

```python
    relance_s: float = 0.0,
```

par :

```python
    relance_s: float = 0.0,
    attendre=None,
```

2. Remplacer :

```python
        relance_s=relance_s,
```

par :

```python
        relance_s=relance_s,
        attendre=attendre,
```

Puis `tests/test_client_connexion.py` :

```python
"""Le client audio face aux longues réponses et aux coupures : lecture cadencée, connexion
servie, reconnexion."""

import asyncio
import logging

import pytest
from test_client_audio import (
    BLOC,
    BLOC_FORT,
    FausseHorloge,
    FauxPeripherique,
    FauxTransport,
    _client,
)
from websockets.exceptions import ConnectionClosedError
from websockets.frames import Close

from atlas_audio.client import AVANCE_MAX_S, DUREE_BLOC_S
from atlas_audio.connexion import boucle_de_connexion, servir_connexion
from atlas_core.protocole import Dire, Interruption, Reveil, StopAudio, encoder_audio_sortant


def _dire(id_enonce: int = 1) -> Dire:
    return Dire(id_enonce=id_enonce, rang=1, texte="Une longue réponse.")


def _trame(id_enonce: int = 1) -> bytes:
    return encoder_audio_sortant(id_enonce, BLOC)


class PeripheriqueDate(FauxPeripherique):
    """Note l'heure de chaque écriture vers le haut-parleur."""

    def __init__(self, horloge: FausseHorloge) -> None:
        super().__init__([])
        self.horloge = horloge
        self.instants: list[float] = []

    async def jouer(self, pcm: bytes) -> None:
        await super().jouer(pcm)
        self.instants.append(self.horloge.t)


# --- la lecture cadencée ----------------------------------------------------------


async def test_la_lecture_ne_prend_jamais_plus_de_cinq_secondes_d_avance():
    h = FausseHorloge()
    depart = h.t
    attentes: list[float] = []

    async def attendre(secondes: float) -> None:
        attentes.append(secondes)
        h.avancer(secondes)

    t, p = FauxTransport(), PeripheriqueDate(h)
    c = _client(t, p, parole=[], horloge=h, attendre=attendre)
    await c.sur_message(_dire())
    for _ in range(400):  # huit secondes de réponse, livrées d'un coup
        await c.sur_trame(_trame())

    assert len(p.joues) == 400
    assert attentes, "au-delà de cinq secondes d'avance, la lecture attend"
    for rang, instant in enumerate(p.instants):
        # La trame n° rang commence à jouer à depart + rang × 20 ms : elle ne part pas
        # plus de cinq secondes avant.
        assert instant >= depart + rang * DUREE_BLOC_S - AVANCE_MAX_S - 1e-9


async def test_une_coupure_pendant_l_attente_jette_la_trame():
    h = FausseHorloge()
    t, p = FauxTransport(), FauxPeripherique([])

    async def attendre(secondes: float) -> None:
        await c.sur_message(StopAudio(id_enonce=1))  # arrivé pendant l'attente
        h.avancer(secondes)

    c = _client(t, p, parole=[], horloge=h, attendre=attendre)
    await c.sur_message(_dire())
    for _ in range(251):
        await c.sur_trame(_trame())

    assert len(p.joues) == 250, "la trame qui attendait n'est jamais jouée"
    assert p.vidages == 1


class PeripheriqueCoupeEnEcrivant(FauxPeripherique):
    """Le Core coupe la réponse pendant que la première trame s'écrit."""

    client = None

    async def jouer(self, pcm: bytes) -> None:
        await super().jouer(pcm)
        await self.client.sur_message(StopAudio(id_enonce=1))


async def test_une_coupure_pendant_l_ecriture_n_arme_pas_le_bargein():
    h = FausseHorloge()
    t, p = FauxTransport(), PeripheriqueCoupeEnEcrivant([BLOC_FORT] * 6)
    c = _client(t, p, parole=[True] * 6, reveil_au=0, horloge=h)
    p.client = c
    await c.sur_message(_dire())
    await c.sur_trame(_trame())

    await c.boucle_capture()

    assert not any(isinstance(m, Interruption) for m in t.json)
    assert isinstance(t.json[0], Reveil), "l'horloge de lecture n'a pas avancé pour rien"


# --- la connexion servie ---------------------------------------------------------------


class FauxWs:
    """Rejoue ce que le Core envoie ; un `asyncio.Event` dans la suite fait attendre."""

    def __init__(self, *etapes) -> None:
        self.etapes = etapes

    def __aiter__(self):
        return self._flux()

    async def _flux(self):
        for etape in self.etapes:
            if isinstance(etape, asyncio.Event):
                await etape.wait()
                continue
            yield etape
            await asyncio.sleep(0)


async def test_un_stop_audio_passe_devant_le_son_en_attente():
    h = FausseHorloge()
    en_attente, jamais = asyncio.Event(), asyncio.Event()

    async def attendre(_secondes: float) -> None:
        en_attente.set()
        await jamais.wait()  # le haut-parleur a cinq secondes d'avance : on patiente

    t, p = FauxTransport(), FauxPeripherique([])
    c = _client(t, p, parole=[], horloge=h, attendre=attendre)
    ws = FauxWs(
        _dire().model_dump_json(),
        *[_trame()] * 300,
        en_attente,
        StopAudio(id_enonce=1).model_dump_json(),
    )

    await asyncio.wait_for(servir_connexion(ws, c), timeout=2)

    assert len(p.joues) == 250
    assert p.vidages >= 1, "le StopAudio a été traité sans attendre la lecture"


async def test_un_message_illisible_du_core_ne_coupe_pas_la_connexion():
    t, p = FauxTransport(), FauxPeripherique([])
    c = _client(t, p, parole=[])
    ws = FauxWs("pas du json", '{"type":"inconnu"}', _dire().model_dump_json(), _trame())

    await asyncio.wait_for(servir_connexion(ws, c), timeout=2)

    assert p.joues == [BLOC]


class PeripheriqueSilencieux(FauxPeripherique):
    """Un micro qui ne livre jamais rien : la capture reste en attente."""

    async def lire_bloc(self) -> bytes:
        await asyncio.Event().wait()
        return b""


async def test_la_fin_de_la_connexion_arrete_le_son_et_ses_taches():
    t, p = FauxTransport(), PeripheriqueSilencieux([])
    c = _client(t, p, parole=[])

    await asyncio.wait_for(servir_connexion(FauxWs(_dire().model_dump_json()), c), timeout=2)

    assert p.vidages == 1, "le son d'une connexion perdue se tait"
    autres = [x for x in asyncio.all_tasks() if x is not asyncio.current_task()]
    assert all(x.done() for x in autres), "capture et lecture sont arrêtées"


# --- la reconnexion ------------------------------------------------------------------


class Fin(Exception):
    """Arrête la boucle de connexion, qui sinon tourne toujours."""


def _refus(code: int) -> ConnectionClosedError:
    return ConnectionClosedError(Close(code, ""), None)


class Ouverture:
    def __init__(self, scenario) -> None:
        self.scenario = scenario

    async def __aenter__(self):
        if isinstance(self.scenario, OSError):
            raise self.scenario  # le Core ne répond pas
        return self.scenario

    async def __aexit__(self, *exc) -> bool:
        return False


class Core:
    """Chaque ouverture rejoue le scénario suivant : `OSError` à la connexion, ou une
    connexion acceptée que `servir` perd (normalement, ou sur un code de fermeture)."""

    def __init__(self, *scenarios) -> None:
        self.scenarios = list(scenarios)
        self.servies: list = []

    def ouvrir(self) -> Ouverture:
        return Ouverture(self.scenarios.pop(0))

    async def servir(self, ws) -> None:
        self.servies.append(ws)
        if isinstance(ws, Exception):
            raise ws


async def _delais(core: Core, tentatives: int) -> list[float]:
    delais: list[float] = []

    async def attendre(secondes: float) -> None:
        delais.append(secondes)
        if len(delais) == tentatives:
            raise Fin

    with pytest.raises(Fin):
        await boucle_de_connexion(core.ouvrir, core.servir, attendre=attendre)
    return delais


async def test_les_tentatives_s_espacent_jusqu_a_trente_secondes():
    core = Core(*[OSError("refusé")] * 8)
    assert await _delais(core, 8) == [1, 2, 4, 8, 16, 30, 30, 30]


async def test_une_connexion_acceptee_remet_le_compte_a_zero():
    core = Core(OSError(), OSError(), "connexion perdue", OSError())
    assert await _delais(core, 4) == [1, 2, 1, 2]
    assert core.servies == ["connexion perdue"]


async def test_une_cle_refusee_ne_remet_pas_le_compte_a_zero(caplog):
    core = Core(OSError(), _refus(4401), _refus(4401))
    with caplog.at_level(logging.ERROR, logger="atlas_audio.connexion"):
        assert await _delais(core, 3) == [1, 2, 4]
    assert "ATLAS_AUDIO_CLE" in caplog.text


async def test_un_core_sans_cle_est_signale(caplog):
    with caplog.at_level(logging.ERROR, logger="atlas_audio.connexion"):
        await _delais(Core(_refus(4000)), 1)
    assert "ATLAS_AUDIO_CLE" in caplog.text and "son .env" in caplog.text


async def test_une_connexion_perdue_en_route_est_retentee():
    core = Core(_refus(1011), "de nouveau là")
    assert await _delais(core, 2) == [1, 1]
    assert len(core.servies) == 2
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `uv run pytest tests/test_client_connexion.py -q`
Expected: FAIL — `ImportError: cannot import name 'AVANCE_MAX_S' from 'atlas_audio.client'`.

- [ ] **Step 3: Écrire la connexion**

`src/atlas_audio/connexion.py` :

```python
"""La connexion du client audio au Core : la servir, et la retrouver quand elle se perd."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable, Sequence
from contextlib import AbstractAsyncContextManager
from typing import Protocol

from pydantic import TypeAdapter, ValidationError

from atlas_core.protocole import MessageCore

_journal = logging.getLogger(__name__)

# Entre deux tentatives de connexion au Core ; le dernier délai se répète.
DELAIS_RECONNEXION_S = (1, 2, 4, 8, 16, 30)
# Fermetures du Core qui disent que la clé du client est absente ou refusée.
FERMETURE_CLE_ABSENTE = 4000
FERMETURE_NON_AUTORISE = 4401

_MESSAGES_CORE: TypeAdapter[MessageCore] = TypeAdapter(MessageCore)


class ClientConnecte(Protocol):
    """Ce que la connexion attend du client audio (`ClientAudio`)."""

    async def boucle_capture(self) -> None: ...
    async def sur_message(self, msg) -> None: ...
    async def sur_trame(self, trame: bytes) -> None: ...
    async def arreter(self) -> None: ...


async def servir_connexion(ws, client: ClientConnecte) -> None:
    """Sert une connexion au Core jusqu'à sa fin. L'audio d'Atlas part dans une file que
    la tâche de lecture vide à son rythme ; les messages de contrôle, eux, sont traités
    dès leur arrivée : un `StopAudio` n'attend jamais derrière des secondes de son."""
    file: asyncio.Queue[bytes] = asyncio.Queue()
    taches = [
        asyncio.create_task(client.boucle_capture()),
        asyncio.create_task(_jouer_la_file(client, file)),
    ]
    try:
        async for recu in ws:
            if isinstance(recu, bytes):
                file.put_nowait(recu)
                continue
            try:
                msg = _MESSAGES_CORE.validate_json(recu)
            except ValidationError as e:
                _journal.warning("message du Core illisible : %s", e)
                continue
            await client.sur_message(msg)
    finally:
        for tache in taches:
            tache.cancel()
        for tache in taches:
            with contextlib.suppress(asyncio.CancelledError):
                await tache
        await client.arreter()


async def _jouer_la_file(client: ClientConnecte, file: asyncio.Queue[bytes]) -> None:
    while True:
        trame = await file.get()
        try:
            await client.sur_trame(trame)
        except ValueError as e:
            _journal.warning("trame audio du Core illisible : %s", e)


def _code_de_fermeture(e: BaseException) -> int | None:
    """Le code de fermeture envoyé par le Core, si l'exception en porte un."""
    return getattr(getattr(e, "rcvd", None), "code", None)


async def boucle_de_connexion(
    ouvrir: Callable[[], AbstractAsyncContextManager],
    servir: Callable[[object], Awaitable[None]],
    attendre: Callable[[float], Awaitable[None]] = asyncio.sleep,
    delais: Sequence[float] = DELAIS_RECONNEXION_S,
) -> None:
    """Garde le client branché au Core : s'il disparaît, on se reconnecte, de plus en
    plus patiemment (1, 2, 4, 8, 16 puis 30 s). Une connexion acceptée remet ce compte à
    zéro ; une clé refusée, non."""
    echecs = 0
    while True:
        acceptee = False
        try:
            async with ouvrir() as ws:
                acceptee = True
                await servir(ws)
            _journal.warning("le Core a fermé la connexion")
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 — on se reconnecte, quoi qu'il arrive
            code = _code_de_fermeture(e)
            if code == FERMETURE_NON_AUTORISE:
                acceptee = False
                _journal.error("le Core refuse la clé : vérifie ATLAS_AUDIO_CLE des deux côtés")
            elif code == FERMETURE_CLE_ABSENTE:
                acceptee = False
                _journal.error("le Core n'a pas de clé : ajoute ATLAS_AUDIO_CLE dans son .env")
            else:
                _journal.warning("Core injoignable ou connexion perdue (%s)", type(e).__name__)
        if acceptee:
            echecs = 0
        delai = delais[min(echecs, len(delais) - 1)]
        echecs += 1
        _journal.info("nouvelle tentative de connexion dans %s s", delai)
        await attendre(delai)
```

- [ ] **Step 4: Adapter le client**

Dans `src/atlas_audio/client.py` :

1. Remplacer :

```python
Deux boucles concurrentes : l'une lit le micro et parle au Core, l'autre reçoit
du Core et joue le son. Le client ne décide de rien d'autre que du barge-in —
il le décide localement parce que 200 ms d'aller-retour réseau rendraient
l'interruption molle — et de la relance : une fois la réponse d'Atlas jouée, il
rouvre l'écoute un moment sans mot de réveil, pour que la conversation continue.
```

par :

```python
Trois tâches par connexion au Core (voir `connexion.py`) : l'une lit le micro et parle
au Core, une autre reçoit du Core, et la dernière joue le son à son rythme, sans jamais
prendre plus de quelques secondes d'avance. Le client ne décide de rien d'autre que du
barge-in — il le décide localement parce que 200 ms d'aller-retour réseau rendraient
l'interruption molle — et de la relance : une fois la réponse d'Atlas jouée, il rouvre
l'écoute un moment sans mot de réveil, pour que la conversation continue. Si le Core
disparaît, le client se reconnecte seul.
```

2. Remplacer :

```python
from collections.abc import Callable
```

par :

```python
from collections.abc import Awaitable, Callable
```

3. Remplacer :

```python
from .aec import ouvrir_peripherique
```

par :

```python
from .aec import ouvrir_peripherique
from .connexion import boucle_de_connexion, servir_connexion
```

4. Remplacer :

```python
MARGE_SORTIE_S = 0.15  # latence de sortie du haut-parleur, à régler au banc
```

par :

```python
MARGE_SORTIE_S = 0.15  # latence de sortie du haut-parleur, à régler au banc
# Au plus ce son d'avance confié au haut-parleur (le binaire Swift en accepterait 30 s
# avant de freiner) : un vidage reste immédiat, et l'horloge de lecture reste juste.
AVANCE_MAX_S = 5.0
```

5. Remplacer :

```python
        relance_s: float = 0.0,
```

par :

```python
        relance_s: float = 0.0,
        attendre: Callable[[float], Awaitable[None]] | None = None,
```

6. Remplacer :

```python
        self._horloge = horloge or time.monotonic
```

par :

```python
        self._horloge = horloge or time.monotonic
        self._attendre = attendre or asyncio.sleep
```

7. Remplacer :

```python
        identifiant, pcm = decoder_audio_sortant(trame)
        if identifiant <= self._id_coupe or identifiant != self._id_courant:
            return  # trame d'un énoncé interrompu : on la jette
        await self._peripherique.jouer(pcm)
        self._fin_lecture = max(self._horloge(), self._fin_lecture) + DUREE_BLOC_S
```

par :

```python
        """Joue une trame, sans jamais dépasser `AVANCE_MAX_S` d'avance : au-delà, on
        attend que le haut-parleur en ait joué une partie. Une coupure pendant l'attente
        ou pendant l'écriture jette la trame."""
        identifiant, pcm = decoder_audio_sortant(trame)
        while True:
            if not self._a_jouer(identifiant):
                return  # trame d'un énoncé interrompu : on la jette
            # L'avance qu'aurait le haut-parleur une fois cette trame écrite ; la
            # demi-trame de marge absorbe les arrondis de l'horloge.
            avance = self._fin_lecture - self._horloge() + DUREE_BLOC_S
            if avance <= AVANCE_MAX_S + DUREE_BLOC_S / 2:
                break
            await self._attendre(avance - AVANCE_MAX_S)
        await self._peripherique.jouer(pcm)
        if self._a_jouer(identifiant):
            # Sinon, coupée pendant l'écriture : le vidage l'a suivie, l'horloge n'avance pas.
            self._fin_lecture = max(self._horloge(), self._fin_lecture) + DUREE_BLOC_S

    def _a_jouer(self, identifiant: int) -> bool:
        return identifiant > self._id_coupe and identifiant == self._id_courant

    async def arreter(self) -> None:
        """La connexion au Core est perdue : ce qui restait à jouer se tait."""
        self._couper()
        with contextlib.suppress(Exception):  # le binaire Swift a pu mourir avec elle
            await self._peripherique.vider()
```

8. Remplacer :

```python
    import json

    import websockets
    from pydantic import TypeAdapter

    from atlas_core.protocole import MessageCore

    adaptateur = TypeAdapter(MessageCore)
    logging.basicConfig(level=logging.INFO)
    # Réglages et réveilleur d'abord : une variable mal formée ou un modèle absent
    # doit échouer avant que le périphérique audio soit ouvert.
    reglages = lire_reglages()
```

par :

```python
    import websockets

    logging.basicConfig(level=logging.INFO)
    # Réglages, clé et réveilleur d'abord : une variable mal formée ou un modèle absent
    # doit échouer avant que le périphérique audio soit ouvert.
    reglages = lire_reglages()
    cle = lire_cle_audio()
```

9. Remplacer :

```python
    peripherique = await ouvrir_peripherique()

    async with websockets.connect(URL_CORE) as ws:
        transport = TransportWebSocket(ws)
        client = ClientAudio(
            transport=transport,
            peripherique=peripherique,
            detecteur=DetecteurVoix(),
```

par :

```python
    detecteur = DetecteurVoix()
    peripherique = await ouvrir_peripherique()

    async def servir(ws) -> None:
        transport = TransportWebSocket(ws)
        # Un client neuf à chaque connexion : le Core ouvre une session neuve, dont les
        # énoncés repartent de 1 ; les repères de l'ancien client les jetteraient tous.
        client = ClientAudio(
            transport=transport,
            peripherique=peripherique,
            detecteur=detecteur,
```

10. Remplacer :

```python
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
```

par :

```python
        await transport.envoyer_json(Bonjour(client="m5", capacites=["aec", "vad"], cle=cle))
        _journal.info("connecté au Core")
        await servir_connexion(ws, client)

    try:
        await boucle_de_connexion(lambda: websockets.connect(URL_CORE), servir)
    finally:
        await peripherique.fermer()
```

- [ ] **Step 5: Vérifier que tout passe**

Run: `uv run pytest tests/test_client_connexion.py tests/test_client_audio.py tests/test_client_parole.py tests/test_integration_boucle.py -q && uv run pytest -q && uv run ruff check . && uv run ruff format --check .`
Expected: tout passe, dont les 11 tests de `test_client_connexion.py` ; toute la suite passe (553 tests, 3 ignorés). `src/atlas_audio/client.py` fait 414 lignes.

- [ ] **Step 6: Commit**

```bash
git add src/atlas_audio/connexion.py src/atlas_audio/client.py tests/test_client_audio.py tests/test_client_connexion.py
git commit -F - <<'MSG'
Cadence la lecture et reconnecte seul le client audio au Core

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

### Task 10: Le déploiement sur le néo

**Files:**
- Create: `scripts/neo/LISEZMOI.md`, `scripts/neo/fr.atlas.core.plist`, `scripts/neo/installer_service.sh` (exécutable)
- Test: `tests/test_neo.py`

**Interfaces:**
- Consumes: `make run-core` (existant, charge `.env`) ; les variables de la Task 1.
- Produces: le modèle du service `fr.atlas.core` (repères `__DOSSIER__`, `__MAISON__`, `__UTILISATEUR__`) ; `installer_service.sh` (sans argument : vérifie `.env`, puis installe avec sudo ; `--apercu` : affiche le service rempli, sans rien installer) ; le guide pas à pas (spec §8).

- [ ] **Step 1: Écrire les tests qui échouent**

`tests/test_neo.py` :

```python
"""Le déploiement sur le néo : le modèle du service launchd, son installateur, son guide."""

import plistlib
import re
import subprocess
from pathlib import Path

import pytest

NEO = Path(__file__).resolve().parent.parent / "scripts" / "neo"


def _service() -> dict:
    modele = (NEO / "fr.atlas.core.plist").read_text()
    rempli = (
        modele.replace("__DOSSIER__", "/Users/atlas/atlas")
        .replace("__MAISON__", "/Users/atlas")
        .replace("__UTILISATEUR__", "atlas")
    )
    return plistlib.loads(rempli.encode())


def test_le_service_lance_le_core_et_le_relance_s_il_tombe():
    service = _service()
    assert service["Label"] == "fr.atlas.core"
    assert service["ProgramArguments"] == ["/usr/bin/make", "run-core"]
    assert service["WorkingDirectory"] == "/Users/atlas/atlas"
    assert service["UserName"] == "atlas", "jamais root : Claude tourne sous l'utilisateur"
    assert service["RunAtLoad"] is True and service["KeepAlive"] is True


def test_le_service_trouve_uv_et_claude():
    environnement = _service()["EnvironmentVariables"]
    assert environnement["HOME"] == "/Users/atlas"
    assert environnement["PATH"].split(":")[0] == "/Users/atlas/.local/bin"


def test_le_journal_du_service_va_dans_donnees():
    service = _service()
    assert service["StandardOutPath"] == "/Users/atlas/atlas/donnees/logs/core.log"
    assert service["StandardErrorPath"] == service["StandardOutPath"]


def test_l_installateur_est_un_script_bash_valide():
    script = NEO / "installer_service.sh"
    assert script.stat().st_mode & 0o111, "le script doit être exécutable"
    subprocess.run(["bash", "-n", str(script)], check=True)


def test_l_apercu_de_l_installateur_remplit_le_modele():
    script = NEO / "installer_service.sh"
    sortie = subprocess.run(
        ["bash", str(script), "--apercu"], check=True, capture_output=True, text=True
    ).stdout
    assert "__" not in sortie, "tous les repères sont remplacés"
    service = plistlib.loads(sortie.encode())
    assert service["WorkingDirectory"] == str(NEO.parent.parent)
    assert service["UserName"] and service["EnvironmentVariables"]["HOME"]


@pytest.mark.parametrize(
    ("contenu", "manque"),
    [
        (None, ".env"),
        (
            "ATLAS_WEB_CLE=a\nATLAS_AUDIO_CLE=b\n# CLAUDE_CODE_OAUTH_TOKEN=\n",
            "CLAUDE_CODE_OAUTH_TOKEN",
        ),
        ("ATLAS_WEB_CLE=a\nATLAS_AUDIO_CLE=\nCLAUDE_CODE_OAUTH_TOKEN=c\n", "ATLAS_AUDIO_CLE"),
    ],
)
def test_l_installateur_refuse_un_env_incomplet(tmp_path, contenu, manque):
    # Une copie du dépôt réduite au script et au modèle : il s'arrête avant tout sudo.
    (tmp_path / "scripts" / "neo").mkdir(parents=True)
    for nom in ("installer_service.sh", "fr.atlas.core.plist"):
        (tmp_path / "scripts" / "neo" / nom).write_bytes((NEO / nom).read_bytes())
    if contenu is not None:
        (tmp_path / ".env").write_text(contenu)

    resultat = subprocess.run(
        ["bash", str(tmp_path / "scripts" / "neo" / "installer_service.sh")],
        capture_output=True,
        text=True,
    )

    assert resultat.returncode == 1
    assert manque in resultat.stderr


@pytest.mark.parametrize("fichier", sorted(p.name for p in NEO.iterdir()))
def test_rien_de_prive_dans_le_deploiement(fichier):
    texte = (NEO / fichier).read_text()
    assert not re.search(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", texte), "aucune adresse IP"
    assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", texte), "aucune adresse e-mail"
    assert not re.search(r"sk-ant-\w", texte), "aucun jeton"
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `uv run pytest tests/test_neo.py -q`
Expected: FAIL — `FileNotFoundError` sur `scripts/neo` (le dossier n'existe pas encore).

- [ ] **Step 3: Écrire le modèle du service**

`scripts/neo/fr.atlas.core.plist` :

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<!--
  Modèle du service launchd du Core d'Atlas, sur le néo. Ne pas l'installer tel quel :
  installer_service.sh y remplace les repères (dossier du dépôt, dossier personnel,
  utilisateur), puis le dépose dans /Library/LaunchDaemons. Le Core démarre avec le néo,
  sans session ouverte, et launchd le relance s'il tombe. `make run-core` charge le .env
  du dépôt.
-->
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>fr.atlas.core</string>
    <key>UserName</key>
    <string>__UTILISATEUR__</string>
    <key>WorkingDirectory</key>
    <string>__DOSSIER__</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/make</string>
        <string>run-core</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>HOME</key>
        <string>__MAISON__</string>
        <key>PATH</key>
        <string>__MAISON__/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>ThrottleInterval</key>
    <integer>10</integer>
    <key>StandardOutPath</key>
    <string>__DOSSIER__/donnees/logs/core.log</string>
    <key>StandardErrorPath</key>
    <string>__DOSSIER__/donnees/logs/core.log</string>
</dict>
</plist>
```

- [ ] **Step 4: Écrire l'installateur**

`scripts/neo/installer_service.sh` :

```bash
#!/usr/bin/env bash
# Installe (ou réinstalle) le service launchd qui lance le Core d'Atlas au démarrage du
# néo et le relance s'il tombe. À lancer depuis le dépôt cloné sur le néo, en tant que
# l'utilisateur qui fera tourner Atlas (pas en root) : le script demande lui-même sudo
# pour écrire dans /Library/LaunchDaemons.
#
#   ./scripts/neo/installer_service.sh            installe le service
#   ./scripts/neo/installer_service.sh --apercu   affiche le service, sans rien installer
set -euo pipefail

ETIQUETTE="fr.atlas.core"
DOSSIER="$(cd "$(dirname "$0")/../.." && pwd)"
MODELE="$DOSSIER/scripts/neo/$ETIQUETTE.plist"
CIBLE="/Library/LaunchDaemons/$ETIQUETTE.plist"
UTILISATEUR="$(id -un)"

generer() {
    sed -e "s|__DOSSIER__|$DOSSIER|g" \
        -e "s|__MAISON__|$HOME|g" \
        -e "s|__UTILISATEUR__|$UTILISATEUR|g" \
        "$MODELE"
}

if [[ "${1:-}" == "--apercu" ]]; then
    generer
    exit 0
fi
if [[ "$UTILISATEUR" == "root" ]]; then
    echo "Lance ce script sans sudo : il le demandera lui-même." >&2
    exit 1
fi
if [[ ! -f "$DOSSIER/.env" ]]; then
    echo "Il manque $DOSSIER/.env : écris-le d'abord (étape 4 du LISEZMOI)." >&2
    exit 1
fi
for nom in ATLAS_WEB_CLE ATLAS_AUDIO_CLE CLAUDE_CODE_OAUTH_TOKEN; do
    if ! grep -Eq "^${nom}=.+" "$DOSSIER/.env"; then
        echo "Il manque $nom dans $DOSSIER/.env (étapes 3 et 4 du LISEZMOI)." >&2
        exit 1
    fi
done

mkdir -p "$DOSSIER/donnees/logs"
TEMPORAIRE="$(mktemp)"
trap 'rm -f "$TEMPORAIRE"' EXIT
generer >"$TEMPORAIRE"
plutil -lint "$TEMPORAIRE" >/dev/null

sudo launchctl bootout "system/$ETIQUETTE" 2>/dev/null || true
sudo install -m 644 -o root -g wheel "$TEMPORAIRE" "$CIBLE"
sudo launchctl bootstrap system "$CIBLE"
echo "Service $ETIQUETTE installé : le Core tourne, et redémarrera avec le néo."
echo "Son journal : tail -f $DOSSIER/donnees/logs/core.log"
```

Puis : `chmod +x scripts/neo/installer_service.sh`. Ne lancez jamais ce script sans `--apercu` : il demande sudo et installe un service système ; c'est David qui le lance, sur le néo.

- [ ] **Step 5: Écrire le guide**

`scripts/neo/LISEZMOI.md` :

````markdown
# Le Core d'Atlas sur le néo

Le Core quitte le Mac de développement pour le MacBook néo de la baie : il y tourne en
service, démarre avec la machine et redémarre s'il tombe. Le client audio reste sur le M5,
et la page s'ouvre à l'adresse du néo.

Dans ce guide, `neo.local` désigne le néo sur le réseau local : remplace-le par son nom ou
son adresse chez toi. Rien de ce qui suit ne sort du réseau local.

## 1. Installer les outils et le dépôt

Sur le néo, dans un terminal (ou par SSH) :

```bash
xcode-select --install          # make et git, si ce n'est pas déjà fait
curl -LsSf https://astral.sh/uv/install.sh | sh
curl -fsSL https://claude.ai/install.sh | bash
git clone https://github.com/flynnslegacy/atlas.git ~/atlas
cd ~/atlas
make install
```

Ouvre un nouveau terminal après les deux installateurs, pour que `uv` et `claude` soient
dans le `PATH`.

## 2. Garder le néo éveillé

Le Core doit répondre à toute heure : le néo ne doit pas se mettre en veille. Vérifie-le
dans Réglages Système, ou avec `pmset -g` (la ligne `sleep` doit valoir 0).

## 3. Connecter Claude à l'abonnement

```bash
claude setup-token
```

La commande ouvre la connexion à ton compte Claude dans un navigateur ; par SSH, elle
affiche une adresse à ouvrir ailleurs et un code à recoller dans le terminal. Elle affiche
ensuite un jeton valable un an.

**Ce jeton est un secret.** Il ne va que dans le `.env` du néo (étape 4), jamais dans le
dépôt, jamais dans un message. Note dans ton agenda de le renouveler (même commande) avant
son échéance, dans un an.

## 4. Écrire le `.env` du néo

```bash
cp .env.example .env
chmod 600 .env
```

Puis, dans `.env` :

- `ATLAS_STT_URL` et `ATLAS_TTS_URL` : les adresses des services sur l'Unraid ;
- `ATLAS_WEB_CLE` : la clé de la page (la même que sur le M5 si tu veux garder tes
  appareils déjà connectés, sinon une nouvelle) ;
- `ATLAS_AUDIO_CLE` : une nouvelle clé, que tu recopieras sur le M5 (étape 7) ;
- `CLAUDE_CODE_OAUTH_TOKEN` : décommente la ligne et colle le jeton de l'étape 3 ;
- `ATLAS_CERVEAU=claude`, et au besoin `ATLAS_CERVEAU_MODELE` et `ATLAS_CERVEAU_OUBLI_MIN`.

Pour générer une clé :

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(24))"
```

## 5. Essayer le Core à la main

```bash
make run-core
```

Depuis le M5 : `curl http://neo.local:8080/sante` doit répondre `{"ok":true,…}`. Arrête
ensuite le Core avec Ctrl-C.

## 6. Installer le service

```bash
./scripts/neo/installer_service.sh
```

Le script vérifie le `.env`, demande ton mot de passe (sudo) et installe le service
`fr.atlas.core`. Le Core démarre aussitôt, puis à chaque démarrage du néo, même sans
session ouverte ; launchd le relance s'il tombe.

- Le journal : `tail -f ~/atlas/donnees/logs/core.log`
- Redémarrer le Core : `sudo launchctl kickstart -k system/fr.atlas.core`
- Arrêter le service : `sudo launchctl bootout system/fr.atlas.core`
- Mettre Atlas à jour : `git pull && make install`, puis redémarrer le Core.

## 7. Brancher le M5 sur le néo

Sur le M5, arrête le Core s'il tourne encore, puis, dans le `.env` du M5 :

- `ATLAS_CORE_URL=ws://neo.local:8080/ws/audio`
- `ATLAS_AUDIO_CLE` : la même clé que sur le néo.

Puis `make run-audio`. Si le Core disparaît (redémarrage du néo, coupure du réseau), le
client audio se reconnecte seul : 1, 2, 4, 8, 16 puis 30 secondes entre les tentatives.
Une clé refusée est signalée dans son journal.

## 8. Ouvrir la page

Sur l'iPhone, l'iPad ou le Mac : `http://neo.local:8080/`, avec la clé `ATLAS_WEB_CLE`.
````

- [ ] **Step 6: Vérifier que tout passe**

Run: `uv run pytest tests/test_neo.py -q && bash scripts/neo/installer_service.sh --apercu | plutil -lint - && uv run pytest -q && uv run ruff check . && uv run ruff format --check .`
Expected: 11 tests passent ; `plutil` répond `<stdin>: OK` ; toute la suite passe (564 tests, 3 ignorés).

- [ ] **Step 7: Commit**

```bash
git add scripts/neo/LISEZMOI.md scripts/neo/fr.atlas.core.plist scripts/neo/installer_service.sh tests/test_neo.py
git commit -F - <<'MSG'
Prépare le déploiement du Core sur le néo

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

### Task 11: L'essai réel du cerveau, et les specs à jour

**Files:**
- Create: `scripts/essai_cerveau.py`
- Modify: `docs/superpowers/specs/2026-09-22-atlas-design.md` (§6.2, §6.6, §13, §15)
- Modify: `docs/superpowers/specs/2026-09-24-phase-2a-cerveau-design.md` (l'exemple de ligne de date)

**Interfaces:**
- Consumes: `CerveauClaude`, `options_cerveau`, `purger_cles_api`, `RECHERCHE`, `ErreurCerveau` (Task 5) ; `Config` (Task 1).
- Produces: un script lancé à la main par David (section finale), hors de `make test` (il n'est ni dans `tests/` ni nommé `test_*`).

- [ ] **Step 1: Écrire le script d'essai**

`scripts/essai_cerveau.py` :

```python
"""Essai réel du cerveau, hors de `make test` : le vrai CLI claude, les options exactes.

Six questions : une présentation, l'heure (la ligne de date), un rappel de la question
précédente (la conversation), une recherche web, une longue réponse coupée en route, puis
une question juste après la coupure (le ménage). Chaque question part de sa propre tâche,
comme les tours de la session.

Il consomme un peu de l'abonnement Claude : à lancer à la main, avec l'accord de David.

    uv run python scripts/essai_cerveau.py
"""

from __future__ import annotations

import asyncio
import os
import re
import tempfile
import time
from pathlib import Path

from claude_agent_sdk import ClaudeSDKClient

from atlas_core.cerveau import RECHERCHE, ErreurCerveau
from atlas_core.cerveau_claude import CerveauClaude, options_cerveau, purger_cles_api
from atlas_core.config import Config

QUESTIONS = [
    ("Bonjour Atlas, présente-toi en une phrase.", None),
    ("Quelle heure est-il, et quel jour sommes-nous ?", None),
    ("Qu'est-ce que je t'ai demandé juste avant ?", None),
    ("Quel temps fait-il à Paris aujourd'hui ?", None),
    ("Raconte-moi en détail l'histoire de la tour Eiffel.", 120),
    ("Pardon, je t'ai coupé : résume-la en une phrase.", None),
]


async def poser(cerveau: CerveauClaude, texte: str, couper_apres: int | None) -> None:
    print(f"\n» {texte}")
    debut = time.monotonic()
    premier: float | None = None
    rendu = 0
    flux = cerveau.repondre(texte)
    try:
        async for fragment in flux:
            if premier is None:
                premier = time.monotonic() - debut
                print(f"  [premier fragment après {premier:.1f} s]")
            if fragment is RECHERCHE:
                print("  [recherche web]")
                continue
            print(fragment, end="", flush=True)
            rendu += len(fragment)
            if couper_apres is not None and rendu >= couper_apres:
                print("\n  [coupé ici, comme par un barge-in]")
                break
    except ErreurCerveau as e:
        print(f"\n  [erreur] {e}")
    finally:
        await flux.aclose()
    print(f"\n  [{time.monotonic() - debut:.1f} s]")


def _transcriptions(dossier: Path) -> list[Path]:
    """Les transcriptions que le CLI aurait écrites pour ce dossier de travail."""
    projets = Path.home() / ".claude" / "projects"
    if not projets.is_dir():
        return []
    # Le CLI range chaque dossier de travail sous un nom où tout ce qui n'est ni lettre ni
    # chiffre devient « - ».
    marque = re.sub(r"[^A-Za-z0-9]", "-", dossier.name)
    return [f for d in projets.iterdir() if marque in d.name for f in d.glob("*.jsonl")]


async def principal() -> None:
    config = Config.depuis_environnement()
    retirees = purger_cles_api(os.environ)
    if retirees:
        print(f"Retiré de l'environnement : {', '.join(retirees)}")
    print(f"Modèle : {config.cerveau_modele}")
    with tempfile.TemporaryDirectory(prefix="atlas-essai-") as nom:
        dossier = Path(nom).resolve()
        cerveau = CerveauClaude(
            lambda: ClaudeSDKClient(options=options_cerveau(config.cerveau_modele, dossier))
        )
        try:
            for texte, couper_apres in QUESTIONS:
                await asyncio.create_task(poser(cerveau, texte, couper_apres))
        finally:
            await cerveau.fermer()
        ecrites = _transcriptions(dossier)
    if ecrites:
        print(f"\nATTENTION : le CLI a écrit {len(ecrites)} transcription(s) sur le disque :")
        for chemin in ecrites:
            print(f"  {chemin}")
    else:
        print("\nAucune transcription écrite sur le disque par le CLI.")


if __name__ == "__main__":
    asyncio.run(principal())
```

**Ne le lancez pas** : il appelle le vrai Claude et consomme l'abonnement de David. Vérifiez seulement qu'il se compile : `uv run python -m py_compile scripts/essai_cerveau.py`.

- [ ] **Step 2: Amender la spec parente**

Dans `docs/superpowers/specs/2026-09-22-atlas-design.md` :

1. Remplacer :

```markdown
d'abonnement et non une clé API — emprunté à ethanplusai, et vérifié par un test.

**Rotation de contexte.** Quand le contexte approche de sa limite, le Core fait produire
```

par :

```markdown
d'abonnement et non une clé API — emprunté à ethanplusai, et vérifié par un test.

**Amendé le 24/09/2026 (phase 2a).** Le Brain passe par le SDK Agent de Claude
(`claude-agent-sdk`), qui pilote ce même CLI en `stream-json`, connecté à l'abonnement de
David. En 2a, Claude n'a que la recherche web, aucun serveur MCP et aucun réglage de la
machine ; le serveur MCP d'Atlas arrive en 2c. La rotation de contexte avec résumé
ci-dessous arrive en 2b : d'ici là, le compactage automatique de Claude Code gère un
contexte qui se remplit, et la conversation repart de zéro après
`ATLAS_CERVEAU_OUBLI_MIN` minutes sans échange. Voir `2026-09-24-phase-2a-cerveau-design.md`.

**Rotation de contexte.** Quand le contexte approche de sa limite, le Core fait produire
```

2. Remplacer :

```markdown
| `hello` | `{client, sample_rate, caps: ["aec","vad","wakeword"]}` |
```

par :

```markdown
| `hello` | `{client, sample_rate, caps: ["aec","vad","wakeword"], key}` |
```

3. Remplacer :

```markdown
| `confirm_response` | `{request_id, accepted: bool}` |
```

par :

```markdown
| `confirm_response` | `{request_id, accepted: bool}` |

**Amendé le 24/09/2026 (phase 2a).** `hello` porte la clé du client audio
(`ATLAS_AUDIO_CLE`) et doit être le premier message, dans les 5 s : sinon le Core ferme
la connexion (4401). Sans clé configurée, le Core refuse tout client audio (4000).
```

4. Remplacer :

```markdown
- **Vérification de l'origine** sur toutes les routes qui modifient un état.
```

par :

```markdown
- **Vérification de l'origine** sur toutes les routes qui modifient un état.
- **`/ws/audio` protégé par une clé** (amendé le 24/09/2026, phase 2a) : `ATLAS_AUDIO_CLE`,
  dans le `hello` du client audio, comparée en temps constant. Les navigateurs restent
  refusés avant même l'acceptation.
```

5. Remplacer :

```markdown
et le document produit se relit sans retouche.
```

par :

```markdown
et le document produit se relit sans retouche.
**Amendé le 24/09/2026.** La phase 2 est découpée en trois étapes, chacune avec sa spec,
son plan et sa fusion : 2a, le cerveau branché (`2026-09-24-phase-2a-cerveau-design.md`) ;
2b, la mémoire ; 2c, outils et permissions.
```

- [ ] **Step 3: Corriger l'exemple de la spec 2a**

Dans `docs/superpowers/specs/2026-09-24-phase-2a-cerveau-design.md` (le 24 septembre 2026 est un jeudi) :

Remplacer :

```markdown
Chaque question part précédée d'une ligne de contexte, par exemple `[mercredi 24 septembre 2026, 21 h 50]`. Claude
```

par :

```markdown
Chaque question part précédée d'une ligne de contexte, par exemple `[jeudi 24 septembre 2026, 21 h 50]`. Claude
```

- [ ] **Step 4: Vérifier que tout passe**

Run: `uv run pytest -q && uv run ruff check . && uv run ruff format --check . && node --test "tests/web/*.test.mjs"`
Expected: 564 tests Python passent (3 ignorés), 72 tests JavaScript passent, ruff ne dit rien.

- [ ] **Step 5: Commit**

```bash
git add scripts/essai_cerveau.py docs/superpowers/specs/2026-09-22-atlas-design.md docs/superpowers/specs/2026-09-24-phase-2a-cerveau-design.md
git commit -F - <<'MSG'
Ajoute l'essai réel du cerveau et met les specs à jour

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

## L'essai avec David, sur le vrai matériel

Après la Task 11, sur la branche `phase-2a-cerveau`, avant la PR. C'est David qui lance tout ce qui ouvre le micro ou appelle Claude.

1. **La clé du client audio.** Dans le `.env` du M5 (jamais commité), là où tournent pour l'instant le Core et le client :

   ```bash
   printf '\nATLAS_AUDIO_CLE=%s\n' "$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')" >> .env
   ```

   Sans elle, le client audio refuse de démarrer et le Core refuse tout client audio.

2. **L'essai réel du cerveau** (il consomme un peu de l'abonnement) :

   ```bash
   uv run python scripts/essai_cerveau.py
   ```

   Attendu : un premier fragment en 3 s au plus pour les questions sans recherche ; le bon jour et la bonne heure ; le rappel de la question précédente ; « [recherche web] » pour la météo ; la longue réponse coupée, puis une réponse normale juste après ; et, à la fin, « Aucune transcription écrite sur le disque par le CLI ».

3. **Sur le M5**, `make run-core` et `make run-audio`, la page ouverte sur l'iPhone :
   - **Conversation** : une question, puis une suite qui s'appuie sur la réponse (« Et demain ? »).
   - **Premier mot** : 3 s au plus après la fin de la question, sans recherche (délai « réflexion » de l'historique).
   - **Recherche web** : « Je regarde ça », l'orbe en réflexion pendant la recherche, puis la réponse.
   - **Interruption** : une réponse d'environ une minute (« Raconte-moi l'histoire de la tour Eiffel en détail »), coupée en pleine phrase, puis une autre coupée dans un blanc entre deux phrases.
   - **Clavier** : une question tapée depuis l'iPhone reçoit sa réponse à voix haute.
4. **Le déploiement** : David suit `scripts/neo/LISEZMOI.md` ; puis il redémarre le néo : le client audio du M5 se reconnecte seul, et la page marche à l'adresse du néo.
5. **Non-régression** : `make test` au vert.

Ce qui ne va pas devient une correction sur la branche, avec son test, avant la PR.

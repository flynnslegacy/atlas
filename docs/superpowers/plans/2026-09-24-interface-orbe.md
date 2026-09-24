# Interface graphique (orbe et conversation) — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Une page web servie par le Core d'Atlas : une orbe animée (12 styles) devant un fond animé (6 styles), la conversation en sous-titres, une saisie au clavier, un mode muet, le tout protégé par une clé d'accès.

**Architecture:** Côté Core, un diffuseur relaie vers les pages ce que publient les sessions (état, niveau de voix, question, réponse, erreur, délais, muet) ; une régie partagée tient le mode muet et fait passer les questions tapées par la session du client audio (ou une session sans voix) ; une connexion `/ws/web` protégée par clé et origine relie les pages, et le Core sert la page à sa racine avec une politique de sécurité stricte. Côté page, des modules JavaScript standard sans compilation : l'état (pur, testé avec `node --test`), la connexion, et un fichier par orbe et par fond, tous dessinés en Canvas 2D derrière une interface commune.

**Tech Stack:** Python 3.13, FastAPI/Starlette, pydantic v2, pytest (asyncio auto) ; JavaScript ES modules, Canvas 2D, `node --test` (Node ≥ 22, Node 26 installé).

**Spec:** `docs/superpowers/specs/2026-09-24-interface-orbe-design.md` (à lire avec ce plan : elle fait foi en cas de doute).

## Global Constraints

- Code, identifiants, messages et commentaires en français, comme le reste du dépôt ; lignes de 100 caractères au plus (ruff).
- Aucune nouvelle dépendance Python. Aucune dépendance JavaScript, aucune étape de compilation, aucune ressource extérieure (pas de CDN).
- JavaScript : modules ES, indentation de 2 espaces, guillemets doubles, points-virgules, lignes de 120 caractères au plus. Tests dans `tests/web/*.test.mjs`, lancés par `node --test "tests/web/*.test.mjs"`.
- Texte affiché inséré uniquement par `textContent` : jamais `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval` ni `new Function` dans `src/atlas_web/`.
- En-tête `Content-Security-Policy` : `default-src 'self'; connect-src 'self' ws://<hôte> wss://<hôte>; img-src 'self' data:; base-uri 'none'; form-action 'self'; frame-ancestors 'none'`.
- Clé d'accès : variable `ATLAS_WEB_CLE` ; comparaison par `hmac.compare_digest` ; 5 s pour s'authentifier ; codes de fermeture `4000` (clé non configurée), `4401` (non autorisé), `1008` (origine refusée, avant acceptation).
- Messages Core → page : `etat`, `niveau` (0 à 1, au plus 15 par seconde, en écoute et en parole seulement), `question` (texte, source `voix` ou `clavier`), `reponse`, `erreur` (code, message), `latences` (`transcription_ms`, `reflexion_ms`, `premiere_voix_ms`), `muet` (`actif`), `historique` (`echanges`). Page → Core : `authentification` (`cle`), `saisie` (`texte`, 1 à 1 000 caractères après suppression des espaces de bord), `muet` (`actif`).
- Historique : 50 échanges. Reconnexion : 1, 2, 4, 8, 16 puis 30 s. Sous-titres effacés après 10 s de repos.
- Couleurs d'état : repos `[100, 130, 170]`, écoute `[34, 211, 238]`, réflexion `[167, 139, 250]`, parole `[251, 191, 36]`, hors ligne `[90, 96, 110]`.
- Orbe par défaut `aurore`, fond par défaut `bokeh` ; clés de stockage du navigateur `atlas.orbe`, `atlas.fond`, `atlas.cle`.
- Une orbe dessine sur un calque transparent (`clearRect`) et ne peint jamais tout son canevas d'une couleur opaque ; un fond peint tout son canevas.
- Fichiers de moins de 500 lignes.
- Dépôt public : aucune adresse IP, aucun domaine, nom ou courriel privé dans ce qui est commité.
- Git : ajouter les fichiers par leur chemin, jamais `git add -A` (le dossier `spikes/` n'est pas suivi et reste privé). Messages de commit en français, terminés par la ligne `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Avant chaque commit : `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .`, et, dès que `tests/web/` existe, `node --test "tests/web/*.test.mjs"`. Si `ruff format --check` échoue, lancer `uv run ruff format <fichiers>` : la mise en forme fait foi.
- Le code de ce plan a été vérifié tel quel avant d'être écrit ici : appliquées dans l'ordre, les 13 tâches donnent 366 tests Python et 67 tests JavaScript qui passent, un lint propre, et une page servie par le Core qui répond à une question tapée. Un écart entre le plan et ce que vous observez est donc à signaler, pas à contourner.

## Carte des fichiers

| Fichier | Tâche | Rôle |
|---|---|---|
| `src/atlas_core/niveaux.py` | 1 | Niveau RMS → 0..1 ; calendrier des niveaux calés sur la lecture |
| `src/atlas_core/protocole_web.py` | 2 | Messages pydantic de `/ws/web` et décodage des messages de page |
| `src/atlas_core/diffuseur.py` | 3 | Abonnements des pages, publication synchrone, historique de 50 échanges |
| `src/atlas_core/etat.py` | 4 | Transition repos → réflexion (question tapée) |
| `src/atlas_core/session.py` | 4 | Publication au diffuseur, niveaux, délais, question tapée, muet, départ du client |
| `src/atlas_core/regie.py` | 5 | Mode muet, routage des questions tapées |
| `src/atlas_core/config.py` | 6 | `web_cle` |
| `src/atlas_core/web.py` | 6 | Origine, clé, politique de sécurité |
| `src/atlas_core/hub.py` | 6 | `/ws/web`, régie, service de la page, en-têtes |
| `.env.example` | 6 | `ATLAS_WEB_CLE` documentée |
| `src/atlas_web/package.json` | 7 | Déclare les `.js` comme modules ES (pour Node) |
| `src/atlas_web/etat.js` | 7 | État de la page, reconstruit à partir des messages (pur) |
| `src/atlas_web/historique.js` | 7 | Formats des délais, rendu de l'historique |
| `src/atlas_web/registre.js` | 7 | Registre générique (orbes, fonds) et stockage sûr |
| `src/atlas_web/connexion.js` | 8 | WebSocket, authentification, reconnexion |
| `src/atlas_web/dessin.js` | 9 | Outils de dessin partagés |
| `src/atlas_web/orbes/*.js` | 9, 10 | Les 12 orbes et leur registre |
| `src/atlas_web/fonds/*.js` | 11 | Les 6 fonds et leur registre |
| `src/atlas_web/index.html`, `style.css`, `app.js`, `sous_titres.js`, `parametres.js` | 12 | La page « cinéma » |
| `tests/test_niveaux.py`, `test_protocole_web.py`, `test_diffuseur.py`, `test_session_web.py`, `test_regie.py`, `test_config.py`, `test_web_securite.py`, `test_hub_web.py` | 1–6 | Tests Python |
| `tests/web/*.test.mjs`, `tests/web/faux_canevas.mjs`, `tests/web/faux_dom.mjs` | 7–12 | Tests JavaScript et leurs doublures |
| `Makefile`, `docs/superpowers/specs/2026-09-22-atlas-design.md` | 13 | `make test` lance aussi `node --test` ; spec parente amendée |

---

### Task 1: Les niveaux de voix (`niveaux.py`)

**Files:**
- Create: `src/atlas_core/niveaux.py`
- Test: `tests/test_niveaux.py`

**Interfaces:**
- Consumes: `FREQUENCE_HZ` (16000) de `atlas_core.protocole`.
- Produces: `niveau(pcm: bytes) -> float` ; constantes `CADENCE_HZ = 15`, `INTERVALLE_S = 1 / 15` ; type `Planifier = Callable[[float, Callable[[float], None], float], Poignee]` (où `Poignee` a `.cancel()`) ; `CalendrierNiveaux(publier: Callable[[float], None], horloge: Callable[[], float], planifier: Planifier | None = None)` avec `.ajouter(pcm: bytes) -> None` et `.annuler() -> None`. Sans `planifier`, il utilise `asyncio.get_running_loop().call_later(delai, publier, valeur)`.

- [ ] **Step 1: Écrire les tests qui échouent**

`tests/test_niveaux.py` :

```python
import asyncio
import struct
import time

from atlas_core.niveaux import INTERVALLE_S, CalendrierNiveaux, niveau


def _pcm(amplitude: int, echantillons: int = 320) -> bytes:
    """Un créneau ±amplitude : sa valeur efficace vaut exactement l'amplitude."""
    return struct.pack(f"<{echantillons}h", *([amplitude, -amplitude] * (echantillons // 2)))


def test_le_silence_vaut_zero():
    assert niveau(b"\x00" * 640) == 0.0


def test_un_morceau_vide_vaut_zero():
    assert niveau(b"") == 0.0


def test_un_signal_fort_vaut_un():
    assert niveau(_pcm(32000)) == 1.0


def test_moins_35_dbfs_vaut_la_moitie():
    amplitude = round(32768 * 10 ** (-35 / 20))
    assert abs(niveau(_pcm(amplitude)) - 0.5) < 0.01


class FaussePoignee:
    def __init__(self, delai: float, rappel, valeur: float) -> None:
        self.delai, self.rappel, self.valeur = delai, rappel, valeur
        self.annulee = False

    def cancel(self) -> None:
        self.annulee = True


class FauxPlanificateur:
    def __init__(self) -> None:
        self.prevues: list[FaussePoignee] = []

    def __call__(self, delai, rappel, valeur) -> FaussePoignee:
        poignee = FaussePoignee(delai, rappel, valeur)
        self.prevues.append(poignee)
        return poignee


def _calendrier(horloge: list[float]):
    plan = FauxPlanificateur()
    return CalendrierNiveaux(lambda v: None, horloge=lambda: horloge[0], planifier=plan), plan


def test_les_niveaux_sont_cales_sur_la_lecture_et_limites_a_15_par_seconde():
    horloge = [100.0]
    calendrier, plan = _calendrier(horloge)
    for _ in range(50):  # une seconde de voix arrivée d'un coup : la synthèse est en avance
        calendrier.ajouter(_pcm(3000))
    delais = [p.delai for p in plan.prevues]
    assert delais[0] == 0.0
    assert 12 <= len(delais) <= 15
    assert all(b - a >= INTERVALLE_S - 1e-9 for a, b in zip(delais, delais[1:], strict=False))
    assert delais[-1] < 1.0


def test_apres_un_silence_la_lecture_repart_du_present():
    horloge = [0.0]
    calendrier, plan = _calendrier(horloge)
    calendrier.ajouter(_pcm(3000))
    horloge[0] = 5.0
    calendrier.ajouter(_pcm(3000))
    assert [p.delai for p in plan.prevues] == [0.0, 0.0]


def test_annuler_arrete_les_niveaux_prevus_et_remet_la_lecture_a_zero():
    horloge = [0.0]
    calendrier, plan = _calendrier(horloge)
    for _ in range(20):
        calendrier.ajouter(_pcm(3000))
    calendrier.annuler()
    assert plan.prevues and all(p.annulee for p in plan.prevues)
    calendrier.ajouter(_pcm(3000))
    assert plan.prevues[-1].delai == 0.0


async def test_par_defaut_le_niveau_est_publie_par_la_boucle():
    recus: list[float] = []
    calendrier = CalendrierNiveaux(recus.append, horloge=time.monotonic)
    calendrier.ajouter(_pcm(32000))
    await asyncio.sleep(0.01)
    assert recus == [1.0]
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `uv run pytest tests/test_niveaux.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'atlas_core.niveaux'`.

- [ ] **Step 3: Écrire l'implémentation**

`src/atlas_core/niveaux.py` :

```python
"""Le volume de la voix, ramené de 0 à 1 pour l'orbe des pages.

Deux sources : la voix de David, reçue pendant l'écoute, et celle d'Atlas, envoyée
pendant la parole. La synthèse va environ deux fois plus vite que la lecture : les
niveaux de la voix d'Atlas sont donc calés sur le moment où chaque morceau sera joué.
"""

from __future__ import annotations

import asyncio
import math
import sys
from array import array
from collections.abc import Callable
from typing import Protocol

from .protocole import FREQUENCE_HZ

PLANCHER_DBFS = -60.0
PLAFOND_DBFS = -10.0
CADENCE_HZ = 15  # au plus 15 niveaux par seconde vers les pages
INTERVALLE_S = 1 / CADENCE_HZ


def niveau(pcm: bytes) -> float:
    """Niveau efficace d'un morceau PCM s16le : 0 sous −60 dBFS, 1 au-dessus de −10 dBFS."""
    utile = len(pcm) - len(pcm) % 2
    if utile == 0:
        return 0.0
    echantillons = array("h")
    echantillons.frombytes(pcm[:utile])
    if sys.byteorder == "big":
        echantillons.byteswap()
    rms = math.sqrt(sum(e * e for e in echantillons) / len(echantillons)) / 32768
    if rms <= 0:
        return 0.0
    dbfs = 20 * math.log10(rms)
    return min(1.0, max(0.0, (dbfs - PLANCHER_DBFS) / (PLAFOND_DBFS - PLANCHER_DBFS)))


class Poignee(Protocol):
    def cancel(self) -> None: ...


Planifier = Callable[[float, Callable[[float], None], float], Poignee]


def _planifier_sur_la_boucle(delai: float, rappel: Callable[[float], None], valeur: float):
    return asyncio.get_running_loop().call_later(max(0.0, delai), rappel, valeur)


class CalendrierNiveaux:
    """Publie le niveau de chaque morceau de la voix d'Atlas au moment où il sera joué."""

    def __init__(
        self,
        publier: Callable[[float], None],
        horloge: Callable[[], float],
        planifier: Planifier | None = None,
    ) -> None:
        self._publier = publier
        self._horloge = horloge
        self._planifier = planifier or _planifier_sur_la_boucle
        self._fin_lecture = 0.0
        self._dernier = -math.inf
        self._poignees: list[Poignee] = []

    def ajouter(self, pcm: bytes) -> None:
        maintenant = self._horloge()
        if maintenant >= self._fin_lecture:
            self._poignees.clear()  # tout ce qui était prévu a déjà été joué
        debut = max(maintenant, self._fin_lecture)
        self._fin_lecture = debut + len(pcm) / 2 / FREQUENCE_HZ
        if debut - self._dernier < INTERVALLE_S:
            return
        self._dernier = debut
        self._poignees.append(self._planifier(debut - maintenant, self._publier, niveau(pcm)))

    def annuler(self) -> None:
        """Interruption : plus rien ne doit bouger l'orbe au nom de la phrase coupée."""
        for poignee in self._poignees:
            poignee.cancel()
        self._poignees.clear()
        self._fin_lecture = 0.0
        self._dernier = -math.inf
```

- [ ] **Step 4: Vérifier que les tests passent**

Run: `uv run pytest tests/test_niveaux.py -q && uv run ruff check . && uv run ruff format --check .`
Expected: PASS (8 tests), aucune remarque de ruff.

- [ ] **Step 5: Commit**

```bash
git add src/atlas_core/niveaux.py tests/test_niveaux.py
git commit -F - <<'MSG'
Calcule le niveau de voix et le cale sur la lecture

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

### Task 2: Les messages de la page (`protocole_web.py`)

**Files:**
- Create: `src/atlas_core/protocole_web.py`
- Test: `tests/test_protocole_web.py`

**Interfaces:**
- Consumes: `Etat`, `Erreur` de `atlas_core.protocole` (réutilisés tels quels : mêmes champs `type`/`valeur` et `type`/`code`/`message`).
- Produces: `Niveau(valeur: float ∈ [0, 1])`, `Question(texte, source)`, `Reponse(texte)`, `Latences(transcription_ms, reflexion_ms, premiere_voix_ms: int | None)`, `Muet(actif: bool)`, `Echange(heure, source, question, reponse="", erreur=None, latences=None)`, `Historique(echanges: list[Echange])`, `Authentification(cle)`, `Saisie(texte)` ; type `Source = Literal["voix", "clavier"]` ; `LONGUEUR_MAX_SAISIE = 1000` ; `decoder_message_page(brut: str) -> Authentification | Saisie | Muet` qui lève `ValueError` avec un message lisible (le premier message d'erreur de pydantic, sans le préfixe « Value error, »).

- [ ] **Step 1: Écrire les tests qui échouent**

`tests/test_protocole_web.py` :

```python
import json

import pytest
from pydantic import ValidationError

from atlas_core.protocole import Etat
from atlas_core.protocole_web import (
    LONGUEUR_MAX_SAISIE,
    Authentification,
    Echange,
    Historique,
    Latences,
    Muet,
    Niveau,
    Saisie,
    decoder_message_page,
)


def test_les_trois_messages_de_page_se_decodent():
    assert decoder_message_page('{"type":"authentification","cle":"abc"}') == Authentification(
        cle="abc"
    )
    assert decoder_message_page('{"type":"saisie","texte":"Quelle heure ?"}') == Saisie(
        texte="Quelle heure ?"
    )
    assert decoder_message_page('{"type":"muet","actif":true}') == Muet(actif=True)


def test_une_saisie_perd_ses_espaces_de_bord():
    assert decoder_message_page('{"type":"saisie","texte":"  bonjour \\n"}').texte == "bonjour"


@pytest.mark.parametrize("texte", ["", "   ", "x" * (LONGUEUR_MAX_SAISIE + 1)])
def test_une_saisie_vide_ou_trop_longue_est_refusee_lisiblement(texte):
    with pytest.raises(ValueError, match="entre 1 et 1000 caractères") as e:
        decoder_message_page(json.dumps({"type": "saisie", "texte": texte}))
    assert "Value error" not in str(e.value)


def test_une_saisie_de_1000_caracteres_passe():
    assert (
        len(decoder_message_page(json.dumps({"type": "saisie", "texte": "x" * 1000})).texte) == 1000
    )


@pytest.mark.parametrize(
    "brut",
    [
        '{"type":"inconnu"}',
        "pas du json",
        '{"type":"authentification","cle":' + '"' + "k" * 300 + '"}',
    ],
)
def test_le_reste_est_refuse(brut):
    with pytest.raises(ValueError):
        decoder_message_page(brut)


def test_un_niveau_reste_entre_0_et_1():
    with pytest.raises(ValidationError):
        Niveau(valeur=1.5)


def test_l_historique_se_serialise_avec_ses_latences():
    h = Historique(
        echanges=[
            Echange(
                heure="14:31",
                source="clavier",
                question="Quelle heure ?",
                reponse="Il est quatorze heures trente et une.",
                latences=Latences(reflexion_ms=12),
            )
        ]
    )
    donnees = json.loads(h.model_dump_json())
    assert donnees["type"] == "historique"
    assert donnees["echanges"][0]["latences"]["reflexion_ms"] == 12
    assert donnees["echanges"][0]["erreur"] is None


def test_l_etat_du_protocole_audio_sert_aussi_aux_pages():
    assert json.loads(Etat(valeur="parole").model_dump_json()) == {
        "type": "etat",
        "valeur": "parole",
    }
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `uv run pytest tests/test_protocole_web.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'atlas_core.protocole_web'`.

- [ ] **Step 3: Écrire l'implémentation**

`src/atlas_core/protocole_web.py` :

```python
"""Messages échangés entre le Core et les pages web, sur la connexion /ws/web.

`Etat` et `Erreur` viennent du protocole audio, à l'identique : une page et le
client audio lisent les mêmes.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, TypeAdapter, ValidationError, field_validator

from .protocole import Erreur, Etat

LONGUEUR_MAX_SAISIE = 1000
TAILLE_MAX_CLE = 256

Source = Literal["voix", "clavier"]


# --- Core vers page -----------------------------------------------------


class Niveau(BaseModel):
    type: Literal["niveau"] = "niveau"
    valeur: float = Field(ge=0.0, le=1.0)


class Question(BaseModel):
    type: Literal["question"] = "question"
    texte: str
    source: Source


class Reponse(BaseModel):
    type: Literal["reponse"] = "reponse"
    texte: str


class Latences(BaseModel):
    type: Literal["latences"] = "latences"
    transcription_ms: int | None = None
    reflexion_ms: int | None = None
    premiere_voix_ms: int | None = None


class Muet(BaseModel):
    """Dans les deux sens : la page le demande, le Core le confirme à toutes les pages."""

    type: Literal["muet"] = "muet"
    actif: bool


class Echange(BaseModel):
    heure: str
    source: Source
    question: str
    reponse: str = ""
    erreur: str | None = None
    latences: Latences | None = None


class Historique(BaseModel):
    type: Literal["historique"] = "historique"
    echanges: list[Echange]


MessageWeb = Etat | Niveau | Question | Reponse | Erreur | Latences | Muet | Historique


# --- page vers Core -----------------------------------------------------


class Authentification(BaseModel):
    type: Literal["authentification"] = "authentification"
    cle: str = Field(max_length=TAILLE_MAX_CLE)


class Saisie(BaseModel):
    type: Literal["saisie"] = "saisie"
    texte: str

    @field_validator("texte")
    @classmethod
    def _longueur(cls, texte: str) -> str:
        texte = texte.strip()
        if not 1 <= len(texte) <= LONGUEUR_MAX_SAISIE:
            raise ValueError(f"la question doit faire entre 1 et {LONGUEUR_MAX_SAISIE} caractères")
        return texte


MessagePage = Annotated[Authentification | Saisie | Muet, Field(discriminator="type")]
_adaptateur_page = TypeAdapter(MessagePage)


def decoder_message_page(brut: str) -> MessagePage:
    """Décode un message de page. Lève ValueError, avec un message que la page peut afficher."""
    try:
        return _adaptateur_page.validate_json(brut)
    except ValidationError as e:
        premiere = e.errors()[0]
        message = str(premiere.get("msg", "message invalide")).removeprefix("Value error, ")
        raise ValueError(message) from e
```

- [ ] **Step 4: Vérifier que les tests passent**

Run: `uv run pytest tests/test_protocole_web.py -q && uv run ruff check . && uv run ruff format --check .`
Expected: PASS, aucune remarque de ruff.

- [ ] **Step 5: Commit**

```bash
git add src/atlas_core/protocole_web.py tests/test_protocole_web.py
git commit -F - <<'MSG'
Décrit les messages échangés avec les pages web

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

### Task 3: Le diffuseur (`diffuseur.py`)

**Files:**
- Create: `src/atlas_core/diffuseur.py`
- Test: `tests/test_diffuseur.py`

**Interfaces:**
- Consumes: `Etat`, `Erreur` (protocole) ; `Echange`, `Historique`, `Latences`, `Muet`, `Niveau`, `Question`, `Reponse` (Task 2).
- Produces: `Diffuseur(taille_historique: int = 50, heure: Callable[[], str] | None = None)` avec `.publier(msg: BaseModel) -> None` (**synchrone**), `.abonner(envoyer: Callable[[BaseModel], Awaitable[None]]) -> Abonnement` (à appeler dans une boucle asyncio en marche), `.historique() -> Historique` ; `Abonnement` avec `.envoyer_prive(msg) -> None` et `async .fermer() -> None`. Constantes `TAILLE_HISTORIQUE = 50`, `RETARD_MAX_NIVEAUX = 32`. À l'abonnement, la page reçoit dans l'ordre : `Historique`, `Muet`, le dernier `Etat` publié (repos au départ).

- [ ] **Step 1: Écrire les tests qui échouent**

`tests/test_diffuseur.py` :

```python
import asyncio

from atlas_core.diffuseur import RETARD_MAX_NIVEAUX, Diffuseur
from atlas_core.protocole import Erreur, Etat
from atlas_core.protocole_web import Historique, Latences, Muet, Niveau, Question, Reponse


class Page:
    def __init__(self) -> None:
        self.recus: list = []

    async def envoyer(self, msg) -> None:
        self.recus.append(msg)

    def types(self) -> list[str]:
        return [m.type for m in self.recus]


async def _laisser_passer() -> None:
    for _ in range(10):
        await asyncio.sleep(0)


def _diffuseur() -> Diffuseur:
    return Diffuseur(heure=lambda: "14:31")


async def test_une_page_recoit_d_abord_l_historique_le_muet_et_l_etat():
    d = _diffuseur()
    d.publier(Etat(valeur="ecoute"))
    page = Page()
    abonnement = d.abonner(page.envoyer)
    await _laisser_passer()
    assert page.types() == ["historique", "muet", "etat"]
    assert page.recus[2].valeur == "ecoute"
    await abonnement.fermer()


async def test_les_messages_arrivent_dans_l_ordre_a_toutes_les_pages():
    d = _diffuseur()
    pages = [Page(), Page()]
    abonnements = [d.abonner(p.envoyer) for p in pages]
    d.publier(Etat(valeur="parole"))
    d.publier(Reponse(texte="Il est midi."))
    await _laisser_passer()
    for p in pages:
        assert p.types()[3:] == ["etat", "reponse"]
    for a in abonnements:
        await a.fermer()


def test_l_historique_garde_question_reponse_et_latences():
    d = _diffuseur()
    d.publier(Question(texte="quelle heure est-il", source="voix"))
    d.publier(Reponse(texte="Il est midi."))
    d.publier(Reponse(texte="Tu déjeunes ?"))
    d.publier(Latences(transcription_ms=420, reflexion_ms=12, premiere_voix_ms=900))
    d.publier(Etat(valeur="repos"))
    (e,) = d.historique().echanges
    assert (e.heure, e.source, e.question) == ("14:31", "voix", "quelle heure est-il")
    assert e.reponse == "Il est midi. Tu déjeunes ?"
    assert e.latences.transcription_ms == 420 and e.erreur is None


def test_une_erreur_s_attache_a_l_echange_en_cours_ou_en_cree_un():
    d = _diffuseur()
    d.publier(Question(texte="bonjour", source="clavier"))
    d.publier(Erreur(code="tour", message="Je n'ai pas pu répondre : panne"))
    d.publier(Etat(valeur="repos"))
    d.publier(Erreur(code="tour", message="Je n'ai pas pu répondre : TimeoutError"))
    premier, second = d.historique().echanges
    assert premier.question == "bonjour" and premier.erreur.endswith("panne")
    assert second.question == "" and second.erreur.endswith("TimeoutError")


def test_l_historique_est_limite():
    d = Diffuseur(taille_historique=3, heure=lambda: "09:00")
    for i in range(5):
        d.publier(Question(texte=f"q{i}", source="voix"))
        d.publier(Etat(valeur="repos"))
    assert [e.question for e in d.historique().echanges] == ["q2", "q3", "q4"]


def test_l_historique_rendu_est_une_copie():
    d = _diffuseur()
    d.publier(Question(texte="q", source="voix"))
    copie = d.historique()
    d.publier(Reponse(texte="r"))
    assert isinstance(copie, Historique) and copie.echanges[0].reponse == ""


async def test_le_muet_publie_est_rappele_aux_nouvelles_pages():
    d = _diffuseur()
    d.publier(Muet(actif=True))
    page = Page()
    abonnement = d.abonner(page.envoyer)
    await _laisser_passer()
    assert page.recus[1] == Muet(actif=True)
    await abonnement.fermer()


async def test_une_page_lente_perd_des_niveaux_mais_jamais_le_reste():
    d = _diffuseur()
    feu_vert = asyncio.Event()
    recus: list = []

    async def envoyer_lentement(msg) -> None:
        await feu_vert.wait()
        recus.append(msg)

    abonnement = d.abonner(envoyer_lentement)
    await _laisser_passer()
    for _ in range(100):
        d.publier(Niveau(valeur=0.5))
    d.publier(Etat(valeur="parole"))
    d.publier(Reponse(texte="Il est midi."))
    feu_vert.set()
    await _laisser_passer()
    await asyncio.sleep(0.01)
    niveaux = [m for m in recus if isinstance(m, Niveau)]
    assert len(niveaux) <= RETARD_MAX_NIVEAUX
    assert [m.type for m in recus][-2:] == ["etat", "reponse"]
    await abonnement.fermer()


async def test_une_page_fermee_ne_recoit_plus_rien():
    d = _diffuseur()
    page = Page()
    abonnement = d.abonner(page.envoyer)
    await _laisser_passer()
    await abonnement.fermer()
    d.publier(Reponse(texte="trop tard"))
    await _laisser_passer()
    assert page.types() == ["historique", "muet", "etat"]


async def test_un_envoi_prive_ne_va_qu_a_sa_page():
    d = _diffuseur()
    a, b = Page(), Page()
    abonnement_a, abonnement_b = d.abonner(a.envoyer), d.abonner(b.envoyer)
    abonnement_a.envoyer_prive(Erreur(code="message_invalide", message="non"))
    await _laisser_passer()
    assert "erreur" in a.types() and "erreur" not in b.types()
    await abonnement_a.fermer()
    await abonnement_b.fermer()


async def test_une_page_en_panne_ne_gene_ni_les_autres_ni_le_core():
    d = _diffuseur()

    async def envoyer_en_panne(msg) -> None:
        raise ConnectionError("page fermée")

    saine = Page()
    en_panne = d.abonner(envoyer_en_panne)
    abonnement = d.abonner(saine.envoyer)
    await _laisser_passer()
    d.publier(Reponse(texte="toujours là"))
    await _laisser_passer()
    assert saine.types()[-1] == "reponse"
    await en_panne.fermer()
    await abonnement.fermer()
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `uv run pytest tests/test_diffuseur.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'atlas_core.diffuseur'`.

- [ ] **Step 3: Écrire l'implémentation**

`src/atlas_core/diffuseur.py` :

```python
"""Relaie vers les pages ce qui se passe dans le Core, et garde les derniers échanges.

La publication est synchrone : le Core ne ralentit jamais pour une page. Chaque page
a sa file, vidée par sa propre tâche vers sa connexion.
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
from collections import deque
from collections.abc import Awaitable, Callable

from pydantic import BaseModel

from .protocole import Erreur, Etat
from .protocole_web import Echange, Historique, Latences, Muet, Niveau, Question, Reponse

TAILLE_HISTORIQUE = 50
# Une page qui n'arrive pas à suivre perd des niveaux (l'orbe saute une image), jamais
# un état, un texte ou une erreur.
RETARD_MAX_NIVEAUX = 32

Envoyer = Callable[[BaseModel], Awaitable[None]]


def _heure_locale() -> str:
    return dt.datetime.now().strftime("%H:%M")


class Abonnement:
    """Une page abonnée : sa file, et la tâche qui la vide vers la connexion."""

    def __init__(self, diffuseur: Diffuseur, envoyer: Envoyer) -> None:
        self._diffuseur = diffuseur
        self._file: asyncio.Queue[BaseModel] = asyncio.Queue()
        self._tache = asyncio.create_task(self._pomper(envoyer))

    def deposer(self, msg: BaseModel) -> None:
        if isinstance(msg, Niveau) and self._file.qsize() >= RETARD_MAX_NIVEAUX:
            return
        self._file.put_nowait(msg)

    def envoyer_prive(self, msg: BaseModel) -> None:
        """Pour cette page seulement : une erreur de saisie, par exemple."""
        self._file.put_nowait(msg)

    async def _pomper(self, envoyer: Envoyer) -> None:
        while True:
            await envoyer(await self._file.get())

    async def fermer(self) -> None:
        self._diffuseur.retirer(self)
        self._tache.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await self._tache


class Diffuseur:
    def __init__(
        self, taille_historique: int = TAILLE_HISTORIQUE, heure: Callable[[], str] | None = None
    ) -> None:
        self._abonnements: list[Abonnement] = []
        self._echanges: deque[Echange] = deque(maxlen=taille_historique)
        self._en_cours: Echange | None = None
        self._dernier_etat = Etat(valeur="repos")
        self._muet = False
        self._heure = heure or _heure_locale

    def abonner(self, envoyer: Envoyer) -> Abonnement:
        """Abonne une page : elle reçoit d'abord l'historique, le mode muet et l'état courant."""
        abonnement = Abonnement(self, envoyer)
        for msg in (self.historique(), Muet(actif=self._muet), self._dernier_etat):
            abonnement.deposer(msg)
        self._abonnements.append(abonnement)
        return abonnement

    def retirer(self, abonnement: Abonnement) -> None:
        if abonnement in self._abonnements:
            self._abonnements.remove(abonnement)

    def historique(self) -> Historique:
        return Historique(echanges=[e.model_copy(deep=True) for e in self._echanges])

    def publier(self, msg: BaseModel) -> None:
        self._noter(msg)
        for abonnement in list(self._abonnements):
            abonnement.deposer(msg)

    def _noter(self, msg: BaseModel) -> None:
        if isinstance(msg, Etat):
            self._dernier_etat = msg
            if msg.valeur == "repos":
                self._en_cours = None
        elif isinstance(msg, Muet):
            self._muet = msg.actif
        elif isinstance(msg, Question):
            self._en_cours = Echange(heure=self._heure(), source=msg.source, question=msg.texte)
            self._echanges.append(self._en_cours)
        elif isinstance(msg, Reponse) and self._en_cours is not None:
            self._en_cours.reponse = f"{self._en_cours.reponse} {msg.texte}".strip()
        elif isinstance(msg, Latences) and self._en_cours is not None:
            self._en_cours.latences = msg
        elif isinstance(msg, Erreur):
            if self._en_cours is not None:
                self._en_cours.erreur = msg.message
            else:
                self._echanges.append(
                    Echange(heure=self._heure(), source="voix", question="", erreur=msg.message)
                )
```

- [ ] **Step 4: Vérifier que les tests passent**

Run: `uv run pytest tests/test_diffuseur.py -q && uv run ruff check . && uv run ruff format --check .`
Expected: PASS (11 tests), aucune remarque de ruff.

- [ ] **Step 5: Commit**

```bash
git add src/atlas_core/diffuseur.py tests/test_diffuseur.py
git commit -F - <<'MSG'
Ajoute le diffuseur qui relaie le Core vers les pages

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```


---

### Task 4: La session publie, répond aux questions tapées et sait se taire

**Files:**
- Modify: `src/atlas_core/etat.py:13` (transitions du repos)
- Modify: `tests/test_etat.py` (listes de transitions)
- Replace: `src/atlas_core/session.py` (contenu complet ci-dessous)
- Test: `tests/test_session_web.py` (nouveau) ; `tests/test_session.py` doit passer **sans modification**

**Interfaces:**
- Consumes: `Diffuseur` (Task 3), `CalendrierNiveaux`, `INTERVALLE_S`, `Planifier`, `niveau` (Task 1), `Latences`, `Niveau`, `Question`, `Reponse`, `Source` (Task 2).
- Produces: `Session(envoyer_json, envoyer_binaire, transcription, synthese, cerveau, diffuseur: Diffuseur | None = None, avec_voix: Callable[[], bool] | None = None, horloge: Callable[[], float] | None = None, planifier: Planifier | None = None)` avec, en plus de `sur_message`, `sur_audio` et `fermer` : `async sur_saisie(texte: str)`, `async taire()`. Fonction publique `async sans_destinataire(_message) -> None` (un envoi vers personne, pour la session sans voix). Chaque `Etat` envoyé au client est aussi publié au diffuseur ; une question non vide publie `Question`, chaque phrase publie `Reponse`, chaque tour terminé publie `Latences` juste avant l'`Etat` « repos », une erreur publie l'`Erreur`.

- [ ] **Step 1: Mettre à jour la machine d'états et son test**

Dans `src/atlas_core/etat.py`, remplacer la ligne des transitions du repos :

```python
    "repos": {"ecoute"},
```

par :

```python
    "repos": {"ecoute", "reflexion"},  # « reflexion » : une question tapée, sans écoute
```

Dans `tests/test_etat.py`, ajouter `("repos", "reflexion"),` à la liste de `test_les_transitions_permises_passent`, et retirer `("repos", "reflexion")` de celle de `test_les_transitions_interdites_levent`, qui devient :

```python
    [("repos", "parole"), ("ecoute", "parole"), ("reflexion", "ecoute")],
```

- [ ] **Step 2: Écrire les tests qui échouent**

`tests/test_session_web.py` :

```python
import asyncio
from collections.abc import AsyncIterator

from atlas_core.diffuseur import Diffuseur
from atlas_core.protocole import (
    Dire,
    Erreur,
    Etat,
    FinEnonce,
    Interruption,
    Reveil,
    StopAudio,
    Transcription,
)
from atlas_core.protocole_web import Latences, Niveau, Question, Reponse
from atlas_core.session import Session


class Collecteur:
    def __init__(self) -> None:
        self.json: list = []
        self.binaire: list[bytes] = []

    async def envoyer_json(self, msg) -> None:
        self.json.append(msg)

    async def envoyer_binaire(self, trame: bytes) -> None:
        self.binaire.append(trame)

    def etats(self) -> list[str]:
        return [m.valeur for m in self.json if isinstance(m, Etat)]

    def de(self, classe) -> list:
        return [m for m in self.json if isinstance(m, classe)]


class DiffuseurEspion(Diffuseur):
    def __init__(self) -> None:
        super().__init__(heure=lambda: "12:00")
        self.publies: list = []

    def publier(self, msg) -> None:
        self.publies.append(msg)
        super().publier(msg)

    def de(self, classe) -> list:
        return [m for m in self.publies if isinstance(m, classe)]


class Temps:
    """Une horloge qu'on avance à la main."""

    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


class FausseTranscription:
    def __init__(self, texte: str = "quelle heure est-il", temps=None, duree: float = 0.0):
        self.texte, self.temps, self.duree = texte, temps, duree
        self.appels = 0

    async def transcrire(self, pcm: bytes) -> str:
        self.appels += 1
        if self.temps:
            self.temps.t += self.duree
        return self.texte


class TranscriptionSansMessage:
    async def transcrire(self, pcm: bytes) -> str:
        raise TimeoutError()


class FausseSynthese:
    def __init__(self, blocs: int = 3, lenteur: float = 0.0, temps=None, duree_premier=0.0):
        self.blocs, self.lenteur = blocs, lenteur
        self.temps, self.duree_premier = temps, duree_premier
        self.appels = 0

    async def synthetiser(self, texte: str) -> AsyncIterator[bytes]:
        self.appels += 1
        for i in range(self.blocs):
            if self.lenteur:
                await asyncio.sleep(self.lenteur)
            if i == 0 and self.temps:
                self.temps.t += self.duree_premier
            yield b"\x00" * 640


class CerveauFixe:
    def __init__(self, phrase: str = "Il est midi. Tu déjeunes ?", temps=None, duree=0.0):
        self.phrase, self.temps, self.duree = phrase, temps, duree

    async def repondre(self, texte: str) -> AsyncIterator[str]:
        if self.temps:
            self.temps.t += self.duree
        for mot in self.phrase.split(" "):
            yield mot + " "
            await asyncio.sleep(0)


class FaussePoignee:
    def __init__(self) -> None:
        self.annulee = False

    def cancel(self) -> None:
        self.annulee = True


class FauxPlanificateur:
    def __init__(self) -> None:
        self.prevues: list[FaussePoignee] = []

    def __call__(self, delai, rappel, valeur) -> FaussePoignee:
        self.prevues.append(FaussePoignee())
        return self.prevues[-1]


def _session(collecteur, diffuseur=None, **options) -> Session:
    return Session(
        envoyer_json=collecteur.envoyer_json,
        envoyer_binaire=collecteur.envoyer_binaire,
        transcription=options.pop("transcription", FausseTranscription()),
        synthese=options.pop("synthese", FausseSynthese()),
        cerveau=options.pop("cerveau", CerveauFixe()),
        diffuseur=diffuseur,
        planifier=options.pop("planifier", FauxPlanificateur()),
        **options,
    )


async def _tour_a_la_voix(session, blocs: int = 5) -> None:
    await session.sur_message(Reveil(confiance=0.9, horodatage=0.0))
    for _ in range(blocs):
        await session.sur_audio(b"\x00" * 640)
    await session.sur_message(FinEnonce(duree_ms=blocs * 20))
    await asyncio.sleep(0.01)


async def test_un_tour_a_la_voix_est_publie_pour_les_pages():
    c, d = Collecteur(), DiffuseurEspion()
    s = _session(c, d)
    await _tour_a_la_voix(s)
    await s.fermer()
    sans_niveaux = [m.type for m in d.publies if not isinstance(m, Niveau)]
    assert sans_niveaux == [
        "etat",
        "etat",
        "question",
        "etat",
        "reponse",
        "reponse",
        "latences",
        "etat",
    ]
    question = d.de(Question)[0]
    assert (question.texte, question.source) == ("quelle heure est-il", "voix")
    assert [r.texte for r in d.de(Reponse)] == ["Il est midi.", "Tu déjeunes ?"]
    assert c.etats() == ["ecoute", "reflexion", "parole", "repos"]


async def test_les_trois_delais_sont_mesures():
    temps = Temps()
    c, d = Collecteur(), DiffuseurEspion()
    s = _session(
        c,
        d,
        horloge=temps,
        transcription=FausseTranscription(temps=temps, duree=0.42),
        cerveau=CerveauFixe(temps=temps, duree=1.2),
        synthese=FausseSynthese(temps=temps, duree_premier=0.3),
    )
    await _tour_a_la_voix(s)
    await s.fermer()
    assert d.de(Latences) == [
        Latences(transcription_ms=420, reflexion_ms=1200, premiere_voix_ms=1920)
    ]


async def test_l_ecoute_publie_au_plus_15_niveaux_par_seconde():
    temps = Temps()
    c, d = Collecteur(), DiffuseurEspion()
    s = _session(c, d, horloge=temps)
    await s.sur_message(Reveil(confiance=0.9, horodatage=0.0))
    for _ in range(10):  # 200 ms de voix
        temps.t += 0.02
        await s.sur_audio(b"\x00" * 640)
    assert len(d.de(Niveau)) == 3
    await s.fermer()


async def test_la_voix_d_atlas_programme_des_niveaux_que_l_interruption_annule():
    c, d = Collecteur(), DiffuseurEspion()
    plan = FauxPlanificateur()
    s = _session(c, d, planifier=plan, synthese=FausseSynthese(blocs=40, lenteur=0.001))
    await s.sur_message(Reveil(confiance=0.9, horodatage=0.0))
    await s.sur_audio(b"\x00" * 640)
    await s.sur_message(FinEnonce(duree_ms=20))
    await asyncio.sleep(0.02)
    assert plan.prevues
    await s.sur_message(Interruption(horodatage=0.0))
    assert all(p.annulee for p in plan.prevues)
    await s.fermer()


async def test_une_question_tapee_au_repos_est_repondue_sans_transcription():
    c, d = Collecteur(), DiffuseurEspion()
    transcription = FausseTranscription()
    s = _session(c, d, transcription=transcription)
    await s.sur_saisie("quelle heure est-il")
    await asyncio.sleep(0.01)
    await s.fermer()
    assert transcription.appels == 0 and not c.de(Transcription)
    assert c.etats() == ["reflexion", "parole", "repos"]
    assert d.de(Question)[0].source == "clavier"
    assert c.binaire, "Atlas répond à voix haute"
    assert d.de(Latences)[0].transcription_ms is None


async def test_une_question_tapee_pendant_la_parole_coupe_et_repond():
    c = Collecteur()
    s = _session(c, synthese=FausseSynthese(blocs=10, lenteur=0.005))
    await _tour_a_la_voix(s)
    await s.sur_saisie("bonjour")
    await asyncio.sleep(0.2)
    await s.fermer()
    assert c.de(StopAudio)[0].id_enonce == 1
    assert {m.id_enonce for m in c.de(Dire)} == {1, 2}
    assert c.etats()[-3:] == ["reflexion", "parole", "repos"]


async def test_une_question_tapee_pendant_l_ecoute_abandonne_la_capture():
    c = Collecteur()
    transcription = FausseTranscription()
    s = _session(c, transcription=transcription)
    await s.sur_message(Reveil(confiance=0.9, horodatage=0.0))
    await s.sur_audio(b"\x00" * 640)
    await s.sur_saisie("bonjour")
    await s.sur_message(FinEnonce(duree_ms=20))
    await asyncio.sleep(0.02)
    await s.fermer()
    assert transcription.appels == 0
    assert c.etats() == ["ecoute", "reflexion", "parole", "repos"]


async def test_sans_voix_la_reponse_est_seulement_ecrite():
    c, d = Collecteur(), DiffuseurEspion()
    synthese = FausseSynthese()
    s = _session(c, d, synthese=synthese, avec_voix=lambda: False)
    await s.sur_saisie("quelle heure est-il")
    await asyncio.sleep(0.01)
    await s.fermer()
    assert synthese.appels == 0
    assert not c.binaire and not c.de(Dire)
    assert [r.texte for r in d.de(Reponse)] == ["Il est midi.", "Tu déjeunes ?"]
    assert d.de(Latences)[0].premiere_voix_ms is None


async def test_taire_coupe_la_voix_et_laisse_finir_le_texte():
    voix = {"active": True}
    c, d = Collecteur(), DiffuseurEspion()
    s = _session(
        c, d, avec_voix=lambda: voix["active"], synthese=FausseSynthese(blocs=20, lenteur=0.005)
    )
    await s.sur_saisie("quelle heure est-il")
    await asyncio.sleep(0.03)
    voix["active"] = False
    await s.taire()
    trames = len(c.binaire)
    await asyncio.sleep(0.2)
    await s.fermer()
    assert c.de(StopAudio)[-1].id_enonce == 1
    assert len(c.binaire) <= trames + 1
    assert [r.texte for r in d.de(Reponse)] == ["Il est midi.", "Tu déjeunes ?"]
    assert c.etats()[-1] == "repos"


async def test_le_client_audio_qui_part_laisse_finir_la_reponse_ecrite():
    c, d = Collecteur(), DiffuseurEspion()
    s = _session(c, d, synthese=FausseSynthese(blocs=20, lenteur=0.005))
    await s.sur_saisie("quelle heure est-il")
    await asyncio.sleep(0.03)
    await s.fermer()
    trames = len(c.binaire)
    await asyncio.sleep(0.3)
    assert len(c.binaire) == trames
    assert [r.texte for r in d.de(Reponse)] == ["Il est midi.", "Tu déjeunes ?"]
    assert d.de(Latences) and d.publies[-1] == Etat(valeur="repos")


async def test_fermer_pendant_un_tour_a_la_voix_l_annule():
    c, d = Collecteur(), DiffuseurEspion()
    s = _session(c, d, synthese=FausseSynthese(blocs=20, lenteur=0.005))
    await _tour_a_la_voix(s)
    await s.fermer()
    await asyncio.sleep(0.05)
    assert not d.de(Latences)


async def test_une_erreur_sans_message_donne_au_moins_son_type():
    c, d = Collecteur(), DiffuseurEspion()
    s = _session(c, d, transcription=TranscriptionSansMessage())
    await _tour_a_la_voix(s)
    await s.fermer()
    assert d.de(Erreur)[0].message == "Je n'ai pas pu répondre : TimeoutError"
    assert c.de(Erreur)[0].message == "Je n'ai pas pu répondre : TimeoutError"
    assert c.etats()[-1] == "repos"
```

- [ ] **Step 3: Vérifier qu'ils échouent**

Run: `uv run pytest tests/test_session_web.py tests/test_etat.py -q`
Expected: FAIL. `test_etat.py` passe déjà si l'étape 1 est faite ; `test_session_web.py` échoue sur `TypeError: Session.__init__() got an unexpected keyword argument 'diffuseur'`.

- [ ] **Step 4: Réécrire `src/atlas_core/session.py`**

Contenu complet :

```python
"""Orchestration d'un tour de parole, pour une connexion cliente.

Une Session par client audio, et une session sans voix pour les questions tapées
quand aucun client audio n'est connecté. Elle ne connaît ni le réseau ni le
transport : elle reçoit des messages décodés et appelle deux fonctions d'envoi.
Tout ce qui se passe est aussi publié au diffuseur, pour les pages web. C'est ce
qui la rend testable sans WebSocket.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Awaitable, Callable

from .cerveau import Cerveau
from .diffuseur import Diffuseur
from .etat import MachineEtat, Valeur
from .niveaux import INTERVALLE_S, CalendrierNiveaux, Planifier, niveau
from .phrases import DecoupeurPhrases
from .protocole import (
    Dire,
    Erreur,
    Etat,
    FinEnonce,
    Interruption,
    MessageClient,
    MessageCore,
    Reveil,
    StopAudio,
    Transcription,
    encoder_audio_sortant,
)
from .protocole_web import Latences, Niveau, Question, Reponse, Source

_journal = logging.getLogger(__name__)

EnvoyerJson = Callable[[MessageCore], Awaitable[None]]
EnvoyerBinaire = Callable[[bytes], Awaitable[None]]


async def sans_destinataire(_message: object) -> None:
    """Envoi vers personne : session sans voix, ou client audio déjà parti."""


def _ms(secondes: float) -> int:
    return round(secondes * 1000)


class Session:
    def __init__(
        self,
        envoyer_json: EnvoyerJson,
        envoyer_binaire: EnvoyerBinaire,
        transcription,
        synthese,
        cerveau: Cerveau,
        diffuseur: Diffuseur | None = None,
        avec_voix: Callable[[], bool] | None = None,
        horloge: Callable[[], float] | None = None,
        planifier: Planifier | None = None,
    ) -> None:
        self._envoyer_json = envoyer_json
        self._envoyer_binaire = envoyer_binaire
        self._transcription = transcription
        self._synthese = synthese
        self._cerveau = cerveau
        # Sans diffuseur fourni, un diffuseur sans abonné : publier ne coûte presque rien.
        self._diffuseur = diffuseur or Diffuseur()
        self._avec_voix = avec_voix or (lambda: True)
        self._horloge = horloge or time.monotonic
        self._machine = MachineEtat()
        self._tampon: list[bytes] = []
        self._tache: asyncio.Task | None = None
        self._id_enonce = 0
        self._niveaux = CalendrierNiveaux(self._publier_niveau, self._horloge, planifier)
        self._dernier_niveau = float("-inf")
        self._t_fin = 0.0  # fin de la phrase de David, ou envoi de la question tapée
        self._premiere_voix_ms: int | None = None
        self._ecrit_en_cours = False

    # --- entrées ---------------------------------------------------------

    async def sur_message(self, msg: MessageClient) -> None:
        if isinstance(msg, Reveil):
            await self._reveiller()
        elif isinstance(msg, FinEnonce):
            await self._fin_enonce()
        elif isinstance(msg, Interruption):
            await self._interrompre()

    async def sur_audio(self, pcm: bytes) -> None:
        if self._machine.valeur != "ecoute":
            return
        self._tampon.append(pcm)
        maintenant = self._horloge()
        if maintenant - self._dernier_niveau >= INTERVALLE_S:
            self._dernier_niveau = maintenant
            self._publier_niveau(niveau(pcm))

    async def sur_saisie(self, texte: str) -> None:
        """Une question tapée : elle passe devant tout, comme une coupure à la voix."""
        await self._annuler_tache()
        if self._machine.valeur != "repos":
            await self._envoyer_json(StopAudio(id_enonce=self._id_enonce))
            self._niveaux.annuler()
            self._tampon.clear()
        if self._machine.valeur == "parole":
            self._machine.aller_vers("ecoute")
        if self._machine.valeur != "reflexion":
            self._machine.aller_vers("reflexion")
        await self._etat("reflexion")
        self._t_fin = self._horloge()
        self._tache = asyncio.create_task(self._tour_texte(texte))

    async def taire(self) -> None:
        """Le mode muet vient d'être activé : la voix se tait, le texte continue."""
        if self._machine.valeur == "parole":
            await self._envoyer_json(StopAudio(id_enonce=self._id_enonce))
            self._niveaux.annuler()

    async def fermer(self) -> None:
        if self._ecrit_en_cours and self._tache is not None and not self._tache.done():
            # Le client audio part pendant une réponse à une question tapée : elle se
            # termine par écrit, pour les pages.
            self._envoyer_json = sans_destinataire
            self._envoyer_binaire = sans_destinataire
            self._avec_voix = lambda: False
            self._niveaux.annuler()
            return
        await self._annuler_tache()
        self._niveaux.annuler()

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
        self._t_fin = self._horloge()
        self._machine.aller_vers("reflexion")
        await self._etat("reflexion")
        self._tache = asyncio.create_task(self._tour())

    async def _interrompre(self) -> None:
        await self._annuler_tache()
        await self._envoyer_json(StopAudio(id_enonce=self._id_enonce))
        self._niveaux.annuler()
        if self._machine.valeur == "parole":
            self._machine.aller_vers("ecoute")
            self._tampon.clear()
            await self._etat("ecoute")
        elif self._machine.valeur == "reflexion":
            self._machine.aller_vers("repos")
            await self._etat("repos")
        elif self._machine.valeur == "repos":
            # Le tour s'est déjà terminé quand l'interruption arrive (on a coupé
            # juste à la fin de la phrase) : sans cette branche, le Core reste au
            # repos sans écouter, alors que le client, lui, s'est déjà remis à
            # capturer et à envoyer de l'audio.
            self._machine.aller_vers("ecoute")
            self._tampon.clear()
            await self._etat("ecoute")

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
            debut = self._horloge()
            texte = await self._transcription.transcrire(pcm)
            transcription_ms = _ms(self._horloge() - debut)
            await self._envoyer_json(Transcription(texte=texte, finale=True))
            if not texte.strip():
                self._machine.aller_vers("repos")
                await self._etat("repos")
                return
            await self._repondre(texte, "voix", transcription_ms)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 — on ne laisse jamais mourir la session
            await self._echouer(e)

    async def _tour_texte(self, texte: str) -> None:
        self._ecrit_en_cours = True
        try:
            await self._repondre(texte, "clavier", None)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 — on ne laisse jamais mourir la session
            await self._echouer(e)
        finally:
            self._ecrit_en_cours = False

    async def _repondre(self, texte: str, source: Source, transcription_ms: int | None) -> None:
        self._diffuseur.publier(Question(texte=texte, source=source))
        self._machine.aller_vers("parole")
        await self._etat("parole")
        self._id_enonce += 1
        identifiant = self._id_enonce
        self._premiere_voix_ms = None
        reflexion_ms: int | None = None
        debut = self._horloge()

        decoupeur = DecoupeurPhrases()
        rang = 0
        async with contextlib.aclosing(self._cerveau.repondre(texte)) as fragments:
            async for fragment in fragments:
                if reflexion_ms is None:
                    reflexion_ms = _ms(self._horloge() - debut)
                for phrase in decoupeur.ajouter(fragment):
                    rang += 1
                    await self._dire(identifiant, rang, phrase)
        for phrase in decoupeur.vider():
            rang += 1
            await self._dire(identifiant, rang, phrase)

        self._diffuseur.publier(
            Latences(
                transcription_ms=transcription_ms,
                reflexion_ms=reflexion_ms,
                premiere_voix_ms=self._premiere_voix_ms,
            )
        )
        self._machine.aller_vers("repos")
        await self._etat("repos")

    async def _echouer(self, e: Exception) -> None:
        _journal.exception("échec du tour de parole")
        # str(e) est vide pour certaines exceptions (httpx.ConnectTimeout…) : le type,
        # au moins, dit ce qui s'est passé.
        erreur = Erreur(
            code="tour", message=f"Je n'ai pas pu répondre : {str(e) or type(e).__name__}"
        )
        await self._envoyer_json(erreur)
        self._diffuseur.publier(erreur)
        if self._machine.peut_aller_vers("repos"):
            self._machine.aller_vers("repos")
            await self._etat("repos")

    async def _dire(self, identifiant: int, rang: int, phrase: str) -> None:
        self._diffuseur.publier(Reponse(texte=phrase))
        if not self._avec_voix():
            return
        await self._envoyer_json(Dire(id_enonce=identifiant, rang=rang, texte=phrase))
        n = 0
        async with contextlib.aclosing(self._synthese.synthetiser(phrase)) as blocs:
            async for bloc in blocs:
                if not self._avec_voix():
                    return  # muet activé en pleine phrase : taire() a déjà coupé le son
                n += 1
                if self._premiere_voix_ms is None:
                    self._premiere_voix_ms = _ms(self._horloge() - self._t_fin)
                await self._envoyer_binaire(encoder_audio_sortant(identifiant, bloc))
                self._niveaux.ajouter(bloc)
        if n == 0 and phrase.strip():
            # Sans cela, une synthèse muette (voix absente…) rend Atlas silencieux
            # sans que rien, nulle part, ne dise pourquoi.
            raise RuntimeError(f"la synthèse n'a produit aucun audio pour « {phrase} »")

    async def _etat(self, valeur: Valeur) -> None:
        etat = Etat(valeur=valeur)
        await self._envoyer_json(etat)
        self._diffuseur.publier(etat)

    def _publier_niveau(self, valeur: float) -> None:
        self._diffuseur.publier(Niveau(valeur=valeur))
```

- [ ] **Step 5: Vérifier que tout passe, anciens tests compris**

Run: `uv run pytest tests/test_session_web.py tests/test_session.py tests/test_etat.py tests/test_integration_boucle.py -q && uv run pytest -q && uv run ruff check . && uv run ruff format --check .`
Expected: PASS partout ; `tests/test_session.py` passe sans aucune modification.

- [ ] **Step 6: Commit**

```bash
git add src/atlas_core/etat.py src/atlas_core/session.py tests/test_etat.py tests/test_session_web.py
git commit -F - <<'MSG'
Fait publier la session, répondre aux questions tapées et se taire

La session publie au diffuseur ce qu'elle envoie au client audio, avec les
niveaux de voix, la question, les réponses et trois délais par tour. Une
question tapée passe devant tout ; le mode muet coupe la voix sans couper
le texte ; si le client audio part pendant une réponse tapée, elle se
termine par écrit. Une erreur sans message affiche au moins son type.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

### Task 5: La régie (`regie.py`)

**Files:**
- Create: `src/atlas_core/regie.py`
- Test: `tests/test_regie.py`

**Interfaces:**
- Consumes: `Diffuseur` (Task 3), `Muet` (Task 2) ; des sessions qui ont `async sur_saisie(texte)` et `async taire()` (Task 4).
- Produces: `Regie(diffuseur: Diffuseur, fabrique_session_ecrite: Callable[[], SessionPilotable])` avec l'attribut public `diffuseur`, la propriété `muet: bool`, `voix_active() -> bool`, `rattacher(session)`, `detacher(session)`, `async saisie(texte: str)`, `async basculer_muet(actif: bool)`.

- [ ] **Step 1: Écrire les tests qui échouent**

`tests/test_regie.py` :

```python
from atlas_core.diffuseur import Diffuseur
from atlas_core.protocole_web import Muet
from atlas_core.regie import Regie


class SessionEspionne:
    def __init__(self) -> None:
        self.saisies: list[str] = []
        self.taire_appels = 0

    async def sur_saisie(self, texte: str) -> None:
        self.saisies.append(texte)

    async def taire(self) -> None:
        self.taire_appels += 1


class DiffuseurEspion(Diffuseur):
    def __init__(self) -> None:
        super().__init__()
        self.publies: list = []

    def publier(self, msg) -> None:
        self.publies.append(msg)
        super().publier(msg)


def _regie():
    creees: list[SessionEspionne] = []

    def fabrique() -> SessionEspionne:
        creees.append(SessionEspionne())
        return creees[-1]

    return Regie(DiffuseurEspion(), fabrique), creees


def test_la_voix_est_active_par_defaut():
    regie, _ = _regie()
    assert regie.muet is False and regie.voix_active() is True


async def test_une_question_tapee_va_au_client_audio_connecte():
    regie, creees = _regie()
    audio = SessionEspionne()
    regie.rattacher(audio)
    await regie.saisie("quelle heure est-il")
    assert audio.saisies == ["quelle heure est-il"] and creees == []


async def test_sans_client_audio_une_seule_session_ecrite_est_creee():
    regie, creees = _regie()
    await regie.saisie("un")
    await regie.saisie("deux")
    assert len(creees) == 1 and creees[0].saisies == ["un", "deux"]


async def test_detacher_le_client_audio_renvoie_vers_la_session_ecrite():
    regie, creees = _regie()
    audio = SessionEspionne()
    regie.rattacher(audio)
    regie.detacher(SessionEspionne())  # une autre session : sans effet
    await regie.saisie("un")
    regie.detacher(audio)
    await regie.saisie("deux")
    assert audio.saisies == ["un"] and creees[0].saisies == ["deux"]


async def test_le_muet_est_publie_et_fait_taire_le_client_audio():
    regie, _ = _regie()
    audio = SessionEspionne()
    regie.rattacher(audio)
    await regie.basculer_muet(True)
    assert regie.muet is True and regie.voix_active() is False
    assert regie.diffuseur.publies == [Muet(actif=True)]
    assert audio.taire_appels == 1
    await regie.basculer_muet(False)
    assert regie.voix_active() is True and audio.taire_appels == 1
    assert regie.diffuseur.publies[-1] == Muet(actif=False)


async def test_le_muet_sans_client_audio_ne_plante_pas():
    regie, _ = _regie()
    await regie.basculer_muet(True)
    assert regie.muet is True
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `uv run pytest tests/test_regie.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'atlas_core.regie'`.

- [ ] **Step 3: Écrire l'implémentation**

`src/atlas_core/regie.py` :

```python
"""La régie : ce que partagent toutes les connexions du Core.

Le diffuseur des pages, le mode muet, et la session qui reçoit les questions tapées :
celle du client audio connecté, pour qu'Atlas réponde à voix haute, ou à défaut une
session sans voix.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from .diffuseur import Diffuseur
from .protocole_web import Muet


class SessionPilotable(Protocol):
    async def sur_saisie(self, texte: str) -> None: ...

    async def taire(self) -> None: ...


class Regie:
    def __init__(
        self, diffuseur: Diffuseur, fabrique_session_ecrite: Callable[[], SessionPilotable]
    ) -> None:
        self.diffuseur = diffuseur
        self._fabrique_session_ecrite = fabrique_session_ecrite
        self._session_audio: SessionPilotable | None = None
        self._session_ecrite: SessionPilotable | None = None
        self._muet = False

    @property
    def muet(self) -> bool:
        return self._muet

    def voix_active(self) -> bool:
        return not self._muet

    def rattacher(self, session: SessionPilotable) -> None:
        """Un client audio vient de se connecter : il répondra aux questions tapées."""
        self._session_audio = session

    def detacher(self, session: SessionPilotable) -> None:
        if self._session_audio is session:
            self._session_audio = None

    async def saisie(self, texte: str) -> None:
        session = self._session_audio
        if session is None:
            if self._session_ecrite is None:
                self._session_ecrite = self._fabrique_session_ecrite()
            session = self._session_ecrite
        await session.sur_saisie(texte)

    async def basculer_muet(self, actif: bool) -> None:
        self._muet = actif
        self.diffuseur.publier(Muet(actif=actif))
        if actif and self._session_audio is not None:
            await self._session_audio.taire()
```

- [ ] **Step 4: Vérifier que les tests passent**

Run: `uv run pytest tests/test_regie.py -q && uv run ruff check . && uv run ruff format --check .`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add src/atlas_core/regie.py tests/test_regie.py
git commit -F - <<'MSG'
Ajoute la régie : mode muet et routage des questions tapées

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

### Task 6: La connexion `/ws/web`, la clé et le service de la page

**Files:**
- Modify: `src/atlas_core/config.py` (champ `web_cle`)
- Create: `src/atlas_core/web.py`
- Replace: `src/atlas_core/hub.py` (contenu complet ci-dessous)
- Create: `src/atlas_web/index.html` (page provisoire, remplacée à la Task 12)
- Modify: `.env.example` (ajout de `ATLAS_WEB_CLE`)
- Test: `tests/test_config.py`, `tests/test_web_securite.py`, `tests/test_hub_web.py` (nouveaux) ; `tests/test_hub.py` doit passer sans modification

**Interfaces:**
- Consumes: `Diffuseur` (3), `Session`, `sans_destinataire` (4), `Regie` (5), `Authentification`, `Muet`, `Saisie`, `decoder_message_page` (2).
- Produces: `Config.web_cle: str` (vide si absente) ; `web.origine_autorisee(origine: str | None, hote: str | None) -> bool`, `web.cle_valide(proposee: str, attendue: str) -> bool`, `web.politique_securite(hote: str) -> str` ; dans `hub` : `DELAI_AUTHENTIFICATION_S = 5.0`, `FERMETURE_CLE_ABSENTE = 4000`, `FERMETURE_NON_AUTORISE = 4401`, `FERMETURE_ORIGINE = 1008`, `RACINE_WEB` (le dossier `src/atlas_web`), la variable de module `_regie`, `creer_session(envoyer_json, envoyer_binaire)` (signature inchangée), `creer_session_ecrite()`, la route `/ws/web` et le montage de la page sur `/`.

- [ ] **Step 1: Écrire les tests qui échouent**

`tests/test_config.py` :

```python
from atlas_core.config import Config


def test_la_cle_web_vient_de_l_environnement(monkeypatch):
    monkeypatch.setenv("ATLAS_WEB_CLE", "  cle-secrete  ")
    assert Config.depuis_environnement().web_cle == "cle-secrete"


def test_sans_cle_web_la_valeur_est_vide(monkeypatch):
    monkeypatch.delenv("ATLAS_WEB_CLE", raising=False)
    assert Config.depuis_environnement().web_cle == ""
```

`tests/test_web_securite.py` :

```python
import pytest

from atlas_core.web import cle_valide, origine_autorisee, politique_securite


@pytest.mark.parametrize(
    "origine,hote,attendu",
    [
        ("http://atlas.local:8080", "atlas.local:8080", True),
        ("http://ATLAS.local:8080", "atlas.local:8080", True),
        ("https://atlas.local:8080", "atlas.local:8080", True),
        ("http://ailleurs.example", "atlas.local:8080", False),
        ("http://atlas.local:9999", "atlas.local:8080", False),
        (None, "atlas.local:8080", False),
        ("http://atlas.local:8080", None, False),
        ("", "", False),
    ],
)
def test_l_origine_doit_etre_la_page_du_core(origine, hote, attendu):
    assert origine_autorisee(origine, hote) is attendu


def test_la_cle_est_comparee_exactement():
    assert cle_valide("abc", "abc") is True
    assert cle_valide("abd", "abc") is False
    assert cle_valide("", "abc") is False


def test_une_cle_attendue_vide_ne_valide_jamais_rien():
    assert cle_valide("", "") is False


def test_la_politique_autorise_la_connexion_au_meme_hote():
    politique = politique_securite("atlas.local:8080")
    assert politique.startswith("default-src 'self'; ")
    assert "connect-src 'self' ws://atlas.local:8080 wss://atlas.local:8080;" in politique
    assert "frame-ancestors 'none'" in politique


def test_un_hote_bizarre_n_entre_pas_dans_la_politique():
    politique = politique_securite("x; script-src *")
    assert "script-src" not in politique
    assert "connect-src 'self';" in politique
```

`tests/test_hub_web.py` :

```python
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from atlas_core import hub
from atlas_core.diffuseur import Diffuseur

ORIGINE = {"origin": "http://testserver"}
CLE = "cle-de-test"


class RegieEspionne:
    def __init__(self) -> None:
        self.diffuseur = Diffuseur()
        self.saisies: list[str] = []
        self.muets: list[bool] = []

    def voix_active(self) -> bool:
        return True

    def rattacher(self, session) -> None:
        pass

    def detacher(self, session) -> None:
        pass

    async def saisie(self, texte: str) -> None:
        self.saisies.append(texte)

    async def basculer_muet(self, actif: bool) -> None:
        self.muets.append(actif)


@pytest.fixture
def regie(monkeypatch) -> RegieEspionne:
    espionne = RegieEspionne()
    monkeypatch.setattr(hub, "_regie", espionne)
    monkeypatch.setattr(hub, "_config", replace(hub._config, web_cle=CLE))
    return espionne


def _entrer(ws, cle: str = CLE) -> list[str]:
    ws.send_json({"type": "authentification", "cle": cle})
    return [ws.receive_json()["type"] for _ in range(3)]


def test_une_page_authentifiee_recoit_historique_muet_et_etat(regie):
    with TestClient(hub.app) as client, client.websocket_connect("/ws/web", headers=ORIGINE) as ws:
        assert _entrer(ws) == ["historique", "muet", "etat"]


def test_saisie_et_muet_arrivent_a_la_regie(regie):
    with TestClient(hub.app) as client, client.websocket_connect("/ws/web", headers=ORIGINE) as ws:
        _entrer(ws)
        ws.send_json({"type": "saisie", "texte": " quelle heure est-il "})
        ws.send_json({"type": "muet", "actif": True})
        ws.send_json({"type": "saisie", "texte": ""})  # sa réponse prouve que tout est traité
        erreur = ws.receive_json()
    assert erreur["type"] == "erreur" and erreur["code"] == "message_invalide"
    assert "entre 1 et 1000 caractères" in erreur["message"]
    assert regie.saisies == ["quelle heure est-il"] and regie.muets == [True]


def test_une_mauvaise_cle_ferme_la_connexion(regie):
    with TestClient(hub.app) as client, client.websocket_connect("/ws/web", headers=ORIGINE) as ws:
        ws.send_json({"type": "authentification", "cle": "pas-la-bonne"})
        with pytest.raises(WebSocketDisconnect) as fermeture:
            ws.receive_json()
    assert fermeture.value.code == hub.FERMETURE_NON_AUTORISE


def test_un_autre_premier_message_ferme_la_connexion(regie):
    with TestClient(hub.app) as client, client.websocket_connect("/ws/web", headers=ORIGINE) as ws:
        ws.send_json({"type": "saisie", "texte": "sans clé"})
        with pytest.raises(WebSocketDisconnect) as fermeture:
            ws.receive_json()
    assert fermeture.value.code == hub.FERMETURE_NON_AUTORISE
    assert regie.saisies == []


def test_sans_authentification_la_connexion_se_ferme(regie, monkeypatch):
    monkeypatch.setattr(hub, "DELAI_AUTHENTIFICATION_S", 0.05)
    with TestClient(hub.app) as client, client.websocket_connect("/ws/web", headers=ORIGINE) as ws:
        with pytest.raises(WebSocketDisconnect) as fermeture:
            ws.receive_json()
    assert fermeture.value.code == hub.FERMETURE_NON_AUTORISE


def test_sans_cle_configuree_la_page_est_prevenue(regie, monkeypatch):
    monkeypatch.setattr(hub, "_config", replace(hub._config, web_cle=""))
    with TestClient(hub.app) as client, client.websocket_connect("/ws/web", headers=ORIGINE) as ws:
        erreur = ws.receive_json()
        with pytest.raises(WebSocketDisconnect) as fermeture:
            ws.receive_json()
    assert erreur["code"] == "cle_absente" and "ATLAS_WEB_CLE" in erreur["message"]
    assert fermeture.value.code == hub.FERMETURE_CLE_ABSENTE


def test_une_autre_origine_est_refusee_avant_meme_d_accepter(regie):
    with TestClient(hub.app) as client:
        with pytest.raises(WebSocketDisconnect) as fermeture:
            with client.websocket_connect("/ws/web", headers={"origin": "http://ailleurs.example"}):
                pass
    assert fermeture.value.code == hub.FERMETURE_ORIGINE


def test_la_page_est_servie_avec_sa_politique_de_securite():
    with TestClient(hub.app) as client:
        r = client.get("/")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert r.headers["content-security-policy"].startswith("default-src 'self'")
    assert "ws://testserver" in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff"


def test_la_route_de_sante_reste_disponible():
    with TestClient(hub.app) as client:
        assert client.get("/sante").json()["ok"] is True
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `uv run pytest tests/test_config.py tests/test_web_securite.py tests/test_hub_web.py -q`
Expected: FAIL (`AttributeError`/`ModuleNotFoundError` : `web_cle`, `atlas_core.web`, `hub.FERMETURE_*` n'existent pas).

- [ ] **Step 3: Ajouter la clé à la configuration**

Dans `src/atlas_core/config.py`, remplacer la docstring du module par :

```python
"""Configuration lue dans l'environnement.

Des adresses, et la clé d'accès des pages web : jamais écrite dans le code, elle ne
vient que du .env du Core.
"""
```

ajouter le champ après `port_core: int` :

```python
    web_cle: str  # vide : la page web reste fermée
```

et, dans `depuis_environnement`, après la ligne de `port_core` :

```python
            web_cle=os.environ.get("ATLAS_WEB_CLE", "").strip(),
```

- [ ] **Step 4: Écrire les garde-fous (`src/atlas_core/web.py`)**

```python
"""Garde-fous de la page web : origine des connexions, clé d'accès, politique de sécurité."""

from __future__ import annotations

import hmac
import re
from urllib.parse import urlsplit

# Un hôte « normal » (nom ou IPv4, IPv6 entre crochets, port facultatif) : lui seul entre
# dans l'en-tête de politique de sécurité, pour qu'un en-tête Host fantaisiste n'y
# injecte rien.
_HOTE_SUR = re.compile(r"^(?:[A-Za-z0-9.\-]+|\[[0-9A-Fa-f:.]+\])(?::\d{1,5})?$")


def origine_autorisee(origine: str | None, hote: str | None) -> bool:
    """La connexion vient-elle de la page servie par ce même Core ?"""
    if not origine or not hote:
        return False
    try:
        netloc = urlsplit(origine).netloc
    except ValueError:
        return False
    return bool(netloc) and netloc.lower() == hote.lower()


def cle_valide(proposee: str, attendue: str) -> bool:
    """Comparaison en temps constant ; une clé attendue vide ne valide jamais rien."""
    if not attendue:
        return False
    return hmac.compare_digest(proposee.encode(), attendue.encode())


def politique_securite(hote: str) -> str:
    connexions = "'self'"
    if _HOTE_SUR.match(hote or ""):
        connexions += f" ws://{hote} wss://{hote}"
    return (
        "default-src 'self'; "
        f"connect-src {connexions}; "
        "img-src 'self' data:; "
        "base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
    )
```

- [ ] **Step 5: Créer la page provisoire**

`src/atlas_web/index.html` (remplacée par la vraie page à la Task 12) :

```html
<!doctype html>
<html lang="fr">
<head><meta charset="utf-8"><title>Atlas</title></head>
<body><p>Atlas</p></body>
</html>
```

- [ ] **Step 6: Réécrire `src/atlas_core/hub.py`**

Contenu complet :

```python
"""Serveur du Core : route de santé, WebSocket audio, WebSocket et page web."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from .cerveau import CerveauBouchon
from .config import Config
from .diffuseur import Diffuseur
from .protocole import Erreur, decoder_audio_entrant, decoder_message
from .protocole_web import Authentification, Muet, Saisie, decoder_message_page
from .regie import Regie
from .session import Session, sans_destinataire
from .synthese import ClientSynthese
from .transcription import ClientTranscription
from .web import cle_valide, origine_autorisee, politique_securite

_journal = logging.getLogger(__name__)
_config = Config.depuis_environnement()
_http: httpx.AsyncClient | None = None

RACINE_WEB = Path(__file__).resolve().parent.parent / "atlas_web"
DELAI_AUTHENTIFICATION_S = 5.0
FERMETURE_CLE_ABSENTE = 4000
FERMETURE_NON_AUTORISE = 4401
FERMETURE_ORIGINE = 1008  # « policy violation », avant même d'accepter la connexion


@asynccontextmanager
async def _cycle_de_vie(app: FastAPI):
    global _http
    _http = httpx.AsyncClient()
    try:
        yield
    finally:
        await _http.aclose()
        _http = None


app = FastAPI(title="atlas-core", lifespan=_cycle_de_vie)


def _services() -> dict:
    assert _http is not None, "le cycle de vie de l'application n'a pas démarré"
    return {
        "transcription": ClientTranscription(_config.stt_url, _http),
        "synthese": ClientSynthese(_config.tts_url, _config.tts_voix, _http),
        "cerveau": CerveauBouchon(),
    }


def creer_session(envoyer_json, envoyer_binaire) -> Session:
    return Session(
        envoyer_json=envoyer_json,
        envoyer_binaire=envoyer_binaire,
        diffuseur=_regie.diffuseur,
        avec_voix=_regie.voix_active,
        **_services(),
    )


def creer_session_ecrite() -> Session:
    """Répond aux questions tapées quand aucun client audio n'est connecté : par écrit."""
    return Session(
        envoyer_json=sans_destinataire,
        envoyer_binaire=sans_destinataire,
        diffuseur=_regie.diffuseur,
        avec_voix=lambda: False,
        **_services(),
    )


_regie = Regie(Diffuseur(), lambda: creer_session_ecrite())


@app.middleware("http")
async def _en_tetes_de_securite(request: Request, call_next):
    reponse = await call_next(request)
    reponse.headers["Content-Security-Policy"] = politique_securite(request.headers.get("host", ""))
    reponse.headers["X-Content-Type-Options"] = "nosniff"
    reponse.headers["Referrer-Policy"] = "no-referrer"
    return reponse


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
    _regie.rattacher(session)
    try:
        while True:
            recu = await ws.receive()
            if recu["type"] == "websocket.disconnect":
                break
            if (texte := recu.get("text")) is not None:
                try:
                    await session.sur_message(decoder_message(texte))
                except ValueError as e:
                    await envoyer_json(Erreur(code="message_invalide", message=str(e)))
            elif (binaire := recu.get("bytes")) is not None:
                try:
                    await session.sur_audio(decoder_audio_entrant(binaire))
                except ValueError as e:
                    await envoyer_json(Erreur(code="trame_invalide", message=str(e)))
    except WebSocketDisconnect:
        pass
    finally:
        _regie.detacher(session)
        await session.fermer()


async def _recevoir_texte(ws: WebSocket) -> str | None:
    """Le prochain message texte de la page, ou None si elle s'est déconnectée."""
    while True:
        recu = await ws.receive()
        if recu["type"] == "websocket.disconnect":
            return None
        if (texte := recu.get("text")) is not None:
            return texte


@app.websocket("/ws/web")
async def ws_web(ws: WebSocket) -> None:
    if not origine_autorisee(ws.headers.get("origin"), ws.headers.get("host")):
        await ws.close(code=FERMETURE_ORIGINE)
        return
    await ws.accept()
    if not _config.web_cle:
        message = (
            "La clé d'accès n'est pas configurée : ajoute ATLAS_WEB_CLE dans le .env du Core, "
            "puis redémarre-le."
        )
        await ws.send_text(Erreur(code="cle_absente", message=message).model_dump_json())
        await ws.close(code=FERMETURE_CLE_ABSENTE)
        return

    try:
        premier = await asyncio.wait_for(_recevoir_texte(ws), DELAI_AUTHENTIFICATION_S)
    except TimeoutError:
        premier = ""
    if premier is None:
        return  # la page est déjà partie
    try:
        demande = decoder_message_page(premier)
    except ValueError:
        demande = None
    if not isinstance(demande, Authentification) or not cle_valide(demande.cle, _config.web_cle):
        await ws.close(code=FERMETURE_NON_AUTORISE)
        return

    async def envoyer(msg) -> None:
        await ws.send_text(msg.model_dump_json())

    abonnement = _regie.diffuseur.abonner(envoyer)
    try:
        while (texte := await _recevoir_texte(ws)) is not None:
            try:
                msg = decoder_message_page(texte)
            except ValueError as e:
                abonnement.envoyer_prive(Erreur(code="message_invalide", message=str(e)))
                continue
            if isinstance(msg, Saisie):
                await _regie.saisie(msg.texte)
            elif isinstance(msg, Muet):
                await _regie.basculer_muet(msg.actif)
    except WebSocketDisconnect:
        pass
    finally:
        await abonnement.fermer()


# Toujours en dernier : monté sur « / », il capterait sinon les routes déclarées après lui.
app.mount("/", StaticFiles(directory=RACINE_WEB, html=True), name="web")
```

- [ ] **Step 7: Documenter la clé dans `.env.example`**

Ajouter à la fin de `.env.example` :

```
# Page web d'Atlas (orbe et conversation), servie par le Core à sa racine.
# Clé d'accès demandée par la page, une fois par appareil. Vide : la page reste fermée.
# À générer avec : python3 -c "import secrets; print(secrets.token_urlsafe(24))"
# (la vraie valeur ne va que dans le .env du Core, jamais dans ce fichier).
ATLAS_WEB_CLE=
```

- [ ] **Step 8: Vérifier que tout passe**

Run: `uv run pytest tests/test_config.py tests/test_web_securite.py tests/test_hub_web.py tests/test_hub.py -q && uv run pytest -q && uv run ruff check . && uv run ruff format --check .`
Expected: PASS partout ; `tests/test_hub.py` passe sans modification.

- [ ] **Step 9: Commit**

```bash
git add src/atlas_core/config.py src/atlas_core/web.py src/atlas_core/hub.py src/atlas_web/index.html .env.example tests/test_config.py tests/test_web_securite.py tests/test_hub_web.py
git commit -F - <<'MSG'
Ouvre la connexion /ws/web, protégée par clé et origine, et sert la page

Le Core sert la page à sa racine, avec une politique de sécurité qui
n'autorise que lui-même. /ws/web refuse une autre origine avant même
d'accepter, ferme sans clé valide en 5 s, et relaie saisies et mode muet
à la régie.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```


---

### Task 7: Les fondations de la page (état, historique, registres)

**Files:**
- Create: `src/atlas_web/package.json`, `src/atlas_web/etat.js`, `src/atlas_web/historique.js`, `src/atlas_web/registre.js`
- Create: `tests/web/faux_dom.mjs`
- Test: `tests/web/etat.test.mjs`, `tests/web/historique.test.mjs`, `tests/web/registre.test.mjs`

**Interfaces:**
- Consumes: rien (modules purs, sans DOM).
- Produces:
  - `etat.js` : `COULEURS`, `COULEUR_HORS_LIGNE`, `LIBELLES`, `DELAI_SOUS_TITRES_MS = 10000`, `TAILLE_HISTORIQUE = 50`, `SEUIL_SYLLABE = 0.55`, `REFRACTAIRE_SYLLABE_S = 0.18` ; `creerEtat()` ; `heureDe(ms) -> "HH:MM"` ; `appliquerMessage(etat, message, maintenantMs)` ; `avancer(etat, dt)` ; `sousTitresVisibles(etat, maintenantMs) -> bool` ; `sceneDe(etat, dt, reduire = false) -> { etat, volume, couleur, syllabe, dt }`. L'objet état a les champs `enLigne, etat, reposDepuis, volumeCible, volume, couleur, syllabe, auDessusSeuil, depuisSyllabe, question, reponse, erreur, historique, muet`. Un échange d'historique : `{ heure, source, question, reponse, erreur, latences }`.
  - `historique.js` : `formaterDuree(ms) -> string | null`, `formaterLatences(latences) -> string`, `rendreHistorique(document, liste, echanges)`.
  - `registre.js` : `lireStockage(stockage, cle)`, `ecrireStockage(stockage, cle, valeur) -> bool` (n'échouent jamais), `creerRegistre(elements, idParDefaut, cle) -> { tous, parDefaut, choisi(stockage), choisir(stockage, id) }`.
  - `tests/web/faux_dom.mjs` : `fauxElement(tag)`, `fauxDocument()`, `fauxStockage(initial)`, `stockageCasse`.

- [ ] **Step 1: Écrire les doublures et les tests qui échouent**

`src/atlas_web/package.json` (sert à Node : sans lui, les `.js` ne seraient pas lus comme des modules) :

```json
{
  "private": true,
  "type": "module"
}
```

`tests/web/faux_dom.mjs` :

```js
// Doublures minimales du DOM et du stockage du navigateur, pour node --test.

export function fauxElement(tag) {
  const classes = new Set();
  const ecouteurs = {};
  return {
    tagName: tag.toUpperCase(),
    children: [],
    className: "",
    textContent: "",
    type: "",
    hidden: false,
    classList: {
      add: (nom) => classes.add(nom),
      remove: (nom) => classes.delete(nom),
      contains: (nom) => classes.has(nom),
      toggle(nom, force) {
        const actif = force ?? !classes.has(nom);
        if (actif) classes.add(nom);
        else classes.delete(nom);
        return actif;
      },
    },
    append(...enfants) {
      this.children.push(...enfants);
    },
    replaceChildren(...enfants) {
      this.children = enfants;
    },
    addEventListener(type, rappel) {
      (ecouteurs[type] ??= []).push(rappel);
    },
    declencher(type, evenement = {}) {
      for (const rappel of ecouteurs[type] ?? []) rappel(evenement);
    },
  };
}

export function fauxDocument() {
  return { createElement: (tag) => fauxElement(tag) };
}

export function fauxStockage(initial = {}) {
  const valeurs = new Map(Object.entries(initial));
  return {
    getItem: (cle) => valeurs.get(cle) ?? null,
    setItem: (cle, valeur) => valeurs.set(cle, String(valeur)),
  };
}

export const stockageCasse = {
  getItem() {
    throw new Error("stockage interdit");
  },
  setItem() {
    throw new Error("stockage interdit");
  },
};
```

`tests/web/etat.test.mjs` :

```js
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  COULEURS,
  COULEUR_HORS_LIGNE,
  DELAI_SOUS_TITRES_MS,
  TAILLE_HISTORIQUE,
  appliquerMessage,
  avancer,
  creerEtat,
  heureDe,
  sceneDe,
  sousTitresVisibles,
} from "../../src/atlas_web/etat.js";

const T0 = Date.UTC(2026, 8, 24, 12, 0, 0);

function proche(a, b, tolerance = 1) {
  a.forEach((x, i) => assert.ok(Math.abs(x - b[i]) <= tolerance, `${a} ≉ ${b}`));
}

function avancerLongtemps(etat, secondes, dt = 1 / 60) {
  for (let t = 0; t < secondes; t += dt) avancer(etat, dt);
}

test("un état neuf est hors ligne, au repos et gris", () => {
  const e = creerEtat();
  assert.equal(e.enLigne, false);
  assert.equal(e.etat, "repos");
  assert.deepEqual(e.couleur, COULEUR_HORS_LIGNE);
  assert.deepEqual(e.historique, []);
});

test("les messages etat et niveau pilotent l'orbe", () => {
  const e = creerEtat();
  appliquerMessage(e, { type: "etat", valeur: "ecoute" }, T0);
  appliquerMessage(e, { type: "niveau", valeur: 0.8 }, T0);
  assert.equal(e.etat, "ecoute");
  assert.equal(e.volumeCible, 0.8);
  appliquerMessage(e, { type: "etat", valeur: "reflexion" }, T0);
  assert.equal(e.volumeCible, 0);
});

test("le volume rejoint sa cible en douceur", () => {
  const e = creerEtat();
  e.enLigne = true;
  e.etat = "parole";
  e.volumeCible = 1;
  avancer(e, 1 / 60);
  assert.ok(e.volume > 0 && e.volume < 0.5);
  avancerLongtemps(e, 1);
  assert.ok(e.volume > 0.99);
});

test("au repos, la cible du volume retombe d'elle-même", () => {
  const e = creerEtat();
  e.enLigne = true;
  e.volumeCible = 1;
  avancerLongtemps(e, 3);
  assert.ok(e.volumeCible < 0.01 && e.volume < 0.05);
});

test("la couleur glisse vers celle de l'état, puis vers le gris hors ligne", () => {
  const e = creerEtat();
  e.enLigne = true;
  e.etat = "parole";
  avancer(e, 1 / 60);
  assert.notDeepEqual(e.couleur, COULEURS.parole);
  avancerLongtemps(e, 3);
  proche(e.couleur, COULEURS.parole);
  e.enLigne = false;
  avancerLongtemps(e, 3);
  proche(e.couleur, COULEUR_HORS_LIGNE);
});

test("une syllabe est signalée une fois par montée du volume", () => {
  const e = creerEtat();
  e.enLigne = true;
  e.etat = "ecoute";
  const syllabes = [];
  for (const cible of [0.9, 0.1, 0.9]) {
    e.volumeCible = cible;
    for (let i = 0; i < 30; i++) {
      avancer(e, 1 / 60);
      syllabes.push(e.syllabe);
    }
  }
  assert.equal(syllabes.filter(Boolean).length, 2);
});

test("question puis réponses : sous-titres et historique", () => {
  const e = creerEtat();
  appliquerMessage(e, { type: "question", texte: "Quelle heure ?", source: "clavier" }, T0);
  appliquerMessage(e, { type: "reponse", texte: "Il est midi." }, T0);
  appliquerMessage(e, { type: "reponse", texte: "Tu déjeunes ?" }, T0);
  assert.equal(e.question, "Quelle heure ?");
  assert.equal(e.reponse, "Il est midi. Tu déjeunes ?");
  const [echange] = e.historique;
  assert.equal(echange.source, "clavier");
  assert.equal(echange.reponse, "Il est midi. Tu déjeunes ?");
  assert.match(echange.heure, /^\d\d:\d\d$/);
});

test("une erreur pendant un tour s'attache à l'échange, sinon elle en crée un", () => {
  const e = creerEtat();
  appliquerMessage(e, { type: "etat", valeur: "reflexion" }, T0);
  appliquerMessage(e, { type: "question", texte: "Bonjour", source: "voix" }, T0);
  appliquerMessage(e, { type: "erreur", code: "tour", message: "Je n'ai pas pu répondre : panne" }, T0);
  appliquerMessage(e, { type: "etat", valeur: "repos" }, T0);
  appliquerMessage(e, { type: "erreur", code: "tour", message: "Je n'ai pas pu répondre : délai" }, T0);
  assert.equal(e.historique.length, 2);
  assert.equal(e.historique[0].erreur, "Je n'ai pas pu répondre : panne");
  assert.equal(e.historique[1].question, "");
  assert.equal(e.erreur, "Je n'ai pas pu répondre : délai");
});

test("l'erreur de clé absente ne va pas dans l'historique", () => {
  const e = creerEtat();
  appliquerMessage(e, { type: "erreur", code: "cle_absente", message: "ATLAS_WEB_CLE…" }, T0);
  assert.deepEqual(e.historique, []);
});

test("les latences s'attachent au dernier échange, le muet est suivi", () => {
  const e = creerEtat();
  appliquerMessage(e, { type: "question", texte: "q", source: "voix" }, T0);
  appliquerMessage(
    e,
    { type: "latences", transcription_ms: 420, reflexion_ms: 12, premiere_voix_ms: null },
    T0,
  );
  appliquerMessage(e, { type: "muet", actif: true }, T0);
  assert.deepEqual(e.historique[0].latences, {
    transcription_ms: 420,
    reflexion_ms: 12,
    premiere_voix_ms: null,
  });
  assert.equal(e.muet, true);
});

test("l'historique du Core remplace celui de la page", () => {
  const e = creerEtat();
  appliquerMessage(e, { type: "question", texte: "ancienne", source: "voix" }, T0);
  const echange = { heure: "09:00", source: "clavier", question: "q", reponse: "r", erreur: null, latences: null };
  appliquerMessage(e, { type: "historique", echanges: [echange] }, T0);
  assert.deepEqual(e.historique, [echange]);
});

test("l'historique de la page est limité", () => {
  const e = creerEtat();
  for (let i = 0; i < TAILLE_HISTORIQUE + 5; i++) {
    appliquerMessage(e, { type: "question", texte: `q${i}`, source: "voix" }, T0);
  }
  assert.equal(e.historique.length, TAILLE_HISTORIQUE);
  assert.equal(e.historique[0].question, "q5");
});

test("les sous-titres s'effacent après 10 s de repos", () => {
  const e = creerEtat();
  appliquerMessage(e, { type: "etat", valeur: "parole" }, T0);
  assert.equal(sousTitresVisibles(e, T0 + 60000), true);
  appliquerMessage(e, { type: "etat", valeur: "repos" }, T0);
  assert.equal(sousTitresVisibles(e, T0 + DELAI_SOUS_TITRES_MS - 1), true);
  assert.equal(sousTitresVisibles(e, T0 + DELAI_SOUS_TITRES_MS + 1), false);
});

test("une erreur au repos reste affichée 10 s", () => {
  const e = creerEtat();
  appliquerMessage(e, { type: "etat", valeur: "repos" }, T0);
  appliquerMessage(e, { type: "erreur", code: "tour", message: "panne" }, T0 + 60000);
  assert.equal(sousTitresVisibles(e, T0 + 65000), true);
});

test("la scène d'une page hors ligne est au repos, et réduite si demandé", () => {
  const e = creerEtat();
  e.etat = "parole";
  e.volume = 1;
  assert.equal(sceneDe(e, 0.016).etat, "repos");
  e.enLigne = true;
  const scene = sceneDe(e, 0.016, true);
  assert.equal(scene.etat, "parole");
  assert.equal(scene.volume, 0.6);
  assert.equal(scene.dt, 0.016);
  assert.equal(scene.couleur, e.couleur);
});

test("heureDe écrit l'heure locale sur deux chiffres", () => {
  assert.match(heureDe(T0), /^\d\d:\d\d$/);
});
```

`tests/web/historique.test.mjs` :

```js
import assert from "node:assert/strict";
import { test } from "node:test";

import { formaterDuree, formaterLatences, rendreHistorique } from "../../src/atlas_web/historique.js";
import { fauxDocument } from "./faux_dom.mjs";

test("les durées s'écrivent en ms sous la seconde, en secondes au-delà", () => {
  assert.equal(formaterDuree(420), "420 ms");
  assert.equal(formaterDuree(1234), "1,2 s");
  assert.equal(formaterDuree(null), null);
  assert.equal(formaterDuree(undefined), null);
});

test("les délais d'un échange se lisent d'une traite", () => {
  assert.equal(
    formaterLatences({ transcription_ms: 420, reflexion_ms: 1234, premiere_voix_ms: null }),
    "transcription 420 ms · réflexion 1,2 s",
  );
  assert.equal(formaterLatences(null), "");
});

test("l'historique se rend en texte brut, un élément par échange", () => {
  const document = fauxDocument();
  const liste = document.createElement("ol");
  rendreHistorique(document, liste, [
    {
      heure: "14:31",
      source: "clavier",
      question: "<b>q</b>",
      reponse: "r",
      erreur: null,
      latences: { transcription_ms: null, reflexion_ms: 12, premiere_voix_ms: 900 },
    },
    { heure: "14:32", source: "voix", question: "", reponse: "", erreur: "panne", latences: null },
  ]);
  assert.equal(liste.children.length, 2);
  const [premier, second] = liste.children;
  assert.deepEqual(
    premier.children.map((p) => [p.className, p.textContent]),
    [
      ["entete", "14:31 ⌨"],
      ["question", "<b>q</b>"],
      ["reponse", "r"],
      ["latences", "réflexion 12 ms · voix 900 ms"],
    ],
  );
  assert.deepEqual(second.children.map((p) => p.className), ["entete", "question", "erreur"]);
  assert.equal(second.children[0].textContent, "14:32 🎙");
  assert.equal(second.children[1].textContent, "(rien d'entendu)");
});
```

`tests/web/registre.test.mjs` :

```js
import assert from "node:assert/strict";
import { test } from "node:test";

import { creerRegistre, ecrireStockage, lireStockage } from "../../src/atlas_web/registre.js";
import { fauxStockage, stockageCasse } from "./faux_dom.mjs";

const ELEMENTS = [{ id: "a" }, { id: "b" }, { id: "c" }];

test("sans choix mémorisé, l'élément par défaut est choisi", () => {
  const registre = creerRegistre(ELEMENTS, "b", "cle");
  assert.equal(registre.choisi(fauxStockage()).id, "b");
  assert.equal(registre.parDefaut.id, "b");
  assert.equal(registre.tous, ELEMENTS);
});

test("un choix mémorisé est retrouvé, un choix inconnu est ignoré", () => {
  const registre = creerRegistre(ELEMENTS, "b", "cle");
  assert.equal(registre.choisi(fauxStockage({ cle: "c" })).id, "c");
  assert.equal(registre.choisi(fauxStockage({ cle: "z" })).id, "b");
});

test("choisir mémorise et rend l'élément", () => {
  const registre = creerRegistre(ELEMENTS, "b", "cle");
  const stockage = fauxStockage();
  assert.equal(registre.choisir(stockage, "a").id, "a");
  assert.equal(stockage.getItem("cle"), "a");
});

test("choisir un élément inconnu lève une erreur", () => {
  assert.throws(() => creerRegistre(ELEMENTS, "b", "cle").choisir(fauxStockage(), "z"), /inconnu/);
});

test("un stockage indisponible ne casse rien", () => {
  const registre = creerRegistre(ELEMENTS, "b", "cle");
  assert.equal(registre.choisi(stockageCasse).id, "b");
  assert.equal(registre.choisi(null).id, "b");
  assert.equal(registre.choisir(stockageCasse, "c").id, "c");
});

test("les identifiants en double et un défaut introuvable sont refusés", () => {
  assert.throws(() => creerRegistre([{ id: "a" }, { id: "a" }], "a", "cle"), /double/);
  assert.throws(() => creerRegistre(ELEMENTS, "z", "cle"), /défaut/);
});

test("lire et écrire le stockage n'échouent jamais", () => {
  assert.equal(lireStockage(stockageCasse, "cle"), null);
  assert.equal(ecrireStockage(stockageCasse, "cle", "v"), false);
  const stockage = fauxStockage();
  assert.equal(ecrireStockage(stockage, "cle", "v"), true);
  assert.equal(lireStockage(stockage, "cle"), "v");
});
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `node --test "tests/web/*.test.mjs"`
Expected: FAIL, `Cannot find module '…/src/atlas_web/etat.js'` (et de même pour `historique.js`, `registre.js`).

- [ ] **Step 3: Écrire les trois modules**

`src/atlas_web/etat.js` :

```js
// L'état de la page, reconstruit à partir des messages du Core. Aucun accès au DOM :
// tout ici se teste avec node --test.

export const COULEURS = {
  repos: [100, 130, 170],
  ecoute: [34, 211, 238],
  reflexion: [167, 139, 250],
  parole: [251, 191, 36],
};
export const COULEUR_HORS_LIGNE = [90, 96, 110];
export const LIBELLES = { repos: "Repos", ecoute: "Écoute", reflexion: "Réflexion", parole: "Parole" };
export const DELAI_SOUS_TITRES_MS = 10000;
export const TAILLE_HISTORIQUE = 50;
export const SEUIL_SYLLABE = 0.55;
export const REFRACTAIRE_SYLLABE_S = 0.18;

export function creerEtat() {
  return {
    enLigne: false,
    etat: "repos",
    reposDepuis: null,
    volumeCible: 0,
    volume: 0,
    couleur: COULEUR_HORS_LIGNE.slice(),
    syllabe: false,
    auDessusSeuil: false,
    depuisSyllabe: Infinity,
    question: "",
    reponse: "",
    erreur: "",
    historique: [],
    muet: false,
  };
}

export function heureDe(ms) {
  const d = new Date(ms);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function joindre(avant, texte) {
  return avant ? `${avant} ${texte}` : texte;
}

function ajouterEchange(e, echange) {
  e.historique.push(echange);
  if (e.historique.length > TAILLE_HISTORIQUE) e.historique.shift();
}

export function appliquerMessage(e, message, maintenantMs) {
  const dernier = e.historique[e.historique.length - 1];
  switch (message.type) {
    case "etat":
      e.etat = message.valeur;
      e.reposDepuis = message.valeur === "repos" ? maintenantMs : null;
      if (message.valeur === "repos" || message.valeur === "reflexion") e.volumeCible = 0;
      break;
    case "niveau":
      e.volumeCible = message.valeur;
      break;
    case "question":
      e.question = message.texte;
      e.reponse = "";
      e.erreur = "";
      ajouterEchange(e, {
        heure: heureDe(maintenantMs),
        source: message.source,
        question: message.texte,
        reponse: "",
        erreur: null,
        latences: null,
      });
      break;
    case "reponse":
      e.reponse = joindre(e.reponse, message.texte);
      if (dernier) dernier.reponse = joindre(dernier.reponse, message.texte);
      break;
    case "erreur":
      e.erreur = message.message;
      if (e.etat === "repos") e.reposDepuis = maintenantMs; // l'erreur reste 10 s à l'écran
      if (message.code === "cle_absente") break;
      if (dernier && e.etat !== "repos") {
        dernier.erreur = message.message;
      } else {
        e.question = "";
        ajouterEchange(e, {
          heure: heureDe(maintenantMs),
          source: "voix",
          question: "",
          reponse: "",
          erreur: message.message,
          latences: null,
        });
      }
      break;
    case "latences":
      if (dernier) {
        dernier.latences = {
          transcription_ms: message.transcription_ms ?? null,
          reflexion_ms: message.reflexion_ms ?? null,
          premiere_voix_ms: message.premiere_voix_ms ?? null,
        };
      }
      break;
    case "muet":
      e.muet = message.actif;
      break;
    case "historique":
      e.historique = message.echanges.map((x) => ({
        heure: x.heure,
        source: x.source,
        question: x.question,
        reponse: x.reponse ?? "",
        erreur: x.erreur ?? null,
        latences: x.latences ?? null,
      }));
      break;
    default:
      break;
  }
  return e;
}

export function avancer(e, dt) {
  // Hors écoute et parole, le Core n'envoie plus de niveaux : la cible retombe seule.
  if (!e.enLigne || e.etat === "repos" || e.etat === "reflexion") {
    e.volumeCible *= Math.exp(-dt * 3);
  }
  e.volume += (e.volumeCible - e.volume) * (1 - Math.exp(-dt * 14));
  const cible = e.enLigne ? (COULEURS[e.etat] ?? COULEURS.repos) : COULEUR_HORS_LIGNE;
  const k = 1 - Math.exp(-dt * 4);
  for (let i = 0; i < 3; i++) e.couleur[i] += (cible[i] - e.couleur[i]) * k;
  // Une syllabe : le volume franchit le seuil vers le haut, pas plus d'une fois par
  // montée, et jamais à moins de 180 ms de la précédente.
  e.depuisSyllabe += dt;
  e.syllabe = false;
  if (e.volume >= SEUIL_SYLLABE) {
    if (!e.auDessusSeuil && e.depuisSyllabe >= REFRACTAIRE_SYLLABE_S) {
      e.syllabe = true;
      e.depuisSyllabe = 0;
    }
    e.auDessusSeuil = true;
  } else if (e.volume < SEUIL_SYLLABE * 0.7) {
    e.auDessusSeuil = false;
  }
  return e;
}

export function sousTitresVisibles(e, maintenantMs) {
  return !(e.etat === "repos" && e.reposDepuis !== null && maintenantMs - e.reposDepuis > DELAI_SOUS_TITRES_MS);
}

export function sceneDe(e, dt, reduire = false) {
  return {
    etat: e.enLigne ? e.etat : "repos",
    volume: e.volume * (reduire ? 0.6 : 1),
    couleur: e.couleur,
    syllabe: e.syllabe,
    dt,
  };
}
```

`src/atlas_web/historique.js` :

```js
// L'historique de la conversation, affiché dans son panneau. Texte brut seulement.

export function formaterDuree(ms) {
  if (ms === null || ms === undefined) return null;
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(1).replace(".", ",")} s`;
}

const DELAIS = [
  ["transcription_ms", "transcription"],
  ["reflexion_ms", "réflexion"],
  ["premiere_voix_ms", "voix"],
];

export function formaterLatences(latences) {
  if (!latences) return "";
  return DELAIS.map(([cle, libelle]) => {
    const duree = formaterDuree(latences[cle]);
    return duree ? `${libelle} ${duree}` : null;
  })
    .filter(Boolean)
    .join(" · ");
}

function paragraphe(document, classe, texte) {
  const p = document.createElement("p");
  p.className = classe;
  p.textContent = texte;
  return p;
}

export function rendreHistorique(document, liste, echanges) {
  const elements = echanges.map((echange) => {
    const li = document.createElement("li");
    li.append(paragraphe(document, "entete", `${echange.heure} ${echange.source === "clavier" ? "⌨" : "🎙"}`));
    li.append(paragraphe(document, "question", echange.question || "(rien d'entendu)"));
    if (echange.reponse) li.append(paragraphe(document, "reponse", echange.reponse));
    if (echange.erreur) li.append(paragraphe(document, "erreur", echange.erreur));
    const latences = formaterLatences(echange.latences);
    if (latences) li.append(paragraphe(document, "latences", latences));
    return li;
  });
  liste.replaceChildren(...elements);
}
```

`src/atlas_web/registre.js` :

```js
// Un registre d'éléments interchangeables (orbes, fonds), avec le choix mémorisé par
// ce navigateur. Le stockage peut manquer ou refuser (navigation privée) : rien ne casse.

export function lireStockage(stockage, cle) {
  try {
    return stockage?.getItem(cle) ?? null;
  } catch {
    return null;
  }
}

export function ecrireStockage(stockage, cle, valeur) {
  try {
    stockage?.setItem(cle, valeur);
    return Boolean(stockage);
  } catch {
    return false;
  }
}

export function creerRegistre(elements, idParDefaut, cle) {
  const vus = new Set();
  for (const element of elements) {
    if (vus.has(element.id)) throw new Error(`identifiant en double : ${element.id}`);
    vus.add(element.id);
  }
  const parDefaut = elements.find((element) => element.id === idParDefaut);
  if (!parDefaut) throw new Error(`élément par défaut introuvable : ${idParDefaut}`);
  return {
    tous: elements,
    parDefaut,
    choisi(stockage) {
      const id = lireStockage(stockage, cle);
      return elements.find((element) => element.id === id) ?? parDefaut;
    },
    choisir(stockage, id) {
      const element = elements.find((candidat) => candidat.id === id);
      if (!element) throw new Error(`élément inconnu : ${id}`);
      ecrireStockage(stockage, cle, id);
      return element;
    },
  };
}
```

- [ ] **Step 4: Vérifier que les tests passent**

Run: `node --test "tests/web/*.test.mjs" && uv run pytest -q`
Expected: PASS (tous les tests JavaScript et Python).

- [ ] **Step 5: Commit**

```bash
git add src/atlas_web/package.json src/atlas_web/etat.js src/atlas_web/historique.js src/atlas_web/registre.js tests/web/faux_dom.mjs tests/web/etat.test.mjs tests/web/historique.test.mjs tests/web/registre.test.mjs
git commit -F - <<'MSG'
Pose les fondations de la page : état, historique et registres

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

### Task 8: La connexion de la page (`connexion.js`)

**Files:**
- Create: `src/atlas_web/connexion.js`
- Test: `tests/web/connexion.test.mjs`

**Interfaces:**
- Consumes: rien (le WebSocket et la minuterie sont injectables).
- Produces: `DELAIS_RECONNEXION_MS = [1000, 2000, 4000, 8000, 16000, 30000]`, `FERMETURE_CLE_ABSENTE = 4000`, `FERMETURE_NON_AUTORISE = 4401` ; `new Connexion({ url, lireCle, surMessage, surStatut, FabriqueWebSocket = globalThis.WebSocket, planifier = (rappel, delai) => setTimeout(rappel, delai) })` avec `demarrer()`, `arreter()`, `envoyer(message) -> bool`. Statuts transmis à `surStatut` : `"connexion"`, `"en_ligne"`, `"hors_ligne"`, `"cle_requise"`, `"cle_refusee"`, `"cle_absente"`. La page est « en ligne » au premier message reçu qui n'est pas une erreur (l'historique, juste après l'authentification).

- [ ] **Step 1: Écrire les tests qui échouent**

`tests/web/connexion.test.mjs` :

```js
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  Connexion,
  DELAIS_RECONNEXION_MS,
  FERMETURE_CLE_ABSENTE,
  FERMETURE_NON_AUTORISE,
} from "../../src/atlas_web/connexion.js";

class FauxWebSocket {
  static crees = [];

  constructor(url) {
    this.url = url;
    this.envoyes = [];
    this.readyState = 0;
    this.fermee = false;
    FauxWebSocket.crees.push(this);
  }

  send(texte) {
    this.envoyes.push(JSON.parse(texte));
  }

  close() {
    this.fermee = true;
    this.readyState = 3;
  }

  // Ce que fait le serveur, simulé.
  ouvrir() {
    this.readyState = 1;
    this.onopen?.();
  }

  recevoir(message) {
    this.onmessage?.({ data: JSON.stringify(message) });
  }

  couper(code) {
    this.readyState = 3;
    this.onclose?.({ code });
  }
}

function monter({ cle = "cle" } = {}) {
  FauxWebSocket.crees = [];
  const statuts = [];
  const messages = [];
  const planifies = [];
  const connexion = new Connexion({
    url: "ws://atlas.local:8080/ws/web",
    lireCle: () => cle,
    surMessage: (message) => messages.push(message),
    surStatut: (statut) => statuts.push(statut),
    FabriqueWebSocket: FauxWebSocket,
    planifier: (rappel, delai) => planifies.push({ rappel, delai }),
  });
  return { connexion, statuts, messages, planifies, derniere: () => FauxWebSocket.crees.at(-1) };
}

test("la clé part dans le premier message, puis la page est en ligne", () => {
  const m = monter();
  m.connexion.demarrer();
  const ws = m.derniere();
  ws.ouvrir();
  assert.equal(ws.url, "ws://atlas.local:8080/ws/web");
  assert.deepEqual(ws.envoyes, [{ type: "authentification", cle: "cle" }]);
  ws.recevoir({ type: "historique", echanges: [] });
  assert.deepEqual(m.statuts, ["connexion", "en_ligne"]);
  assert.deepEqual(m.messages, [{ type: "historique", echanges: [] }]);
});

test("sans clé mémorisée, rien ne part et la clé est demandée", () => {
  const m = monter({ cle: null });
  m.connexion.demarrer();
  assert.equal(FauxWebSocket.crees.length, 0);
  assert.deepEqual(m.statuts, ["cle_requise"]);
});

test("une clé refusée ou non configurée arrête les tentatives", () => {
  for (const [code, statut] of [
    [FERMETURE_NON_AUTORISE, "cle_refusee"],
    [FERMETURE_CLE_ABSENTE, "cle_absente"],
  ]) {
    const m = monter();
    m.connexion.demarrer();
    m.derniere().ouvrir();
    m.derniere().couper(code);
    assert.equal(m.statuts.at(-1), statut);
    assert.equal(m.planifies.length, 0);
  }
});

test("une coupure relance la connexion, de plus en plus espacée, jusqu'à 30 s", () => {
  const m = monter();
  m.connexion.demarrer();
  for (let i = 0; i < 8; i++) {
    m.derniere().couper(1006);
    m.planifies.at(-1).rappel();
  }
  assert.deepEqual(
    m.planifies.map((p) => p.delai),
    [1000, 2000, 4000, 8000, 16000, 30000, 30000, 30000],
  );
  assert.equal(m.statuts.filter((s) => s === "hors_ligne").length, 8);
});

test("une connexion réussie remet l'attente à une seconde", () => {
  const m = monter();
  m.connexion.demarrer();
  m.derniere().couper(1006);
  m.planifies.at(-1).rappel();
  m.derniere().couper(1006);
  m.planifies.at(-1).rappel();
  const ws = m.derniere();
  ws.ouvrir();
  ws.recevoir({ type: "muet", actif: false });
  ws.couper(1006);
  assert.equal(m.planifies.at(-1).delai, DELAIS_RECONNEXION_MS[0]);
});

test("envoyer ne part qu'une fois en ligne", () => {
  const m = monter();
  m.connexion.demarrer();
  const ws = m.derniere();
  assert.equal(m.connexion.envoyer({ type: "saisie", texte: "q" }), false);
  ws.ouvrir();
  assert.equal(m.connexion.envoyer({ type: "saisie", texte: "q" }), false);
  ws.recevoir({ type: "historique", echanges: [] });
  assert.equal(m.connexion.envoyer({ type: "saisie", texte: "q" }), true);
  assert.deepEqual(ws.envoyes.at(-1), { type: "saisie", texte: "q" });
});

test("arrêter empêche toute reconnexion", () => {
  const m = monter();
  m.connexion.demarrer();
  const ws = m.derniere();
  m.connexion.arreter();
  assert.equal(ws.fermee, true);
  ws.couper(1006);
  assert.equal(m.planifies.length, 0);
});

test("redémarrer abandonne l'ancienne connexion sans la relancer", () => {
  const m = monter();
  m.connexion.demarrer();
  const ancienne = m.derniere();
  m.connexion.demarrer();
  assert.equal(ancienne.fermee, true);
  ancienne.couper(1006);
  assert.equal(m.planifies.length, 0);
  assert.equal(FauxWebSocket.crees.length, 2);
});

test("un message illisible est ignoré", () => {
  const m = monter();
  m.connexion.demarrer();
  const ws = m.derniere();
  ws.ouvrir();
  ws.onmessage({ data: "pas du json" });
  assert.deepEqual(m.messages, []);
});
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `node --test "tests/web/connexion.test.mjs"`
Expected: FAIL, `Cannot find module '…/src/atlas_web/connexion.js'`.

- [ ] **Step 3: Écrire `src/atlas_web/connexion.js`**

```js
// La connexion à /ws/web : authentification, messages, reconnexion espacée.

export const DELAIS_RECONNEXION_MS = [1000, 2000, 4000, 8000, 16000, 30000];
export const FERMETURE_CLE_ABSENTE = 4000;
export const FERMETURE_NON_AUTORISE = 4401;
const OUVERT = 1;

export class Connexion {
  constructor({
    url,
    lireCle,
    surMessage,
    surStatut,
    FabriqueWebSocket = globalThis.WebSocket,
    planifier = (rappel, delai) => setTimeout(rappel, delai),
  }) {
    this._url = url;
    this._lireCle = lireCle;
    this._surMessage = surMessage;
    this._surStatut = surStatut;
    this._Fabrique = FabriqueWebSocket;
    this._planifier = planifier;
    this._ws = null;
    this._enLigne = false;
    this._tentatives = 0;
    this._arretee = true;
  }

  demarrer() {
    this._arretee = false;
    this._tentatives = 0;
    this._abandonner();
    this._ouvrir();
  }

  arreter() {
    this._arretee = true;
    this._abandonner();
  }

  envoyer(message) {
    if (!this._ws || this._ws.readyState !== OUVERT || !this._enLigne) return false;
    this._ws.send(JSON.stringify(message));
    return true;
  }

  _abandonner() {
    const ancienne = this._ws;
    this._ws = null;
    this._enLigne = false;
    if (ancienne) {
      ancienne.onopen = null;
      ancienne.onmessage = null;
      ancienne.onclose = null;
      ancienne.close();
    }
  }

  _ouvrir() {
    const cle = this._lireCle();
    if (!cle) {
      this._surStatut("cle_requise");
      return;
    }
    this._surStatut("connexion");
    const ws = new this._Fabrique(this._url);
    this._ws = ws;
    this._enLigne = false;
    ws.onopen = () => ws.send(JSON.stringify({ type: "authentification", cle }));
    ws.onmessage = (evenement) => {
      let message;
      try {
        message = JSON.parse(evenement.data);
      } catch {
        return;
      }
      if (!this._enLigne && message.type !== "erreur") {
        this._enLigne = true;
        this._tentatives = 0;
        this._surStatut("en_ligne");
      }
      this._surMessage(message);
    };
    ws.onclose = (evenement) => {
      if (this._ws !== ws) return;
      this._ws = null;
      this._enLigne = false;
      if (this._arretee) return;
      if (evenement.code === FERMETURE_NON_AUTORISE) {
        this._surStatut("cle_refusee");
        return;
      }
      if (evenement.code === FERMETURE_CLE_ABSENTE) {
        this._surStatut("cle_absente");
        return;
      }
      this._surStatut("hors_ligne");
      const delai = DELAIS_RECONNEXION_MS[Math.min(this._tentatives, DELAIS_RECONNEXION_MS.length - 1)];
      this._tentatives += 1;
      this._planifier(() => {
        if (!this._arretee && !this._ws) this._ouvrir();
      }, delai);
    };
  }
}
```

- [ ] **Step 4: Vérifier que les tests passent**

Run: `node --test "tests/web/*.test.mjs"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/atlas_web/connexion.js tests/web/connexion.test.mjs
git commit -F - <<'MSG'
Relie la page au Core, avec clé et reconnexion espacée

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

### Task 9: Les outils de dessin et les six premières orbes

Les orbes reprennent les maquettes validées par David (fichier local, jamais commité : `.superpowers/brainstorm/32259-1790251451/content/parametres-orbe-12.html`), adaptées à l'interface commune : tout ce qui venait de variables globales (`etat`, `volume`, `couleur`, `nouvelleSyllabe`) vient désormais de `scene`, et le calque est effacé (`clearRect`) au lieu d'être peint en noir. Le code ci-dessous fait foi.

**Files:**
- Create: `src/atlas_web/dessin.js`
- Create: `src/atlas_web/orbes/particules.js`, `liquide.js`, `anneaux.js`, `armillaire.js`, `relief.js`, `cymatique.js`
- Create: `tests/web/faux_canevas.mjs`
- Test: `tests/web/orbes.test.mjs`

**Interfaces:**
- Consumes: rien.
- Produces:
  - `dessin.js` : `TOUR` (2π), `melanger(base, couleur, part) -> [r, g, b]`, `rgba(couleur, alpha, eclaircir = 0) -> string`, `geo(canvas) -> { w, h, m, cx, cy, k }` (`m` le plus petit côté, `k = m / 400`), `lueur(ctx, x, y, r, couleur, alpha, eclaircir = 0)`, `preparerOrbe(ctx, g, scene)`, `tourner(p, ay, ax)`, `trace(ctx, points)`, `vignette(ctx, w, h)`, `haloFond(ctx, w, h, scene, alpha)`, `dimensionner(canvas, dprMax = 2)`.
  - Chaque orbe : `export default { id, nom, idee, creer(canvas) }`, où `creer` rend `{ dessiner(t, scene) }` et `scene = { etat, volume, couleur, syllabe, dt }`.
  - `faux_canevas.mjs` : `fauxCanevas(largeur = 400, hauteur = 400) -> { canvas, bilan: { dessins, peinturesOpaquesPleines } }`, `ETATS`, `IMAGES_PAR_ETAT = 75`, `animer(module, canevas, couleur = [34, 211, 238])`.

- [ ] **Step 1: Écrire la doublure de canevas et le test de contrat qui échoue**

`tests/web/faux_canevas.mjs` :

```js
// Une doublure du contexte 2D : elle accepte tout appel, refuse les nombres invalides
// et les rayons négatifs (un vrai navigateur lèverait une erreur), compte ce qui est
// dessiné et relève toute peinture opaque de tout le canevas.

export const ETATS = ["repos", "ecoute", "reflexion", "parole"];
export const IMAGES_PAR_ETAT = 75;

const RAYONS = { arc: [2], ellipse: [2, 3], createRadialGradient: [2, 5] };
const DESSINS = new Set(["fill", "stroke", "fillRect", "strokeRect"]);

function estOpaque(style) {
  if (typeof style !== "string") return false; // un dégradé
  const alpha = style.match(/^rgba\((?:[^,]+,){3}\s*([\d.]+)\)$/i);
  if (alpha) return Number(alpha[1]) >= 0.99;
  return /^(#|rgb\()/i.test(style);
}

export function fauxCanevas(largeur = 400, hauteur = 400) {
  const bilan = { dessins: 0, peinturesOpaquesPleines: 0 };
  const canvas = { width: largeur, height: hauteur, clientWidth: largeur, clientHeight: hauteur };
  const etat = {
    fillStyle: "#000000",
    strokeStyle: "#000000",
    lineWidth: 1,
    globalCompositeOperation: "source-over",
    globalAlpha: 1,
  };
  const ctx = new Proxy(etat, {
    get(cible, nom) {
      if (nom in cible) return cible[nom];
      return (...args) => {
        args.forEach((valeur, i) => {
          if (typeof valeur === "number" && !Number.isFinite(valeur)) {
            throw new Error(`${String(nom)} : argument ${i} = ${valeur}`);
          }
        });
        for (const i of RAYONS[nom] ?? []) {
          if (args[i] < 0) throw new Error(`${String(nom)} : rayon négatif (${args[i]})`);
        }
        if (nom === "createRadialGradient" || nom === "createLinearGradient") {
          return {
            addColorStop(position, couleur) {
              if (!(position >= 0 && position <= 1)) throw new Error(`addColorStop : ${position}`);
              if (String(couleur).includes("NaN")) throw new Error(`addColorStop : ${couleur}`);
            },
          };
        }
        if (DESSINS.has(nom)) bilan.dessins += 1;
        const plein =
          nom === "fillRect" &&
          args[0] <= 0 &&
          args[1] <= 0 &&
          args[0] + args[2] >= canvas.width &&
          args[1] + args[3] >= canvas.height;
        if (plein && estOpaque(cible.fillStyle)) bilan.peinturesOpaquesPleines += 1;
        return undefined;
      };
    },
    set(cible, nom, valeur) {
      if (typeof valeur === "string" && valeur.includes("NaN")) throw new Error(`${String(nom)} = ${valeur}`);
      if (typeof valeur === "number" && !Number.isFinite(valeur)) throw new Error(`${String(nom)} = ${valeur}`);
      cible[nom] = valeur;
      return true;
    },
  });
  canvas.getContext = () => ctx;
  return { canvas, bilan };
}

export function animer(module, canevas, couleur = [34, 211, 238]) {
  const dessin = module.creer(canevas.canvas);
  let t = 0;
  for (const etat of ETATS) {
    for (let i = 0; i < IMAGES_PAR_ETAT; i++) {
      t += 1 / 60;
      const parle = etat === "ecoute" || etat === "parole";
      const volume = parle ? 0.5 + 0.5 * Math.sin(i / 3) : 0.05;
      dessin.dessiner(t, { etat, volume, couleur, syllabe: i % 12 === 0, dt: 1 / 60 });
    }
  }
}
```

`tests/web/orbes.test.mjs` (version de cette tâche ; la Task 10 la remplace pour passer par le registre) :

```js
import assert from "node:assert/strict";
import { test } from "node:test";

import anneaux from "../../src/atlas_web/orbes/anneaux.js";
import armillaire from "../../src/atlas_web/orbes/armillaire.js";
import cymatique from "../../src/atlas_web/orbes/cymatique.js";
import liquide from "../../src/atlas_web/orbes/liquide.js";
import particules from "../../src/atlas_web/orbes/particules.js";
import relief from "../../src/atlas_web/orbes/relief.js";
import { ETATS, IMAGES_PAR_ETAT, animer, fauxCanevas } from "./faux_canevas.mjs";

function verifierOrbe(module) {
  assert.match(module.id, /^[a-z]+$/);
  assert.ok(module.nom.length > 0 && module.idee.length > 0);
  for (const [largeur, hauteur] of [[400, 400], [640, 400]]) {
    const canevas = fauxCanevas(largeur, hauteur);
    animer(module, canevas);
    assert.ok(canevas.bilan.dessins >= ETATS.length * IMAGES_PAR_ETAT, `${module.id} ne dessine pas à chaque image`);
    assert.equal(canevas.bilan.peinturesOpaquesPleines, 0, `${module.id} cache le fond`);
  }
}

for (const module of [particules, liquide, anneaux, armillaire, relief, cymatique]) {
  test(`l'orbe ${module.id} s'anime dans les quatre états sans cacher le fond`, () => verifierOrbe(module));
}
```

- [ ] **Step 2: Vérifier qu'il échoue**

Run: `node --test "tests/web/orbes.test.mjs"`
Expected: FAIL, `Cannot find module '…/src/atlas_web/orbes/anneaux.js'`.

- [ ] **Step 3: Écrire `src/atlas_web/dessin.js`**

```js
// Outils de dessin partagés par les orbes et les fonds.

export const TOUR = Math.PI * 2;

export function melanger(base, couleur, part) {
  return [0, 1, 2].map((i) => base[i] * (1 - part) + couleur[i] * part);
}

export function rgba(couleur, alpha, eclaircir = 0) {
  const [r, g, b] = couleur.map((x) => Math.round(x + (255 - x) * eclaircir));
  return `rgba(${r},${g},${b},${Math.max(0, Math.min(1, alpha))})`;
}

export function geo(canvas) {
  const w = canvas.width;
  const h = canvas.height;
  const m = Math.min(w, h);
  return { w, h, m, cx: w / 2, cy: h / 2, k: m / 400 };
}

export function lueur(ctx, x, y, r, couleur, alpha, eclaircir = 0) {
  if (!(r > 0)) return;
  const degrade = ctx.createRadialGradient(x, y, 0, x, y, r);
  degrade.addColorStop(0, rgba(couleur, alpha, eclaircir));
  degrade.addColorStop(1, rgba(couleur, 0));
  ctx.fillStyle = degrade;
  ctx.beginPath();
  ctx.arc(x, y, r, 0, TOUR);
  ctx.fill();
}

// Le calque de l'orbe reste transparent : on l'efface, puis un halo doux l'entoure.
export function preparerOrbe(ctx, g, scene) {
  ctx.globalCompositeOperation = "source-over";
  ctx.clearRect(0, 0, g.w, g.h);
  lueur(ctx, g.cx, g.cy, g.m * 0.5, scene.couleur, 0.08 + scene.volume * 0.1);
}

export function tourner(p, ay, ax) {
  const x = p[0] * Math.cos(ay) + p[2] * Math.sin(ay);
  const z0 = -p[0] * Math.sin(ay) + p[2] * Math.cos(ay);
  return [x, p[1] * Math.cos(ax) - z0 * Math.sin(ax), p[1] * Math.sin(ax) + z0 * Math.cos(ax)];
}

export function trace(ctx, points) {
  ctx.beginPath();
  points.forEach((p, i) => (i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])));
}

export function vignette(ctx, w, h) {
  const v = ctx.createRadialGradient(w / 2, h / 2, Math.min(w, h) * 0.35, w / 2, h / 2, Math.max(w, h) * 0.75);
  v.addColorStop(0, "rgba(0,0,0,0)");
  v.addColorStop(1, "rgba(0,0,0,0.65)");
  ctx.globalCompositeOperation = "source-over";
  ctx.fillStyle = v;
  ctx.fillRect(0, 0, w, h);
}

// Le halo d'un fond, centré là où flotte l'orbe (42 % de la hauteur).
export function haloFond(ctx, w, h, scene, alpha) {
  const g = ctx.createRadialGradient(w / 2, h * 0.42, 0, w / 2, h * 0.42, h * 0.6);
  g.addColorStop(0, rgba(scene.couleur, alpha + scene.volume * 0.08));
  g.addColorStop(1, "rgba(0,0,0,0)");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, w, h);
}

export function dimensionner(canvas, dprMax = 2) {
  const dpr = Math.min(dprMax, globalThis.devicePixelRatio || 1);
  const w = Math.max(1, Math.round(canvas.clientWidth * dpr));
  const h = Math.max(1, Math.round(canvas.clientHeight * dpr));
  if (canvas.width !== w || canvas.height !== h) {
    canvas.width = w;
    canvas.height = h;
  }
}
```

- [ ] **Step 4: Écrire les six orbes**

`src/atlas_web/orbes/particules.js` :

```js
import { geo, preparerOrbe, rgba, tourner, TOUR } from "../dessin.js";

export default {
  id: "particules",
  nom: "Sphère de particules",
  idee: "Un nuage de points en 3D qui se gonfle avec la voix.",
  creer(canvas) {
    const ctx = canvas.getContext("2d");
    const points = [];
    const nombre = 500;
    const angleOr = Math.PI * (3 - Math.sqrt(5));
    for (let i = 0; i < nombre; i++) {
      const y = 1 - (i / (nombre - 1)) * 2;
      const r = Math.sqrt(1 - y * y);
      const phi = i * angleOr;
      points.push([Math.cos(phi) * r, y, Math.sin(phi) * r, Math.random() * TOUR]);
    }
    return {
      dessiner(t, scene) {
        const g = geo(canvas);
        const R = g.m * 0.3;
        const ay = t * (scene.etat === "reflexion" ? 0.9 : 0.18);
        const bande = Math.sin(t * 2.2);
        preparerOrbe(ctx, g, scene);
        ctx.globalCompositeOperation = "lighter";
        for (const p of points) {
          const q = tourner(p, ay, 0.35);
          const d = 1 + scene.volume * 0.32 * Math.sin(3 * p[1] + t * 5 + p[3]);
          const profondeur = (q[2] + 1) / 2;
          let alpha = 0.18 + 0.7 * profondeur;
          if (scene.etat === "reflexion" && Math.abs(p[1] - bande) < 0.12) alpha = 1;
          ctx.fillStyle = rgba(scene.couleur, alpha, 0.25 * profondeur);
          ctx.beginPath();
          ctx.arc(g.cx + q[0] * R * d, g.cy + q[1] * R * d, (0.6 + 1.6 * profondeur) * g.k, 0, TOUR);
          ctx.fill();
        }
      },
    };
  },
};
```

`src/atlas_web/orbes/liquide.js` :

```js
import { geo, preparerOrbe, rgba, trace, TOUR } from "../dessin.js";

export default {
  id: "liquide",
  nom: "Orbe liquide",
  idee: "Une goutte de lumière aux contours mouvants.",
  creer(canvas) {
    const ctx = canvas.getContext("2d");
    return {
      dessiner(t, scene) {
        const g = geo(canvas);
        const R = g.m * 0.27;
        const lent = scene.etat === "reflexion" ? 2.2 : 1;
        const v = scene.volume;
        preparerOrbe(ctx, g, scene);
        ctx.globalCompositeOperation = "lighter";
        for (let k = 0; k < 3; k++) {
          const points = [];
          for (let i = 0; i <= 100; i++) {
            const th = (i / 100) * TOUR;
            const r =
              R *
              (0.82 + 0.09 * k) *
              (1 +
                (0.04 + v * 0.2) * Math.sin(3 * th + t * 2.1 * lent + k * 1.7) +
                0.05 * Math.sin(5 * th - t * 1.6 * lent + k * 2.3) +
                (0.02 + v * 0.08) * Math.sin(2 * th + t * 1.3 * lent * (k + 1)));
            points.push([g.cx + r * Math.cos(th), g.cy + r * Math.sin(th)]);
          }
          trace(ctx, points);
          const degrade = ctx.createRadialGradient(g.cx, g.cy - R * 0.2, R * 0.05, g.cx, g.cy, R * 1.2);
          degrade.addColorStop(0, rgba(scene.couleur, 0.55, 0.6));
          degrade.addColorStop(0.6, rgba(scene.couleur, 0.35));
          degrade.addColorStop(1, rgba(scene.couleur, 0));
          ctx.fillStyle = degrade;
          ctx.fill();
        }
      },
    };
  },
};
```

`src/atlas_web/orbes/anneaux.js` :

```js
import { geo, lueur, preparerOrbe, rgba, TOUR } from "../dessin.js";

const ANNEAUX = [
  { r: 0.4, n: 18, l: 5, v: 0.35 },
  { r: 0.55, n: 64, l: 2, v: -0.22 },
  { r: 0.7, n: 10, l: 7, v: 0.12 },
  { r: 0.84, n: 96, l: 1.5, v: -0.06 },
];

// Chaque anneau a des segments manquants, tirés une fois pour toutes.
function present(segment, anneau) {
  const x = Math.sin(segment * 12.9898 + anneau * 78.233) * 43758.5453;
  return x - Math.floor(x) >= 0.3;
}

export default {
  id: "anneaux",
  nom: "Anneaux « réacteur »",
  idee: "Des anneaux en segments autour d'un cœur, façon cockpit.",
  creer(canvas) {
    const ctx = canvas.getContext("2d");
    return {
      dessiner(t, scene) {
        const g = geo(canvas);
        const R = g.m * 0.36;
        const v = scene.volume;
        const acceleration = scene.etat === "reflexion" ? 4 : 1;
        preparerOrbe(ctx, g, scene);
        ctx.globalCompositeOperation = "lighter";
        lueur(ctx, g.cx, g.cy, R * (0.28 + v * 0.12), scene.couleur, 0.95, 0.7);
        ANNEAUX.forEach((anneau, j) => {
          ctx.lineWidth = anneau.l * g.k;
          const pas = TOUR / anneau.n;
          for (let s = 0; s < anneau.n; s++) {
            if (!present(s, j)) continue;
            const debut = s * pas + t * anneau.v * acceleration;
            ctx.strokeStyle = rgba(scene.couleur, 0.35 + 0.55 * v * (j % 2 ? 1 : 0.6));
            ctx.beginPath();
            ctx.arc(g.cx, g.cy, R * anneau.r, debut, debut + pas * 0.7);
            ctx.stroke();
          }
        });
        if (scene.etat === "parole" || scene.etat === "ecoute") {
          ctx.lineWidth = 1.5 * g.k;
          ctx.strokeStyle = rgba(scene.couleur, 0.7, 0.3);
          ctx.beginPath();
          for (let i = 0; i <= 180; i++) {
            const th = (i / 180) * TOUR;
            const r = R * (0.95 + v * 0.06 * Math.sin(24 * th + t * 12));
            const x = g.cx + r * Math.cos(th);
            const y = g.cy + r * Math.sin(th);
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
          }
          ctx.stroke();
        }
      },
    };
  },
};
```

`src/atlas_web/orbes/armillaire.js` :

```js
import { geo, lueur, melanger, preparerOrbe, rgba, tourner, TOUR } from "../dessin.js";

const LAITON = [201, 168, 106];
const EPS = (23.4 * Math.PI) / 180;
const ANNEAUX = [
  { c: [0, 0, 0], u: [1, 0, 0], v: [0, 0, 1], r: 1, vitesse: 0, epaisseur: 2.2 }, // équateur
  { c: [0, 0.4, 0], u: [1, 0, 0], v: [0, 0, 1], r: Math.sqrt(0.84), vitesse: 0, epaisseur: 1 }, // tropiques
  { c: [0, -0.4, 0], u: [1, 0, 0], v: [0, 0, 1], r: Math.sqrt(0.84), vitesse: 0, epaisseur: 1 },
  { c: [0, 0, 0], u: [0, 1, 0], v: [1, 0, 0], r: 1, vitesse: 0.9, epaisseur: 1.6 }, // méridiens
  { c: [0, 0, 0], u: [0, 1, 0], v: [0, 0, 1], r: 1, vitesse: -0.6, epaisseur: 1.6 },
  {
    c: [0, 0, 0],
    u: [1, 0, 0],
    v: [0, Math.sin(EPS), Math.cos(EPS)],
    r: 1.02,
    vitesse: 0.35,
    epaisseur: 3.2,
    ecliptique: true,
  },
];

function point(anneau, r, th) {
  return [0, 1, 2].map((d) => anneau.c[d] + r * (Math.cos(th) * anneau.u[d] + Math.sin(th) * anneau.v[d]));
}

export default {
  id: "armillaire",
  nom: "Sphère armillaire",
  idee: "L'astrolabe de laiton : Atlas porte la voûte céleste.",
  creer(canvas) {
    const ctx = canvas.getContext("2d");
    const etoiles = [];
    for (let i = 0; i < 120; i++) {
      const u = Math.random() * 2 - 1;
      const th = Math.random() * TOUR;
      const rayon = 0.25 + 0.6 * Math.random();
      const s = Math.sqrt(1 - u * u);
      etoiles.push([Math.cos(th) * s * rayon, u * rayon, Math.sin(th) * s * rayon, Math.random() * TOUR]);
    }
    return {
      dessiner(t, scene) {
        const g = geo(canvas);
        const c = scene.couleur;
        const v = scene.volume;
        const R = g.m * 0.33;
        const gyroscope = scene.etat === "reflexion" ? 1 : 0.08;
        const echelle = 1 + (scene.etat === "ecoute" ? v * 0.05 : 0);
        preparerOrbe(ctx, g, scene);
        ctx.globalCompositeOperation = "lighter";
        lueur(ctx, g.cx, g.cy, R * (0.2 + v * 0.14), c, 1, 0.75);
        const rotation = t * 0.12;
        for (const e of etoiles) {
          const p = tourner(e, rotation, 0.35);
          const alpha = (0.25 + 0.25 * (p[2] + 1)) * (0.6 + 0.4 * Math.sin(t * 2 + e[3]));
          ctx.fillStyle = rgba(melanger(LAITON, c, 0.2), alpha, 0.5);
          ctx.fillRect(g.cx + p[0] * R * echelle, g.cy + p[1] * R * echelle, 1.2 * g.k, 1.2 * g.k);
        }
        for (const anneau of ANNEAUX) {
          const ay = rotation + t * anneau.vitesse * gyroscope;
          let precedent = null;
          for (let i = 0; i <= 120; i++) {
            const th = (i / 120) * TOUR;
            let r = anneau.r;
            if (anneau.ecliptique && scene.etat === "parole") r *= 1 + v * 0.07 * Math.sin(14 * th + t * 11);
            const p = tourner(point(anneau, r, th), ay, 0.35);
            const courant = [g.cx + p[0] * R * echelle, g.cy + p[1] * R * echelle, p[2]];
            if (precedent) {
              const profondeur = ((courant[2] + precedent[2]) / 2 + 1) / 2;
              const teinte = melanger(LAITON, c, anneau.ecliptique ? 0.55 : 0.15);
              ctx.strokeStyle = rgba(teinte, 0.15 + 0.75 * profondeur, anneau.ecliptique ? 0.2 * v : 0);
              ctx.lineWidth = anneau.epaisseur * g.k * (0.6 + 0.6 * profondeur);
              ctx.beginPath();
              ctx.moveTo(precedent[0], precedent[1]);
              ctx.lineTo(courant[0], courant[1]);
              ctx.stroke();
            }
            precedent = courant;
          }
          if (anneau.ecliptique) {
            for (let j = 0; j < 3; j++) {
              const th = t * (scene.etat === "parole" ? 1.6 : 0.4) + j * 2.1;
              const p = tourner(point(anneau, anneau.r, th), ay, 0.35);
              lueur(ctx, g.cx + p[0] * R, g.cy + p[1] * R, 7 * g.k, c, 1, 0.6);
            }
          }
        }
        ctx.globalCompositeOperation = "source-over";
        ctx.strokeStyle = rgba(LAITON, 0.55);
        ctx.lineWidth = 3 * g.k;
        ctx.beginPath();
        ctx.ellipse(g.cx, g.cy + R * 0.02, R * 1.16, R * 0.34, 0, 0, TOUR);
        ctx.stroke();
      },
    };
  },
};
```

`src/atlas_web/orbes/relief.js` :

```js
import { geo, preparerOrbe, rgba, trace } from "../dessin.js";

const LIGNES = 30;

function relief(x, y, largeur, t, scene) {
  const u = x / largeur;
  const bord = Math.max(0, 1 - u * u);
  let h = 0.015 * Math.sin(9 * x + t * 1.3 + y * 7);
  const force = scene.etat === "repos" ? 0.08 : scene.etat === "reflexion" ? 0.25 : scene.volume;
  for (let k = 0; k < 4; k++) {
    const centre = Math.sin(t * 0.35 + k * 1.9 + y * 1.3) * 0.65 * largeur;
    const haut = force * (0.45 + 0.55 * Math.sin(t * (4 + k) + k * 1.7 + y * 3)) * (0.6 + 0.4 * Math.cos(y * 2 + k));
    h += Math.max(0, haut) * Math.exp(-(((x - centre) / 0.16) ** 2));
  }
  if (scene.etat === "reflexion") {
    const front = ((t * 0.7) % 2.4) - 1.2;
    h += 0.35 * Math.exp(-(((y - front) / 0.1) ** 2)) * (0.5 + 0.5 * Math.sin(20 * x - t * 6));
  }
  return h * bord;
}

export default {
  id: "relief",
  nom: "Globe en lignes de relief",
  idee: "Un globe en courbes de niveau : un atlas, ce sont des cartes.",
  creer(canvas) {
    const ctx = canvas.getContext("2d");
    return {
      dessiner(t, scene) {
        const g = geo(canvas);
        const R = g.m * 0.33;
        preparerOrbe(ctx, g, scene);
        for (let i = 0; i < LIGNES; i++) {
          const y = -0.94 + (1.88 * i) / (LIGNES - 1);
          const largeur = Math.sqrt(1 - y * y);
          const points = [];
          for (let j = 0; j <= 60; j++) {
            const x = -largeur + (2 * largeur * j) / 60;
            points.push([g.cx + x * R, g.cy + y * R - relief(x, y, largeur, t, scene) * R * 0.45]);
          }
          // Chaque ligne masque celles de derrière : le globe a un corps sombre.
          trace(ctx, points);
          ctx.lineTo(points[points.length - 1][0], g.cy + y * R + 2 * g.k);
          ctx.lineTo(points[0][0], g.cy + y * R + 2 * g.k);
          ctx.closePath();
          ctx.fillStyle = "rgba(5,7,13,0.92)";
          ctx.fill();
          trace(ctx, points);
          ctx.strokeStyle = rgba(scene.couleur, 0.35 + 0.6 * (0.45 + 0.55 * (i / (LIGNES - 1))), 0.15);
          ctx.lineWidth = 1.4 * g.k;
          ctx.stroke();
        }
      },
    };
  },
};
```

`src/atlas_web/orbes/cymatique.js` :

```js
import { geo, preparerOrbe, rgba, TOUR } from "../dessin.js";

const GRAINS = 3000;
const MODES = [[1, 2], [2, 3], [1, 4], [3, 4], [2, 5], [3, 5], [1, 6], [4, 5], [2, 7], [3, 7], [5, 6]];

export default {
  id: "cymatique",
  nom: "Cymatique",
  idee: "Du sable qui dessine les figures de la voix sur une plaque.",
  creer(canvas) {
    const ctx = canvas.getContext("2d");
    const X = new Float32Array(GRAINS);
    const Y = new Float32Array(GRAINS);
    for (let i = 0; i < GRAINS; i++) {
      const r = Math.sqrt(Math.random());
      const th = Math.random() * TOUR;
      X[i] = r * Math.cos(th);
      Y[i] = r * Math.sin(th);
    }
    let mode = 1;
    let secousse = 1;
    let prochain = 0;
    function changerDeFigure(t, attente) {
      mode = (mode + 1 + Math.floor(Math.random() * 3)) % MODES.length;
      secousse = 1;
      prochain = t + attente;
    }
    return {
      dessiner(t, scene) {
        const parle = scene.etat === "ecoute" || scene.etat === "parole";
        if (parle && scene.syllabe && t > prochain) changerDeFigure(t, 0.45);
        else if (scene.etat === "reflexion" && t > prochain) changerDeFigure(t, 1.3);
        const f = Math.min(3, Math.max(0, scene.dt * 60)); // en images de 1/60 s
        secousse *= 0.94 ** f;
        const [n, m] = MODES[mode];
        const pi = Math.PI;
        const agitation = (scene.etat === "repos" ? 0.0015 : 0.003 + 0.035 * secousse + 0.008 * scene.volume) * f;
        for (let i = 0; i < GRAINS; i++) {
          const x = X[i];
          const y = Y[i];
          const cnx = Math.cos(n * pi * x);
          const cmy = Math.cos(m * pi * y);
          const cmx = Math.cos(m * pi * x);
          const cny = Math.cos(n * pi * y);
          // Figure de Chladni : le sable fuit les ventres et s'amasse sur les lignes immobiles.
          const valeur = cnx * cmy - cmx * cny;
          const gx = -n * pi * Math.sin(n * pi * x) * cmy + m * pi * Math.sin(m * pi * x) * cny;
          const gy = -m * pi * cnx * Math.sin(m * pi * y) + n * pi * cmx * Math.sin(n * pi * y);
          const pas = (0.0012 * f * valeur) / (n + m);
          const bruit = agitation * (0.3 + Math.abs(valeur));
          let nx = x - pas * gx + (Math.random() - 0.5) * bruit;
          let ny = y - pas * gy + (Math.random() - 0.5) * bruit;
          const d2 = nx * nx + ny * ny;
          if (d2 > 0.98) {
            const s = 0.97 / Math.sqrt(d2);
            nx *= s;
            ny *= s;
          }
          X[i] = nx;
          Y[i] = ny;
        }
        const g = geo(canvas);
        const R = g.m * 0.36;
        preparerOrbe(ctx, g, scene);
        ctx.globalCompositeOperation = "lighter";
        ctx.fillStyle = rgba(scene.couleur, scene.etat === "repos" ? 0.35 : 0.6, 0.35);
        const taille = 1.4 * g.k;
        for (let i = 0; i < GRAINS; i++) ctx.fillRect(g.cx + X[i] * R, g.cy + Y[i] * R, taille, taille);
        ctx.globalCompositeOperation = "source-over";
        ctx.strokeStyle = rgba(scene.couleur, 0.25);
        ctx.lineWidth = 1.2 * g.k;
        ctx.beginPath();
        ctx.arc(g.cx, g.cy, R * 1.01, 0, TOUR);
        ctx.stroke();
      },
    };
  },
};
```

- [ ] **Step 5: Vérifier que les tests passent**

Run: `node --test "tests/web/*.test.mjs"`
Expected: PASS (six tests d'orbes en plus).

- [ ] **Step 6: Commit**

```bash
git add src/atlas_web/dessin.js src/atlas_web/orbes/particules.js src/atlas_web/orbes/liquide.js src/atlas_web/orbes/anneaux.js src/atlas_web/orbes/armillaire.js src/atlas_web/orbes/relief.js src/atlas_web/orbes/cymatique.js tests/web/faux_canevas.mjs tests/web/orbes.test.mjs
git commit -F - <<'MSG'
Dessine les six premières orbes, sur un calque transparent

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

### Task 10: Les six autres orbes et leur registre

**Files:**
- Create: `src/atlas_web/orbes/oscilloscope.js`, `plasma.js`, `constellations.js`, `aurore.js`, `galaxie.js`, `mandala.js`
- Create: `src/atlas_web/orbes/index.js`
- Replace: `tests/web/orbes.test.mjs`

**Interfaces:**
- Consumes: `dessin.js` (Task 9), `creerRegistre` (Task 7), les six premières orbes (Task 9).
- Produces: `orbes` (registre) dans `src/atlas_web/orbes/index.js`, défaut `aurore`, clé `atlas.orbe`, dans cet ordre : `particules, liquide, anneaux, armillaire, relief, cymatique, oscilloscope, plasma, constellations, aurore, galaxie, mandala`.

- [ ] **Step 1: Remplacer le test de contrat par sa version complète**

`tests/web/orbes.test.mjs` :

```js
import assert from "node:assert/strict";
import { test } from "node:test";

import { orbes } from "../../src/atlas_web/orbes/index.js";
import { ETATS, IMAGES_PAR_ETAT, animer, fauxCanevas } from "./faux_canevas.mjs";

const ORDRE = [
  "particules",
  "liquide",
  "anneaux",
  "armillaire",
  "relief",
  "cymatique",
  "oscilloscope",
  "plasma",
  "constellations",
  "aurore",
  "galaxie",
  "mandala",
];

test("les douze orbes sont enregistrées, l'aurore par défaut", () => {
  assert.deepEqual(
    orbes.tous.map((o) => o.id),
    ORDRE,
  );
  assert.equal(orbes.parDefaut.id, "aurore");
});

for (const module of orbes.tous) {
  test(`l'orbe ${module.id} s'anime dans les quatre états sans cacher le fond`, () => {
    assert.ok(module.nom.length > 0 && module.idee.length > 0);
    for (const [largeur, hauteur] of [
      [400, 400],
      [640, 400],
    ]) {
      const canevas = fauxCanevas(largeur, hauteur);
      animer(module, canevas);
      assert.ok(canevas.bilan.dessins >= ETATS.length * IMAGES_PAR_ETAT, `${module.id} ne dessine pas à chaque image`);
      assert.equal(canevas.bilan.peinturesOpaquesPleines, 0, `${module.id} cache le fond`);
    }
  });
}
```

- [ ] **Step 2: Vérifier qu'il échoue**

Run: `node --test "tests/web/orbes.test.mjs"`
Expected: FAIL, `Cannot find module '…/src/atlas_web/orbes/index.js'`.

- [ ] **Step 3: Écrire les six orbes**

`src/atlas_web/orbes/oscilloscope.js` :

```js
import { geo, melanger, preparerOrbe, rgba, trace, TOUR } from "../dessin.js";

const PHOSPHORE = [124, 255, 140];
const RAPPORTS = { repos: [1, 1], ecoute: [1, 2], reflexion: [3, 4], parole: [2, 3] };

export default {
  id: "oscilloscope",
  nom: "Oscilloscope",
  idee: "Des courbes de Lissajous en phosphore vert, façon labo rétro.",
  creer(canvas) {
    const ctx = canvas.getContext("2d");
    let a = 1;
    let b = 2;
    return {
      dessiner(t, scene) {
        const g = geo(canvas);
        const R = g.m * 0.36;
        const v = scene.volume;
        preparerOrbe(ctx, g, scene);
        ctx.fillStyle = "rgba(2,8,5,0.85)"; // l'écran du tube
        ctx.beginPath();
        ctx.arc(g.cx, g.cy, R * 1.04, 0, TOUR);
        ctx.fill();
        ctx.strokeStyle = "rgba(124,255,140,0.10)";
        ctx.lineWidth = g.k;
        for (let i = -4; i <= 4; i++) {
          const d = (i * R) / 4;
          const l = Math.sqrt(Math.max(0, R * R - d * d));
          ctx.beginPath();
          ctx.moveTo(g.cx - l, g.cy + d);
          ctx.lineTo(g.cx + l, g.cy + d);
          ctx.stroke();
          ctx.beginPath();
          ctx.moveTo(g.cx + d, g.cy - l);
          ctx.lineTo(g.cx + d, g.cy + l);
          ctx.stroke();
        }
        ctx.strokeStyle = "rgba(124,255,140,0.25)";
        ctx.lineWidth = 2 * g.k;
        ctx.beginPath();
        ctx.arc(g.cx, g.cy, R * 1.04, 0, TOUR);
        ctx.stroke();
        const cible = RAPPORTS[scene.etat] ?? RAPPORTS.repos;
        const k = 1 - Math.exp(-scene.dt * 1.2); // la figure glisse d'un rapport à l'autre
        a += (cible[0] - a) * k;
        b += (cible[1] - b) * k;
        const phase = t * (scene.etat === "reflexion" ? 1.5 : 0.4);
        const amplitude = R * (0.45 + 0.5 * v);
        const points = [];
        for (let i = 0; i <= 500; i++) {
          const tau = (i / 500) * TOUR;
          let y = Math.sin(b * tau);
          if (scene.etat === "parole" || scene.etat === "ecoute") y += v * 0.08 * Math.sin(37 * tau + t * 25);
          points.push([g.cx + Math.sin(a * tau + phase) * amplitude, g.cy + y * amplitude]);
        }
        const teinte = melanger(PHOSPHORE, scene.couleur, 0.35);
        ctx.globalCompositeOperation = "lighter";
        ctx.strokeStyle = rgba(teinte, 0.22);
        ctx.lineWidth = 6 * g.k;
        trace(ctx, points);
        ctx.stroke();
        ctx.strokeStyle = rgba(teinte, 0.95, 0.4);
        ctx.lineWidth = 1.6 * g.k;
        trace(ctx, points);
        ctx.stroke();
      },
    };
  },
};
```

`src/atlas_web/orbes/plasma.js` :

```js
import { geo, lueur, preparerOrbe, rgba, trace, TOUR } from "../dessin.js";

export default {
  id: "plasma",
  nom: "Boule plasma",
  idee: "Des filaments électriques qui cherchent le verre au son de la voix.",
  creer(canvas) {
    const ctx = canvas.getContext("2d");
    const filaments = [];
    for (let i = 0; i < 9; i++) {
      filaments.push({ angle: (i / 9) * TOUR, derive: (Math.random() - 0.5) * 0.6, graine: Math.random() * 100 });
    }
    return {
      dessiner(t, scene) {
        const g = geo(canvas);
        const R = g.m * 0.37;
        const v = scene.volume;
        const c = scene.couleur;
        const f = Math.min(3, Math.max(0, scene.dt * 60));
        preparerOrbe(ctx, g, scene);
        const verre = ctx.createRadialGradient(g.cx, g.cy, 0, g.cx, g.cy, R);
        verre.addColorStop(0, rgba(c, 0.1));
        verre.addColorStop(1, "rgba(10,14,25,0.9)");
        ctx.fillStyle = verre;
        ctx.beginPath();
        ctx.arc(g.cx, g.cy, R, 0, TOUR);
        ctx.fill();
        ctx.globalCompositeOperation = "lighter";
        const actifs = scene.etat === "repos" ? 4 : scene.etat === "reflexion" ? 9 : 5 + Math.round(v * 4);
        const vers = t * 0.5;
        for (let i = 0; i < actifs; i++) {
          const filament = filaments[i];
          const deriveEtat = filament.derive * 0.01 * (scene.etat === "reflexion" ? 4 : 1);
          filament.angle += (deriveEtat + (Math.random() - 0.5) * 0.02) * f;
          let angle = filament.angle;
          // Quand Atlas parle, les filaments convergent, comme vers une main posée sur le verre.
          if (scene.etat === "parole") angle += Math.atan2(Math.sin(vers - angle), Math.cos(vers - angle)) * 0.35 * v;
          const points = [];
          for (let j = 0; j <= 16; j++) {
            const s = j / 16;
            const ondulation =
              Math.sin(filament.graine + j * 1.7 + t * 9) + 0.5 * Math.sin(filament.graine * 2 + j * 3.1 - t * 13);
            const ecart = ondulation * s * R * 0.12 * (0.6 + v);
            const r = s * R * 0.97;
            points.push([
              g.cx + Math.cos(angle) * r - Math.sin(angle) * ecart,
              g.cy + Math.sin(angle) * r + Math.cos(angle) * ecart,
            ]);
          }
          ctx.strokeStyle = rgba(c, 0.18);
          ctx.lineWidth = 5 * g.k * (0.7 + v * 0.6);
          trace(ctx, points);
          ctx.stroke();
          ctx.strokeStyle = rgba(c, 0.85, 0.6);
          ctx.lineWidth = 1.2 * g.k;
          trace(ctx, points);
          ctx.stroke();
          const bout = points[points.length - 1];
          lueur(ctx, bout[0], bout[1], 10 * g.k, c, 0.8, 0.5);
        }
        lueur(ctx, g.cx, g.cy, R * 0.22 * (1 + v * 0.5), c, 1, 0.8);
        ctx.globalCompositeOperation = "source-over";
        ctx.strokeStyle = "rgba(200,220,255,0.18)";
        ctx.lineWidth = 2 * g.k;
        ctx.beginPath();
        ctx.arc(g.cx, g.cy, R, 0, TOUR);
        ctx.stroke();
        const rx = g.cx - R * 0.35;
        const ry = g.cy - R * 0.4;
        const reflet = ctx.createRadialGradient(rx, ry, 0, rx, ry, R * 0.45);
        reflet.addColorStop(0, "rgba(255,255,255,0.10)");
        reflet.addColorStop(1, "rgba(255,255,255,0)");
        ctx.fillStyle = reflet;
        ctx.beginPath();
        ctx.arc(g.cx, g.cy, R, 0, TOUR);
        ctx.fill();
      },
    };
  },
};
```

`src/atlas_web/orbes/constellations.js` :

```js
import { geo, lueur, preparerOrbe, rgba, TOUR } from "../dessin.js";

function placerEtoiles() {
  const etoiles = [];
  for (let essai = 0; essai < 3000 && etoiles.length < 36; essai++) {
    const r = Math.sqrt(Math.random()) * 0.92;
    const th = Math.random() * TOUR;
    const p = [r * Math.cos(th), r * Math.sin(th), Math.random() * TOUR];
    if (etoiles.every((q) => Math.hypot(q[0] - p[0], q[1] - p[1]) > 0.17)) etoiles.push(p);
  }
  return etoiles;
}

function relier(etoiles) {
  const aretes = [];
  etoiles.forEach((p, i) => {
    const voisins = etoiles
      .map((q, j) => [Math.hypot(q[0] - p[0], q[1] - p[1]), j])
      .sort((x, y) => x[0] - y[0]);
    for (let k = 1; k <= 2 && k < voisins.length; k++) {
      const j = voisins[k][1];
      if (!aretes.some(([a, b]) => (a === i && b === j) || (a === j && b === i))) aretes.push([i, j]);
    }
  });
  return aretes;
}

export default {
  id: "constellations",
  nom: "Constellations",
  idee: "Des étoiles qui se relient ; des éclairs y courent quand il réfléchit.",
  creer(canvas) {
    const ctx = canvas.getContext("2d");
    const etoiles = placerEtoiles();
    const aretes = relier(etoiles);
    const impulsions = [];
    let prochaine = 0;
    function lancer() {
      if (aretes.length) {
        impulsions.push({ arete: Math.floor(Math.random() * aretes.length), p: 0, sens: Math.random() > 0.5 });
      }
    }
    return {
      dessiner(t, scene) {
        const g = geo(canvas);
        const R = g.m * 0.38;
        const rotation = t * 0.05;
        const c = scene.couleur;
        const v = scene.volume;
        const P = etoiles.map((e) => [
          g.cx + (e[0] * Math.cos(rotation) - e[1] * Math.sin(rotation)) * R,
          g.cy + (e[0] * Math.sin(rotation) + e[1] * Math.cos(rotation)) * R,
          e[2],
        ]);
        if ((scene.etat === "ecoute" || scene.etat === "parole") && scene.syllabe) {
          lancer();
          lancer();
          lancer();
        } else if (scene.etat === "reflexion" && t > prochaine) {
          lancer();
          prochaine = t + 0.12;
        }
        preparerOrbe(ctx, g, scene);
        ctx.globalCompositeOperation = "lighter";
        const alphaLigne = scene.etat === "repos" ? 0.06 : scene.etat === "reflexion" ? 0.28 : 0.12 + 0.3 * v;
        ctx.lineWidth = g.k;
        ctx.strokeStyle = rgba(c, alphaLigne, 0.2);
        for (const [a, b] of aretes) {
          ctx.beginPath();
          ctx.moveTo(P[a][0], P[a][1]);
          ctx.lineTo(P[b][0], P[b][1]);
          ctx.stroke();
        }
        for (let i = impulsions.length - 1; i >= 0; i--) {
          const impulsion = impulsions[i];
          impulsion.p += scene.dt * 1.5;
          if (impulsion.p >= 1) {
            impulsions.splice(i, 1);
            continue;
          }
          const [a, b] = aretes[impulsion.arete];
          const depart = P[impulsion.sens ? a : b];
          const arrivee = P[impulsion.sens ? b : a];
          const x = depart[0] + (arrivee[0] - depart[0]) * impulsion.p;
          const y = depart[1] + (arrivee[1] - depart[1]) * impulsion.p;
          lueur(ctx, x, y, 6 * g.k, c, 1, 0.6);
        }
        for (const p of P) {
          const scintillement = 0.5 + 0.5 * Math.sin(t * 2.5 + p[2]);
          lueur(ctx, p[0], p[1], (3 + 3 * v + 2 * scintillement) * g.k, c, 0.5 + 0.4 * scintillement, 0.6);
        }
      },
    };
  },
};
```

`src/atlas_web/orbes/aurore.js` :

```js
import { geo, preparerOrbe, rgba, TOUR } from "../dessin.js";

export default {
  id: "aurore",
  nom: "Aurore boréale",
  idee: "Des rideaux de lumière qui ondulent dans un hublot.",
  creer(canvas) {
    const ctx = canvas.getContext("2d");
    return {
      dessiner(t, scene) {
        const g = geo(canvas);
        const R = g.m * 0.38;
        const c = scene.couleur;
        preparerOrbe(ctx, g, scene);
        ctx.save();
        ctx.beginPath();
        ctx.arc(g.cx, g.cy, R, 0, TOUR);
        ctx.clip();
        const ciel = ctx.createLinearGradient(0, g.cy - R, 0, g.cy + R);
        ciel.addColorStop(0, "rgba(4,6,12,0.92)");
        ciel.addColorStop(1, "rgba(11,20,36,0.92)");
        ctx.fillStyle = ciel;
        ctx.fillRect(g.cx - R, g.cy - R, 2 * R, 2 * R);
        ctx.globalCompositeOperation = "lighter";
        const force = scene.etat === "repos" ? 0.25 : scene.etat === "reflexion" ? 0.55 : 0.35 + 0.65 * scene.volume;
        const vitesse = scene.etat === "reflexion" ? 2.5 : 1;
        const pas = 3 * g.k;
        for (let n = 0; n < 3; n++) {
          for (let x = g.cx - R; x < g.cx + R; x += pas) {
            const u = (x - g.cx) / R;
            const base = g.cy + R * (0.22 + 0.16 * Math.sin(u * 2.2 + t * 0.5 * vitesse + n * 1.3) + n * 0.09);
            const haut = R * (0.2 + 0.45 * force * (0.55 + 0.45 * Math.sin(u * 6 + t * (2 + n) * vitesse + n)));
            for (let s = 0; s < 6; s++) {
              ctx.fillStyle = rgba(c, (0.12 + force * 0.22) * (1 - s / 6) ** 1.3, 0.25 + 0.2 * n);
              ctx.fillRect(x, base - (haut * (s + 1)) / 6, pas, haut / 6);
            }
            ctx.fillStyle = rgba(c, 0.25 + force * 0.4, 0.6); // le liseré lumineux au pied du rideau
            ctx.fillRect(x, base - 1.5 * g.k, pas, 1.5 * g.k);
          }
        }
        ctx.restore();
        ctx.globalCompositeOperation = "source-over";
        ctx.strokeStyle = rgba(c, 0.35);
        ctx.lineWidth = 2 * g.k;
        ctx.beginPath();
        ctx.arc(g.cx, g.cy, R, 0, TOUR);
        ctx.stroke();
      },
    };
  },
};
```

`src/atlas_web/orbes/galaxie.js` :

```js
import { geo, lueur, preparerOrbe, rgba, TOUR } from "../dessin.js";

const BRAS = 3;
const INCLINAISON = -0.35;

export default {
  id: "galaxie",
  nom: "Galaxie spirale",
  idee: "Des bras d'étoiles qui tournent ; la voix y lance des ondes.",
  creer(canvas) {
    const ctx = canvas.getContext("2d");
    const etoiles = [];
    for (let i = 0; i < 1300; i++) {
      const bras = i % BRAS;
      const r = Math.random() ** 0.7;
      etoiles.push([r, (bras * TOUR) / BRAS + r * 4.2 + (Math.random() - 0.5) * 0.5]);
    }
    const cos = Math.cos(INCLINAISON);
    const sin = Math.sin(INCLINAISON);
    return {
      dessiner(t, scene) {
        const g = geo(canvas);
        const R = g.m * 0.42;
        const taille = 1.3 * g.k;
        const c = scene.couleur;
        const v = scene.volume;
        const vitesse = scene.etat === "reflexion" ? 1.2 : 0.25;
        const parle = scene.etat === "parole" || scene.etat === "ecoute";
        preparerOrbe(ctx, g, scene);
        ctx.globalCompositeOperation = "lighter";
        for (const [r, angleDepart] of etoiles) {
          const angle = angleDepart + (t * vitesse * 0.35) / (0.25 + r); // le centre tourne plus vite
          const x0 = Math.cos(angle) * r;
          const y0 = Math.sin(angle) * r * 0.5;
          const onde = parle ? Math.max(0, Math.sin(r * 10 - t * 6)) * v : 0;
          ctx.fillStyle = rgba(c, 0.2 + 0.5 * (1 - r) + onde * 0.6, 0.3 * (1 - r));
          ctx.fillRect(g.cx + (x0 * cos - y0 * sin) * R, g.cy + (x0 * sin + y0 * cos) * R, taille, taille);
        }
        lueur(ctx, g.cx, g.cy, R * (0.16 + v * 0.08), c, 1, 0.8);
      },
    };
  },
};
```

`src/atlas_web/orbes/mandala.js` :

```js
import { geo, lueur, preparerOrbe, rgba, TOUR } from "../dessin.js";

export default {
  id: "mandala",
  nom: "Mandala",
  idee: "Un kaléidoscope à 12 branches qui respire avec la voix.",
  creer(canvas) {
    const ctx = canvas.getContext("2d");
    return {
      dessiner(t, scene) {
        const g = geo(canvas);
        const R = g.m * 0.38;
        const c = scene.couleur;
        const v = scene.volume;
        const rotation = t * (scene.etat === "reflexion" ? 0.6 : 0.08);
        const souffle = 1 + v * 0.22;
        preparerOrbe(ctx, g, scene);
        ctx.globalCompositeOperation = "lighter";
        ctx.save();
        ctx.translate(g.cx, g.cy);
        ctx.rotate(rotation);
        for (let s = 0; s < 12; s++) {
          ctx.save();
          ctx.rotate((s * Math.PI) / 6);
          if (s % 2) ctx.scale(1, -1); // une branche sur deux en miroir : le kaléidoscope
          for (let k = 0; k < 3; k++) {
            const r1 = R * (0.12 + 0.26 * k) * souffle;
            const r2 = R * (0.34 + 0.26 * k) * souffle;
            const bosse = R * (0.1 + 0.07 * Math.sin(t * 1.5 + k * 1.3 + (scene.etat === "parole" ? v * 4 : 0)));
            ctx.strokeStyle = rgba(c, 0.45 + 0.4 * v - k * 0.1, k * 0.15);
            ctx.lineWidth = (1.6 - k * 0.35) * g.k;
            ctx.beginPath();
            ctx.moveTo(r1, 0);
            ctx.quadraticCurveTo((r1 + r2) / 2, bosse, r2, 0);
            ctx.quadraticCurveTo((r1 + r2) / 2, -bosse * 0.35, r1, 0);
            ctx.stroke();
            ctx.fillStyle = rgba(c, 0.8, 0.5);
            ctx.beginPath();
            ctx.arc(r2, 0, (1.6 - k * 0.3) * g.k * (1 + v), 0, TOUR);
            ctx.fill();
          }
          ctx.restore();
        }
        ctx.restore();
        lueur(ctx, g.cx, g.cy, R * (0.14 + v * 0.1), c, 1, 0.8);
      },
    };
  },
};
```

- [ ] **Step 4: Écrire le registre `src/atlas_web/orbes/index.js`**

```js
import { creerRegistre } from "../registre.js";
import anneaux from "./anneaux.js";
import armillaire from "./armillaire.js";
import aurore from "./aurore.js";
import constellations from "./constellations.js";
import cymatique from "./cymatique.js";
import galaxie from "./galaxie.js";
import liquide from "./liquide.js";
import mandala from "./mandala.js";
import oscilloscope from "./oscilloscope.js";
import particules from "./particules.js";
import plasma from "./plasma.js";
import relief from "./relief.js";

// L'ordre est celui de la galerie des paramètres.
export const orbes = creerRegistre(
  [
    particules,
    liquide,
    anneaux,
    armillaire,
    relief,
    cymatique,
    oscilloscope,
    plasma,
    constellations,
    aurore,
    galaxie,
    mandala,
  ],
  "aurore",
  "atlas.orbe",
);
```

- [ ] **Step 5: Vérifier que les tests passent**

Run: `node --test "tests/web/*.test.mjs"`
Expected: PASS (douze orbes et le registre).

- [ ] **Step 6: Commit**

```bash
git add src/atlas_web/orbes/oscilloscope.js src/atlas_web/orbes/plasma.js src/atlas_web/orbes/constellations.js src/atlas_web/orbes/aurore.js src/atlas_web/orbes/galaxie.js src/atlas_web/orbes/mandala.js src/atlas_web/orbes/index.js tests/web/orbes.test.mjs
git commit -F - <<'MSG'
Ajoute les six autres orbes et leur registre, l'aurore par défaut

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

### Task 11: Les six fonds et leur registre

Les fonds reprennent la maquette validée (fichier local : `.superpowers/brainstorm/32259-1790251451/content/fonds-ecran.html`), adaptée à l'interface commune. Le code ci-dessous fait foi.

**Files:**
- Create: `src/atlas_web/fonds/nuit.js`, `etoiles.js`, `nebuleuse.js`, `horizon.js`, `bokeh.js`, `tunnel.js`, `index.js`
- Test: `tests/web/fonds.test.mjs`

**Interfaces:**
- Consumes: `dessin.js` (Task 9), `creerRegistre` (Task 7), `faux_canevas.mjs` (Task 9).
- Produces: `fonds` (registre) dans `src/atlas_web/fonds/index.js`, défaut `bokeh`, clé `atlas.fond`, dans cet ordre : `nuit, etoiles, nebuleuse, horizon, bokeh, tunnel`. Chaque fond : `export default { id, nom, idee, creer(canvas) }`, `dessiner(t, scene)` peint tout le canevas.

- [ ] **Step 1: Écrire le test qui échoue**

`tests/web/fonds.test.mjs` :

```js
import assert from "node:assert/strict";
import { test } from "node:test";

import { fonds } from "../../src/atlas_web/fonds/index.js";
import { ETATS, IMAGES_PAR_ETAT, animer, fauxCanevas } from "./faux_canevas.mjs";

test("les six fonds sont enregistrés, le bokeh par défaut", () => {
  assert.deepEqual(
    fonds.tous.map((f) => f.id),
    ["nuit", "etoiles", "nebuleuse", "horizon", "bokeh", "tunnel"],
  );
  assert.equal(fonds.parDefaut.id, "bokeh");
});

for (const module of fonds.tous) {
  test(`le fond ${module.id} s'anime dans les quatre états, en paysage comme en portrait`, () => {
    assert.ok(module.nom.length > 0 && module.idee.length > 0);
    for (const [largeur, hauteur] of [
      [1280, 800],
      [390, 844],
    ]) {
      const canevas = fauxCanevas(largeur, hauteur);
      animer(module, canevas);
      assert.ok(canevas.bilan.dessins >= ETATS.length * IMAGES_PAR_ETAT, `${module.id} ne dessine pas à chaque image`);
    }
  });
}
```

- [ ] **Step 2: Vérifier qu'il échoue**

Run: `node --test "tests/web/fonds.test.mjs"`
Expected: FAIL, `Cannot find module '…/src/atlas_web/fonds/index.js'`.

- [ ] **Step 3: Écrire les six fonds**

`src/atlas_web/fonds/nuit.js` :

```js
import { haloFond, vignette } from "../dessin.js";

export default {
  id: "nuit",
  nom: "Nuit",
  idee: "Un dégradé bleu nuit et un vignettage : la référence sobre.",
  creer(canvas) {
    const ctx = canvas.getContext("2d");
    return {
      dessiner(t, scene) {
        const w = canvas.width;
        const h = canvas.height;
        const degrade = ctx.createLinearGradient(0, 0, 0, h);
        degrade.addColorStop(0, "#0a1020");
        degrade.addColorStop(1, "#020308");
        ctx.globalCompositeOperation = "source-over";
        ctx.fillStyle = degrade;
        ctx.fillRect(0, 0, w, h);
        haloFond(ctx, w, h, scene, 0.1);
        vignette(ctx, w, h);
      },
    };
  },
};
```

`src/atlas_web/fonds/etoiles.js` :

```js
import { haloFond, melanger, rgba, TOUR, vignette } from "../dessin.js";

const COUCHES = [
  { nombre: 140, vitesse: 0.01 },
  { nombre: 70, vitesse: 0.022 },
  { nombre: 30, vitesse: 0.045 },
];

export default {
  id: "etoiles",
  nom: "Champ d'étoiles",
  idee: "Trois couches d'étoiles qui s'écartent du centre : on avance dans l'espace.",
  creer(canvas) {
    const ctx = canvas.getContext("2d");
    const etoiles = [];
    COUCHES.forEach((couche, c) => {
      for (let i = 0; i < couche.nombre; i++) {
        etoiles.push({ couche: c, angle: Math.random() * TOUR, distance: Math.random(), phase: Math.random() * TOUR });
      }
    });
    return {
      dessiner(t, scene) {
        const w = canvas.width;
        const h = canvas.height;
        const rayon = Math.hypot(w, h) / 2;
        const echelle = Math.max(0.5, Math.min(w, h) / 700);
        ctx.globalCompositeOperation = "source-over";
        ctx.fillStyle = "#03050b";
        ctx.fillRect(0, 0, w, h);
        haloFond(ctx, w, h, scene, 0.07);
        const acceleration = scene.etat === "reflexion" ? 3 : 1;
        const teinte = melanger([220, 230, 255], scene.couleur, 0.25);
        ctx.globalCompositeOperation = "lighter";
        for (const e of etoiles) {
          e.distance += scene.dt * acceleration * COUCHES[e.couche].vitesse * (0.3 + e.distance);
          if (e.distance > 1) {
            e.distance = 0.02 + Math.random() * 0.1;
            e.angle = Math.random() * TOUR;
          }
          const x = w / 2 + Math.cos(e.angle) * e.distance * rayon;
          const y = h / 2 + Math.sin(e.angle) * e.distance * rayon;
          ctx.fillStyle = rgba(teinte, (0.25 + 0.6 * e.distance) * (0.7 + 0.3 * Math.sin(t * 3 + e.phase)));
          ctx.beginPath();
          ctx.arc(x, y, (0.5 + e.couche * 0.6 + e.distance * 1.2) * echelle, 0, TOUR);
          ctx.fill();
        }
        vignette(ctx, w, h);
      },
    };
  },
};
```

`src/atlas_web/fonds/nebuleuse.js` :

```js
import { melanger, rgba, vignette } from "../dessin.js";

const TEINTES = [
  [60, 40, 120],
  [20, 60, 120],
  [120, 40, 90],
  [30, 90, 110],
];

export default {
  id: "nebuleuse",
  nom: "Nébuleuse",
  idee: "Des nuages colorés qui dérivent lentement, teintés par l'état.",
  creer(canvas) {
    const ctx = canvas.getContext("2d");
    const nuages = [];
    for (let i = 0; i < 7; i++) {
      nuages.push({
        x: Math.random(),
        y: Math.random(),
        r: 0.25 + Math.random() * 0.3,
        phase: Math.random() * 6.28,
        teinte: TEINTES[i % TEINTES.length],
      });
    }
    const poussiere = [];
    for (let i = 0; i < 90; i++) poussiere.push([Math.random(), Math.random(), Math.random() * 6.28]);
    return {
      dessiner(t, scene) {
        const w = canvas.width;
        const h = canvas.height;
        ctx.globalCompositeOperation = "source-over";
        ctx.fillStyle = "#03040a";
        ctx.fillRect(0, 0, w, h);
        ctx.globalCompositeOperation = "lighter";
        for (const nuage of nuages) {
          const x = (nuage.x + 0.06 * Math.sin(t * 0.05 + nuage.phase)) * w;
          const y = (nuage.y + 0.05 * Math.cos(t * 0.04 + nuage.phase)) * h;
          const r = nuage.r * Math.max(w, h);
          const teinte = melanger(nuage.teinte, scene.couleur, 0.35);
          const degrade = ctx.createRadialGradient(x, y, 0, x, y, r);
          degrade.addColorStop(0, rgba(teinte, 0.22));
          degrade.addColorStop(1, rgba(teinte, 0));
          ctx.fillStyle = degrade;
          ctx.fillRect(0, 0, w, h);
        }
        const taille = Math.max(1, Math.min(w, h) / 900);
        for (const [px, py, phase] of poussiere) {
          ctx.fillStyle = rgba([230, 235, 255], 0.3 + 0.3 * Math.sin(t * 2 + phase));
          ctx.fillRect(px * w, py * h, taille, taille);
        }
        vignette(ctx, w, h);
      },
    };
  },
};
```

`src/atlas_web/fonds/horizon.js` :

```js
import { melanger, rgba, vignette } from "../dessin.js";

export default {
  id: "horizon",
  nom: "Horizon quadrillé",
  idee: "Un sol en perspective qui défile ; l'orbe flotte au-dessus de l'horizon.",
  creer(canvas) {
    const ctx = canvas.getContext("2d");
    let defilement = 0;
    let eclat = 0;
    return {
      dessiner(t, scene) {
        const w = canvas.width;
        const h = canvas.height;
        const horizon = h * 0.66;
        const c = scene.couleur;
        const ciel = ctx.createLinearGradient(0, 0, 0, horizon);
        ciel.addColorStop(0, "#02030a");
        ciel.addColorStop(1, rgba(melanger([20, 16, 40], c, 0.3), 1));
        ctx.globalCompositeOperation = "source-over";
        ctx.fillStyle = ciel;
        ctx.fillRect(0, 0, w, horizon);
        ctx.fillStyle = "#020309";
        ctx.fillRect(0, horizon, w, h - horizon);
        defilement = (defilement + scene.dt * (scene.etat === "reflexion" ? 0.9 : 0.35)) % 1;
        if (scene.syllabe) eclat = 1; // le sol pulse sur chaque syllabe
        eclat *= Math.exp(-scene.dt * 6);
        ctx.globalCompositeOperation = "lighter";
        ctx.lineWidth = Math.max(1, w / 700);
        for (let i = 0; i < 18; i++) {
          const z = (i + defilement) / 18;
          const y = horizon + (h - horizon) * z ** 2.2;
          ctx.strokeStyle = rgba(c, 0.08 + 0.35 * z + eclat * 0.2 * z);
          ctx.beginPath();
          ctx.moveTo(0, y);
          ctx.lineTo(w, y);
          ctx.stroke();
        }
        ctx.strokeStyle = rgba(c, 0.18 + eclat * 0.15);
        for (let i = -16; i <= 16; i++) {
          ctx.beginPath();
          ctx.moveTo(w / 2 + i * w * 0.012, horizon);
          ctx.lineTo(w / 2 + i * w * 0.16, h);
          ctx.stroke();
        }
        const lueur = ctx.createLinearGradient(0, horizon - h * 0.08, 0, horizon + h * 0.02);
        lueur.addColorStop(0, "rgba(0,0,0,0)");
        lueur.addColorStop(1, rgba(c, 0.25 + scene.volume * 0.15));
        ctx.fillStyle = lueur;
        ctx.fillRect(0, horizon - h * 0.08, w, h * 0.1);
        vignette(ctx, w, h);
      },
    };
  },
};
```

`src/atlas_web/fonds/bokeh.js` :

```js
import { haloFond, melanger, rgba, TOUR, vignette } from "../dessin.js";

export default {
  id: "bokeh",
  nom: "Bokeh",
  idee: "Des halos de lumière flous qui dérivent à plusieurs profondeurs.",
  creer(canvas) {
    const ctx = canvas.getContext("2d");
    const halos = [];
    for (let i = 0; i < 38; i++) {
      halos.push({
        x: Math.random(),
        y: Math.random(),
        profondeur: 0.3 + Math.random() * 0.7,
        phase: Math.random() * TOUR,
        teinte: Math.random() > 0.5 ? [255, 180, 120] : [120, 170, 255],
      });
    }
    return {
      dessiner(t, scene) {
        const w = canvas.width;
        const h = canvas.height;
        const base = Math.max(w, h);
        ctx.globalCompositeOperation = "source-over";
        ctx.fillStyle = "#04050c";
        ctx.fillRect(0, 0, w, h);
        haloFond(ctx, w, h, scene, 0.06);
        ctx.globalCompositeOperation = "lighter";
        for (const halo of halos) {
          halo.y -= scene.dt * 0.012 * halo.profondeur;
          if (halo.y < -0.2) {
            halo.y = 1.2;
            halo.x = Math.random();
          }
          const x = (halo.x + 0.02 * Math.sin(t * 0.3 + halo.phase)) * w;
          const y = halo.y * h;
          const r = (0.02 + 0.07 * (1 - halo.profondeur)) * base; // les plus proches sont les plus flous
          const alpha = (0.05 + 0.1 * halo.profondeur) * (0.8 + 0.2 * Math.sin(t + halo.phase));
          const teinte = melanger(halo.teinte, scene.couleur, 0.4);
          const degrade = ctx.createRadialGradient(x, y, r * 0.6, x, y, r);
          degrade.addColorStop(0, rgba(teinte, alpha));
          degrade.addColorStop(1, rgba(teinte, 0));
          ctx.fillStyle = degrade;
          ctx.beginPath();
          ctx.arc(x, y, r, 0, TOUR);
          ctx.fill();
        }
        vignette(ctx, w, h);
      },
    };
  },
};
```

`src/atlas_web/fonds/tunnel.js` :

```js
import { rgba, TOUR, vignette } from "../dessin.js";

export default {
  id: "tunnel",
  nom: "Tunnel",
  idee: "Des anneaux en perspective qui viennent vers toi, plus vite quand il réfléchit.",
  creer(canvas) {
    const ctx = canvas.getContext("2d");
    let avance = 0;
    return {
      dessiner(t, scene) {
        const w = canvas.width;
        const h = canvas.height;
        const cy = h * 0.42; // le point de fuite, derrière l'orbe
        const c = scene.couleur;
        ctx.globalCompositeOperation = "source-over";
        ctx.fillStyle = "#02030a";
        ctx.fillRect(0, 0, w, h);
        avance = (avance + scene.dt * (scene.etat === "reflexion" ? 0.6 : 0.15)) % 1;
        ctx.globalCompositeOperation = "lighter";
        ctx.lineWidth = Math.max(1, w / 800);
        for (let i = 0; i < 14; i++) {
          const z = (i + avance) / 14;
          const e = z ** 2.4;
          ctx.strokeStyle = rgba(c, 0.04 + 0.22 * z * (1 - z * 0.3));
          ctx.beginPath();
          ctx.ellipse(w / 2, cy, w * 0.08 + e * w * 0.75, h * 0.08 + e * h * 0.75, 0, 0, TOUR);
          ctx.stroke();
        }
        ctx.strokeStyle = rgba(c, 0.06);
        for (let k = 0; k < 12; k++) {
          const a = (k / 12) * TOUR + t * 0.02;
          ctx.beginPath();
          ctx.moveTo(w / 2 + Math.cos(a) * w * 0.08, cy + Math.sin(a) * h * 0.08);
          ctx.lineTo(w / 2 + Math.cos(a) * w * 0.9, cy + Math.sin(a) * h * 0.9);
          ctx.stroke();
        }
        vignette(ctx, w, h);
      },
    };
  },
};
```

`src/atlas_web/fonds/index.js` :

```js
import { creerRegistre } from "../registre.js";
import bokeh from "./bokeh.js";
import etoiles from "./etoiles.js";
import horizon from "./horizon.js";
import nebuleuse from "./nebuleuse.js";
import nuit from "./nuit.js";
import tunnel from "./tunnel.js";

// L'ordre est celui de la galerie des paramètres.
export const fonds = creerRegistre([nuit, etoiles, nebuleuse, horizon, bokeh, tunnel], "bokeh", "atlas.fond");
```

- [ ] **Step 4: Vérifier que les tests passent**

Run: `node --test "tests/web/*.test.mjs"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/atlas_web/fonds/nuit.js src/atlas_web/fonds/etoiles.js src/atlas_web/fonds/nebuleuse.js src/atlas_web/fonds/horizon.js src/atlas_web/fonds/bokeh.js src/atlas_web/fonds/tunnel.js src/atlas_web/fonds/index.js tests/web/fonds.test.mjs
git commit -F - <<'MSG'
Ajoute les six fonds animés et leur registre, le bokeh par défaut

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```


---

### Task 12: La page « cinéma »

**Files:**
- Replace: `src/atlas_web/index.html` (la page provisoire de la Task 6)
- Create: `src/atlas_web/style.css`, `src/atlas_web/app.js`, `src/atlas_web/sous_titres.js`, `src/atlas_web/parametres.js`
- Modify: `tests/web/faux_dom.mjs` (la fonction `fauxDocument`)
- Test: `tests/web/sous_titres.test.mjs`, `tests/web/parametres.test.mjs`, `tests/web/page.test.mjs`

**Interfaces:**
- Consumes: tout ce qui précède côté page. `etat.js` : `LIBELLES`, `appliquerMessage`, `avancer`, `creerEtat`, `sceneDe`, `sousTitresVisibles`. `historique.js` : `rendreHistorique`. `registre.js` : `lireStockage`, `ecrireStockage`, et les registres `{ tous, parDefaut, choisi, choisir }`. `connexion.js` : `Connexion` et ses statuts. `dessin.js` : `dimensionner`, `rgba`. `orbes/index.js` : `orbes`. `fonds/index.js` : `fonds`. Côté Core (Task 6), la page est servie à `/` et la connexion est `/ws/web` sur le même hôte.
- Produces:
  - `sous_titres.js` : `afficherSousTitres({ conteneur, question, reponse }, etat, maintenantMs)`.
  - `parametres.js` : `ouvrirGalerie({ document, conteneur, registre, stockage, scene, surChoix, planifier, annuler }) -> { fermer() }`, où `scene()` rend la scène courante, `surChoix(element)` est appelé après un clic, `planifier(rappel) -> id` et `annuler(id)` valent par défaut `requestAnimationFrame` et `cancelAnimationFrame`.
  - `faux_dom.mjs` : `fauxDocument()` rend désormais `{ createElement, canevas }` ; `createElement("canvas")` rend un élément doté d'un faux contexte 2D, et `canevas` liste les `{ canvas, bilan }` créés.
  - Identifiants de `index.html` utilisés par `app.js` : `fond`, `orbe`, `pastille`, `libelle-etat`, `muet`, `ouvrir-historique`, `ouvrir-parametres`, `sous-titres`, `st-question`, `st-reponse`, `saisie`, `champ`, `panneau-historique`, `liste-historique`, `panneau-parametres`, `galerie-orbes`, `galerie-fonds`, `panneau-cle`, `formulaire-cle`, `message-cle`, `champ-cle`.

- [ ] **Step 1: Donner des canevas au faux document**

Dans `tests/web/faux_dom.mjs`, ajouter l'import en tête du fichier :

```js
import { fauxCanevas } from "./faux_canevas.mjs";
```

et remplacer la fonction `fauxDocument` par :

```js
export function fauxDocument() {
  const canevas = [];
  return {
    canevas,
    createElement(tag) {
      const element = fauxElement(tag);
      if (tag !== "canvas") return element;
      const faux = fauxCanevas(160, 160);
      canevas.push(faux);
      return Object.assign(element, faux.canvas);
    },
  };
}
```

Run: `node --test "tests/web/*.test.mjs"`
Expected: PASS (rien d'autre n'a changé).

- [ ] **Step 2: Écrire les tests qui échouent**

`tests/web/sous_titres.test.mjs` :

```js
import assert from "node:assert/strict";
import { test } from "node:test";

import { DELAI_SOUS_TITRES_MS, appliquerMessage, creerEtat } from "../../src/atlas_web/etat.js";
import { afficherSousTitres } from "../../src/atlas_web/sous_titres.js";
import { fauxElement } from "./faux_dom.mjs";

const T0 = Date.UTC(2026, 8, 24, 12, 0, 0);

function compterEcritures(element) {
  let valeur = "";
  element.ecritures = 0;
  Object.defineProperty(element, "textContent", {
    get: () => valeur,
    set: (texte) => {
      valeur = texte;
      element.ecritures += 1;
    },
  });
  return element;
}

function elements() {
  return {
    conteneur: fauxElement("section"),
    question: compterEcritures(fauxElement("p")),
    reponse: compterEcritures(fauxElement("p")),
  };
}

test("la question et la réponse s'affichent, l'erreur en rouge à la place de la réponse", () => {
  const e = creerEtat();
  const el = elements();
  appliquerMessage(e, { type: "etat", valeur: "reflexion" }, T0);
  appliquerMessage(e, { type: "question", texte: "Quelle heure ?", source: "clavier" }, T0);
  appliquerMessage(e, { type: "reponse", texte: "Il est midi." }, T0);
  afficherSousTitres(el, e, T0);
  assert.equal(el.question.textContent, "Quelle heure ?");
  assert.equal(el.reponse.textContent, "Il est midi.");
  assert.equal(el.reponse.classList.contains("erreur"), false);
  appliquerMessage(e, { type: "erreur", code: "tour", message: "Je n'ai pas pu répondre : panne" }, T0);
  afficherSousTitres(el, e, T0);
  assert.equal(el.question.textContent, "Quelle heure ?");
  assert.equal(el.reponse.textContent, "Je n'ai pas pu répondre : panne");
  assert.equal(el.reponse.classList.contains("erreur"), true);
});

test("les sous-titres s'effacent après 10 s de repos", () => {
  const e = creerEtat();
  const el = elements();
  appliquerMessage(e, { type: "etat", valeur: "repos" }, T0);
  afficherSousTitres(el, e, T0 + 1000);
  assert.equal(el.conteneur.classList.contains("efface"), false);
  afficherSousTitres(el, e, T0 + DELAI_SOUS_TITRES_MS + 1);
  assert.equal(el.conteneur.classList.contains("efface"), true);
});

test("le texte n'est réécrit que s'il change", () => {
  const e = creerEtat();
  const el = elements();
  appliquerMessage(e, { type: "question", texte: "q", source: "voix" }, T0);
  for (let i = 0; i < 60; i++) afficherSousTitres(el, e, T0);
  assert.equal(el.question.ecritures, 1);
  assert.equal(el.reponse.ecritures, 0);
});
```

`tests/web/parametres.test.mjs` :

```js
import assert from "node:assert/strict";
import { test } from "node:test";

import { fonds } from "../../src/atlas_web/fonds/index.js";
import { orbes } from "../../src/atlas_web/orbes/index.js";
import { ouvrirGalerie } from "../../src/atlas_web/parametres.js";
import { fauxDocument, fauxStockage } from "./faux_dom.mjs";

const SCENE = { etat: "ecoute", volume: 0.5, couleur: [34, 211, 238], syllabe: false, dt: 1 / 60 };

function monter(registre) {
  const document = fauxDocument();
  const conteneur = document.createElement("div");
  const stockage = fauxStockage();
  const images = [];
  const annulees = [];
  const choix = [];
  const galerie = ouvrirGalerie({
    document,
    conteneur,
    registre,
    stockage,
    scene: () => SCENE,
    surChoix: (element) => choix.push(element.id),
    planifier: (rappel) => images.push(rappel), // l'identifiant rendu : la longueur de la file
    annuler: (id) => annulees.push(id),
  });
  return { document, conteneur, stockage, images, annulees, choix, galerie };
}

const marquees = (conteneur) => conteneur.children.filter((carte) => carte.classList.contains("choisie"));

test("la galerie des orbes montre les douze, l'aurore marquée", () => {
  const m = monter(orbes);
  assert.equal(m.conteneur.children.length, 12);
  const [aurore] = marquees(m.conteneur);
  assert.equal(marquees(m.conteneur).length, 1);
  assert.equal(aurore.children[1].textContent, "Aurore boréale");
});

test("les aperçus s'animent à chaque image", () => {
  const m = monter(fonds);
  m.images.shift()(0);
  m.images.shift()(16);
  assert.equal(m.document.canevas.length, 6);
  for (const { bilan } of m.document.canevas) assert.ok(bilan.dessins > 0);
  assert.equal(m.images.length, 1); // l'image suivante est déjà demandée
});

test("un clic applique le choix, le mémorise et déplace la marque", () => {
  const m = monter(orbes);
  const plasma = m.conteneur.children[7];
  plasma.declencher("click");
  assert.deepEqual(m.choix, ["plasma"]);
  assert.equal(m.stockage.getItem("atlas.orbe"), "plasma");
  assert.deepEqual(marquees(m.conteneur), [plasma]);
});

test("fermer arrête les aperçus et vide la galerie", () => {
  const m = monter(orbes);
  const enAttente = m.images.shift();
  m.galerie.fermer();
  assert.deepEqual(m.annulees, [1]);
  assert.equal(m.conteneur.children.length, 0);
  enAttente(16); // une image déjà partie ne relance rien
  assert.equal(m.images.length, 0);
});
```

`tests/web/page.test.mjs` :

```js
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const RACINE = fileURLToPath(new URL("../../src/atlas_web/", import.meta.url));

function fichiers(dossier = RACINE) {
  return readdirSync(dossier, { withFileTypes: true }).flatMap((entree) => {
    const chemin = join(dossier, entree.name);
    if (entree.isDirectory()) return fichiers(chemin);
    return /\.(js|html|css)$/.test(entree.name) ? [chemin] : [];
  });
}

const lire = (chemin) => readFileSync(chemin, "utf8");
const INDEX = lire(join(RACINE, "index.html"));

test("aucun script n'insère de HTML ni n'évalue de texte", () => {
  const interdits = [/innerHTML/, /outerHTML/, /insertAdjacentHTML/, /document\.write/, /\beval\(/, /new Function/];
  for (const chemin of fichiers().filter((c) => c.endsWith(".js"))) {
    for (const motif of interdits) assert.doesNotMatch(lire(chemin), motif, chemin);
  }
});

test("la page ne charge rien de l'extérieur", () => {
  for (const chemin of fichiers()) assert.doesNotMatch(lire(chemin), /https?:\/\//, chemin);
});

test("index.html n'a ni script, ni style, ni gestionnaire d'événement en ligne", () => {
  assert.doesNotMatch(INDEX, /<script(?![^>]*\bsrc=)[^>]*>/);
  assert.doesNotMatch(INDEX, /<style/);
  assert.doesNotMatch(INDEX, /\sstyle=/);
  assert.doesNotMatch(INDEX, /\son[a-z]+=/);
});

test("chaque élément cherché par app.js existe dans index.html", () => {
  const ids = new Set([...lire(join(RACINE, "app.js")).matchAll(/\$\("([^"]+)"\)/g)].map((m) => m[1]));
  assert.ok(ids.size >= 15);
  for (const id of ids) assert.match(INDEX, new RegExp(`id="${id}"`), id);
});

test("app.js est un module valide", () => {
  const verification = spawnSync(process.execPath, ["--check", join(RACINE, "app.js")], { encoding: "utf8" });
  assert.equal(verification.status, 0, verification.stderr);
});
```

- [ ] **Step 3: Vérifier qu'ils échouent**

Run: `node --test "tests/web/*.test.mjs"`
Expected: FAIL, `Cannot find module '…/src/atlas_web/sous_titres.js'`, `'…/parametres.js'`, et `ENOENT … app.js` pour `page.test.mjs`.

- [ ] **Step 4: Écrire `sous_titres.js` et `parametres.js`**

`src/atlas_web/sous_titres.js` :

```js
import { sousTitresVisibles } from "./etat.js";

// Les sous-titres : la question en petit, la réponse (ou l'erreur, en rouge) en grand.
// Appelée à chaque image : le DOM n'est touché que si le texte change.
export function afficherSousTitres({ conteneur, question, reponse }, etat, maintenantMs) {
  const texte = etat.erreur || etat.reponse;
  if (question.textContent !== etat.question) question.textContent = etat.question;
  if (reponse.textContent !== texte) reponse.textContent = texte;
  reponse.classList.toggle("erreur", Boolean(etat.erreur));
  conteneur.classList.toggle("efface", !sousTitresVisibles(etat, maintenantMs));
}
```

`src/atlas_web/parametres.js` :

```js
import { dimensionner } from "./dessin.js";

// Une galerie d'aperçus animés (orbes ou fonds). Un clic applique et mémorise le choix.
// Les aperçus ne tournent que tant que la galerie est ouverte.
export function ouvrirGalerie({
  document,
  conteneur,
  registre,
  stockage,
  scene,
  surChoix,
  planifier = (rappel) => requestAnimationFrame(rappel),
  annuler = (id) => cancelAnimationFrame(id),
}) {
  const choisi = registre.choisi(stockage).id;
  const cartes = registre.tous.map((element) => {
    const carte = document.createElement("button");
    carte.type = "button";
    carte.title = element.idee;
    carte.classList.add("carte");
    carte.classList.toggle("choisie", element.id === choisi);
    const canvas = document.createElement("canvas");
    const nom = document.createElement("span");
    nom.textContent = element.nom;
    carte.append(canvas, nom);
    return { carte, canvas, element, dessin: null };
  });
  for (const { carte, element } of cartes) {
    carte.addEventListener("click", () => {
      registre.choisir(stockage, element.id);
      for (const autre of cartes) autre.carte.classList.toggle("choisie", autre.element === element);
      surChoix(element);
    });
  }
  conteneur.replaceChildren(...cartes.map((c) => c.carte));

  let ouverte = true;
  let debut = null;
  let id = null;
  function image(ms) {
    if (!ouverte) return;
    debut ??= ms;
    const s = scene();
    for (const c of cartes) {
      dimensionner(c.canvas, 1);
      c.dessin ??= c.element.creer(c.canvas);
      c.dessin.dessiner((ms - debut) / 1000, s);
    }
    id = planifier(image);
  }
  id = planifier(image);

  return {
    fermer() {
      ouverte = false;
      if (id !== null) annuler(id);
      id = null;
      conteneur.replaceChildren();
    },
  };
}
```

- [ ] **Step 5: Écrire la page**

`src/atlas_web/index.html` (remplace la page provisoire) :

```html
<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="theme-color" content="#02030a">
  <title>Atlas</title>
  <link rel="icon" href="data:,">
  <link rel="stylesheet" href="style.css">
  <script type="module" src="app.js"></script>
</head>
<body>
  <canvas id="fond" aria-hidden="true"></canvas>
  <canvas id="orbe" aria-hidden="true"></canvas>

  <header id="barre">
    <div class="etat" role="status">
      <span id="pastille"></span>
      <span id="libelle-etat">Connexion…</span>
    </div>
    <label class="interrupteur">
      <input type="checkbox" id="muet">
      <span>Muet</span>
    </label>
    <button type="button" class="icone" id="ouvrir-historique" aria-label="Historique">☰</button>
    <button type="button" class="icone" id="ouvrir-parametres" aria-label="Paramètres">⚙</button>
  </header>

  <section id="sous-titres" aria-live="polite">
    <p id="st-question"></p>
    <p id="st-reponse"></p>
  </section>

  <form id="saisie" autocomplete="off">
    <input id="champ" type="text" maxlength="1000" enterkeyhint="send"
           placeholder="Écrire à Atlas…" aria-label="Question pour Atlas">
  </form>

  <section id="panneau-historique" class="panneau" aria-label="Historique" hidden>
    <header>
      <h2>Historique</h2>
      <button type="button" class="icone fermer" aria-label="Fermer">✕</button>
    </header>
    <ol id="liste-historique"></ol>
  </section>

  <section id="panneau-parametres" class="panneau" aria-label="Paramètres" hidden>
    <header>
      <h2>Paramètres</h2>
      <button type="button" class="icone fermer" aria-label="Fermer">✕</button>
    </header>
    <h3>Orbe</h3>
    <div id="galerie-orbes" class="galerie"></div>
    <h3>Fond</h3>
    <div id="galerie-fonds" class="galerie fonds"></div>
  </section>

  <section id="panneau-cle" class="cle" hidden>
    <form id="formulaire-cle">
      <h2>Clé d'accès</h2>
      <p id="message-cle"></p>
      <input id="champ-cle" type="password" autocomplete="off" aria-label="Clé d'accès">
      <button type="submit">Valider</button>
    </form>
  </section>
</body>
</html>
```

`src/atlas_web/style.css` :

```css
/* Atlas — disposition « cinéma » : le fond, l'orbe, les sous-titres et la saisie. */

:root {
  color-scheme: dark;
  --texte: #e6e9f2;
  --texte-doux: #8b93a7;
  --erreur: #f87171;
  --accent: #fbbf24;
  --verre: rgba(10, 13, 24, 0.72);
  --verre-fort: rgba(8, 10, 18, 0.94);
  --bord: rgba(255, 255, 255, 0.12);
  --marge: max(16px, env(safe-area-inset-left));
}

[hidden] {
  display: none !important;
}

* {
  box-sizing: border-box;
}

html,
body {
  margin: 0;
  height: 100%;
  overflow: hidden;
  overscroll-behavior: none;
  background: #02030a;
  color: var(--texte);
  font: 16px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif;
  -webkit-font-smoothing: antialiased;
}

button {
  font: inherit;
  color: inherit;
  background: none;
  border: 0;
  cursor: pointer;
}

/* Les deux calques : le fond peint tout l'écran, l'orbe transparente flotte devant. */
#fond {
  position: fixed;
  inset: 0;
  width: 100%;
  height: 100%;
  display: block;
}

#orbe {
  position: fixed;
  left: 50%;
  top: 42%;
  width: min(62vh, 92vw);
  height: min(62vh, 92vw);
  transform: translate(-50%, -50%);
  display: block;
  pointer-events: none;
}

/* La barre du haut. */
#barre {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: max(12px, env(safe-area-inset-top)) var(--marge) 12px;
}

/* « Hors ligne — nouvelle tentative… » peut passer sur deux lignes sur un téléphone. */
.etat {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  margin-right: auto;
  font-size: 15px;
  line-height: 1.25;
  letter-spacing: 0.02em;
}

#pastille {
  flex: none;
}

#pastille {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: rgb(90, 96, 110);
}

.icone {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-size: 19px;
  color: var(--texte-doux);
}

.icone:hover,
.icone:focus-visible {
  color: var(--texte);
  background: rgba(255, 255, 255, 0.06);
}

/* L'interrupteur « muet » : une case à cocher habillée. */
.interrupteur {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: var(--texte-doux);
  cursor: pointer;
  user-select: none;
}

.interrupteur input {
  appearance: none;
  -webkit-appearance: none;
  position: relative;
  margin: 0;
  width: 38px;
  height: 22px;
  border-radius: 11px;
  background: rgba(255, 255, 255, 0.14);
  cursor: pointer;
  transition: background 0.2s;
}

.interrupteur input::after {
  content: "";
  position: absolute;
  top: 3px;
  left: 3px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--texte);
  transition: transform 0.2s;
}

.interrupteur input:checked {
  background: var(--accent);
}

.interrupteur input:checked::after {
  transform: translateX(16px);
}

.interrupteur input:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

/* Les sous-titres, au-dessus de la saisie. */
#sous-titres {
  position: fixed;
  left: 50%;
  bottom: calc(92px + env(safe-area-inset-bottom));
  width: min(760px, calc(100vw - 32px));
  transform: translateX(-50%);
  text-align: center;
  pointer-events: none;
  transition: opacity 0.8s;
}

#sous-titres.efface {
  opacity: 0;
}

#st-question {
  margin: 0 0 6px;
  font-size: 14px;
  color: var(--texte-doux);
}

#st-reponse {
  margin: 0;
  font-size: clamp(18px, 2.6vw, 24px);
  text-shadow: 0 1px 12px rgba(0, 0, 0, 0.8);
}

#st-reponse.erreur {
  color: var(--erreur);
}

/* La saisie, en bas. */
#saisie {
  position: fixed;
  left: 50%;
  bottom: max(20px, env(safe-area-inset-bottom));
  width: min(760px, calc(100vw - 32px));
  transform: translateX(-50%);
}

#champ {
  width: 100%;
  padding: 12px 18px;
  border-radius: 24px;
  border: 1px solid var(--bord);
  background: var(--verre);
  color: var(--texte);
  font: inherit;
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}

#champ::placeholder {
  color: var(--texte-doux);
}

#champ:focus {
  outline: none;
  border-color: rgba(251, 191, 36, 0.6);
}

/* Les panneaux : historique et paramètres, par-dessus l'orbe. */
.panneau {
  position: fixed;
  left: 50%;
  bottom: 0;
  width: min(900px, 100vw);
  max-height: 82vh;
  transform: translateX(-50%);
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 0 var(--marge) max(24px, env(safe-area-inset-bottom));
  background: var(--verre-fort);
  border: 1px solid var(--bord);
  border-bottom: 0;
  border-radius: 18px 18px 0 0;
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
}

.panneau > header {
  position: sticky;
  top: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 0 8px;
  background: var(--verre-fort);
}

.panneau h2 {
  margin: 0;
  font-size: 17px;
  font-weight: 600;
}

.panneau h3 {
  margin: 18px 0 10px;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--texte-doux);
}

#liste-historique {
  list-style: none;
  margin: 0;
  padding: 0;
}

#liste-historique li {
  padding: 12px 0;
  border-top: 1px solid var(--bord);
}

#liste-historique p {
  margin: 2px 0;
}

#liste-historique .entete,
#liste-historique .latences {
  font-size: 12px;
  color: var(--texte-doux);
  font-variant-numeric: tabular-nums;
}

#liste-historique .question {
  color: var(--texte-doux);
}

#liste-historique .erreur {
  color: var(--erreur);
}

.galerie {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(128px, 40vw), 1fr));
  gap: 10px;
}

.carte {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 8px;
  border-radius: 12px;
  border: 1px solid var(--bord);
  background: rgba(0, 0, 0, 0.35);
  font-size: 13px;
}

.carte canvas {
  width: 100%;
  aspect-ratio: 1;
  display: block;
}

.galerie.fonds .carte canvas {
  aspect-ratio: 16 / 10;
  border-radius: 6px;
}

.carte.choisie {
  border-color: var(--accent);
  box-shadow: 0 0 0 1px var(--accent);
}

.carte:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

/* L'écran de la clé d'accès. */
.cle {
  position: fixed;
  inset: 0;
  display: grid;
  place-items: center;
  padding: 16px;
  background: rgba(2, 3, 10, 0.78);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
}

.cle form {
  width: min(380px, 100%);
  display: grid;
  gap: 12px;
  padding: 24px;
  border-radius: 16px;
  border: 1px solid var(--bord);
  background: var(--verre-fort);
}

.cle h2 {
  margin: 0;
  font-size: 18px;
}

.cle p {
  margin: 0;
  font-size: 14px;
  color: var(--texte-doux);
}

.cle input {
  padding: 10px 14px;
  border-radius: 10px;
  border: 1px solid var(--bord);
  background: rgba(0, 0, 0, 0.4);
  color: var(--texte);
  font: inherit;
}

.cle button {
  padding: 10px;
  border-radius: 10px;
  background: var(--accent);
  color: #111;
  font-weight: 600;
}

@media (prefers-reduced-motion: reduce) {
  #sous-titres,
  .interrupteur input,
  .interrupteur input::after {
    transition: none;
  }
}
```

`src/atlas_web/app.js` :

```js
// Le démarrage de la page : relie la connexion, l'état, l'orbe, le fond et les panneaux.

import { Connexion } from "./connexion.js";
import { dimensionner, rgba } from "./dessin.js";
import { LIBELLES, appliquerMessage, avancer, creerEtat, sceneDe } from "./etat.js";
import { fonds } from "./fonds/index.js";
import { rendreHistorique } from "./historique.js";
import { orbes } from "./orbes/index.js";
import { ouvrirGalerie } from "./parametres.js";
import { ecrireStockage, lireStockage } from "./registre.js";
import { afficherSousTitres } from "./sous_titres.js";

const $ = (id) => document.getElementById(id);
const CLE_STOCKAGE = "atlas.cle";
const SEUIL_GLISSEMENT_PX = 60;
const TOUCHENT_HISTORIQUE = new Set(["question", "reponse", "erreur", "latences", "historique"]);
const STATUTS = {
  connexion: "Connexion…",
  hors_ligne: "Hors ligne — nouvelle tentative…",
  cle_requise: "Clé requise",
  cle_refusee: "Clé refusée",
  cle_absente: "Clé non configurée",
};
const MESSAGES_CLE = {
  cle_requise: "Entre la clé d'accès d'Atlas : la valeur de ATLAS_WEB_CLE dans le .env du Core.",
  cle_refusee: "Le Core a refusé cette clé. Vérifie ATLAS_WEB_CLE dans son .env.",
  cle_absente: "Le Core n'a pas de clé : ajoute ATLAS_WEB_CLE dans son .env, redémarre-le, puis entre-la ici.",
};

let stockage = null;
try {
  stockage = window.localStorage;
} catch {
  stockage = null; // stockage interdit : les choix ne seront pas mémorisés, la page marche quand même
}
let cleEnMemoire = null;

const etat = creerEtat();
let statut = "connexion";
let orbe = orbes.choisi(stockage).creer($("orbe"));
let fond = fonds.choisi(stockage).creer($("fond"));
let sceneCourante = sceneDe(etat, 0);
let galeries = [];
const reduire = window.matchMedia("(prefers-reduced-motion: reduce)");
const sousTitres = { conteneur: $("sous-titres"), question: $("st-question"), reponse: $("st-reponse") };

// --- La connexion -----------------------------------------------------------------

const connexion = new Connexion({
  url: `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/web`,
  lireCle: () => cleEnMemoire ?? lireStockage(stockage, CLE_STOCKAGE),
  surMessage(message) {
    appliquerMessage(etat, message, Date.now());
    if (message.type === "muet") $("muet").checked = message.actif;
    if (TOUCHENT_HISTORIQUE.has(message.type) && !$("panneau-historique").hidden) {
      rendreHistorique(document, $("liste-historique"), etat.historique);
    }
  },
  surStatut(nouveau) {
    statut = nouveau;
    etat.enLigne = nouveau === "en_ligne";
    if (nouveau in MESSAGES_CLE) demanderCle(MESSAGES_CLE[nouveau]);
  },
});

function demanderCle(message) {
  fermerPanneaux();
  $("message-cle").textContent = message;
  $("champ-cle").value = "";
  $("panneau-cle").hidden = false;
  $("champ-cle").focus();
}

$("formulaire-cle").addEventListener("submit", (evenement) => {
  evenement.preventDefault();
  const cle = $("champ-cle").value.trim();
  if (!cle) return;
  cleEnMemoire = cle;
  ecrireStockage(stockage, CLE_STOCKAGE, cle);
  $("panneau-cle").hidden = true;
  connexion.demarrer();
});

// --- La saisie et le muet ---------------------------------------------------------

$("saisie").addEventListener("submit", (evenement) => {
  evenement.preventDefault();
  const texte = $("champ").value.trim();
  if (texte && connexion.envoyer({ type: "saisie", texte })) $("champ").value = "";
});

$("muet").addEventListener("change", () => {
  // Le Core confirme à toutes les pages ; hors ligne, l'interrupteur revient à sa place.
  if (!connexion.envoyer({ type: "muet", actif: $("muet").checked })) $("muet").checked = etat.muet;
});

// --- Les panneaux -----------------------------------------------------------------

function ouvrirParametres() {
  const commun = { document, stockage, scene: () => sceneCourante };
  galeries = [
    ouvrirGalerie({
      ...commun,
      conteneur: $("galerie-orbes"),
      registre: orbes,
      surChoix: (choix) => {
        orbe = choix.creer($("orbe"));
      },
    }),
    ouvrirGalerie({
      ...commun,
      conteneur: $("galerie-fonds"),
      registre: fonds,
      surChoix: (choix) => {
        fond = choix.creer($("fond"));
      },
    }),
  ];
}

function ouvrirPanneau(panneau) {
  const dejaOuvert = !panneau.hidden;
  fermerPanneaux();
  if (dejaOuvert) return; // le même bouton ouvre et ferme
  panneau.hidden = false;
  panneau.scrollTop = 0;
  if (panneau === $("panneau-historique")) rendreHistorique(document, $("liste-historique"), etat.historique);
  else ouvrirParametres();
}

function fermerPanneaux() {
  for (const galerie of galeries) galerie.fermer();
  galeries = [];
  $("panneau-historique").hidden = true;
  $("panneau-parametres").hidden = true;
}

$("ouvrir-historique").addEventListener("click", () => ouvrirPanneau($("panneau-historique")));
$("ouvrir-parametres").addEventListener("click", () => ouvrirPanneau($("panneau-parametres")));
for (const bouton of document.querySelectorAll(".panneau .fermer")) {
  bouton.addEventListener("click", fermerPanneaux);
}
document.addEventListener("keydown", (evenement) => {
  if (evenement.key === "Escape") fermerPanneaux();
});

// Glisser vers le haut ouvre l'historique ; vers le bas, depuis le haut d'un panneau, le ferme.
let depart = null;
document.addEventListener(
  "touchstart",
  (evenement) => {
    if (evenement.touches.length !== 1) {
      depart = null;
      return;
    }
    const ouvert = document.querySelector(".panneau:not([hidden])");
    depart = { y: evenement.touches[0].clientY, ouvert, enHaut: !ouvert || ouvert.scrollTop === 0 };
  },
  { passive: true },
);
document.addEventListener(
  "touchend",
  (evenement) => {
    if (!depart || !$("panneau-cle").hidden) return;
    const dy = evenement.changedTouches[0].clientY - depart.y;
    if (!depart.ouvert && dy < -SEUIL_GLISSEMENT_PX) ouvrirPanneau($("panneau-historique"));
    else if (depart.ouvert && depart.enHaut && dy > SEUIL_GLISSEMENT_PX) fermerPanneaux();
    depart = null;
  },
  { passive: true },
);

// --- L'animation ------------------------------------------------------------------

let t = 0;
let precedent = null;
let idImage = null;

function image(ms) {
  const dt = precedent === null ? 0 : Math.min(0.1, (ms - precedent) / 1000);
  precedent = ms;
  // Hors ligne, l'orbe se fige : son temps s'arrête, seule sa couleur glisse vers le gris.
  const pas = etat.enLigne ? dt * (reduire.matches ? 0.5 : 1) : 0;
  t += pas;
  avancer(etat, dt);
  sceneCourante = sceneDe(etat, pas, reduire.matches);
  dimensionner($("fond"));
  dimensionner($("orbe"));
  fond.dessiner(t, sceneCourante);
  orbe.dessiner(t, sceneCourante);
  $("pastille").style.backgroundColor = rgba(etat.couleur, 1);
  const libelle = etat.enLigne ? LIBELLES[etat.etat] : (STATUTS[statut] ?? "");
  if ($("libelle-etat").textContent !== libelle) $("libelle-etat").textContent = libelle;
  afficherSousTitres(sousTitres, etat, Date.now());
  idImage = requestAnimationFrame(image);
}

// Onglet caché : plus aucune image, ni de l'orbe ni du fond.
document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    cancelAnimationFrame(idImage);
    idImage = null;
  } else if (idImage === null) {
    precedent = null;
    idImage = requestAnimationFrame(image);
  }
});

connexion.demarrer();
idImage = requestAnimationFrame(image);
```

- [ ] **Step 6: Vérifier que les tests passent**

Run: `node --test "tests/web/*.test.mjs" && uv run pytest -q`
Expected: PASS. `tests/test_hub_web.py::test_la_page_est_servie_avec_sa_politique_de_securite` sert maintenant la vraie page.

- [ ] **Step 7: Regarder la page dans un navigateur**

Lancer un Core local, sur la boucle locale seulement, avec une clé d'essai jetable :

```bash
ATLAS_WEB_CLE=essai-local uv run uvicorn atlas_core.hub:app --host 127.0.0.1 --port 8080
```

Ouvrir `http://127.0.0.1:8080/` et vérifier :

1. L'écran de la clé s'affiche ; une clé fausse (`mauvaise`) est refusée (« Clé refusée » et l'écran revient) ; `essai-local` est acceptée.
2. La barre affiche « Repos », l'aurore flotte devant le bokeh, sans rectangle noir autour de l'orbe.
3. Taper `Quelle heure est-il ?` puis Entrée : le champ se vide, la question s'affiche en gris, la réponse en grand ; l'orbe passe par la réflexion (violet) puis revient au repos. Les sous-titres s'effacent dix secondes plus tard.
4. ☰ ouvre l'historique : l'échange est là, avec l'heure, ⌨ et les délais. Échap le ferme.
5. L'interrupteur « muet » bascule et reste dans sa position après un rechargement de la page (le Core le renvoie).
6. ⚙ ouvre les deux galeries animées (12 orbes, 6 fonds) ; choisir `plasma` et `horizon` les applique aussitôt, et un rechargement les garde.
7. Arrêter le Core (Ctrl-C) : l'orbe devient grise et immobile, « Hors ligne — nouvelle tentative… ». Le relancer : la page se reconnecte seule, sans redemander la clé.
8. La console du navigateur ne montre aucune erreur, en particulier aucune violation de la politique de sécurité.
9. En largeur de téléphone (375 × 812), rien ne déborde ; seul le libellé « Hors ligne — nouvelle tentative… » peut passer sur deux lignes.

Arrêter le Core ensuite.

- [ ] **Step 8: Commit**

```bash
git add src/atlas_web/index.html src/atlas_web/style.css src/atlas_web/app.js src/atlas_web/sous_titres.js src/atlas_web/parametres.js tests/web/faux_dom.mjs tests/web/sous_titres.test.mjs tests/web/parametres.test.mjs tests/web/page.test.mjs
git commit -F - <<'MSG'
Monte la page « cinéma » : orbe, fond, sous-titres, saisie et panneaux

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

### Task 13: `make test` pour les deux langages, et la spec parente à jour

**Files:**
- Modify: `Makefile`
- Modify: `docs/superpowers/specs/2026-09-22-atlas-design.md` (§6.5, fin du §6.6, phase 4, §17)

**Interfaces:**
- Consumes: les tests JavaScript des Tasks 7 à 12.
- Produces: `make test` (Python puis JavaScript) et `make test-web` (JavaScript seul).

- [ ] **Step 1: Le Makefile**

Dans `Makefile`, remplacer la ligne `.PHONY` et la recette `test` :

```make
.PHONY: install test test-swift lint format bench run-core run-audio
```

```make
test:
	uv run pytest -v
```

par :

```make
.PHONY: install test test-web test-swift lint format bench run-core run-audio
```

```make
test:
	uv run pytest -v
	node --test "tests/web/*.test.mjs"

test-web:
	node --test "tests/web/*.test.mjs"
```

(Les recettes commencent par une tabulation, pas par des espaces.)

Run: `make test`
Expected: les tests Python passent, puis les tests JavaScript ; la commande se termine sans erreur.

- [ ] **Step 2: La spec parente**

Dans `docs/superpowers/specs/2026-09-22-atlas-design.md` :

1. Au §6.5, remplacer le paragraphe :

```
L'orbe Three.js qui réagit à la voix — amplitude d'entrée, état d'écoute, de réflexion, de
parole — et le tableau de bord : état des workflows n8n, contenu de la mémoire, documents
produits, historique de conversation, erreurs, latences mesurées.
```

par :

```
L'orbe qui réagit à la voix — amplitude d'entrée, état d'écoute, de réflexion, de parole —,
dessinée en Canvas 2D, sans Three.js : 12 orbes et 6 fonds animés au choix, avec la
conversation en sous-titres et une saisie au clavier (voir
`2026-09-24-interface-orbe-design.md`). Puis le tableau de bord : état des workflows n8n,
contenu de la mémoire, documents produits, erreurs.
```

2. À la fin du §6.6, juste après la ligne `| \`error\` | \`{code, message_fr}\` |` et avant le `---` qui ouvre le §7, ajouter une ligne vide puis :

```
La page web ouvre une seconde connexion, `/ws/web`, réservée à l'affichage et à la saisie :
clé d'accès dans le premier message, origine vérifiée, messages décrits au §4.4 de
`2026-09-24-interface-orbe-design.md`.
```

3. En phase 4, remplacer :

```
**Phase 4 — Présence et accès.** Orbe et tableau de bord, Hermes en porte mobile.
```

par :

```
**Phase 4 — Présence et accès.** Tableau de bord, Hermes en porte mobile. L'orbe et la
conversation ont été avancées (`2026-09-24-interface-orbe-design.md`).
```

4. Au §17, remplacer :

```
    atlas_web/        front : orbe Three.js + tableau de bord
```

par :

```
    atlas_web/        front : orbe Canvas 2D, conversation, puis tableau de bord
```

Run: `grep -n "Three.js" docs/superpowers/specs/2026-09-22-atlas-design.md`
Expected: plus aucune ligne qui présente Three.js comme le choix retenu.

- [ ] **Step 3: Vérifier l'ensemble**

Run: `make test && make lint`
Expected: tout passe.

- [ ] **Step 4: Commit**

```bash
git add Makefile docs/superpowers/specs/2026-09-22-atlas-design.md
git commit -F - <<'MSG'
Lance les tests de la page avec make test et met la spec parente à jour

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

## L'essai avec David, sur le vrai matériel

Après la Task 13, sur la branche `interface-orbe`, avant la PR. C'est David qui lance tout ce qui ouvre le micro.

1. **La clé.** David génère une clé et l'ajoute à son `.env` (jamais commité) :

   ```bash
   printf '\nATLAS_WEB_CLE=%s\n' "$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')" >> .env
   ```

2. **Le Core et le client audio**, comme d'habitude : `make run-core` dans un terminal, `make run-audio` dans un autre.
3. **Sur le Mac**, la page `http://<adresse-du-core>:8080/` : entrer la clé, puis vérifier :
   - « Hey Atlas » : l'orbe passe au cyan et suit la voix ; violet pendant la réflexion ; or pendant la parole, avec les syllabes qui animent l'orbe au rythme de ce qu'on entend (sans avance ni retard visibles) ;
   - la question dite et la réponse s'affichent en sous-titres, et dans l'historique avec 🎙 et les trois délais ;
   - une question tapée pendant qu'Atlas parle le coupe, et il répond à la question tapée, à voix haute ;
   - avec « muet », une question tapée ou dite reçoit une réponse écrite seulement ;
   - arrêter le client audio pendant une réponse à une question tapée : la réponse se termine par écrit.
4. **Sur l'iPad**, la même adresse : entrer la clé (une fois), vérifier la disposition en portrait et en paysage, le glissement vers le haut (historique) et vers le bas (fermeture), et que la page du Mac et celle de l'iPad montrent la même conversation.
5. **Les réglages** : choisir une orbe et un fond différents sur le Mac et sur l'iPad ; chacun garde le sien.

Ce qui ne va pas devient une correction sur la branche, avec son test, avant la PR.

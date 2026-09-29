# Les réglages des connecteurs et le Core, depuis la page — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Depuis les Paramètres de la page, David saisit les réglages de ses connecteurs (écrits dans le `.env` du Core et appliqués tout de suite, un secret n'en revenant jamais, les clés d'Atlas restant au Terminal), et redémarre le Core, avec ou sans mise à jour, même quand il tourne sur une autre machine.

**Architecture:** `reglages.py` vérifie et écrit un réglage dans le `.env`, pour que `make` le relise à l'identique ; `OutilsMemoire.regler` l'applique aussitôt (l'environnement du Core, le registre, la mémoire). `entretien.py` donne la version, redémarre le Core (une marque `donnees/redemarrer`, puis un arrêt propre) et le met à jour (`git pull --ff-only`, `make install`) ; `make run-core` devient une boucle qui relance le Core par un `make` neuf tant qu'il laisse la marque. Le routage des messages de la page sort de `hub.py` (`routage_pages.py`). La page gagne un formulaire de réglages par connecteur (`reglages.js`) et une rubrique « Le Core » (`core.js`).

**Tech Stack:** Python 3.12+ (venv en 3.13), pydantic v2, FastAPI, asyncio (sous-processus), pytest (asyncio auto) ; GNU Make (celui de macOS, 3.81) ; git ; JavaScript en modules ES sans dépendance, testé par `node --test`.

**Spec:** `docs/superpowers/specs/2026-09-29-reglages-et-core-design.md` (à lire avec ce plan : elle fait foi en cas de doute).

## Global Constraints

- Code, identifiants, messages et commentaires en français, comme le reste du dépôt ; lignes de 100 caractères au plus (ruff) pour Python.
- Aucune nouvelle dépendance Python ni JavaScript.
- La branche `reglages-core` part de `interrupteur-connecteurs` (PR #15, l'interrupteur habillé comme « Hey Atlas ») : ce plan s'applique après son commit 2fe273a et la spec.
- Les réglages modifiables depuis la page : seulement les variables que déclare le connecteur, jamais une clé d'Atlas (toute variable `ATLAS_…` que lit le code d'Atlas — le Core, le client audio, le poste — et `CLAUDE_CODE_OAUTH_TOKEN`), quoi que dise le manifeste. Une valeur : une ligne, sans caractère de contrôle, sans espace au début ni à la fin, sans barre oblique inverse à la fin, 4 096 caractères au plus.
- Un secret va de la page au Core, jamais dans l'autre sens : ni sa valeur, ni sa longueur, ni dans le journal. La valeur d'une clé d'Atlas ne va jamais non plus vers une page.
- Le `.env` du Core est celui que lit `make` (`-include .env`, puis `export`) : une valeur y est écrite pour que `make` la relise à l'identique (`$` doublé, `#` protégé) ; le reste du fichier ne bouge pas ; l'écriture est atomique et le fichier finit en 600.
- Un réglage prend effet tout de suite ; un connecteur actif se recharge, et la conversation se renouvelle comme après une bascule.
- Le redémarrage : la marque `donnees/redemarrer` (à la racine du dépôt), puis un arrêt comme à un Ctrl-C ; `make run-core` relance le Core par un `make` neuf tant qu'il la laisse. La mise à jour : seulement sur `main`, sans fichier suivi modifié ; `git pull --ff-only`, puis `make install`, puis le redémarrage ; 2 minutes, puis 10 minutes au plus ; un échec ne redémarre rien. Un seul redémarrage ou une seule mise à jour à la fois.
- Aucun texte venu d'une page n'entre dans une commande : `git` et `make` sont lancés avec des arguments fixes, dans le dépôt du Core.
- Les messages des pages (`/ws/web`, protégés par la clé) : `regler_connecteur` (`id`, `valeurs`, `effacer`) ; `resultat_reglage` (`id`, `ok`, `message`), à la page qui a demandé ; `liste_connecteurs` gagne `reglages` (`variable`, `description`, `secret`, `defini`, `modifiable`, `valeur`) ; `demande_core` ; `etat_core` (`version`, `date`, `occupe`, `mise_a_jour_possible`, `raison`), à la page qui a demandé ; `redemarrer_core`, `mettre_a_jour_core` ; `core_en_cours` (`etape` : `redemarrage`, `recuperation`, `installation` ; `texte` ; `nouveautes`) et `fin_core` (`ok`, `texte`, `details`), à toutes les pages (un refus : à la page qui a demandé).
- La page, mot pour mot : « Réglages », « Enregistrer », « Effacer », « Défini », « À définir », « se change au Terminal », « Défini — laisse vide pour le garder » ; « Enregistré. » ; la rubrique « Le Core » en bas des Paramètres, « Version <commit>, du <date> », « Redémarrer », « Mettre à jour et redémarrer », « Confirmer », « Annuler » ; « Redémarrer le Core ? La conversation en cours se clôt, avec son résumé au journal. Atlas revient dans une dizaine de secondes. » ; « Mettre Atlas à jour ? Le Core récupère la dernière version, installe ce qui manque, puis redémarre. La conversation en cours se clôt. » ; « Redémarrage du Core… », « Récupération de la dernière version… », « Installation… », « Atlas est déjà à jour. », « Un redémarrage ou une mise à jour est déjà en cours. », « La récupération a échoué : rien n'a changé. », « L'installation a échoué : relance make install au Terminal avant de redémarrer. » ; dans la barre du haut « Le Core ne revient pas », et dans la rubrique « Le Core ne revient pas : regarde son journal (donnees/logs/core.log sur le néo). ». Les textes d'un manifeste et des commits ne sont jamais que du texte.
- Les tests n'écrivent jamais le `.env` du dépôt, ne touchent jamais le dépôt de David et n'arrêtent jamais le Core (`tests/conftest.py` remplace `reglages.FICHIER_ENV`, `entretien.DEPOT` et `entretien.arreter_le_core`) ; ils ne lancent jamais un vrai `git pull` du dépôt, un vrai `make install` ni le vrai Core (le test de la boucle refuse un `Makefile` qui le lancerait).
- Ne jamais lancer `make run-core`, `make install`, ce qui ouvre un micro, le poste, ni ce qui appelle le vrai Claude : c'est David qui le fait.
- Dépôt public : aucune adresse IP, aucun domaine, nom ou courriel privé, aucun jeton dans ce qui est commité.
- Git : ajouter les fichiers par leur chemin, jamais `git add -A` (le dossier `spikes/` n'est pas suivi et reste privé). Messages de commit en français, terminés par la ligne `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Avant chaque commit : `uv run pytest -q`, `uv run ruff check . --extend-exclude spikes`, `uv run ruff format --check . --extend-exclude spikes`, `node --test "tests/web/*.test.mjs"`. Si `ruff format --check` échoue, lancer `uv run ruff format <fichiers>` : la mise en forme fait foi.
- Fichiers de moins de 500 lignes : `hub.py` finit à 437 (le routage des pages en sort, dans `routage_pages.py`), `registre.py` et `memoire.py` à 485, `app.js` à 398, `documents.css` à 408 (les nouveaux styles y vont, `style.css` reste à 439).
- **Copier le code programmatiquement.** Les fichiers neufs sont donnés en entier, les autres par des diffs unifiés exacts (`git apply` les accepte tels quels, copiés d'un bloc) : ne rien retaper à la main.
- Le code de ce plan a été vérifié tel quel avant d'être écrit ici : appliquées dans l'ordre, les 8 tâches donnent 1 277 tests Python (1 274, et 3 ignorés, sans `models/silero_vad.onnx`) et 167 tests JavaScript qui passent, un lint propre, et chaque tâche laisse la suite entière au vert. Les tests ont en outre été mis à l'épreuve par mutations : chaque comportement clé, retiré du code, fait échouer au moins un test. Un écart entre le plan et ce que vous observez est donc à signaler, pas à contourner.

## Review Focus

Les cinq situations que la spec implique sans les décrire, les plus susceptibles de surprendre David ; chacune a son test dans la tâche qui en porte le code.

1. **Deux pages, ou deux clics, qui demandent « Redémarrer » presque en même temps** : un seul redémarrage ; le second reçoit « Un redémarrage ou une mise à jour est déjà en cours. », à lui seul. Task 5 : `test_redemarrer_depuis_une_page_toutes_les_pages_le_voient`.
2. **David retouche le `.env` à la main pendant que le Core tourne, puis enregistre un réglage dans la page** : ses retouches restent. Task 1 : `test_une_retouche_a_la_main_entre_deux_enregistrements_reste`.
3. **Un `.env` rangé ailleurs et lié dans le dépôt (lien symbolique)** : le lien reste, sa cible est écrite. Task 1 : `test_un_env_en_lien_symbolique_garde_son_lien`.
4. **Un fichier non suivi, laissé dans le dépôt du Core, qu'une nouveauté ajoute aussi** : la récupération échoue, le fichier de David reste, rien ne s'installe ni ne redémarre. Task 4 : `test_un_fichier_non_suivi_qu_une_nouveaute_ecraserait_arrete_tout`.
5. **Un Core lancé sans la boucle (une ancienne commande, un autre lanceur)** : il ne revient pas ; au bout d'une minute, la barre du haut dit « Le Core ne revient pas » et la rubrique nomme son journal. Task 7 : `le Core se redémarre depuis les Paramètres, et la barre du haut suit son retour`.

## Décisions prises en écrivant le plan

La spec fait foi ; voici ce qu'elle laissait ouvert et ce que le plan en a fait.

1. **Les clés d'Atlas sont toutes les variables `ATLAS_…` que lit le code d'Atlas** (le Core, le client audio, le poste), et pas seulement celles de `config.py` : sur le M5, le même `.env` sert aux trois. Un test compare la liste au code.
2. **Une valeur vide se retire, elle ne s'écrit pas** : la page met un réglage vidé dans `effacer` ; le Core refuse une valeur vide dans `valeurs`. Une valeur qui finirait par `\` est refusée (`make` y verrait une ligne qui continue).
3. **Le `.env` reconnaît les affectations que `make` lit** (`=`, `:=`, `::=`, `?=`, `+=`, avec ou sans `export`) : la première est remplacée, ses doublons retirés ; un `.env` en lien symbolique garde son lien ; le fichier voisin `.env.tmp` ne reste jamais.
4. **Un connecteur actif rechargé est coupé puis réactivé** (deux bascules) : son interrupteur reste ; s'il ne se recharge pas, il passe « en erreur » et son interrupteur est retiré ; un réglage effacé le rend « à configurer ».
5. **Seuls les réglages changés partent au Core** ; un secret laissé vide est gardé.
6. **L'entretien est créé au démarrage du Core**, efface une marque restée là, et s'arrête avec lui : une mise à jour en cours est tuée avec tout son groupe de processus (`start_new_session`, puis `killpg`), sans attendre ce que `make` a lancé.
7. **La boucle de relance retire, pour le `make` neuf, les variables que le `.env` avait données au premier** (`env -u`, la liste lue dans le `.env` par `sed`) ; elle garde le code de sortie du Core quand il n'a pas laissé la marque ; `COMMANDE_CORE` permet au test de lancer un faux Core. uvicorn relaie le signal d'arrêt : `make` affiche alors « Terminated: 15 », comme avant.
8. **`git` ne pose jamais de question** (`GIT_TERMINAL_PROMPT=0`) ; les nouveautés sont les titres des commits, les plus récents d'abord, cinq au plus, puis « et N autres » ; les dernières lignes d'une erreur : dix au plus, de 200 caractères.
9. **La page tient l'état du Core dans `SuiviCore`** : la barre du haut dit « Redémarrage du Core… » tant que la page est hors ligne après un redémarrage, et le Core est revenu quand la connexion revient en ligne après s'être coupée ; elle redemande alors la version. Ouvrir les Paramètres redemande la version et repart d'une liste de réglages fermée, sans vieux message.

## Carte des fichiers

| Fichier | Tâche | Rôle |
|---|---|---|
| `src/atlas_core/reglages.py` ; `tests/conftest.py` | 1 | Les clés d'Atlas, la vérification d'un réglage, le `.env` écrit pour `make` |
| `src/atlas_core/outils_memoire.py`, `registre.py`, `memoire.py` | 2 | Un réglage appliqué tout de suite |
| `src/atlas_core/protocole_web.py`, `pages.py`, `routage_pages.py`, `hub.py` | 3 | Les messages des réglages ; le routage des pages à part |
| `src/atlas_core/entretien.py`, `protocole_web.py` ; `tests/conftest.py` | 4 | La version, le redémarrage, la mise à jour |
| `src/atlas_core/protocole_web.py`, `routage_pages.py`, `hub.py` ; `Makefile` | 5 | Les boutons du Core côté serveur ; la boucle de relance |
| `src/atlas_web/reglages.js`, `connecteurs.js`, `app.js`, `documents.css` | 6 | Les réglages dans la page |
| `src/atlas_web/core.js`, `app.js`, `index.html`, `documents.css` | 7 | La rubrique « Le Core » |
| `connecteurs/LISEZMOI.md`, `scripts/neo/LISEZMOI.md`, `docs/superpowers/specs/2026-09-28-connecteurs-design.md` | 8 | Les guides et la spec des connecteurs |
| `tests/test_reglages.py`, `test_outils_reglages.py`, `test_entretien.py`, `test_lanceur.py`, `tests/web/reglages.test.mjs`, `tests/web/core.test.mjs` (nouveaux) ; `test_protocole_web.py`, `test_hub_web.py`, `tests/web/connecteurs.test.mjs`, `tests/web/app.test.mjs` | 1–7 | Tests |

---

### Task 1: Le .env, écrit pour make

Ce qui vérifie et écrit un réglage dans le `.env` du Core : seulement les variables que déclare le connecteur,
jamais une clé d'Atlas (toute variable `ATLAS_…` que lit le code d'Atlas, et le jeton de Claude) ; une valeur d'une
ligne, écrite pour que `make` la relise à l'identique (vérifié avec le vrai `make`) ; le reste du fichier intact ;
une écriture atomique, en 600. Les tests n'écrivent jamais le `.env` du dépôt (`tests/conftest.py`). Review Focus 2
et 3 : une retouche à la main entre deux enregistrements reste ; un `.env` en lien symbolique garde son lien.

**Files:**
- Create: `src/atlas_core/reglages.py`
- Modify: `tests/conftest.py`
- Create: `tests/test_reglages.py`

**Interfaces:**
- Consumes: `atlas_core.connecteurs` (`Manifeste`, `Reglage`, `API`).
- Produces: `atlas_core.reglages` : `DEPOT`, `FICHIER_ENV` (`DEPOT / ".env"`, remplacé dans les tests),
  `VALEUR_MAX = 4096`, `CLES_D_ATLAS: frozenset[str]`, `ReglageRefuse(ValueError)`, `modifiable(variable) -> bool`,
  `changements_permis(manifeste, valeurs: Mapping[str, str], effacer: Iterable[str]) -> dict[str, str | None]`
  (None : retirer), `pour_make(valeur) -> str`, `ecrire_env(fichier: Path, changements: Mapping[str, str | None])`
  (`ReglageRefuse` si rien ne s'écrit) ; la fixture automatique `_jamais_le_env_du_depot` de `tests/conftest.py`.

- [ ] **Step 1: Écrire les tests qui échouent**

Modifier `tests/conftest.py` :

```diff
--- a/tests/conftest.py
+++ b/tests/conftest.py
@@ -3,12 +3,22 @@
 La mémoire d'Atlas est un dépôt git sur la machine du Core, et ses connecteurs vivent à côté :
 les tests, qui démarrent le Core, ne doivent jamais toucher les vrais. Les dossiers sont forcés
 avant tout import du Core (`make test` exporte le .env de la machine, qui pourrait en nommer
-d'autres).
+d'autres). Les réglages écrits depuis la page vont dans un .env de test, jamais dans celui du
+dépôt.
 """
 
 import os
 import tempfile
 
+import pytest
+
 _TEMPORAIRE = tempfile.mkdtemp(prefix="atlas-tests-")
 os.environ["ATLAS_MEMOIRE_DOSSIER"] = os.path.join(_TEMPORAIRE, "memoire")
 os.environ["ATLAS_CONNECTEURS_DOSSIER"] = os.path.join(_TEMPORAIRE, "connecteurs")
+
+
+@pytest.fixture(autouse=True)
+def _jamais_le_env_du_depot(monkeypatch, tmp_path_factory):
+    from atlas_core import reglages
+
+    monkeypatch.setattr(reglages, "FICHIER_ENV", tmp_path_factory.mktemp("env") / ".env")
```

Créer `tests/test_reglages.py` :

```python
"""Les réglages écrits dans le .env du Core depuis la page : relus à l'identique par le vrai
`make`, le reste du fichier intact, et jamais une clé d'Atlas."""

import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from atlas_core import reglages
from atlas_core.connecteurs import API, Manifeste, Reglage
from atlas_core.reglages import (
    CLES_D_ATLAS,
    ReglageRefuse,
    changements_permis,
    ecrire_env,
    modifiable,
)

SOURCES = Path(__file__).resolve().parents[1] / "src"
# Ce que fait `make run-core` du .env : il l'inclut, puis exporte tout.
MAKEFILE = "-include .env\nexport\nafficher:\n\t@printenv CLE\n"


def manifeste(*reglages_: Reglage) -> Manifeste:
    return Manifeste(
        nom="Bonjour", description="Dit bonjour.", version="0.1", auteur="Quelqu'un", api=API,
        reglages=reglages_,
    )  # fmt: skip


NOM = Reglage(variable="ATLAS_BONJOUR_NOM", description="Le nom à saluer")
CLE = Reglage(variable="ATLAS_BONJOUR_CLE", description="La clé du service", secret=True)


def relu_par_make(dossier: Path) -> str:
    environ = {k: v for k, v in os.environ.items() if k != "CLE" and not k.startswith("MAKE")}
    r = subprocess.run(
        ["make", "-s", "afficher"], cwd=dossier, env=environ, capture_output=True, text=True
    )
    assert r.returncode == 0, r.stderr
    return r.stdout.removesuffix("\n")


@pytest.mark.skipif(shutil.which("make") is None, reason="make absent")
@pytest.mark.parametrize(
    "valeur",
    [
        "abc",
        "a$b",
        "$(shell touch temoin)",
        "a#b",
        "#au début",
        "a\\#b",
        "a\\\\#b",
        "a\\b",
        '"entre guillemets"',
        "a b  c",
        "é€😀",
        "a=b:c;d`e",
    ],
)
def test_une_valeur_est_relue_par_make_a_l_identique(tmp_path, valeur):
    (tmp_path / "Makefile").write_text(MAKEFILE)
    ecrire_env(tmp_path / ".env", {"CLE": valeur})
    assert relu_par_make(tmp_path) == valeur
    assert not (tmp_path / "temoin").exists(), "make n'exécute jamais une valeur"


def test_le_reste_du_env_ne_bouge_pas(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "# Les clés d'Atlas\n"
        "ATLAS_WEB_CLE=cle-de-la-page\n"
        "\n"
        "ATLAS_BONJOUR_NOM=Ancien\n"
        "une ligne que personne ne comprend\n"
        "export ATLAS_BONJOUR_NOM = Doublon\n"
        "# ATLAS_BONJOUR_CLE=exemple commenté\n"
        "ATLAS_AUTRE=1\n",
        encoding="utf-8",
    )
    ecrire_env(env, {"ATLAS_BONJOUR_NOM": "David", "ATLAS_BONJOUR_CLE": "sésame"})
    assert env.read_text(encoding="utf-8") == (
        "# Les clés d'Atlas\n"
        "ATLAS_WEB_CLE=cle-de-la-page\n"
        "\n"
        "ATLAS_BONJOUR_NOM=David\n"
        "une ligne que personne ne comprend\n"
        "# ATLAS_BONJOUR_CLE=exemple commenté\n"
        "ATLAS_AUTRE=1\n"
        "ATLAS_BONJOUR_CLE=sésame\n"
    )
    ecrire_env(env, {"ATLAS_BONJOUR_NOM": None})
    assert "ATLAS_BONJOUR_NOM" not in env.read_text(encoding="utf-8")
    assert "ATLAS_WEB_CLE=cle-de-la-page\n" in env.read_text(encoding="utf-8")


def test_une_retouche_a_la_main_entre_deux_enregistrements_reste(tmp_path):
    # Review Focus 2 : David modifie le .env pendant que le Core tourne.
    env = tmp_path / ".env"
    ecrire_env(env, {"ATLAS_BONJOUR_NOM": "David"})
    with env.open("a", encoding="utf-8") as fichier:
        fichier.write("ATLAS_AJOUTE_A_LA_MAIN=1\n")
    ecrire_env(env, {"ATLAS_BONJOUR_NOM": "Camille"})
    assert env.read_text(encoding="utf-8") == (
        "ATLAS_BONJOUR_NOM=Camille\nATLAS_AJOUTE_A_LA_MAIN=1\n"
    )


def test_un_env_en_lien_symbolique_garde_son_lien(tmp_path):
    # Review Focus 3 : un .env rangé ailleurs, et lié dans le dépôt.
    cible = tmp_path / "ailleurs" / "atlas.env"
    cible.parent.mkdir()
    cible.write_text("ATLAS_WEB_CLE=cle\n", encoding="utf-8")
    env = tmp_path / ".env"
    env.symlink_to(cible)
    ecrire_env(env, {"ATLAS_BONJOUR_NOM": "David"})
    assert env.is_symlink()
    assert cible.read_text(encoding="utf-8") == "ATLAS_WEB_CLE=cle\nATLAS_BONJOUR_NOM=David\n"


def test_un_env_absent_est_cree_lisible_par_david_seul(tmp_path):
    env = tmp_path / ".env"
    ecrire_env(env, {"ATLAS_BONJOUR_NOM": "David"})
    assert env.read_text(encoding="utf-8") == "ATLAS_BONJOUR_NOM=David\n"
    assert stat.S_IMODE(env.stat().st_mode) == 0o600
    env.chmod(0o644)  # comme le .env du M5 aujourd'hui
    voisin = tmp_path / ".env.tmp"
    voisin.write_text("laissé par un arrêt brutal\n")
    voisin.chmod(0o644)
    ecrire_env(env, {"ATLAS_BONJOUR_NOM": "Camille"})
    assert stat.S_IMODE(env.stat().st_mode) == 0o600
    assert env.read_text(encoding="utf-8") == "ATLAS_BONJOUR_NOM=Camille\n"
    assert [p.name for p in tmp_path.iterdir()] == [".env"], "aucun fichier voisin ne reste"


def test_une_ecriture_qui_echoue_ne_change_rien(tmp_path):
    env = tmp_path / ".env"
    env.write_text("ATLAS_BONJOUR_NOM=Ancien\n", encoding="utf-8")
    tmp_path.chmod(0o500)  # le dossier ne s'écrit plus
    try:
        with pytest.raises(ReglageRefuse, match="Le .env n'a pas pu s'écrire"):
            ecrire_env(env, {"ATLAS_BONJOUR_NOM": "David"})
    finally:
        tmp_path.chmod(0o755)
    assert env.read_text(encoding="utf-8") == "ATLAS_BONJOUR_NOM=Ancien\n"
    assert [p.name for p in tmp_path.iterdir()] == [".env"]


def test_un_env_illisible_est_un_refus(tmp_path):
    env = tmp_path / ".env"
    env.write_bytes("ATLAS_BONJOUR_NOM=Andr\xe9\n".encode("latin-1"))
    with pytest.raises(ReglageRefuse, match="Le .env ne se lit pas"):
        ecrire_env(env, {"ATLAS_BONJOUR_NOM": "David"})


def test_les_changements_permis_ecrivent_et_effacent():
    changements = changements_permis(
        manifeste(NOM, CLE), {"ATLAS_BONJOUR_NOM": "David"}, ["ATLAS_BONJOUR_CLE"]
    )
    assert changements == {"ATLAS_BONJOUR_NOM": "David", "ATLAS_BONJOUR_CLE": None}


@pytest.mark.parametrize(
    ("valeur", "raison"),
    [
        ("", "vide"),
        ("a\nb", "une seule ligne"),
        ("a\tb", "une seule ligne"),
        ("a\x00b", "une seule ligne"),
        (" David", "pas d'espace au début ni à la fin"),
        ("David ", "pas d'espace au début ni à la fin"),
        ("fin\\", "finir par une barre oblique inverse"),
        ("x" * 4097, "4096 caractères au plus"),
    ],
)
def test_une_valeur_qui_ne_convient_pas_est_refusee(valeur, raison):
    with pytest.raises(ReglageRefuse, match=re.escape(raison)):
        changements_permis(manifeste(NOM), {"ATLAS_BONJOUR_NOM": valeur}, [])


def test_seules_les_variables_declarees_par_le_connecteur():
    with pytest.raises(ReglageRefuse, match="ATLAS_AUTRE n'est pas un réglage de ce connecteur"):
        changements_permis(manifeste(NOM), {"ATLAS_AUTRE": "x"}, [])
    with pytest.raises(ReglageRefuse, match="ATLAS_AUTRE n'est pas un réglage de ce connecteur"):
        changements_permis(manifeste(NOM), {}, ["ATLAS_AUTRE"])
    with pytest.raises(ReglageRefuse, match="à la fois écrit et effacé"):
        changements_permis(manifeste(NOM), {"ATLAS_BONJOUR_NOM": "x"}, ["ATLAS_BONJOUR_NOM"])


def test_une_cle_d_atlas_est_refusee_quoi_que_dise_le_manifeste():
    # Un connecteur de la communauté qui déclarerait la clé de la page comme « réglage ».
    piege = Reglage(variable="ATLAS_WEB_CLE", description="Un réglage", secret=True)
    with pytest.raises(ReglageRefuse, match="ATLAS_WEB_CLE est une clé d'Atlas"):
        changements_permis(manifeste(piege), {"ATLAS_WEB_CLE": "prise"}, [])
    with pytest.raises(ReglageRefuse, match="ATLAS_WEB_CLE est une clé d'Atlas"):
        changements_permis(manifeste(piege), {}, ["ATLAS_WEB_CLE"])
    assert not modifiable("ATLAS_POSTE_CLE") and modifiable("ATLAS_BONJOUR_NOM")


def test_les_cles_d_atlas_sont_celles_que_lit_atlas():
    # Une variable lue par le Core, le client audio ou le poste s'ajoute à la liste, ou ce
    # test échoue : sinon, un manifeste pourrait la déclarer, et la page la réécrire.
    lues = {
        nom
        for chemin in SOURCES.rglob("*.py")
        if chemin.name != "reglages.py"
        for nom in re.findall(r'"(ATLAS_[A-Z0-9_]+)"', chemin.read_text(encoding="utf-8"))
    }
    assert lues == CLES_D_ATLAS - {"CLAUDE_CODE_OAUTH_TOKEN"}
    assert "CLAUDE_CODE_OAUTH_TOKEN" in CLES_D_ATLAS


def test_le_env_des_tests_n_est_jamais_celui_du_depot():
    assert reglages.FICHIER_ENV != reglages.DEPOT / ".env"
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `uv run pytest tests/test_reglages.py -q`
Expected: FAIL — erreur de collecte : `ImportError: cannot import name 'reglages' from 'atlas_core'`.

- [ ] **Step 3: Écrire les réglages**

Créer `src/atlas_core/reglages.py` :

```python
"""Les réglages des connecteurs, écrits dans le .env du Core depuis la page (spec des réglages
et du Core, §4).

Le .env est lu par `make` (`-include .env`, puis `export`) : une valeur y est écrite pour que
`make` la relise à l'identique. Seules s'y écrivent les variables déclarées par le connecteur,
jamais une clé d'Atlas, quoi que dise son manifeste ; le reste du fichier ne bouge pas.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Mapping
from pathlib import Path

from .connecteurs import Manifeste

DEPOT = Path(__file__).resolve().parents[2]
FICHIER_ENV = DEPOT / ".env"  # celui que lit `make run-core` ; les tests le remplacent
VALEUR_MAX = 4096

# Les variables qu'Atlas lit lui-même (le Core, le client audio, le poste), et le jeton de
# Claude : jamais écrites depuis la page. Un test la compare au code.
CLES_D_ATLAS = frozenset(
    {
        "CLAUDE_CODE_OAUTH_TOKEN",
        "ATLAS_AEC_BINAIRE",
        "ATLAS_AUDIO_CLE",
        "ATLAS_AUDIO_PERIPHERIQUE",
        "ATLAS_BARGEIN_DBFS",
        "ATLAS_BARGEIN_MS",
        "ATLAS_CERVEAU",
        "ATLAS_CERVEAU_MODELE",
        "ATLAS_CERVEAU_OUBLI_MIN",
        "ATLAS_CONNECTEURS_DOSSIER",
        "ATLAS_CORE_PORT",
        "ATLAS_CORE_URL",
        "ATLAS_MEMOIRE_DOSSIER",
        "ATLAS_MISSION_MIN",
        "ATLAS_MOT_REVEIL",
        "ATLAS_POSTE_CLE",
        "ATLAS_POSTE_URL",
        "ATLAS_RELANCE_S",
        "ATLAS_REVEILLEUR",
        "ATLAS_REVEIL_SEUIL",
        "ATLAS_SILENCE_MS",
        "ATLAS_STT_URL",
        "ATLAS_TTS_URL",
        "ATLAS_TTS_VOIX",
        "ATLAS_VAD_MODELE",
        "ATLAS_VOIX_BARGEIN_DBFS",
        "ATLAS_VOIX_MARGE_S",
        "ATLAS_WEB_CLE",
    }
)
# Une affectation de la variable, telle que `make` la lit (`=`, `:=`, `::=`, `?=`, `+=`).
_AFFECTATION = r"^\s*(?:export\s+)?{}\s*(?::{{1,2}}|\?|\+)?="


class ReglageRefuse(ValueError):
    """Un réglage que le Core n'écrit pas : la raison se lit telle quelle dans la page."""


def modifiable(variable: str) -> bool:
    """Faux pour une clé d'Atlas : elle se change au Terminal."""
    return variable not in CLES_D_ATLAS


def changements_permis(
    manifeste: Manifeste, valeurs: Mapping[str, str], effacer: Iterable[str]
) -> dict[str, str | None]:
    """Ce que la page demande pour ce connecteur, vérifié : variable → valeur à écrire, ou
    None pour la retirer. `ReglageRefuse` au moindre écart : rien ne s'écrit alors."""
    effacer = list(effacer)
    declarees = {r.variable for r in manifeste.reglages}
    for variable in [*valeurs, *effacer]:
        if variable not in declarees:
            raise ReglageRefuse(f"{variable} n'est pas un réglage de ce connecteur.")
        if not modifiable(variable):
            raise ReglageRefuse(f"{variable} est une clé d'Atlas : elle se change au Terminal.")
    changements: dict[str, str | None] = {}
    for variable, valeur in valeurs.items():
        _verifier(variable, valeur)
        changements[variable] = valeur
    for variable in effacer:
        if variable in changements:
            raise ReglageRefuse(f"{variable} : à la fois écrit et effacé.")
        changements[variable] = None
    return changements


def _verifier(variable: str, valeur: str) -> None:
    if not valeur:
        raise ReglageRefuse(f"{variable} : une valeur vide ; « Effacer » le retire.")
    if len(valeur) > VALEUR_MAX:
        raise ReglageRefuse(f"{variable} : {VALEUR_MAX} caractères au plus.")
    if re.search(r"[\x00-\x1f\x7f]", valeur):
        raise ReglageRefuse(f"{variable} : une seule ligne, sans caractère de contrôle.")
    if valeur != valeur.strip():
        raise ReglageRefuse(f"{variable} : pas d'espace au début ni à la fin.")
    if valeur.endswith("\\"):
        # `make` y verrait une ligne qui continue sur la suivante.
        raise ReglageRefuse(f"{variable} : ne peut pas finir par une barre oblique inverse.")


def pour_make(valeur: str) -> str:
    """La valeur telle que `make` la relira à l'identique : `$` doublé, `#` protégé, et les
    barres obliques inverses qui le précèdent doublées."""
    valeur = valeur.replace("$", "$$")
    return re.sub(r"(\\*)#", lambda m: m.group(1) * 2 + "\\#", valeur)


def ecrire_env(fichier: Path, changements: Mapping[str, str | None]) -> None:
    """Remplace la ligne de chaque variable (retire ses doublons), l'ajoute à la fin, ou la
    retire (None), sans toucher au reste. L'écriture est atomique, et le fichier finit
    lisible par David seul. `ReglageRefuse` si elle échoue : rien n'a changé. Un .env en
    lien symbolique garde son lien : c'est sa cible qui s'écrit."""
    fichier = fichier.resolve()
    try:
        texte = fichier.read_text(encoding="utf-8") if fichier.exists() else ""
    except (OSError, UnicodeDecodeError) as e:
        raise ReglageRefuse(f"Le .env ne se lit pas : {type(e).__name__}.") from e
    lignes = texte.splitlines()
    for variable, valeur in changements.items():
        motif = re.compile(_AFFECTATION.format(re.escape(variable)))
        nouvelle = None if valeur is None else f"{variable}={pour_make(valeur)}"
        suite: list[str] = []
        for ligne in lignes:
            if not motif.match(ligne):
                suite.append(ligne)
            elif nouvelle is not None:
                suite.append(nouvelle)  # à la place de la première ; les doublons partent
                nouvelle = None
        if nouvelle is not None:
            suite.append(nouvelle)
        lignes = suite
    temporaire = fichier.with_name(fichier.name + ".tmp")
    try:
        descripteur = os.open(temporaire, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descripteur, "w", encoding="utf-8") as sortie:
            sortie.write("".join(f"{ligne}\n" for ligne in lignes))
        os.chmod(temporaire, 0o600)
        os.replace(temporaire, fichier)
    except OSError as e:
        try:
            temporaire.unlink(missing_ok=True)
        except OSError:
            pass
        raise ReglageRefuse(f"Le .env n'a pas pu s'écrire : {e.strerror or e}.") from e
```

- [ ] **Step 4: Vérifier que tout passe**

Run: `uv run pytest -q && uv run ruff check . --extend-exclude spikes && uv run ruff format --check . --extend-exclude spikes && node --test "tests/web/*.test.mjs"`
Expected: 1236 tests Python passent (3 de moins, et 3 ignorés, si `models/silero_vad.onnx` manque, comme dans une copie neuve), 150 tests JavaScript passent, ruff ne dit rien.

- [ ] **Step 5: Commit**

```bash
git add src/atlas_core/reglages.py tests/conftest.py tests/test_reglages.py
git commit -F - <<'MSG'
Réglages : le .env écrit pour make, jamais une clé d'Atlas

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

### Task 2: Un réglage prend effet tout de suite

`OutilsMemoire.regler` écrit les réglages d'un connecteur et les applique aussitôt : le Core prend la valeur dans
son environnement ; un connecteur « à configurer » devient activable ; un connecteur actif se recharge avec ses
nouveaux réglages (coupé puis réactivé : son interrupteur reste ; s'il ne se recharge pas, « en erreur ») ; un
nouveau secret rejoint ceux que la mémoire refuse d'écrire.

**Files:**
- Modify: `src/atlas_core/memoire.py`
- Modify: `src/atlas_core/outils_memoire.py`
- Modify: `src/atlas_core/registre.py`
- Create: `tests/test_outils_reglages.py`

**Interfaces:**
- Consumes: Task 1 (`ReglageRefuse`, `changements_permis`, `ecrire_env`) ; `Registre.decouvrir`, `basculer`,
  `actifs` ; `Memoire`.
- Produces: `Registre.environ -> MutableMapping[str, str]` (le paramètre `environ` devient un `MutableMapping`) ;
  `Memoire.ajouter_secrets(secrets: Iterable[str])` ; `OutilsMemoire(..., fichier_env: Path | None = None)` ;
  `OutilsMemoire.regler(id_: str, valeurs: Mapping[str, str], effacer: Iterable[str]) -> bool` (vrai : un
  connecteur actif rechargé, la conversation doit se renouveler ; `ReglageRefuse` sinon, rien n'a changé).

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/test_outils_reglages.py` :

```python
"""Un réglage saisi dans la page prend effet tout de suite : écrit dans le .env, pris par le
Core, et un connecteur actif rechargé avec lui, comme après une bascule."""

import json

import pytest
from test_registre import MANIFESTE, code, deposer

from atlas_core.memoire import ErreurMemoire, Memoire
from atlas_core.outils_memoire import OutilsMemoire
from atlas_core.registre import Registre, fichier_des_interrupteurs
from atlas_core.reglages import ReglageRefuse

ORDINAIRE = """
[[reglages]]
variable = "ATLAS_BONJOUR_NOM"
description = "Le nom à saluer"
"""
SECRET = """
[[reglages]]
variable = "ATLAS_BONJOUR_CLE"
description = "La clé du service"
secret = true
"""
# Le connecteur ne se charge pas avec le nom « Boum ».
CAPRICIEUX = code().replace(
    "def creer(contexte):\n",
    "def creer(contexte):\n"
    "    if contexte.reglages['ATLAS_BONJOUR_NOM'] == 'Boum':\n"
    "        raise RuntimeError('boum')\n",
)


@pytest.fixture
def perso(tmp_path):
    return tmp_path / "connecteurs"


@pytest.fixture
def env(tmp_path):
    return tmp_path / ".env"


def outils_de(tmp_path, perso, env, environ) -> OutilsMemoire:
    registre = Registre(tmp_path / "officiels", perso, environ=environ)
    memoire = Memoire.ouvrir(tmp_path / "memoire")
    return OutilsMemoire(memoire, registre=registre, fichier_env=env)


def etat(outils, id_="salut"):
    return next(f for f in outils.registre.decouvrir() if f.id == id_)


async def dire(outils) -> str:
    outil = next(o for o in outils.outils if o.name == "salut_dire")
    return (await outil.handler({}))["content"][0]["text"]


def test_un_reglage_rend_un_connecteur_activable_aussitot(tmp_path, perso, env):
    deposer(perso, "salut", MANIFESTE.format(nom="Salut") + ORDINAIRE)
    environ: dict[str, str] = {}
    outils = outils_de(tmp_path, perso, env, environ)
    assert etat(outils).etat == "a_configurer"
    assert outils.regler("salut", {"ATLAS_BONJOUR_NOM": "David"}, []) is False
    assert env.read_text(encoding="utf-8") == "ATLAS_BONJOUR_NOM=David\n"
    assert environ == {"ATLAS_BONJOUR_NOM": "David"}
    assert (etat(outils).etat, etat(outils).en_attente) == ("coupe", False)


async def test_un_connecteur_actif_se_recharge_avec_ses_nouveaux_reglages(tmp_path, perso, env):
    deposer(perso, "salut", MANIFESTE.format(nom="Salut") + ORDINAIRE)
    outils = outils_de(tmp_path, perso, env, {"ATLAS_BONJOUR_NOM": "David"})
    outils.basculer("salut", True)
    outils.registre.appliquer()
    assert await dire(outils) == "Bonjour David."
    assert outils.regler("salut", {"ATLAS_BONJOUR_NOM": "Camille"}, []) is True
    assert await dire(outils) == "Bonjour Camille."
    assert (etat(outils).etat, etat(outils).en_attente) == ("actif", True)
    interrupteurs = json.loads(fichier_des_interrupteurs(perso).read_text())
    assert interrupteurs == {"actifs": ["communaute:salut"]}, "son interrupteur ne change pas"


def test_effacer_le_reglage_d_un_connecteur_actif_le_coupe(tmp_path, perso, env):
    deposer(perso, "salut", MANIFESTE.format(nom="Salut") + ORDINAIRE)
    environ = {"ATLAS_BONJOUR_NOM": "David"}
    outils = outils_de(tmp_path, perso, env, environ)
    outils.basculer("salut", True)
    assert outils.regler("salut", {}, ["ATLAS_BONJOUR_NOM"]) is True
    assert environ == {} and outils.connecteurs == []
    assert "mcp__atlas__salut_dire" not in outils.noms
    assert etat(outils).etat == "a_configurer"


def test_un_connecteur_actif_qui_ne_se_recharge_plus_passe_en_erreur(tmp_path, perso, env):
    deposer(perso, "salut", MANIFESTE.format(nom="Salut") + ORDINAIRE, source=CAPRICIEUX)
    outils = outils_de(tmp_path, perso, env, {"ATLAS_BONJOUR_NOM": "David"})
    outils.basculer("salut", True)
    assert outils.regler("salut", {"ATLAS_BONJOUR_NOM": "Boum"}, []) is True
    assert (etat(outils).etat, etat(outils).detail) == ("en_erreur", "RuntimeError : boum")
    assert outils.connecteurs == []


def test_un_nouveau_secret_est_refuse_par_la_memoire(tmp_path, perso, env):
    deposer(perso, "salut", MANIFESTE.format(nom="Salut") + ORDINAIRE + SECRET)
    outils = outils_de(tmp_path, perso, env, {})
    valeurs = {"ATLAS_BONJOUR_CLE": "sesame-assez-long", "ATLAS_BONJOUR_NOM": "Léa-Marie Dupont"}
    outils.regler("salut", valeurs, [])
    with pytest.raises(ErreurMemoire, match="mot de passe"):
        outils.memoire.ecrire("profil.md", "# Profil\n\nDavid.\n\nSa clé : sesame-assez-long\n")
    # Un réglage ordinaire n'est pas un secret ; un secret trop court ne se cherche pas.
    outils.memoire.ecrire("profil.md", "# Profil\n\nDavid.\n\nIl salue Léa-Marie Dupont.\n")
    outils.regler("salut", {"ATLAS_BONJOUR_CLE": "court"}, [])
    outils.memoire.ecrire("profil.md", "# Profil\n\nDavid.\n\nUn court séjour.\n")


def test_un_refus_ne_change_rien(tmp_path, perso, env):
    deposer(perso, "salut", MANIFESTE.format(nom="Salut") + ORDINAIRE)
    environ: dict[str, str] = {}
    outils = outils_de(tmp_path, perso, env, environ)
    with pytest.raises(ReglageRefuse, match="ATLAS_AUTRE n'est pas un réglage de ce connecteur"):
        outils.regler("salut", {"ATLAS_BONJOUR_NOM": "David", "ATLAS_AUTRE": "x"}, [])
    assert not env.exists() and environ == {}
    with pytest.raises(ReglageRefuse, match="Ce connecteur n'a pas de réglages"):
        outils.regler("inconnu", {"ATLAS_BONJOUR_NOM": "David"}, [])
    (perso / "casse").mkdir()  # sans manifeste
    with pytest.raises(ReglageRefuse, match="Ce connecteur n'a pas de réglages"):
        outils.regler("casse", {}, [])


def test_sans_env_ni_registre_pas_de_reglages(tmp_path, perso):
    deposer(perso, "salut", MANIFESTE.format(nom="Salut") + ORDINAIRE)
    registre = Registre(tmp_path / "officiels", perso, environ={})
    sans_env = OutilsMemoire(Memoire.ouvrir(tmp_path / "memoire"), registre=registre)
    sans_registre = OutilsMemoire(Memoire.ouvrir(tmp_path / "m2"), fichier_env=tmp_path / ".env")
    for outils in (sans_env, sans_registre):
        with pytest.raises(ReglageRefuse, match="Les réglages ne s'écrivent pas ici"):
            outils.regler("salut", {"ATLAS_BONJOUR_NOM": "David"}, [])
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `uv run pytest tests/test_outils_reglages.py -q`
Expected: FAIL — `7 failed` : `TypeError: OutilsMemoire.__init__() got an unexpected keyword argument
'fichier_env'`.

- [ ] **Step 3: Écrire l'effet immédiat**

Modifier `src/atlas_core/memoire.py` :

```diff
--- a/src/atlas_core/memoire.py
+++ b/src/atlas_core/memoire.py
@@ -207,6 +207,10 @@ class Memoire:
         self._secrets = [s for s in secrets if len(s) >= SECRET_MIN]
         self._verrou = threading.Lock()  # une écriture à la fois
 
+    def ajouter_secrets(self, secrets: Iterable[str]) -> None:
+        """Un réglage secret saisi dans la page : refusé dès maintenant, lui aussi."""
+        self._secrets.extend(s for s in secrets if len(s) >= SECRET_MIN)
+
     @classmethod
     def ouvrir(cls, racine: Path, secrets: Iterable[str] = ()) -> Memoire | None:
         """Crée le dossier et son dépôt au besoin. None si c'est impossible (git absent,
```

Modifier `src/atlas_core/outils_memoire.py` :

```diff
--- a/src/atlas_core/outils_memoire.py
+++ b/src/atlas_core/outils_memoire.py
@@ -10,7 +10,8 @@ from __future__ import annotations
 
 import asyncio
 import logging
-from collections.abc import Callable
+from collections.abc import Callable, Iterable, Mapping
+from pathlib import Path
 from typing import Any
 
 from .confirmation import Confirmations, Suppression
@@ -19,6 +20,7 @@ from .missions import Missions
 from .outils import Fait, Niveau, Outil, ServeurAtlas
 from .outils_documents import outils_des_documents
 from .registre import ConnecteurActif, Registre
+from .reglages import ReglageRefuse, changements_permis, ecrire_env
 
 _journal = logging.getLogger(__name__)
 
@@ -78,7 +80,8 @@ class OutilsMemoire(ServeurAtlas):
     """Le serveur « atlas » : le socle (la mémoire et les documents), et les outils des
     connecteurs actifs du `registre`. `sur_documents` prévient les pages quand un document
     change, `sur_connecteurs` quand des bascules ont pris effet ; `confirmations` tient
-    l'action qui attend le « oui » ; `missions`, la mission en cours sur le Mac."""
+    l'action qui attend le « oui » ; `missions`, la mission en cours sur le Mac ;
+    `fichier_env`, le .env où s'écrivent les réglages des connecteurs saisis dans la page."""
 
     def __init__(
         self,
@@ -88,8 +91,10 @@ class OutilsMemoire(ServeurAtlas):
         missions: Missions | None = None,
         registre: Registre | None = None,
         sur_connecteurs: Callable[[], None] | None = None,
+        fichier_env: Path | None = None,
     ) -> None:
         self.memoire = memoire
+        self.fichier_env = fichier_env
         self.sur_documents = sur_documents or (lambda: None)
         self.sur_connecteurs = sur_connecteurs or (lambda: None)
         self.missions = missions or Missions()
@@ -132,6 +137,33 @@ class OutilsMemoire(ServeurAtlas):
         self._installer(self._tous())
         return True
 
+    def regler(self, id_: str, valeurs: Mapping[str, str], effacer: Iterable[str]) -> bool:
+        """Écrit des réglages d'un connecteur dans le .env et les applique aussitôt : un
+        connecteur actif se recharge avec eux, comme après deux bascules (rend vrai : la
+        conversation se renouvelle). `ReglageRefuse` si rien ne convient : rien n'a changé."""
+        if self.registre is None or self.fichier_env is None:
+            raise ReglageRefuse("Les réglages ne s'écrivent pas ici.")
+        fiche = next((f for f in self.registre.decouvrir() if f.id == id_), None)
+        if fiche is None or fiche.manifeste is None:
+            raise ReglageRefuse("Ce connecteur n'a pas de réglages.")
+        changements = changements_permis(fiche.manifeste, valeurs, effacer)
+        ecrire_env(self.fichier_env, changements)
+        environ = self.registre.environ
+        for variable, valeur in changements.items():
+            if valeur is None:
+                environ.pop(variable, None)
+            else:
+                environ[variable] = valeur
+        secrets = {r.variable for r in fiche.manifeste.reglages if r.secret}
+        self.memoire.ajouter_secrets(v for k, v in changements.items() if v and k in secrets)
+        if fiche.etat != "actif":
+            return False
+        self.registre.basculer(id_, False)
+        self.registre.basculer(id_, True)  # s'il ne se recharge pas : « en erreur »
+        self.connecteurs = self.registre.actifs()
+        self._installer(self._tous())
+        return True
+
     def fin_du_tour(self, arretee: bool = False) -> None:
         """La réponse est finie : une mission ne lui survit pas. `arretee` : la réponse a été
         coupée (David a parlé, ou touché « Stop »)."""
```

Modifier `src/atlas_core/registre.py` :

```diff
--- a/src/atlas_core/registre.py
+++ b/src/atlas_core/registre.py
@@ -26,7 +26,7 @@ import subprocess
 import sys
 import tempfile
 import types
-from collections.abc import Callable, Iterable, Mapping
+from collections.abc import Callable, Iterable, MutableMapping
 from dataclasses import dataclass, field
 from pathlib import Path
 from typing import TYPE_CHECKING, Literal
@@ -126,7 +126,7 @@ class Registre:
         officiels: Path,
         perso: Path,
         *,
-        environ: Mapping[str, str] | None = None,
+        environ: MutableMapping[str, str] | None = None,
         poste: Poste | None = None,
         missions: Missions | None = None,
         installe: Callable[[str], bool] = _installe,
@@ -141,6 +141,11 @@ class Registre:
         self._en_attente: set[str] = set()
         self._fiches: list[Fiche] = []
 
+    @property
+    def environ(self) -> MutableMapping[str, str]:
+        """Où se lisent les réglages des connecteurs : l'environnement du Core."""
+        return self._environ
+
     def reserver(self, noms: Iterable[str]) -> None:
         """Les noms des outils du socle, qu'aucun connecteur ne peut prendre."""
         self._reserves |= set(noms)
```

- [ ] **Step 4: Vérifier que tout passe**

Run: `uv run pytest -q && uv run ruff check . --extend-exclude spikes && uv run ruff format --check . --extend-exclude spikes && node --test "tests/web/*.test.mjs"`
Expected: 1243 tests Python passent (3 de moins, et 3 ignorés, si `models/silero_vad.onnx` manque, comme dans une copie neuve), 150 tests JavaScript passent, ruff ne dit rien.

- [ ] **Step 5: Commit**

```bash
git add src/atlas_core/memoire.py src/atlas_core/outils_memoire.py src/atlas_core/registre.py tests/test_outils_reglages.py
git commit -F - <<'MSG'
Réglages : un réglage prend effet tout de suite

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

### Task 3: Les messages des réglages

La page reçoit les réglages de chaque connecteur dans `liste_connecteurs` (jamais la valeur d'un secret ni d'une
clé d'Atlas) et envoie `regler_connecteur` ; le Core répond `resultat_reglage` à la page qui a demandé, publie la
liste à toutes, et renouvelle la conversation si un connecteur actif s'est rechargé. Le routage des messages de la
page sort de `hub.py` (`routage_pages.py`).

**Files:**
- Modify: `src/atlas_core/hub.py`
- Modify: `src/atlas_core/pages.py`
- Modify: `src/atlas_core/protocole_web.py`
- Create: `src/atlas_core/routage_pages.py`
- Modify: `tests/test_hub_web.py`
- Modify: `tests/test_protocole_web.py`

**Interfaces:**
- Consumes: Task 1 (`modifiable`, `FICHIER_ENV`), Task 2 (`OutilsMemoire.regler`, `Registre.environ`).
- Produces: `protocole_web` : `ReglageConnecteur(variable, description, secret=False, defini=False,
  modifiable=True, valeur="")`, `FicheConnecteur.reglages`, `ResultatReglage(id, ok, message)`,
  `ReglerConnecteur(id, valeurs={}, effacer=[])`, `REGLAGES_MAX = 50` ; `atlas_core.routage_pages` :
  `Contexte(regie, outils, cerveau, abonnement, page)`, `async traiter(msg, ctx)`, `ENREGISTRE`, `SANS_MEMOIRE` ;
  `hub.ouvrir_la_memoire` passe `fichier_env=reglages.FICHIER_ENV`.

- [ ] **Step 1: Écrire les tests qui échouent**

Modifier `tests/test_hub_web.py` :

```diff
--- a/tests/test_hub_web.py
+++ b/tests/test_hub_web.py
@@ -1,11 +1,13 @@
+import json
 import re
 from dataclasses import replace
 
 import pytest
 from fastapi.testclient import TestClient
 from starlette.websockets import WebSocketDisconnect
+from test_registre import deposer
 
-from atlas_core import hub
+from atlas_core import hub, reglages
 from atlas_core.diffuseur import Diffuseur
 from atlas_core.protocole import Bonjour
 
@@ -175,7 +177,19 @@ def test_une_page_liste_les_connecteurs_meme_casses(connecteurs):
         "etat": "en_erreur",
         "detail": "connecteur.toml absent",
         "en_attente": False,
+        "reglages": [],
     }
+    assert poste["reglages"] == [
+        {
+            "variable": "ATLAS_POSTE_CLE",
+            "description": "La clé du poste : la même dans le .env du Core et dans celui du "
+            "Mac qui lance make run-poste",
+            "secret": True,
+            "defini": True,
+            "modifiable": False,
+            "valeur": "",
+        }
+    ]
 
 
 def test_la_liste_demandee_ne_va_qu_a_la_page_qui_la_demande(connecteurs):
@@ -234,6 +248,111 @@ def test_la_note_d_attente_tient_jusqu_a_la_question_suivante(connecteurs):
         assert (fiche["etat"], fiche["en_attente"]) == ("actif", True)
 
 
+BONJOUR = """nom = "Bonjour"
+description = "Atlas te salue."
+version = "0.1"
+auteur = "Quelqu'un"
+api = 1
+
+[[reglages]]
+variable = "ATLAS_BONJOUR_NOM"
+description = "Le nom à saluer"
+
+[[reglages]]
+variable = "ATLAS_BONJOUR_CLE"
+description = "La clé du service"
+secret = true
+
+[[reglages]]
+variable = "ATLAS_AUDIO_CLE"
+description = "Une clé d'Atlas déclarée comme un réglage ordinaire"
+"""
+SECRET = "sesame-de-test-bien-long"
+
+
+def bonjour(liste: dict) -> dict:
+    return next(f for f in liste["connecteurs"] if f["id"] == "bonjour")  # après le poste
+
+
+@pytest.fixture
+def reglables(memoire, monkeypatch, tmp_path):
+    dossier = tmp_path / "connecteurs"
+    deposer(dossier, "bonjour", BONJOUR)
+    monkeypatch.setattr(hub, "_config", replace(hub._config, connecteurs_dossier=dossier))
+    for variable in ("ATLAS_BONJOUR_NOM", "ATLAS_BONJOUR_CLE"):
+        monkeypatch.setenv(variable, "")  # rendue telle qu'avant le test, quoi qu'il écrive
+        monkeypatch.delenv(variable)
+    monkeypatch.setenv("ATLAS_AUDIO_CLE", "cle-audio-de-test")
+
+
+def test_une_page_regle_un_connecteur_et_toutes_les_pages_le_voient(reglables, caplog):
+    with (
+        TestClient(hub.app) as client,
+        client.websocket_connect("/ws/web", headers=ORIGINE) as ws,
+        client.websocket_connect("/ws/web", headers=ORIGINE) as autre,
+    ):
+        _entrer(ws)
+        _entrer(autre)
+        valeurs = {"ATLAS_BONJOUR_NOM": "David", "ATLAS_BONJOUR_CLE": SECRET}
+        ws.send_json({"type": "regler_connecteur", "id": "bonjour", "valeurs": valeurs})
+        recus = [ws.receive_text(), ws.receive_text(), autre.receive_text()]
+    resultat, liste, vue_par_l_autre = (json.loads(r) for r in recus)
+    assert resultat == {"type": "resultat_reglage", "id": "bonjour", "ok": True,
+                        "message": "Enregistré."}  # fmt: skip
+    assert liste == vue_par_l_autre
+    fiche = bonjour(liste)
+    assert fiche["etat"] == "coupe"
+    nom, cle, audio = fiche["reglages"]
+    assert (nom["defini"], nom["valeur"], nom["modifiable"]) == (True, "David", True)
+    assert (cle["defini"], cle["valeur"], cle["secret"]) == (True, "", True)
+    assert (audio["defini"], audio["valeur"], audio["modifiable"]) == (True, "", False)
+    ecrit = reglages.FICHIER_ENV.read_text(encoding="utf-8")
+    assert ecrit == f"ATLAS_BONJOUR_NOM=David\nATLAS_BONJOUR_CLE={SECRET}\n"
+    assert not any(SECRET in r or "cle-audio-de-test" in r for r in recus)
+    assert SECRET not in caplog.text
+
+
+def test_un_reglage_refuse_ne_va_qu_a_la_page_qui_l_a_saisi(reglables):
+    with (
+        TestClient(hub.app) as client,
+        client.websocket_connect("/ws/web", headers=ORIGINE) as ws,
+        client.websocket_connect("/ws/web", headers=ORIGINE) as autre,
+    ):
+        _entrer(ws)
+        _entrer(autre)
+        ws.send_json({"type": "connecteurs"})
+        nom, cle, _ = bonjour(ws.receive_json())["reglages"]
+        assert (nom["defini"], nom["valeur"], cle["defini"]) == (False, "", False)
+        valeurs = {"ATLAS_AUDIO_CLE": "prise"}
+        ws.send_json({"type": "regler_connecteur", "id": "bonjour", "valeurs": valeurs})
+        assert ws.receive_json() == {
+            "type": "resultat_reglage",
+            "id": "bonjour",
+            "ok": False,
+            "message": "ATLAS_AUDIO_CLE est une clé d'Atlas : elle se change au Terminal.",
+        }
+        autre.send_json({"type": "saisie", "texte": ""})  # sa réponse suit tout ce qu'elle a reçu
+        assert autre.receive_json()["type"] == "erreur"
+    assert not reglages.FICHIER_ENV.exists()
+
+
+def test_regler_un_connecteur_actif_renouvelle_la_conversation(reglables, monkeypatch):
+    monkeypatch.setenv("ATLAS_BONJOUR_NOM", "David")
+    monkeypatch.setenv("ATLAS_BONJOUR_CLE", SECRET)
+    with TestClient(hub.app) as client, client.websocket_connect("/ws/web", headers=ORIGINE) as ws:
+        _entrer(ws)
+        renouvellements: list[bool] = []
+        monkeypatch.setattr(hub._cerveau, "renouveler", lambda: renouvellements.append(True))
+        ws.send_json({"type": "activer_connecteur", "id": "bonjour", "actif": True})
+        ws.receive_json()
+        valeurs = {"ATLAS_BONJOUR_NOM": "Camille"}
+        ws.send_json({"type": "regler_connecteur", "id": "bonjour", "valeurs": valeurs})
+        assert ws.receive_json()["ok"] is True
+        fiche = bonjour(ws.receive_json())
+    assert (fiche["etat"], fiche["en_attente"]) == ("actif", True)
+    assert renouvellements == [True, True]
+
+
 def test_sans_memoire_pas_de_connecteurs(regie, monkeypatch):
     monkeypatch.setattr(hub, "_config", replace(hub._config, web_cle=CLE, cerveau="bouchon"))
     with TestClient(hub.app) as client, client.websocket_connect("/ws/web", headers=ORIGINE) as ws:
@@ -242,7 +361,14 @@ def test_sans_memoire_pas_de_connecteurs(regie, monkeypatch):
         liste = ws.receive_json()
         ws.send_json({"type": "activer_connecteur", "id": "poste", "actif": True})
         apres = ws.receive_json()
+        valeurs = {"ATLAS_POSTE_CLE": "x"}
+        ws.send_json({"type": "regler_connecteur", "id": "poste", "valeurs": valeurs})
+        refus = ws.receive_json()
     assert liste == apres == {"type": "liste_connecteurs", "disponible": False, "connecteurs": []}
+    assert (refus["ok"], refus["message"]) == (
+        False,
+        "La mémoire n'est pas disponible : pas de connecteurs.",
+    )
 
 
 class _Attente:
```

Modifier `tests/test_protocole_web.py` :

```diff
--- a/tests/test_protocole_web.py
+++ b/tests/test_protocole_web.py
@@ -27,6 +27,9 @@ from atlas_core.protocole_web import (
     MissionEnCours,
     Muet,
     Niveau,
+    ReglageConnecteur,
+    ReglerConnecteur,
+    ResultatReglage,
     ResumeDocument,
     Saisie,
     decoder_message_page,
@@ -196,6 +199,7 @@ def test_une_page_demande_les_connecteurs_et_en_bascule_un():
                 "etat": "coupe",
                 "detail": "",
                 "en_attente": False,
+                "reglages": [],
             }
         ],
     }
@@ -205,3 +209,50 @@ def test_une_page_demande_les_connecteurs_et_en_bascule_un():
 def test_une_page_ne_nomme_qu_un_identifiant_de_connecteur(id_):
     with pytest.raises(ValueError):
         decoder_message_page(json.dumps({"type": "activer_connecteur", "id": id_, "actif": True}))
+
+
+def test_une_page_regle_un_connecteur():
+    brut = json.dumps(
+        {
+            "type": "regler_connecteur",
+            "id": "bonjour",
+            "valeurs": {"ATLAS_BONJOUR_NOM": "David"},
+            "effacer": ["ATLAS_BONJOUR_CLE"],
+        }
+    )
+    assert decoder_message_page(brut) == ReglerConnecteur(
+        id="bonjour", valeurs={"ATLAS_BONJOUR_NOM": "David"}, effacer=["ATLAS_BONJOUR_CLE"]
+    )
+    assert decoder_message_page('{"type":"regler_connecteur","id":"bonjour"}') == (
+        ReglerConnecteur(id="bonjour")
+    )
+    reglage = ReglageConnecteur(variable="ATLAS_BONJOUR_CLE", description="La clé", secret=True)
+    assert reglage.model_dump() == {
+        "variable": "ATLAS_BONJOUR_CLE",
+        "description": "La clé",
+        "secret": True,
+        "defini": False,
+        "modifiable": True,
+        "valeur": "",
+    }
+    assert ResultatReglage(id="bonjour", ok=True, message="Enregistré.").model_dump() == {
+        "type": "resultat_reglage",
+        "id": "bonjour",
+        "ok": True,
+        "message": "Enregistré.",
+    }
+
+
+@pytest.mark.parametrize(
+    "message",
+    [
+        {"id": "../memoire", "valeurs": {"ATLAS_BONJOUR_NOM": "x"}},
+        {"id": "bonjour", "valeurs": {"PATH": "/tmp"}},
+        {"id": "bonjour", "valeurs": {"ATLAS_BONJOUR_NOM": 42}},
+        {"id": "bonjour", "effacer": ["HOME"]},
+        {"id": "bonjour", "valeurs": {f"ATLAS_V{i}": "x" for i in range(51)}},
+    ],
+)
+def test_un_reglage_ne_nomme_qu_une_variable_d_atlas(message):
+    with pytest.raises(ValueError):
+        decoder_message_page(json.dumps({"type": "regler_connecteur", **message}))
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `uv run pytest tests/test_protocole_web.py tests/test_hub_web.py -q`
Expected: FAIL — erreur de collecte : `ImportError: cannot import name 'ReglageConnecteur' from
'atlas_core.protocole_web'`.

- [ ] **Step 3: Écrire les messages et le routage**

Modifier `src/atlas_core/hub.py` :

```diff
--- a/src/atlas_core/hub.py
+++ b/src/atlas_core/hub.py
@@ -18,6 +18,7 @@ from fastapi.staticfiles import StaticFiles
 from atlas_audio.client import lire_reglages
 from atlas_audio.connexion import PeripheriqueEnPanne
 
+from . import reglages
 from .cerveau import Cerveau, CerveauBouchon
 from .cerveau_claude import CerveauClaude
 from .config import Config
@@ -27,7 +28,7 @@ from .memoire import Memoire
 from .missions import Missions
 from .options_claude import options_cerveau, purger_cles_api
 from .outils_memoire import OutilsMemoire
-from .pages import lire_document, liste_connecteurs, liste_documents
+from .pages import liste_connecteurs
 from .poste import Poste, servir_poste
 from .protocole import Bonjour, Erreur, decoder_audio_entrant, decoder_message
 from .protocole_voix import (
@@ -40,24 +41,17 @@ from .protocole_voix import (
     verifier_bloc_page,
 )
 from .protocole_web import (
-    ActiverConnecteur,
-    Arreter,
     AttenteConfirmation,
     Authentification,
-    Confirmer,
-    DemandeConnecteurs,
-    DemandeDocuments,
     DocumentsChanges,
     FinConfirmation,
     FinMission,
-    LireDocument,
     MissionEnCours,
-    Muet,
-    Saisie,
     decoder_message_page,
 )
 from .regie import Regie
 from .registre import OFFICIELS, Registre
+from .routage_pages import Contexte, traiter
 from .session import Session, sans_destinataire
 from .synthese import ClientSynthese
 from .transcription import ClientTranscription
@@ -131,6 +125,7 @@ def ouvrir_la_memoire(config: Config) -> OutilsMemoire | None:
         lambda: publier(DocumentsChanges()),
         missions=missions,
         registre=registre,
+        fichier_env=reglages.FICHIER_ENV,  # lu ici : les tests le remplacent
     )
     outils.sur_connecteurs = lambda: publier(liste_connecteurs(outils))
     return outils
@@ -344,29 +339,7 @@ async def ws_web(ws: WebSocket) -> None:
             except ValueError as e:
                 abonnement.envoyer_prive(Erreur(code="message_invalide", message=str(e)))
                 continue
-            if isinstance(msg, Saisie):
-                await _regie.saisie(msg.texte, demande.page)
-            elif isinstance(msg, Muet):
-                await _regie.basculer_muet(msg.actif)
-            elif isinstance(msg, DemandeDocuments):
-                abonnement.envoyer_prive(await liste_documents(_outils))
-            elif isinstance(msg, LireDocument):
-                abonnement.envoyer_prive(await lire_document(_outils, msg.chemin))
-            elif isinstance(msg, Confirmer):
-                # Comme taper « oui » ou « non » depuis cette page ; trop tard, rien.
-                if _outils is not None and _outils.confirmations.en_attente:
-                    await _regie.saisie("oui" if msg.oui else "non", demande.page)
-            elif isinstance(msg, Arreter):
-                # Comme taper « stop » depuis cette page ; la mission déjà finie, rien.
-                if _outils is not None and _outils.missions.en_cours is not None:
-                    await _regie.saisie("stop", demande.page)
-            elif isinstance(msg, DemandeConnecteurs):
-                abonnement.envoyer_prive(liste_connecteurs(_outils))
-            elif isinstance(msg, ActiverConnecteur):
-                # La conversation se clôt ; la suivante porte les connecteurs actifs.
-                if _outils is not None and _outils.basculer(msg.id, msg.actif):
-                    _cerveau.renouveler()
-                _regie.diffuseur.publier(liste_connecteurs(_outils))  # toutes les pages
+            await traiter(msg, Contexte(_regie, _outils, _cerveau, abonnement, demande.page))
     except WebSocketDisconnect:
         pass
     finally:
```

Modifier `src/atlas_core/pages.py` :

```diff
--- a/src/atlas_core/pages.py
+++ b/src/atlas_core/pages.py
@@ -4,6 +4,7 @@ document (spec 2c, §7), et la liste des connecteurs (spec des connecteurs, §6)
 from __future__ import annotations
 
 import asyncio
+from collections.abc import Mapping
 
 from .consignes import date_en_lettres, heure_en_chiffres
 from .memoire import ErreurMemoire
@@ -13,9 +14,11 @@ from .protocole_web import (
     FicheConnecteur,
     ListeConnecteurs,
     ListeDocuments,
+    ReglageConnecteur,
     ResumeDocument,
 )
 from .registre import Fiche
+from .reglages import modifiable
 
 MEMOIRE_ABSENTE = "La mémoire n'est pas disponible."
 
@@ -52,11 +55,26 @@ def liste_connecteurs(outils: OutilsMemoire | None) -> ListeConnecteurs:
     """Les connecteurs trouvés, relus à l'instant (manifestes seuls) ; sans mémoire, aucun."""
     if outils is None or outils.registre is None:
         return ListeConnecteurs(disponible=False)
-    return ListeConnecteurs(connecteurs=[_pour_la_page(f) for f in outils.registre.decouvrir()])
+    environ = outils.registre.environ
+    fiches = outils.registre.decouvrir()
+    return ListeConnecteurs(connecteurs=[_pour_la_page(f, environ) for f in fiches])
 
 
-def _pour_la_page(fiche: Fiche) -> FicheConnecteur:
+def _pour_la_page(fiche: Fiche, environ: Mapping[str, str]) -> FicheConnecteur:
     manifeste = fiche.manifeste
+    reglages = [
+        ReglageConnecteur(
+            variable=r.variable,
+            description=r.description,
+            secret=r.secret,
+            defini=bool(environ.get(r.variable, "").strip()),
+            modifiable=modifiable(r.variable),
+            # Jamais la valeur d'un secret, ni celle d'une clé d'Atlas, même déclarée
+            # « ordinaire » par un manifeste.
+            valeur=environ.get(r.variable, "") if not r.secret and modifiable(r.variable) else "",
+        )
+        for r in (manifeste.reglages if manifeste else ())
+    ]
     return FicheConnecteur(
         id=fiche.id,
         nom=manifeste.nom if manifeste else fiche.id,
@@ -67,4 +85,5 @@ def _pour_la_page(fiche: Fiche) -> FicheConnecteur:
         etat=fiche.etat,
         detail=fiche.detail,
         en_attente=fiche.en_attente,
+        reglages=reglages,
     )
```

Modifier `src/atlas_core/protocole_web.py` :

```diff
--- a/src/atlas_core/protocole_web.py
+++ b/src/atlas_core/protocole_web.py
@@ -10,9 +10,10 @@ from typing import Annotated, Literal
 
 from pydantic import BaseModel, Field, TypeAdapter, ValidationError, field_validator
 
-from .connecteurs import ID_MAX, MOTIF_ID
+from .connecteurs import ID_MAX, MOTIF_ID, MOTIF_VARIABLE
 
 LONGUEUR_MAX_SAISIE = 1000
+REGLAGES_MAX = 50  # par message : bien plus qu'un manifeste n'en déclare
 TAILLE_MAX_CLE = 256
 # L'identifiant qu'une page tire au hasard à son ouverture, le même sur /ws/web et sur
 # /ws/voix : une question tapée trouve ainsi la voix de sa page.
@@ -128,6 +129,18 @@ class FinMission(BaseModel):
     texte: str
 
 
+class ReglageConnecteur(BaseModel):
+    """Un réglage d'un connecteur tel que la page le montre : la valeur d'un réglage
+    ordinaire seulement, jamais celle d'un secret ni d'une clé d'Atlas."""
+
+    variable: str
+    description: str
+    secret: bool = False
+    defini: bool = False
+    modifiable: bool = True  # faux pour une clé d'Atlas : elle se change au Terminal
+    valeur: str = ""
+
+
 class FicheConnecteur(BaseModel):
     """Un connecteur tel que la page le montre (spec des connecteurs, §6)."""
 
@@ -140,6 +153,7 @@ class FicheConnecteur(BaseModel):
     etat: Literal["actif", "coupe", "a_configurer", "a_installer", "en_erreur"]
     detail: str = ""
     en_attente: bool = False  # basculé : prend effet à la question suivante
+    reglages: list[ReglageConnecteur] = []
 
 
 class ListeConnecteurs(BaseModel):
@@ -150,6 +164,15 @@ class ListeConnecteurs(BaseModel):
     connecteurs: list[FicheConnecteur] = []
 
 
+class ResultatReglage(BaseModel):
+    """À la page qui a enregistré des réglages : faits, ou pourquoi pas."""
+
+    type: Literal["resultat_reglage"] = "resultat_reglage"
+    id: str
+    ok: bool
+    message: str
+
+
 # --- page vers Core -----------------------------------------------------
 
 
@@ -206,6 +229,19 @@ class ActiverConnecteur(BaseModel):
     actif: bool
 
 
+Variable = Annotated[str, Field(pattern=MOTIF_VARIABLE)]
+
+
+class ReglerConnecteur(BaseModel):
+    """« Enregistrer » ou « Effacer » dans les réglages d'un connecteur. Le Core vérifie
+    chaque variable et chaque valeur ; la page ne décide rien."""
+
+    type: Literal["regler_connecteur"] = "regler_connecteur"
+    id: str = Field(pattern=MOTIF_ID, max_length=ID_MAX)
+    valeurs: dict[Variable, str] = Field(default={}, max_length=REGLAGES_MAX)
+    effacer: list[Variable] = Field(default=[], max_length=REGLAGES_MAX)
+
+
 MessagePage = Annotated[
     Authentification
     | Saisie
@@ -215,7 +251,8 @@ MessagePage = Annotated[
     | Confirmer
     | Arreter
     | DemandeConnecteurs
-    | ActiverConnecteur,
+    | ActiverConnecteur
+    | ReglerConnecteur,
     Field(discriminator="type"),
 ]
 _adaptateur_page = TypeAdapter(MessagePage)
```

Créer `src/atlas_core/routage_pages.py` :

```python
"""Ce que le Core fait d'un message d'une page authentifiée, sur /ws/web : une question tapée,
le mode muet, les documents, les boutons des barres, les connecteurs et leurs réglages."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .pages import lire_document, liste_connecteurs, liste_documents
from .protocole_web import (
    ActiverConnecteur,
    Arreter,
    Confirmer,
    DemandeConnecteurs,
    DemandeDocuments,
    LireDocument,
    MessagePage,
    Muet,
    ReglerConnecteur,
    ResultatReglage,
    Saisie,
)
from .reglages import ReglageRefuse

if TYPE_CHECKING:
    from .cerveau import Cerveau
    from .diffuseur import Abonnement
    from .outils_memoire import OutilsMemoire
    from .regie import Regie

ENREGISTRE = "Enregistré."
SANS_MEMOIRE = "La mémoire n'est pas disponible : pas de connecteurs."


@dataclass
class Contexte:
    """Ce dont un message a besoin : la régie, la mémoire et ses outils (None sans elle), le
    cerveau, et la page qui l'a envoyé (son abonnement, son identifiant)."""

    regie: Regie
    outils: OutilsMemoire | None
    cerveau: Cerveau | None
    abonnement: Abonnement
    page: str | None


async def traiter(msg: MessagePage, ctx: Contexte) -> None:
    outils = ctx.outils
    if isinstance(msg, Saisie):
        await ctx.regie.saisie(msg.texte, ctx.page)
    elif isinstance(msg, Muet):
        await ctx.regie.basculer_muet(msg.actif)
    elif isinstance(msg, DemandeDocuments):
        ctx.abonnement.envoyer_prive(await liste_documents(outils))
    elif isinstance(msg, LireDocument):
        ctx.abonnement.envoyer_prive(await lire_document(outils, msg.chemin))
    elif isinstance(msg, Confirmer):
        # Comme taper « oui » ou « non » depuis cette page ; trop tard, rien.
        if outils is not None and outils.confirmations.en_attente:
            await ctx.regie.saisie("oui" if msg.oui else "non", ctx.page)
    elif isinstance(msg, Arreter):
        # Comme taper « stop » depuis cette page ; la mission déjà finie, rien.
        if outils is not None and outils.missions.en_cours is not None:
            await ctx.regie.saisie("stop", ctx.page)
    elif isinstance(msg, DemandeConnecteurs):
        ctx.abonnement.envoyer_prive(liste_connecteurs(outils))
    elif isinstance(msg, ActiverConnecteur):
        # La conversation se clôt ; la suivante porte les connecteurs actifs.
        if outils is not None and outils.basculer(msg.id, msg.actif):
            ctx.cerveau.renouveler()
        ctx.regie.diffuseur.publier(liste_connecteurs(outils))  # toutes les pages
    elif isinstance(msg, ReglerConnecteur):
        _regler(msg, ctx)


def _regler(msg: ReglerConnecteur, ctx: Contexte) -> None:
    """Écrit les réglages ; le résultat va à la page qui les a saisis, la liste à toutes."""
    try:
        if ctx.outils is None:
            raise ReglageRefuse(SANS_MEMOIRE)
        change = ctx.outils.regler(msg.id, msg.valeurs, msg.effacer)
    except ReglageRefuse as e:
        ctx.abonnement.envoyer_prive(ResultatReglage(id=msg.id, ok=False, message=str(e)))
        return
    if change:
        ctx.cerveau.renouveler()  # un connecteur actif rechargé : comme une bascule
    ctx.abonnement.envoyer_prive(ResultatReglage(id=msg.id, ok=True, message=ENREGISTRE))
    ctx.regie.diffuseur.publier(liste_connecteurs(ctx.outils))
```

- [ ] **Step 4: Vérifier que tout passe**

Run: `uv run pytest -q && uv run ruff check . --extend-exclude spikes && uv run ruff format --check . --extend-exclude spikes && node --test "tests/web/*.test.mjs"`
Expected: 1252 tests Python passent (3 de moins, et 3 ignorés, si `models/silero_vad.onnx` manque, comme dans une copie neuve), 150 tests JavaScript passent, ruff ne dit rien.

- [ ] **Step 5: Commit**

```bash
git add src/atlas_core/hub.py src/atlas_core/pages.py src/atlas_core/protocole_web.py src/atlas_core/routage_pages.py tests/test_hub_web.py tests/test_protocole_web.py
git commit -F - <<'MSG'
Core : les messages des réglages ; le routage des pages à part

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

### Task 4: L'entretien du Core

`Entretien` : la version qui tourne ; le redémarrage (la marque `donnees/redemarrer`, puis l'arrêt comme à un
Ctrl-C) ; la mise à jour (sur `main` sans fichier suivi modifié, `git pull --ff-only`, les nouveautés, `make
install`, puis le redémarrage ; un échec ne redémarre rien). Une commande trop longue, ou le Core qui s'arrête, tue
tout son groupe de processus. Testé sur de vrais dépôts git temporaires ; les tests ne touchent jamais le dépôt de
David ni n'arrêtent le Core (`tests/conftest.py`). Review Focus 4 : un fichier non suivi qu'une nouveauté
écraserait arrête tout.

**Files:**
- Create: `src/atlas_core/entretien.py`
- Modify: `src/atlas_core/protocole_web.py`
- Modify: `tests/conftest.py`
- Create: `tests/test_entretien.py`
- Modify: `tests/test_protocole_web.py`

**Interfaces:**
- Consumes: rien des tâches précédentes.
- Produces: `protocole_web` : `EtatCore(version, date="", occupe=False, mise_a_jour_possible=False, raison="")`,
  `CoreEnCours(etape, texte, nouveautes=[])` (`etape` : `redemarrage`, `recuperation`, `installation`),
  `FinCore(ok, texte, details=[])` ; `atlas_core.entretien` : `DEPOT`, `BRANCHE = "main"`, `INSTALLER`,
  `DELAI_GIT_S = 120`, `DELAI_INSTALLATION_S = 600`, `DELAI_ARRET_S = 0.5`, les textes (`REDEMARRAGE`,
  `RECUPERATION`, `INSTALLATION`, `DEJA_A_JOUR`, `OCCUPE`, `ECHEC_RECUPERATION`, `ECHEC_INSTALLATION`),
  `marque(depot) -> Path`, `arreter_le_core()`, `Entretien(publier, depot=None, *, installer=INSTALLER,
  delais=(DELAI_GIT_S, DELAI_INSTALLATION_S), arreter=None)` avec `occupe`, `tache`, `effacer_la_marque()`,
  `async etat() -> EtatCore`, `demander_redemarrage() -> FinCore | None`, `async demander_mise_a_jour() ->
  FinCore | None` (un refus, ou None), `async fermer()`.

- [ ] **Step 1: Écrire les tests qui échouent**

Modifier `tests/conftest.py` :

```diff
--- a/tests/conftest.py
+++ b/tests/conftest.py
@@ -4,7 +4,7 @@ La mémoire d'Atlas est un dépôt git sur la machine du Core, et ses connecteur
 les tests, qui démarrent le Core, ne doivent jamais toucher les vrais. Les dossiers sont forcés
 avant tout import du Core (`make test` exporte le .env de la machine, qui pourrait en nommer
 d'autres). Les réglages écrits depuis la page vont dans un .env de test, jamais dans celui du
-dépôt.
+dépôt ; et aucun test ne redémarre le Core ni ne met à jour le dépôt de David.
 """
 
 import os
@@ -19,6 +19,8 @@ os.environ["ATLAS_CONNECTEURS_DOSSIER"] = os.path.join(_TEMPORAIRE, "connecteurs
 
 @pytest.fixture(autouse=True)
 def _jamais_le_env_du_depot(monkeypatch, tmp_path_factory):
-    from atlas_core import reglages
+    from atlas_core import entretien, reglages
 
     monkeypatch.setattr(reglages, "FICHIER_ENV", tmp_path_factory.mktemp("env") / ".env")
+    monkeypatch.setattr(entretien, "DEPOT", tmp_path_factory.mktemp("depot"))
+    monkeypatch.setattr(entretien, "arreter_le_core", lambda: None)
```

Créer `tests/test_entretien.py` :

```python
"""L'entretien du Core depuis la page : la version, le redémarrage (la marque, puis l'arrêt), et
la mise à jour, sur de vrais dépôts git temporaires (une origine locale : aucun réseau)."""

import asyncio
import os
import subprocess
from pathlib import Path

import pytest

from atlas_core import entretien as module
from atlas_core.entretien import (
    DEJA_A_JOUR,
    ECHEC_INSTALLATION,
    ECHEC_RECUPERATION,
    OCCUPE,
    Entretien,
    marque,
)
from atlas_core.protocole_web import CoreEnCours, FinCore

REUSSIT = ("sh", "-c", "echo installé > installe")
RATE = ("sh", "-c", "echo 'uv : paquet introuvable' >&2; exit 2")


def lente(dossier) -> tuple[str, ...]:
    """Une installation qui lance un sous-processus et l'attend, comme make lance uv."""
    return ("sh", "-c", f"sleep 30 & echo $! > {dossier}/pid; wait")


def mort(fichier_pid) -> bool:
    try:
        os.kill(int(fichier_pid.read_text()), 0)
    except ProcessLookupError:
        return True
    return False


@pytest.fixture(autouse=True)
def _git_isole(monkeypatch):
    # Ni la configuration git de David, ni la signature de ses commits.
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for cle, valeur in {"NAME": "Test", "EMAIL": "test@example.com"}.items():
        monkeypatch.setenv(f"GIT_AUTHOR_{cle}", valeur)
        monkeypatch.setenv(f"GIT_COMMITTER_{cle}", valeur)
    monkeypatch.setattr(module, "DELAI_ARRET_S", 0)


def git(dossier, *args) -> str:
    r = subprocess.run(["git", *args], cwd=dossier, capture_output=True, text=True, check=True)
    return r.stdout.strip()


class Depots:
    """Une origine, le dépôt du Core qui la suit sur `main`, et un autre clone qui pousse."""

    def __init__(self, racine):
        self.origine, self.core, self.autre = (racine / n for n in ("origine", "core", "autre"))
        git(racine, "init", "-q", "--bare", "-b", "main", str(self.origine))
        git(racine, "clone", "-q", str(self.origine), str(self.autre))
        (self.autre / "LISEZMOI.md").write_text("Atlas\n")
        git(self.autre, "add", "LISEZMOI.md")
        git(self.autre, "commit", "-q", "-m", "Premier")
        git(self.autre, "push", "-q", "origin", "HEAD:main")
        git(racine, "clone", "-q", str(self.origine), str(self.core))

    def pousser(self, *titres: str) -> None:
        for titre in titres:
            git(self.autre, "commit", "-q", "--allow-empty", "-m", titre)
        git(self.autre, "push", "-q", "origin", "HEAD:main")


@pytest.fixture
def depots(tmp_path) -> Depots:
    return Depots(tmp_path)


class Temoins:
    def __init__(self) -> None:
        self.publies: list = []
        self.arrets = 0

    def arreter(self) -> None:
        self.arrets += 1


@pytest.fixture
def temoins() -> Temoins:
    return Temoins()


def entretien(depots, temoins, installer=REUSSIT, delais=(30, 30)) -> Entretien:
    return Entretien(
        temoins.publies.append,
        depots.core,
        installer=installer,
        delais=delais,
        arreter=temoins.arreter,
    )


async def test_la_version_qui_tourne(depots, temoins):
    etat = await entretien(depots, temoins).etat()
    assert etat.version == git(depots.core, "rev-parse", "--short", "HEAD")
    assert etat.date == git(depots.core, "log", "-1", "--format=%cs")
    assert (etat.occupe, etat.mise_a_jour_possible, etat.raison) == (False, True, "")


async def test_hors_d_un_depot_git_la_version_est_inconnue(tmp_path, temoins):
    etat = await Entretien(temoins.publies.append, tmp_path, arreter=temoins.arreter).etat()
    assert (etat.version, etat.date, etat.mise_a_jour_possible) == ("inconnue", "", False)
    assert etat.raison.endswith("mets-le à jour au Terminal.")


async def test_redemarrer_laisse_la_marque_puis_arrete_le_core(depots, temoins):
    e = entretien(depots, temoins)
    assert e.demander_redemarrage() is None
    assert temoins.publies == [CoreEnCours(etape="redemarrage", texte="Redémarrage du Core…")]
    assert marque(depots.core).exists()
    await asyncio.sleep(0.01)
    assert temoins.arrets == 1
    assert e.demander_redemarrage() == FinCore(ok=False, texte=OCCUPE)
    assert await e.demander_mise_a_jour() == FinCore(ok=False, texte=OCCUPE)
    etat = await e.etat()
    assert (etat.occupe, etat.mise_a_jour_possible, etat.raison) == (True, False, OCCUPE)
    assert temoins.arrets == 1


async def test_sans_marque_pas_de_redemarrage(depots, temoins):
    (depots.core / "donnees").write_text("un fichier, pas un dossier\n")
    e = entretien(depots, temoins)
    assert e.demander_redemarrage() is None
    fin = temoins.publies[-1]
    assert (fin.ok, fin.texte.endswith("redémarre-le au Terminal.")) == (False, True)
    await asyncio.sleep(0.01)
    assert temoins.arrets == 0 and e.occupe is False


def test_les_tests_ne_touchent_jamais_le_depot_de_david():
    assert module.DEPOT != Path(module.__file__).resolve().parents[2]
    assert Entretien(lambda msg: None).depot == module.DEPOT


def test_une_marque_restee_la_s_efface_au_demarrage(depots, temoins):
    marque(depots.core).parent.mkdir()
    marque(depots.core).touch()
    e = entretien(depots, temoins)
    e.effacer_la_marque()
    assert not marque(depots.core).exists()
    e.effacer_la_marque()  # aucune : rien à faire


async def test_deja_a_jour(depots, temoins):
    e = entretien(depots, temoins)
    assert await e.demander_mise_a_jour() is None
    await e.tache
    assert temoins.publies == [
        CoreEnCours(etape="recuperation", texte="Récupération de la dernière version…"),
        FinCore(ok=True, texte=DEJA_A_JOUR),
    ]
    assert not (depots.core / "installe").exists() and temoins.arrets == 0
    assert e.occupe is False


async def test_les_nouveautes_l_installation_puis_le_redemarrage(depots, temoins):
    depots.pousser(*(f"Nouveauté {n}" for n in range(1, 8)))
    e = entretien(depots, temoins)
    assert await e.demander_mise_a_jour() is None
    await e.tache
    await asyncio.sleep(0.01)
    nouveautes = [f"Nouveauté {n}" for n in (7, 6, 5, 4, 3)] + ["et 2 autres"]
    assert temoins.publies == [
        CoreEnCours(etape="recuperation", texte="Récupération de la dernière version…"),
        CoreEnCours(etape="installation", texte="Installation…", nouveautes=nouveautes),
        CoreEnCours(etape="redemarrage", texte="Redémarrage du Core…", nouveautes=nouveautes),
    ]
    assert git(depots.core, "log", "-1", "--format=%s") == "Nouveauté 7"
    assert (depots.core / "installe").read_text() == "installé\n", "dans le dépôt du Core"
    assert marque(depots.core).exists() and temoins.arrets == 1
    assert e.occupe is True, "jusqu'à l'arrêt : un autre clic ne relance rien"


async def test_hors_de_main_rien_ne_change(depots, temoins):
    git(depots.core, "switch", "-q", "-c", "essai")
    depots.pousser("Nouveauté")
    e = entretien(depots, temoins)
    raison = "Le dépôt du Core est sur la branche essai, pas sur main : mets-le à jour au Terminal."
    assert await e.demander_mise_a_jour() == FinCore(ok=False, texte=raison)
    etat = await e.etat()
    assert (etat.mise_a_jour_possible, etat.raison) == (False, raison)
    assert temoins.publies == [] and e.occupe is False


async def test_un_fichier_suivi_modifie_bloque_la_mise_a_jour(depots, temoins):
    (depots.core / ".env").write_text("ATLAS_WEB_CLE=x\n")  # non suivi : ne compte pas
    (depots.core / "notes.txt").write_text("brouillon\n")
    assert (await entretien(depots, temoins).etat()).mise_a_jour_possible is True
    (depots.core / "LISEZMOI.md").write_text("Atlas, retouché\n")
    raison = "Le dépôt du Core a des modifications : mets-le à jour au Terminal."
    assert await entretien(depots, temoins).demander_mise_a_jour() == FinCore(
        ok=False, texte=raison
    )


async def test_un_historique_divergent_ne_change_rien(depots, temoins):
    git(depots.core, "config", "pull.rebase", "false")  # git fusionnerait, sans --ff-only
    git(depots.core, "commit", "-q", "--allow-empty", "-m", "Local")
    depots.pousser("Distant")
    avant = git(depots.core, "rev-parse", "HEAD")
    e = entretien(depots, temoins)
    await e.demander_mise_a_jour()
    await e.tache
    fin = temoins.publies[-1]
    assert (fin.type, fin.ok, fin.texte) == ("fin_core", False, ECHEC_RECUPERATION)
    assert fin.details, "les dernières lignes de git"
    assert git(depots.core, "rev-parse", "HEAD") == avant
    assert temoins.arrets == 0 and e.occupe is False


async def test_un_fichier_non_suivi_qu_une_nouveaute_ecraserait_arrete_tout(depots, temoins):
    # Review Focus 4 : un fichier laissé dans le dépôt du Core, qu'une nouveauté ajoute aussi.
    (depots.autre / "notes.txt").write_text("la version d'Atlas\n")
    git(depots.autre, "add", "notes.txt")
    depots.pousser("Des notes")
    (depots.core / "notes.txt").write_text("celles de David\n")
    e = entretien(depots, temoins)
    assert await e.demander_mise_a_jour() is None, "non suivi : il ne bloque pas d'avance"
    await e.tache
    fin = temoins.publies[-1]
    assert (fin.ok, fin.texte) == (False, ECHEC_RECUPERATION)
    assert (depots.core / "notes.txt").read_text() == "celles de David\n"
    assert temoins.arrets == 0 and not (depots.core / "installe").exists()


async def test_une_installation_ratee_ne_redemarre_pas(depots, temoins):
    depots.pousser("Nouveauté")
    e = entretien(depots, temoins, installer=RATE)
    await e.demander_mise_a_jour()
    await e.tache
    assert temoins.publies[-1] == FinCore(
        ok=False, texte=ECHEC_INSTALLATION, details=["uv : paquet introuvable"]
    )
    assert not marque(depots.core).exists() and temoins.arrets == 0 and e.occupe is False


async def test_une_installation_trop_longue_est_arretee(depots, temoins, tmp_path):
    depots.pousser("Nouveauté")
    e = entretien(depots, temoins, installer=lente(tmp_path), delais=(30, 0.5))
    await e.demander_mise_a_jour()
    await asyncio.wait_for(e.tache, 5)  # sans attendre la fin de ce qu'elle a lancé
    fin = temoins.publies[-1]
    assert (fin.ok, fin.texte, fin.details[-1]) == (
        False,
        ECHEC_INSTALLATION,
        "Arrêtée : elle a dépassé son délai.",
    )
    await asyncio.sleep(0.1)
    assert mort(tmp_path / "pid"), "ce qu'elle a lancé est arrêté aussi"
    assert temoins.arrets == 0


async def test_l_arret_du_core_arrete_une_mise_a_jour_en_cours(depots, temoins, tmp_path):
    depots.pousser("Nouveauté")
    e = entretien(depots, temoins, installer=lente(tmp_path))
    await e.demander_mise_a_jour()
    while not (tmp_path / "pid").exists() or not (tmp_path / "pid").read_text():
        await asyncio.sleep(0.01)
    assert e.demander_redemarrage() == FinCore(ok=False, texte=OCCUPE)
    await asyncio.wait_for(e.fermer(), 5)
    assert e.tache.done()
    await asyncio.sleep(0.1)
    assert mort(tmp_path / "pid")
```

Modifier `tests/test_protocole_web.py` :

```diff
--- a/tests/test_protocole_web.py
+++ b/tests/test_protocole_web.py
@@ -11,13 +11,16 @@ from atlas_core.protocole_web import (
     AttenteConfirmation,
     Authentification,
     Confirmer,
+    CoreEnCours,
     DemandeConnecteurs,
     DemandeDocuments,
     Document,
     DocumentsChanges,
     Echange,
+    EtatCore,
     FicheConnecteur,
     FinConfirmation,
+    FinCore,
     FinMission,
     Historique,
     Latences,
@@ -256,3 +259,27 @@ def test_une_page_regle_un_connecteur():
 def test_un_reglage_ne_nomme_qu_une_variable_d_atlas(message):
     with pytest.raises(ValueError):
         decoder_message_page(json.dumps({"type": "regler_connecteur", **message}))
+
+
+def test_les_messages_du_core_vers_les_pages():
+    assert EtatCore(version="ce65d2a", date="2026-09-29").model_dump() == {
+        "type": "etat_core",
+        "version": "ce65d2a",
+        "date": "2026-09-29",
+        "occupe": False,
+        "mise_a_jour_possible": False,
+        "raison": "",
+    }
+    en_cours = CoreEnCours(etape="installation", texte="Installation…", nouveautes=["Un"])
+    assert en_cours.model_dump() == {
+        "type": "core_en_cours",
+        "etape": "installation",
+        "texte": "Installation…",
+        "nouveautes": ["Un"],
+    }
+    assert FinCore(ok=True, texte="Atlas est déjà à jour.").model_dump() == {
+        "type": "fin_core",
+        "ok": True,
+        "texte": "Atlas est déjà à jour.",
+        "details": [],
+    }
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `uv run pytest tests/test_entretien.py tests/test_protocole_web.py -q`
Expected: FAIL — erreurs de collecte : `cannot import name 'entretien' from 'atlas_core'` et `cannot import name
'CoreEnCours' from 'atlas_core.protocole_web'`.

- [ ] **Step 3: Écrire l'entretien**

Créer `src/atlas_core/entretien.py` :

```python
"""L'entretien du Core depuis la page (spec des réglages et du Core, §5 et §6) : la version
qui tourne, le redémarrage, et la mise à jour (`git pull` en avance rapide, `make install`).

Le Core redémarre en s'arrêtant proprement, comme à un Ctrl-C, après avoir laissé la marque
`donnees/redemarrer` : `make run-core` le relance alors par un `make` neuf, qui relit le .env.
Aucun texte venu d'une page n'entre dans une commande : `git` et `make` sont lancés avec des
arguments fixes, dans le dépôt du Core, avec des délais fixes.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel

from .protocole_web import CoreEnCours, EtatCore, FinCore

_journal = logging.getLogger(__name__)

DEPOT = Path(__file__).resolve().parents[2]
BRANCHE = "main"
INSTALLER = ("make", "install")
DELAI_GIT_S = 120.0
DELAI_INSTALLATION_S = 600.0
DELAI_ARRET_S = 0.5  # le temps que « Redémarrage du Core… » parte vers les pages
NOUVEAUTES_MAX = 5
LIGNES_MAX = 10  # les dernières lignes d'une erreur, montrées dans la page
LIGNE_MAX = 200

REDEMARRAGE = "Redémarrage du Core…"
RECUPERATION = "Récupération de la dernière version…"
INSTALLATION = "Installation…"
DEJA_A_JOUR = "Atlas est déjà à jour."
OCCUPE = "Un redémarrage ou une mise à jour est déjà en cours."
ECHEC_RECUPERATION = "La récupération a échoué : rien n'a changé."
ECHEC_INSTALLATION = (
    "L'installation a échoué : relance make install au Terminal avant de redémarrer."
)
TROP_LONGUE = "Arrêtée : elle a dépassé son délai."
AU_TERMINAL = " : mets-le à jour au Terminal."


def marque(depot: Path) -> Path:
    """Laissée par un Core qui demande à `make run-core` de le relancer."""
    return depot / "donnees" / "redemarrer"


def arreter_le_core() -> None:
    """Comme un Ctrl-C : uvicorn s'arrête proprement (la conversation se clôt, avec son
    résumé au journal ; une mission s'arrête ; une confirmation est abandonnée)."""
    os.kill(os.getpid(), signal.SIGTERM)


@dataclass
class _Sortie:
    code: int  # -1 : arrêtée, trop longue
    lignes: list[str]


class Entretien:
    """`publier` envoie un message à toutes les pages ; `arreter`, par défaut
    `arreter_le_core`, arrête le Core une fois la marque laissée."""

    def __init__(
        self,
        publier: Callable[[BaseModel], None],
        depot: Path | None = None,
        *,
        installer: Sequence[str] = INSTALLER,
        delais: tuple[float, float] = (DELAI_GIT_S, DELAI_INSTALLATION_S),
        arreter: Callable[[], None] | None = None,
    ) -> None:
        self._publier = publier
        self.depot = DEPOT if depot is None else depot
        self._installer = list(installer)
        self._delai_git, self._delai_installation = delais
        self._arreter = arreter
        self.occupe = False
        self.tache: asyncio.Task[None] | None = None  # la mise à jour en cours

    def effacer_la_marque(self) -> None:
        """Au démarrage : une marque restée là (un Core tué juste après) ne relance rien."""
        try:
            marque(self.depot).unlink(missing_ok=True)
        except OSError as e:
            _journal.warning("marque de redémarrage non effacée : %s", e)

    async def etat(self) -> EtatCore:
        sortie = await self._lancer(["git", "log", "-1", "--format=%h %cs"], self._delai_git)
        version, _, date = (
            sortie.lignes[0] if sortie.code == 0 and sortie.lignes else ""
        ).partition(" ")
        raison = OCCUPE if self.occupe else await self._raison_du_depot()
        return EtatCore(
            version=version or "inconnue",
            date=date,
            occupe=self.occupe,
            mise_a_jour_possible=raison is None,
            raison=raison or "",
        )

    async def _raison_du_depot(self) -> str | None:
        """Pourquoi le dépôt ne se met pas à jour depuis la page ; None s'il le peut."""
        branche = await self._lancer(["git", "symbolic-ref", "--short", "HEAD"], self._delai_git)
        if branche.code != 0 or not branche.lignes:
            return "Le dépôt du Core n'est sur aucune branche" + AU_TERMINAL
        if branche.lignes[0] != BRANCHE:
            nom = branche.lignes[0]
            return f"Le dépôt du Core est sur la branche {nom}, pas sur {BRANCHE}" + AU_TERMINAL
        suivis = ["git", "status", "--porcelain", "--untracked-files=no"]
        modifies = await self._lancer(suivis, self._delai_git)
        if modifies.lignes:  # git écrit aussi ici son erreur, s'il n'a pas pu lire
            return "Le dépôt du Core a des modifications" + AU_TERMINAL
        return None

    # --- le redémarrage ----------------------------------------------------------------

    def demander_redemarrage(self) -> FinCore | None:
        """Le bouton « Redémarrer » : un refus pour la page qui l'a demandé, ou None."""
        if self.occupe:
            return FinCore(ok=False, texte=OCCUPE)
        self.occupe = True
        self._redemarrer([])
        return None

    def _redemarrer(self, nouveautes: list[str]) -> None:
        self._publier(CoreEnCours(etape="redemarrage", texte=REDEMARRAGE, nouveautes=nouveautes))
        try:
            marque(self.depot).parent.mkdir(parents=True, exist_ok=True)
            marque(self.depot).touch()
        except OSError as e:
            self.occupe = False
            texte = (
                f"Le Core ne peut pas redémarrer ({e.strerror or e}) : redémarre-le au Terminal."
            )
            self._publier(FinCore(ok=False, texte=texte))
            return
        _journal.info("redémarrage demandé depuis la page")
        arreter = self._arreter or arreter_le_core
        asyncio.get_running_loop().call_later(DELAI_ARRET_S, arreter)

    # --- la mise à jour ----------------------------------------------------------------

    async def demander_mise_a_jour(self) -> FinCore | None:
        """Le bouton « Mettre à jour et redémarrer » : un refus pour la page qui l'a demandé,
        ou None, la mise à jour partie en arrière-plan (Atlas continue de répondre)."""
        if self.occupe:
            return FinCore(ok=False, texte=OCCUPE)
        self.occupe = True
        raison = await self._raison_du_depot()
        if raison is not None:
            self.occupe = False
            return FinCore(ok=False, texte=raison)
        self.tache = asyncio.create_task(self._mettre_a_jour())
        return None

    async def _mettre_a_jour(self) -> None:
        redemarre = False
        try:
            self._publier(CoreEnCours(etape="recuperation", texte=RECUPERATION))
            avant = await self._tete()
            tire = await self._lancer(["git", "pull", "--ff-only"], self._delai_git)
            if tire.code != 0:
                self._publier(FinCore(ok=False, texte=ECHEC_RECUPERATION, details=_fin(tire)))
                return
            apres = await self._tete()
            if apres == avant:
                self._publier(FinCore(ok=True, texte=DEJA_A_JOUR))
                return
            titres = await self._lancer(
                ["git", "log", "--format=%s", f"{avant}..{apres}"], self._delai_git
            )
            nouveautes = _resumer(titres.lignes)
            self._publier(
                CoreEnCours(etape="installation", texte=INSTALLATION, nouveautes=nouveautes)
            )
            installe = await self._lancer(self._installer, self._delai_installation)
            if installe.code != 0:
                details = _fin(installe)
                self._publier(FinCore(ok=False, texte=ECHEC_INSTALLATION, details=details))
                return
            redemarre = True
            self._redemarrer(nouveautes)
        finally:
            if not redemarre:
                self.occupe = False

    async def _tete(self) -> str:
        sortie = await self._lancer(["git", "rev-parse", "HEAD"], self._delai_git)
        return sortie.lignes[0] if sortie.code == 0 and sortie.lignes else ""

    async def _lancer(self, commande: list[str], delai: float) -> _Sortie:
        """Lance une commande dans le dépôt, dans son propre groupe de processus : trop
        longue, ou le Core qui s'arrête, et tout le groupe est tué (make et ce qu'il lance)."""
        environ = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}  # jamais une question
        try:
            processus = await asyncio.create_subprocess_exec(
                *commande,
                cwd=self.depot,
                env=environ,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                start_new_session=True,
            )
        except OSError as e:
            return _Sortie(127, [f"{commande[0]} : {e.strerror or e}"])
        try:
            sortie, _ = await asyncio.wait_for(processus.communicate(), delai)
        except TimeoutError:
            await _tuer(processus)
            return _Sortie(-1, [TROP_LONGUE])
        except asyncio.CancelledError:
            await _tuer(processus)
            raise
        lignes = sortie.decode(errors="replace").splitlines()
        for ligne in lignes:
            _journal.info("%s : %s", commande[0], ligne)
        return _Sortie(processus.returncode or 0, lignes)

    async def fermer(self) -> None:
        """L'arrêt du Core : une mise à jour en cours s'arrête, sa commande comprise."""
        if self.tache is not None:
            self.tache.cancel()
            await asyncio.wait([self.tache])  # sans avaler l'annulation de l'arrêt lui-même


async def _tuer(processus: asyncio.subprocess.Process) -> None:
    try:
        os.killpg(processus.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    await processus.wait()


def _resumer(titres: list[str]) -> list[str]:
    """Les titres des nouveaux commits, les plus récents d'abord, cinq au plus."""
    if len(titres) <= NOUVEAUTES_MAX:
        return titres
    return [*titres[:NOUVEAUTES_MAX], f"et {len(titres) - NOUVEAUTES_MAX} autres"]


def _fin(sortie: _Sortie) -> list[str]:
    return [ligne[:LIGNE_MAX] for ligne in sortie.lignes[-LIGNES_MAX:]]
```

Modifier `src/atlas_core/protocole_web.py` :

```diff
--- a/src/atlas_core/protocole_web.py
+++ b/src/atlas_core/protocole_web.py
@@ -164,6 +164,37 @@ class ListeConnecteurs(BaseModel):
     connecteurs: list[FicheConnecteur] = []
 
 
+class EtatCore(BaseModel):
+    """À la page qui le demande : la version qui tourne, et si la mise à jour est possible
+    (sinon, pourquoi : le bouton est alors grisé, avec la raison)."""
+
+    type: Literal["etat_core"] = "etat_core"
+    version: str
+    date: str = ""
+    occupe: bool = False
+    mise_a_jour_possible: bool = False
+    raison: str = ""
+
+
+class CoreEnCours(BaseModel):
+    """À toutes les pages : une étape d'un redémarrage ou d'une mise à jour."""
+
+    type: Literal["core_en_cours"] = "core_en_cours"
+    etape: Literal["redemarrage", "recuperation", "installation"]
+    texte: str
+    nouveautes: list[str] = []
+
+
+class FinCore(BaseModel):
+    """La fin d'une mise à jour sans redémarrage (à jour, ou un échec), à toutes les pages ;
+    un refus, à la page qui a demandé. `details` : les dernières lignes d'une erreur."""
+
+    type: Literal["fin_core"] = "fin_core"
+    ok: bool
+    texte: str
+    details: list[str] = []
+
+
 class ResultatReglage(BaseModel):
     """À la page qui a enregistré des réglages : faits, ou pourquoi pas."""
 
```

- [ ] **Step 4: Vérifier que tout passe**

Run: `uv run pytest -q && uv run ruff check . --extend-exclude spikes && uv run ruff format --check . --extend-exclude spikes && node --test "tests/web/*.test.mjs"`
Expected: 1268 tests Python passent (3 de moins, et 3 ignorés, si `models/silero_vad.onnx` manque, comme dans une copie neuve), 150 tests JavaScript passent, ruff ne dit rien.

- [ ] **Step 5: Commit**

```bash
git add src/atlas_core/entretien.py src/atlas_core/protocole_web.py tests/conftest.py tests/test_entretien.py tests/test_protocole_web.py
git commit -F - <<'MSG'
Core : l'entretien (version, redémarrage, mise à jour)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

### Task 5: Les boutons du Core côté serveur, et la boucle de relance

Les messages `demande_core`, `redemarrer_core` et `mettre_a_jour_core` ; l'entretien créé au démarrage du Core
(une marque restée là s'efface) et arrêté avec lui ; `make run-core` devient une boucle qui relance le Core par un
`make` neuf, qui relit le `.env`, tant qu'il laisse la marque (une variable retirée du `.env` ne survit pas). Le
test de la boucle lance le vrai `make` avec un faux Core, et refuse de tourner avec un `Makefile` qui lancerait le
vrai. Review Focus 1 : deux clics sur « Redémarrer » ne redémarrent qu'une fois.

**Files:**
- Modify: `Makefile`
- Modify: `src/atlas_core/hub.py`
- Modify: `src/atlas_core/protocole_web.py`
- Modify: `src/atlas_core/routage_pages.py`
- Modify: `tests/test_hub_web.py`
- Create: `tests/test_lanceur.py`
- Modify: `tests/test_protocole_web.py`

**Interfaces:**
- Consumes: Task 3 (`Contexte`, `traiter`), Task 4 (`Entretien`, `EtatCore`, `CoreEnCours`, `FinCore`).
- Produces: `protocole_web` : `DemandeCore`, `RedemarrerCore`, `MettreAJourCore` ; `Contexte.entretien` (None par
  défaut) ; `hub._entretien` ; le `Makefile` : `run-core` (la boucle), `core`, `COMMANDE_CORE`, `CLES_DU_ENV`.

- [ ] **Step 1: Écrire les tests qui échouent**

Modifier `tests/test_hub_web.py` :

```diff
--- a/tests/test_hub_web.py
+++ b/tests/test_hub_web.py
@@ -1,5 +1,7 @@
 import json
+import os
 import re
+import subprocess
 from dataclasses import replace
 
 import pytest
@@ -7,7 +9,7 @@ from fastapi.testclient import TestClient
 from starlette.websockets import WebSocketDisconnect
 from test_registre import deposer
 
-from atlas_core import hub, reglages
+from atlas_core import entretien, hub, reglages
 from atlas_core.diffuseur import Diffuseur
 from atlas_core.protocole import Bonjour
 
@@ -353,6 +355,88 @@ def test_regler_un_connecteur_actif_renouvelle_la_conversation(reglables, monkey
     assert renouvellements == [True, True]
 
 
+@pytest.fixture
+def depot(regie, monkeypatch, tmp_path):
+    """Un dépôt git sur main, un commit : celui du Core, le temps du test."""
+    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
+    for cle, valeur in {"NAME": "Test", "EMAIL": "test@example.com"}.items():
+        monkeypatch.setenv(f"GIT_AUTHOR_{cle}", valeur)
+        monkeypatch.setenv(f"GIT_COMMITTER_{cle}", valeur)
+    dossier = tmp_path / "depot"
+    for commande in (["init", "-q", "-b", "main", str(dossier)], ["-C", str(dossier), "commit",
+                     "-q", "--allow-empty", "-m", "Premier"]):  # fmt: skip
+        subprocess.run(["git", *commande], check=True)
+    monkeypatch.setattr(entretien, "DEPOT", dossier)
+    monkeypatch.setattr(entretien, "DELAI_ARRET_S", 0)
+    return dossier
+
+
+def test_la_page_demande_la_version_du_core(depot):
+    with TestClient(hub.app) as client, client.websocket_connect("/ws/web", headers=ORIGINE) as ws:
+        _entrer(ws)
+        ws.send_json({"type": "demande_core"})
+        etat = ws.receive_json()
+    version = subprocess.run(
+        ["git", "-C", str(depot), "rev-parse", "--short", "HEAD"], capture_output=True, text=True
+    ).stdout.strip()
+    assert etat["type"] == "etat_core" and etat["version"] == version
+    assert (etat["occupe"], etat["mise_a_jour_possible"], etat["raison"]) == (False, True, "")
+
+
+def test_redemarrer_depuis_une_page_toutes_les_pages_le_voient(depot, monkeypatch):
+    arrets: list[bool] = []
+    monkeypatch.setattr(entretien, "arreter_le_core", lambda: arrets.append(True))
+    with (
+        TestClient(hub.app) as client,
+        client.websocket_connect("/ws/web", headers=ORIGINE) as ws,
+        client.websocket_connect("/ws/web", headers=ORIGINE) as autre,
+    ):
+        _entrer(ws)
+        _entrer(autre)
+        ws.send_json({"type": "redemarrer_core"})
+        attendu = {"type": "core_en_cours", "etape": "redemarrage",
+                   "texte": "Redémarrage du Core…", "nouveautes": []}  # fmt: skip
+        assert ws.receive_json() == attendu and autre.receive_json() == attendu
+        assert (depot / "donnees" / "redemarrer").exists()
+        ws.send_json({"type": "redemarrer_core"})  # un deuxième clic
+        refus = ws.receive_json()
+        autre.send_json({"type": "saisie", "texte": ""})  # sa réponse suit tout ce qu'elle a reçu
+        assert autre.receive_json()["type"] == "erreur"
+    assert (refus["type"], refus["ok"], refus["texte"]) == ("fin_core", False, entretien.OCCUPE)
+    assert arrets == [True]
+
+
+def test_mettre_a_jour_hors_de_main_est_refuse_a_la_page_qui_le_demande(depot):
+    subprocess.run(["git", "-C", str(depot), "switch", "-q", "-c", "essai"], check=True)
+    with TestClient(hub.app) as client, client.websocket_connect("/ws/web", headers=ORIGINE) as ws:
+        _entrer(ws)
+        ws.send_json({"type": "mettre_a_jour_core"})
+        refus = ws.receive_json()
+    assert (refus["type"], refus["ok"]) == ("fin_core", False)
+    assert refus["texte"] == (
+        "Le dépôt du Core est sur la branche essai, pas sur main : mets-le à jour au Terminal."
+    )
+
+
+def test_au_demarrage_une_marque_restee_la_s_efface(depot):
+    (depot / "donnees").mkdir()
+    (depot / "donnees" / "redemarrer").touch()
+    with TestClient(hub.app):
+        assert not (depot / "donnees" / "redemarrer").exists()
+
+
+def test_l_arret_du_core_arrete_l_entretien(depot, monkeypatch):
+    fermes: list[bool] = []
+
+    async def fermer(self) -> None:
+        fermes.append(True)
+
+    monkeypatch.setattr(entretien.Entretien, "fermer", fermer)
+    with TestClient(hub.app):
+        assert fermes == []
+    assert fermes == [True]
+
+
 def test_sans_memoire_pas_de_connecteurs(regie, monkeypatch):
     monkeypatch.setattr(hub, "_config", replace(hub._config, web_cle=CLE, cerveau="bouchon"))
     with TestClient(hub.app) as client, client.websocket_connect("/ws/web", headers=ORIGINE) as ws:
```

Créer `tests/test_lanceur.py` :

```python
"""`make run-core`, lancé pour de vrai avec un faux Core : il le relance, par un make neuf qui
relit le .env, tant que le Core laisse la marque `donnees/redemarrer`, et s'arrête avec lui
sinon."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

DEPOT = Path(__file__).resolve().parents[1]
# Il note ce qu'il voit du .env ; la première fois, il change le .env et demande à revenir.
FAUX_CORE = """
import os, pathlib, sys
journal = pathlib.Path("journal")
with journal.open("a") as f:
    f.write(f"{os.environ.get('ATLAS_ESSAI')} {os.environ.get('ATLAS_RETIRE', '-')}\\n")
if len(journal.read_text().splitlines()) == 1 and "revenir" in sys.argv:
    pathlib.Path(".env").write_text("ATLAS_ESSAI=2\\n")
    pathlib.Path("donnees").mkdir(exist_ok=True)
    pathlib.Path("donnees/redemarrer").touch()
sys.exit(int(sys.argv[1]))
"""

pytestmark = pytest.mark.skipif(shutil.which("make") is None, reason="make absent")


def lancer(dossier: Path, *arguments: str) -> subprocess.CompletedProcess:
    # Un Makefile qui ignorerait COMMANDE_CORE lancerait le vrai Core : jamais dans un test.
    makefile = (DEPOT / "Makefile").read_text(encoding="utf-8")
    assert "$(COMMANDE_CORE)" in makefile, "run-core ne sait pas encore lancer un autre Core"
    shutil.copy(DEPOT / "Makefile", dossier / "Makefile")
    (dossier / "faux_core.py").write_text(FAUX_CORE)
    environ = {
        k: v for k, v in os.environ.items() if not k.startswith(("ATLAS_", "MAKE", "MFLAGS"))
    }
    commande = f"COMMANDE_CORE={sys.executable} faux_core.py {' '.join(arguments)}"
    return subprocess.run(
        ["make", "-s", "run-core", commande],
        cwd=dossier,
        env=environ,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_le_core_qui_le_demande_revient_avec_le_env_relu(tmp_path):
    (tmp_path / ".env").write_text("ATLAS_ESSAI=1\nexport ATLAS_RETIRE = oui\n")
    r = lancer(tmp_path, "0", "revenir")
    assert r.returncode == 0, r.stderr
    # Relancé une fois, avec la nouvelle valeur ; la variable retirée n'a pas survécu.
    assert (tmp_path / "journal").read_text().splitlines() == ["1 oui", "2 -"]
    assert not (tmp_path / "donnees" / "redemarrer").exists()


def test_sans_marque_la_boucle_s_arrete_avec_le_core(tmp_path):
    (tmp_path / ".env").write_text("ATLAS_ESSAI=1\n")
    r = lancer(tmp_path, "3")
    assert r.returncode != 0, "le Core est tombé : make le dit (launchd le relance)"
    assert (tmp_path / "journal").read_text().splitlines() == ["1 -"]


def test_une_marque_restee_la_ne_relance_rien(tmp_path):
    (tmp_path / "donnees").mkdir()
    (tmp_path / "donnees" / "redemarrer").touch()  # un Core tué juste après l'avoir laissée
    r = lancer(tmp_path, "0")
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "journal").read_text().splitlines() == ["None -"]
```

Modifier `tests/test_protocole_web.py` :

```diff
--- a/tests/test_protocole_web.py
+++ b/tests/test_protocole_web.py
@@ -13,6 +13,7 @@ from atlas_core.protocole_web import (
     Confirmer,
     CoreEnCours,
     DemandeConnecteurs,
+    DemandeCore,
     DemandeDocuments,
     Document,
     DocumentsChanges,
@@ -27,9 +28,11 @@ from atlas_core.protocole_web import (
     LireDocument,
     ListeConnecteurs,
     ListeDocuments,
+    MettreAJourCore,
     MissionEnCours,
     Muet,
     Niveau,
+    RedemarrerCore,
     ReglageConnecteur,
     ReglerConnecteur,
     ResultatReglage,
@@ -283,3 +286,9 @@ def test_les_messages_du_core_vers_les_pages():
         "texte": "Atlas est déjà à jour.",
         "details": [],
     }
+
+
+def test_les_boutons_du_core():
+    assert decoder_message_page('{"type":"demande_core"}') == DemandeCore()
+    assert decoder_message_page('{"type":"redemarrer_core"}') == RedemarrerCore()
+    assert decoder_message_page('{"type":"mettre_a_jour_core"}') == MettreAJourCore()
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `uv run pytest tests/test_lanceur.py tests/test_hub_web.py tests/test_protocole_web.py -q`
Expected: FAIL — erreur de collecte : `ImportError: cannot import name 'DemandeCore' from
'atlas_core.protocole_web'` (et `tests/test_lanceur.py`, lancé seul, échoue sur « run-core ne sait pas encore
lancer un autre Core », sans rien lancer).

- [ ] **Step 3: Écrire les boutons et la boucle**

Modifier `Makefile` :

```diff
--- a/Makefile
+++ b/Makefile
@@ -2,7 +2,12 @@
 -include .env
 export
 
-.PHONY: install test test-web test-swift lint format bench run-core run-audio run-poste
+# Les variables que le .env a données à ce make : `run-core` ne les passe pas au make neuf qui
+# relance le Core, pour qu'une variable retirée du .env ne survive pas à un redémarrage.
+CLES_DU_ENV := $(shell sed -n 's/^[[:space:]]*\(export[[:space:]]\{1,\}\)\{0,1\}\([A-Za-z_][A-Za-z0-9_]*\)[[:space:]]*[:?+]\{0,2\}=.*/\2/p' .env 2>/dev/null)
+COMMANDE_CORE ?= uv run uvicorn atlas_core.hub:app --host 0.0.0.0 --port 8080
+
+.PHONY: install test test-web test-swift lint format bench run-core core run-audio run-poste
 
 # Les dépendances des connecteurs (connecteurs/ et ~/.atlas/connecteurs/) s'installent après.
 install:
@@ -28,8 +33,18 @@ format:
 bench:
 	uv run python bench/bench.py
 
+# Le Core, relancé par un make neuf, qui relit le .env, chaque fois qu'il le demande en
+# laissant la marque donnees/redemarrer (le bouton « Redémarrer » de la page) ; sinon, la
+# boucle s'arrête avec lui (Ctrl-C, ou le Core qui tombe : launchd le relance sur le néo).
 run-core:
-	uv run uvicorn atlas_core.hub:app --host 0.0.0.0 --port 8080
+	@while :; do \
+	  rm -f donnees/redemarrer; \
+	  env $(addprefix -u ,$(CLES_DU_ENV)) $(MAKE) --no-print-directory core; code=$$?; \
+	  [ -f donnees/redemarrer ] || exit $$code; \
+	done
+
+core:
+	$(COMMANDE_CORE)
 
 run-audio:
 	uv run python -m atlas_audio.client
```

Modifier `src/atlas_core/hub.py` :

```diff
--- a/src/atlas_core/hub.py
+++ b/src/atlas_core/hub.py
@@ -24,6 +24,7 @@ from .cerveau_claude import CerveauClaude
 from .config import Config
 from .confirmation import Confirmations
 from .diffuseur import Diffuseur
+from .entretien import Entretien
 from .memoire import Memoire
 from .missions import Missions
 from .options_claude import options_cerveau, purger_cles_api
@@ -65,6 +66,7 @@ _reglages = lire_reglages()
 _http: httpx.AsyncClient | None = None
 _cerveau: Cerveau | None = None
 _outils: OutilsMemoire | None = None  # la mémoire et ses outils, le temps de la vie du Core
+_entretien: Entretien | None = None  # le redémarrage et la mise à jour, depuis la page
 
 RACINE_WEB = Path(__file__).resolve().parent.parent / "atlas_web"
 # Le dossier de travail de Claude : vide, à lui seul, hors de tout projet.
@@ -133,7 +135,9 @@ def ouvrir_la_memoire(config: Config) -> OutilsMemoire | None:
 
 @asynccontextmanager
 async def _cycle_de_vie(app: FastAPI):
-    global _http, _cerveau, _outils
+    global _http, _cerveau, _outils, _entretien
+    _entretien = Entretien(_regie.diffuseur.publier)
+    _entretien.effacer_la_marque()  # celle qui a fait revenir ce Core
     _http = httpx.AsyncClient()
     _cerveau = creer_cerveau(_config)
     _outils = _cerveau.outils if isinstance(_cerveau, CerveauClaude) else None
@@ -143,9 +147,10 @@ async def _cycle_de_vie(app: FastAPI):
         # Le cerveau dans son propre `try` : s'il lève (ou est annulé), le client HTTP se
         # ferme quand même, dans le `finally` qui l'entoure.
         try:
+            await _entretien.fermer()  # une mise à jour en cours s'arrête, sa commande comprise
             await _cerveau.fermer()
         finally:
-            _cerveau = _outils = None
+            _cerveau = _outils = _entretien = None
             await _http.aclose()
             _http = None
 
@@ -339,7 +344,8 @@ async def ws_web(ws: WebSocket) -> None:
             except ValueError as e:
                 abonnement.envoyer_prive(Erreur(code="message_invalide", message=str(e)))
                 continue
-            await traiter(msg, Contexte(_regie, _outils, _cerveau, abonnement, demande.page))
+            contexte = Contexte(_regie, _outils, _cerveau, abonnement, demande.page, _entretien)
+            await traiter(msg, contexte)
     except WebSocketDisconnect:
         pass
     finally:
```

Modifier `src/atlas_core/protocole_web.py` :

```diff
--- a/src/atlas_core/protocole_web.py
+++ b/src/atlas_core/protocole_web.py
@@ -260,6 +260,20 @@ class ActiverConnecteur(BaseModel):
     actif: bool
 
 
+class DemandeCore(BaseModel):
+    """La rubrique « Le Core » des Paramètres, ouverte : sa version, et la mise à jour."""
+
+    type: Literal["demande_core"] = "demande_core"
+
+
+class RedemarrerCore(BaseModel):
+    type: Literal["redemarrer_core"] = "redemarrer_core"
+
+
+class MettreAJourCore(BaseModel):
+    type: Literal["mettre_a_jour_core"] = "mettre_a_jour_core"
+
+
 Variable = Annotated[str, Field(pattern=MOTIF_VARIABLE)]
 
 
@@ -283,7 +297,10 @@ MessagePage = Annotated[
     | Arreter
     | DemandeConnecteurs
     | ActiverConnecteur
-    | ReglerConnecteur,
+    | ReglerConnecteur
+    | DemandeCore
+    | RedemarrerCore
+    | MettreAJourCore,
     Field(discriminator="type"),
 ]
 _adaptateur_page = TypeAdapter(MessagePage)
```

Modifier `src/atlas_core/routage_pages.py` :

```diff
--- a/src/atlas_core/routage_pages.py
+++ b/src/atlas_core/routage_pages.py
@@ -1,5 +1,6 @@
 """Ce que le Core fait d'un message d'une page authentifiée, sur /ws/web : une question tapée,
-le mode muet, les documents, les boutons des barres, les connecteurs et leurs réglages."""
+le mode muet, les documents, les boutons des barres, les connecteurs et leurs réglages, et
+l'entretien du Core (sa version, le redémarrage, la mise à jour)."""
 
 from __future__ import annotations
 
@@ -12,10 +13,13 @@ from .protocole_web import (
     Arreter,
     Confirmer,
     DemandeConnecteurs,
+    DemandeCore,
     DemandeDocuments,
     LireDocument,
     MessagePage,
+    MettreAJourCore,
     Muet,
+    RedemarrerCore,
     ReglerConnecteur,
     ResultatReglage,
     Saisie,
@@ -25,6 +29,7 @@ from .reglages import ReglageRefuse
 if TYPE_CHECKING:
     from .cerveau import Cerveau
     from .diffuseur import Abonnement
+    from .entretien import Entretien
     from .outils_memoire import OutilsMemoire
     from .regie import Regie
 
@@ -35,13 +40,14 @@ SANS_MEMOIRE = "La mémoire n'est pas disponible : pas de connecteurs."
 @dataclass
 class Contexte:
     """Ce dont un message a besoin : la régie, la mémoire et ses outils (None sans elle), le
-    cerveau, et la page qui l'a envoyé (son abonnement, son identifiant)."""
+    cerveau, la page qui l'a envoyé (son abonnement, son identifiant), et l'entretien."""
 
     regie: Regie
     outils: OutilsMemoire | None
     cerveau: Cerveau | None
     abonnement: Abonnement
     page: str | None
+    entretien: Entretien | None = None
 
 
 async def traiter(msg: MessagePage, ctx: Contexte) -> None:
@@ -71,6 +77,20 @@ async def traiter(msg: MessagePage, ctx: Contexte) -> None:
         ctx.regie.diffuseur.publier(liste_connecteurs(outils))  # toutes les pages
     elif isinstance(msg, ReglerConnecteur):
         _regler(msg, ctx)
+    elif ctx.entretien is not None:
+        await _entretenir(msg, ctx.entretien, ctx.abonnement)
+
+
+async def _entretenir(msg: MessagePage, entretien: Entretien, abonnement: Abonnement) -> None:
+    """La version pour la page qui la demande ; un refus aussi ; les étapes, à toutes."""
+    if isinstance(msg, DemandeCore):
+        abonnement.envoyer_prive(await entretien.etat())
+    elif isinstance(msg, RedemarrerCore):
+        if (refus := entretien.demander_redemarrage()) is not None:
+            abonnement.envoyer_prive(refus)
+    elif isinstance(msg, MettreAJourCore):
+        if (refus := await entretien.demander_mise_a_jour()) is not None:
+            abonnement.envoyer_prive(refus)
 
 
 def _regler(msg: ReglerConnecteur, ctx: Contexte) -> None:
```

- [ ] **Step 4: Vérifier que tout passe**

Run: `uv run pytest -q && uv run ruff check . --extend-exclude spikes && uv run ruff format --check . --extend-exclude spikes && node --test "tests/web/*.test.mjs"`
Expected: 1277 tests Python passent (3 de moins, et 3 ignorés, si `models/silero_vad.onnx` manque, comme dans une copie neuve), 150 tests JavaScript passent, ruff ne dit rien.

- [ ] **Step 5: Commit**

```bash
git add Makefile src/atlas_core/hub.py src/atlas_core/protocole_web.py src/atlas_core/routage_pages.py tests/test_hub_web.py tests/test_lanceur.py tests/test_protocole_web.py
git commit -F - <<'MSG'
Core : redémarrer et mettre à jour depuis la page ; make run-core relance le Core

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

### Task 6: Les réglages dans la page

Un connecteur qui a des réglages a un bouton « Réglages » dans sa ligne : un champ par réglage, jamais la valeur
d'un secret (« Défini — laisse vide pour le garder »), « Effacer » pour un secret défini, rien pour une clé d'Atlas
(« se change au Terminal ») ; « Enregistrer » n'envoie que ce qui a changé ; la réponse du Core s'affiche dessous.
Ouverts et réponses survivent aux nouveaux rendus de la liste, jusqu'à la réouverture des Paramètres.

**Files:**
- Modify: `src/atlas_web/app.js`
- Modify: `src/atlas_web/connecteurs.js`
- Modify: `src/atlas_web/documents.css`
- Create: `src/atlas_web/reglages.js`
- Modify: `tests/web/app.test.mjs`
- Modify: `tests/web/connecteurs.test.mjs`
- Create: `tests/web/reglages.test.mjs`

**Interfaces:**
- Consumes: Task 3 (`liste_connecteurs` avec `reglages`, `regler_connecteur`, `resultat_reglage`).
- Produces: `src/atlas_web/reglages.js` : `rendreReglages(document, connecteur, surRegler, resultat = null)`,
  `REGLAGES`, `ENREGISTRER`, `EFFACER`, `DEFINI`, `A_DEFINIR`, `AU_TERMINAL`, `GARDER` ; `rendreConnecteurs(document,
  conteneur, message, surBascule, reglages = {})` (`reglages` : `surRegler`, `ouverts`, `resultats`).

- [ ] **Step 1: Écrire les tests qui échouent**

Modifier `tests/web/app.test.mjs` :

```diff
--- a/tests/web/app.test.mjs
+++ b/tests/web/app.test.mjs
@@ -455,3 +455,52 @@ test("les Paramètres demandent les connecteurs, les montrent, et envoient une b
   interrupteur.declencher("change");
   assert.deepEqual(web.envoyes.at(-1), { type: "activer_connecteur", id: "poste", actif: false });
 });
+
+test("les réglages d'un connecteur partent au Core, et sa réponse s'affiche jusqu'à la réouverture", async () => {
+  FauxWebSocket.ouvertes = [];
+  await chargerPage({ stockage: fauxStockage({ "atlas.cle": "cle" }), FabriqueWebSocket: FauxWebSocket });
+  const $ = (id) => document.getElementById(id);
+  const [web] = FauxWebSocket.ouvertes;
+  web.ouvrir();
+  web.recevoir({ type: "historique", echanges: [] });
+  $("panneau-parametres").hidden = true;
+  $("ouvrir-parametres").declencher("click");
+  const nom = { variable: "ATLAS_BONJOUR_NOM", description: "Le nom", secret: false, defini: false, modifiable: true, valeur: "" };
+  const bonjour = {
+    id: "bonjour",
+    nom: "Bonjour",
+    description: "",
+    version: "0.1",
+    auteur: "Quelqu'un",
+    origine: "communaute",
+    etat: "a_configurer",
+    detail: "il manque ATLAS_BONJOUR_NOM dans le .env du Core",
+    en_attente: false,
+    reglages: [nom],
+  };
+  const regle = { ...bonjour, etat: "coupe", detail: "", reglages: [{ ...nom, defini: true, valeur: "David" }] };
+  const derniers = () => $("liste-connecteurs").children[0].children[0].children.slice(-2);
+  web.recevoir({ type: "liste_connecteurs", disponible: true, connecteurs: [bonjour] });
+  let [ouvrir, formulaire] = derniers();
+  ouvrir.declencher("click");
+  formulaire.children[0].children[0].children[2].value = "David";
+  formulaire.declencher("submit", { preventDefault() {} });
+  assert.deepEqual(web.envoyes.at(-1), {
+    type: "regler_connecteur",
+    id: "bonjour",
+    valeurs: { ATLAS_BONJOUR_NOM: "David" },
+    effacer: [],
+  });
+  web.recevoir({ type: "resultat_reglage", id: "bonjour", ok: true, message: "Enregistré." });
+  [, formulaire] = derniers();
+  assert.deepEqual([formulaire.hidden, formulaire.children.at(-1).textContent], [false, "Enregistré."]);
+  web.recevoir({ type: "liste_connecteurs", disponible: true, connecteurs: [regle] });
+  [, formulaire] = derniers();
+  assert.equal(formulaire.children.at(-1).textContent, "Enregistré.", "toujours là, la liste à jour");
+  $("ouvrir-parametres").declencher("click"); // referme les Paramètres
+  $("ouvrir-parametres").declencher("click"); // les rouvre
+  web.recevoir({ type: "liste_connecteurs", disponible: true, connecteurs: [regle] });
+  [, formulaire] = derniers();
+  assert.equal(formulaire.hidden, true, "une liste fermée");
+  assert.ok(!formulaire.children.some((e) => e.className.startsWith("resultat")), "sans vieux message");
+});
```

Modifier `tests/web/connecteurs.test.mjs` :

```diff
--- a/tests/web/connecteurs.test.mjs
+++ b/tests/web/connecteurs.test.mjs
@@ -137,3 +137,35 @@ test("sans mémoire, ou sans connecteur, la rubrique le dit", () => {
   assert.equal(rendre([], false).conteneur.children[0].textContent, MEMOIRE_ABSENTE);
   assert.equal(rendre([]).conteneur.children[0].textContent, AUCUN_CONNECTEUR);
 });
+
+test("un connecteur qui a des réglages les ouvre d'un bouton, et les garde ouverts d'un rendu à l'autre", () => {
+  const document = fauxDocument();
+  const conteneur = document.createElement("div");
+  const reglage = { variable: "ATLAS_BONJOUR_NOM", description: "Le nom", secret: false, defini: false, modifiable: true, valeur: "" };
+  const bonjour = { ...METEO, id: "bonjour", reglages: [reglage] };
+  const envois = [];
+  const etat = { ouverts: new Set(), resultats: new Map(), surRegler: (...envoi) => envois.push(envoi) };
+  const rendu = () => {
+    rendreConnecteurs(document, conteneur, { disponible: true, connecteurs: [POSTE, bonjour] }, () => {}, etat);
+    return lignes(conteneur).map(morceaux);
+  };
+  let [poste, ligne] = rendu();
+  assert.ok(!poste.reste.some((e) => e.className === "ouvrir-reglages"), "sans réglages, pas de bouton");
+  let [ouvrir, formulaire] = ligne.reste.slice(-2);
+  assert.deepEqual([ouvrir.textContent, ouvrir.type, formulaire.tagName], ["Réglages", "button", "FORM"]);
+  assert.deepEqual([formulaire.hidden, ouvrir.attributs["aria-expanded"]], [true, "false"]);
+  ouvrir.declencher("click");
+  assert.deepEqual([formulaire.hidden, ouvrir.attributs["aria-expanded"]], [false, "true"]);
+  etat.resultats.set("bonjour", { ok: true, message: "Enregistré." });
+  [, ligne] = rendu();
+  [ouvrir, formulaire] = ligne.reste.slice(-2);
+  assert.equal(formulaire.hidden, false, "toujours ouvert après un nouveau rendu");
+  assert.equal(formulaire.children.at(-1).textContent, "Enregistré.");
+  formulaire.children[0].children[0].children[2].value = "David";
+  formulaire.declencher("submit", { preventDefault() {} });
+  assert.deepEqual(envois, [["bonjour", { ATLAS_BONJOUR_NOM: "David" }, []]]);
+  ouvrir.declencher("click");
+  assert.equal(etat.ouverts.has("bonjour"), false);
+  [, ligne] = rendu();
+  assert.equal(ligne.reste.at(-1).hidden, true, "refermé, il le reste");
+});
```

Créer `tests/web/reglages.test.mjs` :

```javascript
import assert from "node:assert/strict";
import { test } from "node:test";

import { AU_TERMINAL, EFFACER, ENREGISTRER, GARDER, rendreReglages } from "../../src/atlas_web/reglages.js";
import { fauxDocument } from "./faux_dom.mjs";

const NOM = {
  variable: "ATLAS_BONJOUR_NOM",
  description: "Le nom à saluer",
  secret: false,
  defini: true,
  modifiable: true,
  valeur: "David",
};
const CLE = {
  variable: "ATLAS_BONJOUR_CLE",
  description: "La clé du service",
  secret: true,
  defini: true,
  modifiable: true,
  valeur: "",
};
const POSTE = {
  variable: "ATLAS_POSTE_CLE",
  description: "La clé du poste",
  secret: true,
  defini: true,
  modifiable: false,
  valeur: "",
};

function rendre(reglages, resultat = null) {
  const envois = [];
  const formulaire = rendreReglages(
    fauxDocument(),
    { id: "bonjour", reglages },
    (id, valeurs, effacer) => envois.push([id, valeurs, effacer]),
    resultat,
  );
  return { formulaire, envois };
}

// Chaque ligne : [étiquette (description, variable, champ), bouton « Effacer » ou statut].
function champ(formulaire, n) {
  return formulaire.children[n].children[0].children[2];
}

function enregistrer(formulaire) {
  formulaire.declencher("submit", { preventDefault() {} });
}

test("un réglage ordinaire montre sa valeur ; un secret, jamais", () => {
  const { formulaire } = rendre([NOM, { ...CLE, valeur: "fuite" }]);
  const [nom, cle] = [champ(formulaire, 0), champ(formulaire, 1)];
  assert.deepEqual([nom.type, nom.value], ["text", "David"]);
  assert.deepEqual([cle.type, cle.value], ["password", ""]);
  assert.equal(cle.attributs.placeholder, GARDER);
  assert.equal(cle.attributs.autocomplete, "off");
  const [description, variable] = formulaire.children[0].children[0].children;
  assert.deepEqual([description.textContent, variable.textContent], ["Le nom à saluer", "ATLAS_BONJOUR_NOM"]);
  assert.equal(formulaire.children.at(-1).textContent, ENREGISTRER);
});

test("« Enregistrer » n'envoie que ce qui a changé", () => {
  const { formulaire, envois } = rendre([NOM, CLE]);
  enregistrer(formulaire);
  assert.deepEqual(envois, [], "rien de changé : rien d'envoyé");
  champ(formulaire, 1).value = "sésame";
  enregistrer(formulaire);
  assert.deepEqual(envois.at(-1), ["bonjour", { ATLAS_BONJOUR_CLE: "sésame" }, []]);
  champ(formulaire, 0).value = "Camille";
  champ(formulaire, 1).value = "";
  enregistrer(formulaire);
  assert.deepEqual(envois.at(-1), ["bonjour", { ATLAS_BONJOUR_NOM: "Camille" }, []], "un secret vide est gardé");
  champ(formulaire, 0).value = "";
  enregistrer(formulaire);
  assert.deepEqual(envois.at(-1), ["bonjour", {}, ["ATLAS_BONJOUR_NOM"]], "un réglage vidé est effacé");
});

test("un réglage vide jamais défini ne s'efface pas", () => {
  const { formulaire, envois } = rendre([{ ...NOM, defini: false, valeur: "" }]);
  enregistrer(formulaire);
  assert.deepEqual(envois, []);
});

test("un secret défini s'efface d'un bouton ; un secret à définir n'en a pas", () => {
  const { formulaire, envois } = rendre([CLE, { ...CLE, variable: "ATLAS_AUTRE", defini: false }]);
  const effacer = formulaire.children[0].children[1];
  assert.deepEqual([effacer.textContent, effacer.type], [EFFACER, "button"]);
  effacer.declencher("click");
  assert.deepEqual(envois, [["bonjour", {}, ["ATLAS_BONJOUR_CLE"]]]);
  assert.equal(formulaire.children[1].children.length, 1, "pas de bouton");
  assert.equal(champ(formulaire, 1).attributs.placeholder, "À définir");
});

test("une clé d'Atlas n'a pas de champ : elle se change au Terminal", () => {
  const { formulaire, envois } = rendre([POSTE]);
  const [etiquette, statut] = formulaire.children[0].children;
  assert.equal(etiquette.children.length, 2, "ni champ, ni valeur");
  assert.equal(statut.textContent, `Défini, ${AU_TERMINAL}`);
  assert.equal(formulaire.children.length, 1, "rien à enregistrer");
  enregistrer(formulaire);
  assert.deepEqual(envois, []);
});

test("la réponse du Core s'affiche sous le formulaire", () => {
  const ok = rendre([NOM], { ok: true, message: "Enregistré." }).formulaire.children.at(-1);
  assert.deepEqual([ok.className, ok.textContent], ["resultat ok", "Enregistré."]);
  const message = "ATLAS_BONJOUR_NOM : pas d'espace au début ni à la fin.";
  const refus = rendre([NOM], { ok: false, message }).formulaire.children.at(-1);
  assert.deepEqual([refus.className, refus.textContent], ["resultat refus", message]);
});

test("les textes d'un manifeste restent du texte", () => {
  const { formulaire } = rendre([{ ...NOM, description: "<b>Nom</b>" }]);
  assert.equal(formulaire.children[0].children[0].children[0].textContent, "<b>Nom</b>");
});
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `node --test tests/web/reglages.test.mjs tests/web/connecteurs.test.mjs tests/web/app.test.mjs`
Expected: FAIL — `reglages.js` introuvable, et 2 tests des connecteurs et de la page qui échouent.

- [ ] **Step 3: Écrire le formulaire**

Modifier `src/atlas_web/app.js` :

```diff
--- a/src/atlas_web/app.js
+++ b/src/atlas_web/app.js
@@ -64,6 +64,20 @@ const sousTitres = { conteneur: $("sous-titres"), question: $("st-question"), re
 
 // --- La connexion -----------------------------------------------------------------
 
+// Les réglages des connecteurs : ceux qui sont ouverts, et la dernière réponse du Core pour
+// chacun, survivent aux nouveaux rendus de la liste (après chaque bascule ou réglage).
+const reglages = {
+  ouverts: new Set(),
+  resultats: new Map(),
+  surRegler: (id, valeurs, effacer) => connexion.envoyer({ type: "regler_connecteur", id, valeurs, effacer }),
+};
+let listeConnecteurs = null;
+
+function montrerConnecteurs() {
+  const surBascule = (id, actif) => connexion.envoyer({ type: "activer_connecteur", id, actif });
+  rendreConnecteurs(document, $("liste-connecteurs"), listeConnecteurs, surBascule, reglages);
+}
+
 const connexion = new Connexion({
   url: `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/web`,
   lireCle: () => cleEnMemoire ?? lireStockage(stockage, CLE_STOCKAGE),
@@ -76,9 +90,12 @@ const connexion = new Connexion({
     }
     if (TOUCHENT_DOCUMENTS.has(message.type)) surDocuments(message);
     if (message.type === "liste_connecteurs") {
-      rendreConnecteurs(document, $("liste-connecteurs"), message, (id, actif) =>
-        connexion.envoyer({ type: "activer_connecteur", id, actif }),
-      );
+      listeConnecteurs = message;
+      montrerConnecteurs();
+    }
+    if (message.type === "resultat_reglage") {
+      reglages.resultats.set(message.id, message);
+      if (listeConnecteurs) montrerConnecteurs();
     }
     if (message.type === "confirmation" || message.type === "confirmation_finie") {
       afficherConfirmation(message.texte, message.type === "confirmation");
@@ -240,6 +257,8 @@ $("retour-documents").addEventListener("click", montrerLaListe);
 
 function ouvrirParametres() {
   connexion.envoyer({ type: "connecteurs" }); // relus à chaque ouverture : un dossier a pu être déposé
+  reglages.ouverts.clear(); // chaque ouverture repart d'une liste fermée, sans vieux message
+  reglages.resultats.clear();
   const commun = { document, stockage, scene: () => sceneCourante };
   galeries = [
     ouvrirGalerie({
```

Modifier `src/atlas_web/connecteurs.js` :

```diff
--- a/src/atlas_web/connecteurs.js
+++ b/src/atlas_web/connecteurs.js
@@ -1,6 +1,8 @@
 // La rubrique « Connecteurs » des Paramètres (spec des connecteurs, §6) : chaque connecteur,
-// son état et son interrupteur. Les textes d'un manifeste viennent d'un tiers : ils ne sont
-// jamais que du texte.
+// son état, son interrupteur et ses réglages. Les textes d'un manifeste viennent d'un tiers :
+// ils ne sont jamais que du texte.
+
+import { REGLAGES, rendreReglages } from "./reglages.js";
 
 export const MEMOIRE_ABSENTE = "La mémoire n'est pas disponible : pas de connecteurs.";
 export const AUCUN_CONNECTEUR = "Aucun connecteur trouvé.";
@@ -30,7 +32,11 @@ function bouton(document, classe, contenu) {
 }
 
 // La liste (message `liste_connecteurs`) ; `surBascule(id, actif)` envoie l'interrupteur au Core.
-export function rendreConnecteurs(document, conteneur, message, surBascule) {
+// `reglages` : `surRegler(id, valeurs, effacer)`, et ce qui survit à un nouveau rendu de la
+// liste : les réglages ouverts (`ouverts`, des identifiants) et les dernières réponses du Core
+// (`resultats`, par identifiant).
+export function rendreConnecteurs(document, conteneur, message, surBascule, reglages = {}) {
+  const { surRegler = () => {}, ouverts = new Set(), resultats = new Map() } = reglages;
   if (!message.disponible) {
     conteneur.replaceChildren(texte(document, "p", "vide", MEMOIRE_ABSENTE));
     return;
@@ -41,10 +47,31 @@ export function rendreConnecteurs(document, conteneur, message, surBascule) {
   }
   const liste = document.createElement("ul");
   liste.className = "connecteurs";
-  liste.append(...message.connecteurs.map((connecteur) => ligne(document, connecteur, surBascule)));
+  for (const connecteur of message.connecteurs) {
+    const element = ligne(document, connecteur, surBascule);
+    if (connecteur.reglages?.length) {
+      element.append(...lesReglages(document, connecteur, surRegler, ouverts, resultats));
+    }
+    liste.append(element);
+  }
   conteneur.replaceChildren(liste);
 }
 
+// Le bouton « Réglages » et son formulaire, ouvert ou fermé comme avant le nouveau rendu.
+function lesReglages(document, connecteur, surRegler, ouverts, resultats) {
+  const ouvrir = bouton(document, "ouvrir-reglages", REGLAGES);
+  const formulaire = rendreReglages(document, connecteur, surRegler, resultats.get(connecteur.id));
+  const montrer = (ouvert) => {
+    formulaire.hidden = !ouvert;
+    ouvrir.setAttribute("aria-expanded", String(ouvert));
+    if (ouvert) ouverts.add(connecteur.id);
+    else ouverts.delete(connecteur.id);
+  };
+  montrer(ouverts.has(connecteur.id));
+  ouvrir.addEventListener("click", () => montrer(formulaire.hidden));
+  return [ouvrir, formulaire];
+}
+
 function ligne(document, connecteur, surBascule) {
   const element = document.createElement("li");
   element.className = "connecteur";
```

Modifier `src/atlas_web/documents.css` :

```diff
--- a/src/atlas_web/documents.css
+++ b/src/atlas_web/documents.css
@@ -279,3 +279,70 @@
   border-color: var(--accent);
   color: #02030a;
 }
+
+/* Les réglages d'un connecteur : un champ chacun ; la valeur d'un secret n'y est jamais. */
+#liste-connecteurs .ouvrir-reglages {
+  margin-top: 6px;
+  font-size: 12px;
+  color: var(--accent);
+}
+
+#liste-connecteurs .reglages {
+  margin-top: 8px;
+  padding: 10px 12px;
+  border-radius: 12px;
+  border: 1px solid var(--bord);
+}
+
+#liste-connecteurs .reglage label {
+  display: flex;
+  flex-direction: column;
+  gap: 4px;
+  font-size: 13px;
+}
+
+#liste-connecteurs .reglage + .reglage {
+  margin-top: 10px;
+}
+
+#liste-connecteurs .reglage .variable,
+#liste-connecteurs .reglage .statut {
+  font-size: 11px;
+  color: var(--texte-doux);
+}
+
+#liste-connecteurs .reglage input {
+  padding: 8px 12px;
+  border-radius: 10px;
+  border: 1px solid var(--bord);
+  background: var(--verre);
+  color: var(--texte);
+  font: inherit;
+}
+
+#liste-connecteurs .reglage input:focus {
+  outline: none;
+  border-color: rgba(251, 191, 36, 0.6);
+}
+
+#liste-connecteurs .reglages button {
+  margin: 8px 8px 0 0;
+  padding: 6px 14px;
+  border-radius: 16px;
+  border: 1px solid var(--bord);
+}
+
+#liste-connecteurs .reglages .enregistrer {
+  background: var(--accent);
+  border-color: var(--accent);
+  color: #02030a;
+}
+
+#liste-connecteurs .reglages .resultat {
+  font-size: 12px;
+  color: var(--accent);
+}
+
+#liste-connecteurs .reglages .resultat.refus {
+  color: var(--erreur);
+}
```

Créer `src/atlas_web/reglages.js` :

```javascript
// Les réglages d'un connecteur, dans sa ligne des Paramètres (spec des réglages et du Core, §4) :
// un champ par réglage. La valeur d'un secret n'arrive jamais dans la page : elle dit seulement
// s'il est défini, et un champ masqué le remplace. Le Core vérifie tout.

export const REGLAGES = "Réglages";
export const ENREGISTRER = "Enregistrer";
export const EFFACER = "Effacer";
export const DEFINI = "Défini";
export const A_DEFINIR = "À définir";
export const AU_TERMINAL = "se change au Terminal";
export const GARDER = "Défini — laisse vide pour le garder";

function texte(document, balise, classe, contenu) {
  const element = document.createElement(balise);
  element.className = classe;
  element.textContent = contenu;
  return element;
}

// Le formulaire ; `surRegler(id, valeurs, effacer)` envoie au Core ce qui a changé ;
// `resultat` : la réponse du Core au dernier envoi pour ce connecteur ({ ok, message }).
export function rendreReglages(document, connecteur, surRegler, resultat = null) {
  const formulaire = document.createElement("form");
  formulaire.className = "reglages";
  const champs = [];
  for (const reglage of connecteur.reglages) {
    const ligne = document.createElement("div");
    ligne.className = "reglage";
    const etiquette = document.createElement("label");
    etiquette.append(
      texte(document, "span", "description", reglage.description),
      texte(document, "span", "variable", reglage.variable),
    );
    ligne.append(etiquette);
    formulaire.append(ligne);
    if (!reglage.modifiable) {
      // Une clé d'Atlas : jamais de champ, quoi que dise le manifeste.
      const statut = `${reglage.defini ? DEFINI : A_DEFINIR}, ${AU_TERMINAL}`;
      ligne.append(texte(document, "p", "statut", statut));
      continue;
    }
    const champ = document.createElement("input");
    champ.type = reglage.secret ? "password" : "text";
    champ.value = reglage.secret ? "" : reglage.valeur;
    champ.setAttribute("autocomplete", "off");
    champ.setAttribute("spellcheck", "false");
    if (reglage.secret) champ.setAttribute("placeholder", reglage.defini ? GARDER : A_DEFINIR);
    etiquette.append(champ);
    champs.push({ reglage, champ });
    if (reglage.secret && reglage.defini) {
      const effacer = texte(document, "button", "effacer", EFFACER);
      effacer.type = "button";
      effacer.addEventListener("click", () => surRegler(connecteur.id, {}, [reglage.variable]));
      ligne.append(effacer);
    }
  }
  if (champs.length) {
    const enregistrer = texte(document, "button", "enregistrer", ENREGISTRER);
    enregistrer.type = "submit";
    formulaire.append(enregistrer);
  }
  if (resultat) {
    formulaire.append(texte(document, "p", `resultat ${resultat.ok ? "ok" : "refus"}`, resultat.message));
  }
  formulaire.addEventListener("submit", (evenement) => {
    evenement.preventDefault();
    const valeurs = {};
    const effacer = [];
    for (const { reglage, champ } of champs) {
      if (reglage.secret) {
        if (champ.value !== "") valeurs[reglage.variable] = champ.value; // vide : on garde
      } else if (champ.value === "") {
        if (reglage.defini) effacer.push(reglage.variable);
      } else if (champ.value !== reglage.valeur) {
        valeurs[reglage.variable] = champ.value;
      }
    }
    if (Object.keys(valeurs).length || effacer.length) surRegler(connecteur.id, valeurs, effacer);
  });
  return formulaire;
}
```

- [ ] **Step 4: Vérifier que tout passe**

Run: `uv run pytest -q && uv run ruff check . --extend-exclude spikes && uv run ruff format --check . --extend-exclude spikes && node --test "tests/web/*.test.mjs"`
Expected: 1277 tests Python passent (3 de moins, et 3 ignorés, si `models/silero_vad.onnx` manque, comme dans une copie neuve), 159 tests JavaScript passent, ruff ne dit rien.

- [ ] **Step 5: Commit**

```bash
git add src/atlas_web/app.js src/atlas_web/connecteurs.js src/atlas_web/documents.css src/atlas_web/reglages.js tests/web/app.test.mjs tests/web/connecteurs.test.mjs tests/web/reglages.test.mjs
git commit -F - <<'MSG'
Page : les réglages des connecteurs

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

### Task 7: La rubrique « Le Core »

En bas des Paramètres : la version, « Redémarrer » et « Mettre à jour et redémarrer » (grisé, avec la raison, s'il
n'est pas possible), chacun confirmé ; les étapes, les nouveautés et la fin, dans toutes les pages. Pendant un
redémarrage, la barre du haut dit « Redémarrage du Core… », puis « Le Core ne revient pas » au bout d'une minute ; le
Core revenu, la page redemande sa version. Review Focus 5 : un Core lancé sans la boucle ne revient pas, et la page
le dit.

**Files:**
- Modify: `src/atlas_web/app.js`
- Create: `src/atlas_web/core.js`
- Modify: `src/atlas_web/documents.css`
- Modify: `src/atlas_web/index.html`
- Modify: `tests/web/app.test.mjs`
- Create: `tests/web/core.test.mjs`

**Interfaces:**
- Consumes: Task 4 et 5 (`etat_core`, `core_en_cours`, `fin_core` ; `demande_core`, `redemarrer_core`,
  `mettre_a_jour_core`).
- Produces: `src/atlas_web/core.js` : `SuiviCore({ envoyer, surChangement, planifier, annuler })` (`etat`,
  `demander()`, `recevoir(message)`, `surStatut(statut)`, `libelle()`), `rendreCore(document, conteneur, etat,
  surAction)`, `CONFIRMATIONS`, `REDEMARRAGE`, `NE_REVIENT_PAS`, `NE_REVIENT_PAS_DETAIL`, `DELAI_RETOUR_MS` ;
  `#rubrique-core` dans `index.html`.

- [ ] **Step 1: Écrire les tests qui échouent**

Modifier `tests/web/app.test.mjs` :

```diff
--- a/tests/web/app.test.mjs
+++ b/tests/web/app.test.mjs
@@ -38,6 +38,7 @@ const IDENTIFIANTS = [
   "parler",
   "pastille",
   "retour-documents",
+  "rubrique-core",
   "saisie",
   "sous-titres",
   "st-question",
@@ -82,7 +83,7 @@ function canevasSain() {
   return { width: 4, height: 4, clientWidth: 4, clientHeight: 4, getContext: () => ctx };
 }
 
-function fauxDocumentDeLaPage() {
+function fauxDocumentDeLaPage({ fondSain = false } = {}) {
   const elements = {};
   for (const id of IDENTIFIANTS) {
     const element = fauxElement("div");
@@ -91,7 +92,7 @@ function fauxDocumentDeLaPage() {
     element.focus = () => {};
     elements[id] = element;
   }
-  elements.fond = canevasQuiLeve();
+  elements.fond = fondSain ? canevasSain() : canevasQuiLeve();
   elements.orbe = canevasSain();
   const ecouteurs = {};
   return {
@@ -101,7 +102,7 @@ function fauxDocumentDeLaPage() {
       if (!element) throw new Error(`identifiant absent du faux document : ${id}`);
       return element;
     },
-    createElement: (tag) => fauxElement(tag),
+    createElement: (tag) => (fondSain && tag === "canvas" ? canevasSain() : fauxElement(tag)),
     querySelectorAll: () => [],
     querySelector: () => null,
     addEventListener(type, rappel) {
@@ -113,11 +114,12 @@ function fauxDocumentDeLaPage() {
   };
 }
 
-// Charge app.js dans un faux navigateur, avec un fond dont le dessin lève à chaque image.
-// Rend la file des rappels que le vrai navigateur aurait donnés à requestAnimationFrame.
-async function chargerPage({ stockage = fauxStockage(), FabriqueWebSocket } = {}) {
+// Charge app.js dans un faux navigateur, avec un fond dont le dessin lève à chaque image (sauf
+// `fondSain` : l'image va alors jusqu'à la barre du haut). Rend la file des rappels que le vrai
+// navigateur aurait donnés à requestAnimationFrame.
+async function chargerPage({ stockage = fauxStockage(), FabriqueWebSocket, fondSain = false } = {}) {
   const file = [];
-  globalThis.document = fauxDocumentDeLaPage();
+  globalThis.document = fauxDocumentDeLaPage({ fondSain });
   globalThis.window = { localStorage: stockage, matchMedia: () => ({ matches: false }) };
   globalThis.WebSocket = FabriqueWebSocket;
   globalThis.location = { protocol: "http:", host: "atlas.test" };
@@ -432,7 +434,7 @@ test("les Paramètres demandent les connecteurs, les montrent, et envoient une b
   web.recevoir({ type: "historique", echanges: [] }); // ce que le Core envoie à chaque connexion
   $("panneau-parametres").hidden = true; // fermé, comme au chargement de la vraie page
   $("ouvrir-parametres").declencher("click");
-  assert.deepEqual(web.envoyes.at(-1), { type: "connecteurs" });
+  assert.deepEqual(web.envoyes.slice(-2), [{ type: "connecteurs" }, { type: "demande_core" }]);
   const poste = {
     id: "poste",
     nom: "Le poste du Mac",
@@ -504,3 +506,48 @@ test("les réglages d'un connecteur partent au Core, et sa réponse s'affiche ju
   assert.equal(formulaire.hidden, true, "une liste fermée");
   assert.ok(!formulaire.children.some((e) => e.className.startsWith("resultat")), "sans vieux message");
 });
+
+test("le Core se redémarre depuis les Paramètres, et la barre du haut suit son retour", async (t) => {
+  t.mock.timers.enable({ apis: ["setTimeout"] });
+  FauxWebSocket.ouvertes = [];
+  const stockage = fauxStockage({ "atlas.cle": "cle" });
+  const file = await chargerPage({ stockage, FabriqueWebSocket: FauxWebSocket, fondSain: true });
+  const $ = (id) => document.getElementById(id);
+  const image = () => file[0](0); // l'image de la page (les galeries ont aussi les leurs)
+  const [web] = FauxWebSocket.ouvertes;
+  web.ouvrir();
+  web.recevoir({ type: "historique", echanges: [] });
+  $("panneau-parametres").hidden = true;
+  $("ouvrir-parametres").declencher("click");
+  assert.deepEqual(web.envoyes.at(-1), { type: "demande_core" });
+  web.recevoir({
+    type: "etat_core",
+    version: "ce65d2a",
+    date: "2026-09-29",
+    occupe: false,
+    mise_a_jour_possible: true,
+    raison: "",
+  });
+  const [version, boutons, confirmation] = $("rubrique-core").children;
+  assert.equal(version.textContent, "Version ce65d2a, du 2026-09-29");
+  boutons.children[0].declencher("click"); // « Redémarrer »
+  confirmation.children[1].declencher("click"); // « Confirmer »
+  assert.deepEqual(web.envoyes.at(-1), { type: "redemarrer_core" });
+
+  web.recevoir({ type: "core_en_cours", etape: "redemarrage", texte: "Redémarrage du Core…", nouveautes: [] });
+  web.onclose({ code: 1012 }); // le Core s'arrête
+  image();
+  assert.equal($("libelle-etat").textContent, "Redémarrage du Core…");
+  t.mock.timers.tick(60000);
+  image();
+  assert.equal($("libelle-etat").textContent, "Le Core ne revient pas");
+  assert.match($("rubrique-core").children.at(-1).textContent, /donnees\/logs\/core\.log/);
+
+  const nouvelle = FauxWebSocket.ouvertes.at(-1); // la page a retenté entre-temps
+  assert.notEqual(nouvelle, web);
+  nouvelle.ouvrir();
+  nouvelle.recevoir({ type: "historique", echanges: [] });
+  assert.deepEqual(nouvelle.envoyes.at(-1), { type: "demande_core" }, "la version, revenue");
+  image();
+  assert.notEqual($("libelle-etat").textContent, "Le Core ne revient pas");
+});
```

Créer `tests/web/core.test.mjs` :

```javascript
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  CONFIRMATIONS,
  DELAI_RETOUR_MS,
  NE_REVIENT_PAS,
  NE_REVIENT_PAS_DETAIL,
  REDEMARRAGE,
  SuiviCore,
  rendreCore,
} from "../../src/atlas_web/core.js";
import { fauxDocument } from "./faux_dom.mjs";

const VERSION = {
  type: "etat_core",
  version: "ce65d2a",
  date: "2026-09-29",
  occupe: false,
  mise_a_jour_possible: true,
  raison: "",
};

function rendre(etat) {
  const document = fauxDocument();
  const conteneur = document.createElement("div");
  const actions = [];
  rendreCore(document, conteneur, etat, (type) => actions.push(type));
  const par = (classe) => conteneur.children.find((e) => e.className === classe);
  const [redemarrer, mettreAJour] = par("boutons").children;
  return { conteneur, par, redemarrer, mettreAJour, actions };
}

test("la version qui tourne, et deux boutons qui demandent confirmation", () => {
  const { par, redemarrer, mettreAJour, actions } = rendre({ version: VERSION, enCours: null, fin: null });
  assert.equal(par("version").textContent, "Version ce65d2a, du 2026-09-29");
  assert.deepEqual([redemarrer.disabled, mettreAJour.disabled], [false, false]);
  const confirmation = par("confirmation-core");
  assert.equal(confirmation.hidden, true);
  mettreAJour.declencher("click");
  assert.deepEqual([confirmation.hidden, confirmation.children[0].textContent], [false, CONFIRMATIONS.mettre_a_jour_core]);
  confirmation.children[2].declencher("click"); // Annuler
  assert.deepEqual([confirmation.hidden, actions], [true, []]);
  redemarrer.declencher("click");
  assert.equal(confirmation.children[0].textContent, CONFIRMATIONS.redemarrer_core);
  confirmation.children[1].declencher("click"); // Confirmer
  assert.deepEqual([confirmation.hidden, actions], [true, ["redemarrer_core"]]);
});

test("la mise à jour impossible est grisée, avec sa raison", () => {
  const raison = "Le dépôt du Core est sur la branche essai, pas sur main : mets-le à jour au Terminal.";
  const version = { ...VERSION, mise_a_jour_possible: false, raison };
  const { par, redemarrer, mettreAJour } = rendre({ version, enCours: null, fin: null });
  assert.deepEqual([redemarrer.disabled, mettreAJour.disabled], [false, true]);
  assert.equal(par("raison").textContent, raison);
});

test("avant la version, ou pendant une étape, les boutons attendent", () => {
  let { par, redemarrer, mettreAJour } = rendre({ version: null, enCours: null, fin: null });
  assert.equal(par("version").textContent, "Version…");
  assert.deepEqual([redemarrer.disabled, mettreAJour.disabled], [true, true]);
  const enCours = { etape: "installation", texte: "Installation…", nouveautes: ["Deux", "Un"] };
  ({ par, redemarrer, mettreAJour } = rendre({ version: VERSION, enCours, fin: null }));
  assert.deepEqual([redemarrer.disabled, mettreAJour.disabled], [true, true]);
  assert.equal(par("etape").textContent, "Installation…");
  assert.deepEqual(par("nouveautes").children.map((li) => li.textContent), ["Deux", "Un"]);
  ({ redemarrer } = rendre({ version: { ...VERSION, occupe: true }, enCours: null, fin: null }));
  assert.equal(redemarrer.disabled, true, "occupé par une autre page");
});

test("la fin : le texte, et les dernières lignes d'une erreur, comme du texte", () => {
  const fin = { ok: false, texte: "La récupération a échoué : rien n'a changé.", details: ["fatal: <b>", "x"] };
  const { par } = rendre({ version: VERSION, enCours: null, fin });
  assert.equal(par("fin refus").textContent, fin.texte);
  assert.equal(par("details").textContent, "fatal: <b>\nx");
  const ok = rendre({ version: VERSION, enCours: null, fin: { ok: true, texte: "Atlas est déjà à jour.", details: [] } });
  assert.equal(ok.par("fin ok").textContent, "Atlas est déjà à jour.");
  assert.equal(ok.par("details"), undefined);
});

function suivi() {
  const envois = [];
  const minuteurs = [];
  let changements = 0;
  const s = new SuiviCore({
    envoyer: (message) => envois.push(message),
    surChangement: () => (changements += 1),
    planifier: (rappel, delai) => minuteurs.push({ rappel, delai, annule: false }) - 1,
    annuler: (n) => {
      if (n !== null && n !== undefined) minuteurs[n].annule = true;
    },
  });
  return { s, envois, minuteurs, changements: () => changements };
}

test("le suivi range la version, les étapes et la fin ; une fin redemande la version", () => {
  const { s, envois, changements } = suivi();
  s.recevoir({ type: "question", texte: "Bonjour", source: "clavier" });
  assert.equal(changements(), 0, "pas un message du Core");
  s.recevoir(VERSION);
  assert.equal(s.etat.version, VERSION);
  const enCours = { type: "core_en_cours", etape: "recuperation", texte: "Récupération…", nouveautes: [] };
  s.recevoir(enCours);
  assert.equal(s.etat.enCours, enCours);
  const fin = { type: "fin_core", ok: true, texte: "Atlas est déjà à jour.", details: [] };
  s.recevoir(fin);
  assert.deepEqual([s.etat.enCours, s.etat.fin], [null, fin]);
  assert.deepEqual(envois, [{ type: "demande_core" }]);
  assert.equal(changements(), 3);
  assert.equal(s.libelle(), null, "aucun redémarrage : la barre dit son statut habituel");
  s.recevoir(enCours); // une autre mise à jour : l'ancienne fin s'efface
  assert.deepEqual([s.etat.enCours, s.etat.fin], [enCours, null]);
});

test("pendant un redémarrage, la barre le dit ; le Core revenu, la version se redemande", () => {
  const { s, envois, minuteurs } = suivi();
  s.recevoir({ type: "core_en_cours", etape: "redemarrage", texte: REDEMARRAGE, nouveautes: [] });
  assert.equal(minuteurs[0].delai, DELAI_RETOUR_MS);
  assert.equal(s.libelle(), REDEMARRAGE);
  s.surStatut("en_ligne"); // encore l'ancienne connexion : pas un retour
  assert.equal(s.libelle(), REDEMARRAGE);
  s.surStatut("hors_ligne");
  s.surStatut("connexion");
  s.surStatut("en_ligne");
  assert.equal(s.libelle(), null);
  assert.equal(minuteurs[0].annule, true);
  assert.deepEqual([s.etat.enCours, s.etat.fin, envois], [null, null, [{ type: "demande_core" }]]);
});

test("un Core qui ne revient pas au bout d'une minute, la page le dit", () => {
  const { s, minuteurs } = suivi();
  s.recevoir({ type: "core_en_cours", etape: "redemarrage", texte: REDEMARRAGE, nouveautes: [] });
  s.surStatut("hors_ligne");
  minuteurs[0].rappel();
  assert.equal(s.libelle(), NE_REVIENT_PAS);
  assert.deepEqual(s.etat.fin, { ok: false, texte: NE_REVIENT_PAS_DETAIL, details: [] });
  s.surStatut("en_ligne"); // il finit par revenir
  assert.deepEqual([s.libelle(), s.etat.fin], [null, null]);
});
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `node --test tests/web/core.test.mjs tests/web/app.test.mjs`
Expected: FAIL — `core.js` introuvable, et 2 tests de la page qui échouent.

- [ ] **Step 3: Écrire la rubrique**

Modifier `src/atlas_web/app.js` :

```diff
--- a/src/atlas_web/app.js
+++ b/src/atlas_web/app.js
@@ -2,6 +2,7 @@
 
 import { rendreConnecteurs } from "./connecteurs.js";
 import { Connexion, identifiantDePage } from "./connexion.js";
+import { SuiviCore, rendreCore } from "./core.js";
 import { dimensionner, rgba } from "./dessin.js";
 import { rendreDocument, rendreListeDocuments } from "./documents.js";
 import { LIBELLES, appliquerMessage, avancer, creerEtat, sceneDe } from "./etat.js";
@@ -78,12 +79,20 @@ function montrerConnecteurs() {
   rendreConnecteurs(document, $("liste-connecteurs"), listeConnecteurs, surBascule, reglages);
 }
 
+// Le Core : sa version, ses deux boutons, les étapes ; et son retour, attendu après un redémarrage.
+const suiviCore = new SuiviCore({ envoyer: (message) => connexion.envoyer(message), surChangement: montrerCore });
+
+function montrerCore() {
+  rendreCore(document, $("rubrique-core"), suiviCore.etat, (type) => connexion.envoyer({ type }));
+}
+
 const connexion = new Connexion({
   url: `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/web`,
   lireCle: () => cleEnMemoire ?? lireStockage(stockage, CLE_STOCKAGE),
   entree: () => ({ page }),
   surMessage(message) {
     appliquerMessage(etat, message, Date.now());
+    suiviCore.recevoir(message);
     if (message.type === "muet") $("muet").checked = message.actif;
     if (TOUCHENT_HISTORIQUE.has(message.type) && !$("panneau-historique").hidden) {
       rendreHistorique(document, $("liste-historique"), etat.historique);
@@ -112,6 +121,7 @@ const connexion = new Connexion({
   },
   surStatut(nouveau) {
     statut = nouveau;
+    suiviCore.surStatut(nouveau);
     etat.enLigne = nouveau === "en_ligne";
     if (nouveau in MESSAGES_CLE) demanderCle(MESSAGES_CLE[nouveau]);
   },
@@ -259,6 +269,8 @@ function ouvrirParametres() {
   connexion.envoyer({ type: "connecteurs" }); // relus à chaque ouverture : un dossier a pu être déposé
   reglages.ouverts.clear(); // chaque ouverture repart d'une liste fermée, sans vieux message
   reglages.resultats.clear();
+  suiviCore.demander();
+  montrerCore();
   const commun = { document, stockage, scene: () => sceneCourante };
   galeries = [
     ouvrirGalerie({
@@ -359,7 +371,7 @@ function image(ms) {
     fond.dessiner(t, sceneCourante);
     orbe.dessiner(t, sceneCourante);
     $("pastille").style.backgroundColor = rgba(etat.couleur, 1);
-    const libelle = etat.enLigne ? LIBELLES[etat.etat] : (STATUTS[statut] ?? "");
+    const libelle = etat.enLigne ? LIBELLES[etat.etat] : (suiviCore.libelle() ?? STATUTS[statut] ?? "");
     if ($("libelle-etat").textContent !== libelle) $("libelle-etat").textContent = libelle;
     afficherSousTitres(sousTitres, etat, Date.now());
   } catch (e) {
```

Créer `src/atlas_web/core.js` :

```javascript
// La rubrique « Le Core » des Paramètres (spec des réglages et du Core, §5 et §6) : la version
// qui tourne, « Redémarrer » et « Mettre à jour et redémarrer », chacun confirmé ; les étapes et
// la fin, que toutes les pages voient ; et, pendant un redémarrage, le retour du Core attendu.

export const REDEMARRER = "Redémarrer";
export const METTRE_A_JOUR = "Mettre à jour et redémarrer";
export const CONFIRMATIONS = {
  redemarrer_core:
    "Redémarrer le Core ? La conversation en cours se clôt, avec son résumé au journal. Atlas revient dans une dizaine de secondes.",
  mettre_a_jour_core:
    "Mettre Atlas à jour ? Le Core récupère la dernière version, installe ce qui manque, puis redémarre. La conversation en cours se clôt.",
};
export const REDEMARRAGE = "Redémarrage du Core…";
export const NE_REVIENT_PAS = "Le Core ne revient pas";
export const NE_REVIENT_PAS_DETAIL =
  "Le Core ne revient pas : regarde son journal (donnees/logs/core.log sur le néo).";
export const DELAI_RETOUR_MS = 60000;

// Ce que la page sait du Core : `etat` (la dernière version reçue, l'étape en cours, la fin),
// et le retour attendu après un redémarrage. `envoyer` parle au Core ; `surChangement`
// redessine la rubrique.
export class SuiviCore {
  constructor({
    envoyer,
    surChangement,
    planifier = (rappel, delai) => setTimeout(rappel, delai),
    annuler = (minuteur) => clearTimeout(minuteur),
  }) {
    this._envoyer = envoyer;
    this._surChangement = surChangement;
    this._planifier = planifier;
    this._annuler = annuler;
    this.etat = { version: null, enCours: null, fin: null };
    this._retour = null; // { parti, perdu, minuteur } pendant un redémarrage
  }

  demander() {
    this._envoyer({ type: "demande_core" });
  }

  recevoir(message) {
    if (message.type === "etat_core") {
      this.etat.version = message;
    } else if (message.type === "core_en_cours") {
      this.etat.enCours = message;
      this.etat.fin = null;
      if (message.etape === "redemarrage") this._attendreLeRetour();
    } else if (message.type === "fin_core") {
      this.etat.fin = message;
      this.etat.enCours = null;
      this.demander(); // le Core n'est plus occupé : la version et les boutons à jour
    } else {
      return;
    }
    this._surChangement();
  }

  // Le statut de la connexion : le Core est revenu quand elle revient en ligne après
  // s'être coupée.
  surStatut(statut) {
    if (!this._retour) return;
    if (statut !== "en_ligne") {
      this._retour.parti = true;
    } else if (this._retour.parti) {
      this._annuler(this._retour.minuteur);
      this._retour = null;
      this.etat.enCours = null;
      this.etat.fin = null;
      this.demander();
      this._surChangement();
    }
  }

  // Le libellé de la barre du haut, hors ligne, pendant un redémarrage ; sinon null.
  libelle() {
    if (!this._retour) return null;
    return this._retour.perdu ? NE_REVIENT_PAS : REDEMARRAGE;
  }

  _attendreLeRetour() {
    if (this._retour) this._annuler(this._retour.minuteur);
    const retour = { parti: false, perdu: false, minuteur: null };
    retour.minuteur = this._planifier(() => {
      retour.perdu = true;
      this.etat.fin = { ok: false, texte: NE_REVIENT_PAS_DETAIL, details: [] };
      this._surChangement();
    }, DELAI_RETOUR_MS);
    this._retour = retour;
  }
}

function texte(document, balise, classe, contenu) {
  const element = document.createElement(balise);
  element.className = classe;
  element.textContent = contenu;
  return element;
}

function bouton(document, classe, contenu) {
  const element = texte(document, "button", classe, contenu);
  element.type = "button";
  return element;
}

// La rubrique ; `surAction(type)` envoie « redemarrer_core » ou « mettre_a_jour_core », une
// fois confirmé.
export function rendreCore(document, conteneur, etat, surAction) {
  const { version, enCours, fin } = etat;
  const elements = [];
  const quand = version?.date ? `, du ${version.date}` : "";
  elements.push(texte(document, "p", "version", version ? `Version ${version.version}${quand}` : "Version…"));

  const occupe = Boolean(enCours) || Boolean(version?.occupe);
  const redemarrer = bouton(document, "redemarrer", REDEMARRER);
  const mettreAJour = bouton(document, "mettre-a-jour", METTRE_A_JOUR);
  redemarrer.disabled = !version || occupe;
  mettreAJour.disabled = !version || occupe || !version.mise_a_jour_possible;
  const boutons = document.createElement("div");
  boutons.className = "boutons";
  boutons.append(redemarrer, mettreAJour);
  elements.push(boutons);
  if (version && !version.mise_a_jour_possible && version.raison) {
    elements.push(texte(document, "p", "raison", version.raison));
  }

  const confirmation = document.createElement("div");
  confirmation.className = "confirmation-core";
  confirmation.hidden = true;
  const question = texte(document, "p", "", "");
  const confirmer = bouton(document, "confirmer", "Confirmer");
  const annuler = bouton(document, "annuler", "Annuler");
  confirmation.append(question, confirmer, annuler);
  elements.push(confirmation);
  let demande = null;
  for (const [element, type] of [
    [redemarrer, "redemarrer_core"],
    [mettreAJour, "mettre_a_jour_core"],
  ]) {
    element.addEventListener("click", () => {
      demande = type;
      question.textContent = CONFIRMATIONS[type];
      confirmation.hidden = false;
    });
  }
  confirmer.addEventListener("click", () => {
    confirmation.hidden = true;
    if (demande) surAction(demande);
  });
  annuler.addEventListener("click", () => {
    confirmation.hidden = true;
  });

  if (enCours) {
    elements.push(texte(document, "p", "etape", enCours.texte));
    if (enCours.nouveautes.length) {
      const liste = document.createElement("ul");
      liste.className = "nouveautes";
      liste.append(...enCours.nouveautes.map((titre) => texte(document, "li", "", titre)));
      elements.push(liste);
    }
  }
  if (fin) {
    elements.push(texte(document, "p", `fin ${fin.ok ? "ok" : "refus"}`, fin.texte));
    if (fin.details.length) elements.push(texte(document, "pre", "details", fin.details.join("\n")));
  }
  conteneur.replaceChildren(...elements);
}
```

Modifier `src/atlas_web/documents.css` :

```diff
--- a/src/atlas_web/documents.css
+++ b/src/atlas_web/documents.css
@@ -346,3 +346,63 @@
 #liste-connecteurs .reglages .resultat.refus {
   color: var(--erreur);
 }
+
+/* La rubrique « Le Core » : sa version, ses deux boutons, leur confirmation, et les étapes
+   d'un redémarrage ou d'une mise à jour. */
+#rubrique-core p {
+  margin: 4px 0 0;
+  font-size: 13px;
+}
+
+#rubrique-core .version,
+#rubrique-core .raison,
+#rubrique-core .nouveautes {
+  font-size: 12px;
+  color: var(--texte-doux);
+}
+
+#rubrique-core button {
+  margin: 8px 8px 0 0;
+  padding: 6px 14px;
+  border-radius: 16px;
+  border: 1px solid var(--bord);
+}
+
+#rubrique-core button:disabled {
+  opacity: 0.4;
+  cursor: not-allowed;
+}
+
+#rubrique-core .confirmation-core {
+  margin-top: 8px;
+  padding: 10px 12px;
+  border-radius: 12px;
+  border: 1px solid rgba(251, 191, 36, 0.5);
+}
+
+#rubrique-core .confirmer {
+  background: var(--accent);
+  border-color: var(--accent);
+  color: #02030a;
+}
+
+#rubrique-core .etape,
+#rubrique-core .fin.ok {
+  color: var(--accent);
+}
+
+#rubrique-core .fin.refus {
+  color: var(--erreur);
+}
+
+#rubrique-core .nouveautes {
+  margin: 4px 0 0;
+  padding-left: 18px;
+}
+
+#rubrique-core .details {
+  margin: 6px 0 0;
+  font-size: 11px;
+  white-space: pre-wrap;
+  color: var(--texte-doux);
+}
```

Modifier `src/atlas_web/index.html` :

```diff
--- a/src/atlas_web/index.html
+++ b/src/atlas_web/index.html
@@ -97,6 +97,8 @@
     <div id="galerie-orbes" class="galerie"></div>
     <h3>Fond</h3>
     <div id="galerie-fonds" class="galerie fonds"></div>
+    <h3>Le Core</h3>
+    <div id="rubrique-core"></div>
   </section>
 
   <section id="panneau-cle" class="cle" hidden>
```

- [ ] **Step 4: Vérifier que tout passe**

Run: `uv run pytest -q && uv run ruff check . --extend-exclude spikes && uv run ruff format --check . --extend-exclude spikes && node --test "tests/web/*.test.mjs"`
Expected: 1277 tests Python passent (3 de moins, et 3 ignorés, si `models/silero_vad.onnx` manque, comme dans une copie neuve), 167 tests JavaScript passent, ruff ne dit rien.

- [ ] **Step 5: Commit**

```bash
git add src/atlas_web/app.js src/atlas_web/core.js src/atlas_web/documents.css src/atlas_web/index.html tests/web/app.test.mjs tests/web/core.test.mjs
git commit -F - <<'MSG'
Page : la rubrique « Le Core »

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

### Task 8: Les guides et la spec des connecteurs

Le guide des connecteurs (les réglages se saisissent aussi dans la page ; une clé d'Atlas reste au Terminal), le
guide du néo (redémarrer et mettre à jour depuis la page) et la spec des connecteurs (D2 et §7 amendés). Pas de
test neuf : le guide des connecteurs reste exécuté par `tests/test_guide_connecteurs.py`.

**Files:**
- Modify: `connecteurs/LISEZMOI.md`
- Modify: `docs/superpowers/specs/2026-09-28-connecteurs-design.md`
- Modify: `scripts/neo/LISEZMOI.md`

**Interfaces:**
- Consumes: Tasks 1 à 7.
- Produces: la documentation.

- [ ] **Step 1: Écrire la documentation**

Modifier `connecteurs/LISEZMOI.md` :

````diff
--- a/connecteurs/LISEZMOI.md
+++ b/connecteurs/LISEZMOI.md
@@ -31,8 +31,11 @@ Atlas le lit sans exécuter aucun code, pour lister le connecteur dans la page.
 | `[[reglages]]` | non | Chacun : `variable` (`ATLAS_…`, dans le `.env` du Core), `description`, `secret` (vrai ou faux) |
 
 Tant qu'un réglage manque dans le `.env`, le connecteur est « à configurer » ; tant qu'une
-dépendance manque, « à installer ». Un réglage `secret` n'est jamais écrit dans la mémoire
-d'Atlas.
+dépendance manque, « à installer ». David saisit les réglages dans la page (Paramètres ›
+Connecteurs › Réglages) ou dans le `.env` ; ils prennent effet aussitôt, sans redémarrer. La
+page ne reçoit jamais la valeur d'un réglage `secret`, qui n'est jamais écrit non plus dans la
+mémoire d'Atlas. Une variable qu'Atlas lit lui-même (`ATLAS_WEB_CLE`, `ATLAS_POSTE_CLE`…) ne
+s'écrit jamais depuis la page, même déclarée par un connecteur : elle se change au Terminal.
 
 ## Le code : `connecteur.py`
 
@@ -104,8 +107,9 @@ def creer(contexte: Contexte) -> Bonjour:
     return Bonjour(contexte)
 ```
 
-Mets `ATLAS_BONJOUR_NOM=David` dans le `.env` du Core, redémarre-le, active « Bonjour » dans
-la page, puis demande à Atlas de te saluer.
+Dans la page, ouvre les réglages de « Bonjour », saisis `David` pour `ATLAS_BONJOUR_NOM` (ou
+mets `ATLAS_BONJOUR_NOM=David` dans le `.env` du Core, puis redémarre-le), active « Bonjour »,
+puis demande à Atlas de te saluer.
 
 ## Tester son connecteur
 
````

Modifier `docs/superpowers/specs/2026-09-28-connecteurs-design.md` :

```diff
--- a/docs/superpowers/specs/2026-09-28-connecteurs-design.md
+++ b/docs/superpowers/specs/2026-09-28-connecteurs-design.md
@@ -34,7 +34,9 @@ spec, comme connecteurs officiels.
 - **D1. Les connecteurs sont les liens vers l'extérieur** : le poste du Mac, l'agenda, le mail, Home Assistant, les
   appels, les réseaux sociaux. La mémoire, les documents et la recherche web restent le socle d'Atlas, toujours actifs.
 - **D2. Les secrets restent dans le `.env` du Core.** Chaque connecteur déclare ses variables ; la page dit seulement
-  lesquelles manquent. Aucun secret ne passe jamais par la page.
+  lesquelles manquent. Amendé le 29 septembre (`2026-09-29-reglages-et-core-design.md`, §4) : la page modifie les
+  réglages déclarés par un connecteur, jamais une clé d'Atlas ; un secret va de la page au Core, jamais dans l'autre
+  sens.
 - **D3. Un connecteur est un dossier** : un manifeste `connecteur.toml`, lisible et lu sans exécuter aucun code, et
   le code Python de ses outils (`connecteur.py`, et d'autres fichiers au besoin).
 - **D4. Deux répertoires** : les connecteurs officiels dans le dépôt (`connecteurs/`), mis à jour par `git pull` ;
@@ -182,6 +184,8 @@ changent pas.
   note.
 - **Un identifiant ou un nom d'outil hors motif** est refusé ; un chemin n'est jamais construit à partir d'un texte
   venu de la page sans passer par la liste des connecteurs découverts.
+- **Les réglages saisis dans la page** (`2026-09-29-reglages-et-core-design.md`, §4) : seulement les variables que
+  déclare le connecteur, jamais une clé d'Atlas ; la valeur d'un secret ne revient jamais vers une page.
 
 ## 8. Fichiers et réglages
 
```

Modifier `scripts/neo/LISEZMOI.md` :

```diff
--- a/scripts/neo/LISEZMOI.md
+++ b/scripts/neo/LISEZMOI.md
@@ -86,9 +86,12 @@ Le script vérifie le `.env`, demande ton mot de passe (sudo) et installe le ser
 session ouverte ; launchd le relance s'il tombe.
 
 - Le journal : `tail -f ~/atlas/donnees/logs/core.log`
-- Redémarrer le Core : `sudo launchctl kickstart -k system/fr.atlas.core`
+- Redémarrer le Core : dans la page, Paramètres › Le Core › « Redémarrer » ; ou
+  `sudo launchctl kickstart -k system/fr.atlas.core`
 - Arrêter le service : `sudo launchctl bootout system/fr.atlas.core`
-- Mettre Atlas à jour : `git pull && make install`, puis redémarrer le Core.
+- Mettre Atlas à jour : dans la page, « Mettre à jour et redémarrer » (le dépôt doit être sur
+  `main`, sans modification : sinon la page dit pourquoi) ; ou `git pull && make install`,
+  puis redémarrer le Core.
 
 ## 7. Brancher le M5 sur le néo
 
@@ -207,9 +210,11 @@ se résume d'abord au journal.
 - Les connecteurs d'Atlas sont dans `connecteurs/` du dépôt. Les tiens, et ceux de la
   communauté, se déposent dans `~/.atlas/connecteurs/` sur la machine du Core (réglage
   `ATLAS_CONNECTEURS_DOSSIER`) ; ils apparaissent dans la page, coupés.
-- Un connecteur « à configurer » attend une variable dans le `.env` du Core, qu'il nomme ;
-  ajoute-la et redémarre le Core. Un connecteur « à installer » attend ses dépendances :
-  lance `make install`, puis redémarre le Core.
+- Un connecteur « à configurer » attend une variable, qu'il nomme : saisis-la dans ses
+  réglages, dans la page (elle prend effet aussitôt), ou ajoute-la dans le `.env` du Core et
+  redémarre-le. Les clés d'Atlas, comme `ATLAS_POSTE_CLE`, se changent au Terminal. Un
+  connecteur « à installer » attend ses dépendances : « Mettre à jour et redémarrer », ou
+  `make install` puis redémarrer le Core.
 - Un connecteur de la communauté fait tourner son code dans Atlas : n'active que ce en quoi
   tu as confiance. Pour en écrire un : `connecteurs/LISEZMOI.md`.
 - Les interrupteurs sont rangés dans `~/.atlas/connecteurs.json`. Sans mémoire, pas de
```

- [ ] **Step 2: Vérifier que tout passe**

Run: `uv run pytest -q && uv run ruff check . --extend-exclude spikes && uv run ruff format --check . --extend-exclude spikes && node --test "tests/web/*.test.mjs"`
Expected: 1277 tests Python passent (3 de moins, et 3 ignorés, si `models/silero_vad.onnx` manque, comme dans une copie neuve), 167 tests JavaScript passent, ruff ne dit rien.

- [ ] **Step 3: Commit**

```bash
git add connecteurs/LISEZMOI.md docs/superpowers/specs/2026-09-28-connecteurs-design.md scripts/neo/LISEZMOI.md
git commit -F - <<'MSG'
Réglages et Core : les guides et la spec des connecteurs

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

## L'essai avec David, sur le M5

Après la Task 8, sur la branche `reglages-core`, avant la PR. C'est David qui lance tout : l'essai consomme un peu
de son abonnement Claude, et redémarre son Core. Les critères sont ceux du §1 de la spec.

1. **Préparer** : `make install`, puis `make run-core` (la boucle), la page ouverte ; le connecteur « bonjour » du
   guide dans `~/.atlas/connecteurs/bonjour/`, sans `ATLAS_BONJOUR_NOM` dans le `.env`.
2. **Régler** : « bonjour » est « à configurer » ; « Réglages », saisir `David`, « Enregistrer » : « Enregistré. »,
   et il devient activable aussitôt ; l'activer (confirmation « Communauté »), puis « Salue-moi. ».
3. **Changer** : saisir un autre nom : « Prend effet à ta prochaine question. » ; la question suivante le salue.
4. **Secret** et **clé d'Atlas** : un réglage secret s'affiche « Défini », jamais sa valeur ; la clé du poste dit
   « se change au Terminal ».
5. **Redémarrer** : Paramètres › Le Core › « Redémarrer », confirmer : « Redémarrage du Core… », puis la page revient
   en ligne seule, avec la version.
6. **Mettre à jour, refus** : la branche `reglages-core` n'est pas `main` : le bouton est grisé et dit pourquoi.
7. **Mettre à jour** : après la fusion, sur `main` : « Atlas est déjà à jour. », ou les nouveautés, l'installation,
   puis le redémarrage.
8. `make test` au vert.

Ce qui ne va pas devient une correction sur la branche, avec son test, avant la PR.

# Phase 2c : les outils et les permissions — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** David réfléchit à voix haute puis demande un document, qu'Atlas écrit en entier dans sa mémoire et que David lit dans un panneau de la page ; chaque outil déclare son niveau d'autorisation (N1, N2, N3), et la suppression d'une fiche ou d'un document attend le « oui » de David, à la voix, au clavier ou d'un bouton.

**Architecture:** `memoire.py` gagne les documents (`documents/<nom>.md`, 50 000 caractères au plus), la suppression et une annulation qui dit ce qu'elle défait. `confirmation.py` tient l'action qui attend le « oui » : une seule à la fois, trente secondes, la réponse de David lue sans Claude, et les lignes qui disent le résultat à Claude. `outils.py` déclare les niveaux et applique leur règle autour de chaque outil du serveur « atlas » ; `outils_memoire.py` et `outils_documents.py` y déclarent leurs outils. Le cerveau lit la phrase de David avant Claude quand une action attend, pose la question à sa place dans la réponse, et abandonne l'action quand la conversation se termine. Le hub sert aux pages la liste et le contenu des documents, et les prévient d'une confirmation en cours ; la page met les documents en forme (`markdown.js`, jamais de HTML) et montre la question avec ses boutons.

**Tech Stack:** Python 3.12+ (venv en 3.13), `claude-agent-sdk` 0.2.159 (`tool`, `create_sdk_mcp_server`), git en ligne de commande, pydantic v2, FastAPI, pytest (asyncio auto) ; JavaScript en modules ES sans dépendance, testé par `node --test`.

**Spec:** `docs/superpowers/specs/2026-09-25-phase-2c-outils-design.md` (à lire avec ce plan : elle fait foi en cas de doute).

## Global Constraints

- Code, identifiants, messages et commentaires en français, comme le reste du dépôt ; lignes de 100 caractères au plus (ruff) pour Python.
- Aucune nouvelle dépendance Python ni JavaScript.
- Les niveaux sont dans le code : `Niveau.N1` (lire, chercher), `Niveau.N2` (écrire une fiche, écrire un document, annuler), `Niveau.N3` (supprimer). Claude ne choisit jamais un niveau ; un outil N3 ne change rien avant le « oui ».
- Le serveur d'outils s'appelle `atlas` ; ses outils, pour Claude, dans cet ordre : `mcp__atlas__memoire_lire`, `mcp__atlas__memoire_chercher`, `mcp__atlas__memoire_ecrire`, `mcp__atlas__document_ecrire`, `mcp__atlas__memoire_annuler`, `mcp__atlas__memoire_supprimer`. Claude garde en plus `WebSearch`, et rien d'autre (pas de `WebFetch`).
- Un document : `documents/<nom>.md`, le nom `[a-z0-9]+(-[a-z0-9]+)*` de 60 caractères au plus ; « # Titre » (100 au plus), une ligne vide, une phrase de résumé (200 au plus) ; 50 000 caractères au plus en tout. Les vérifications de la 2b s'appliquent (chemin, format, secrets) ; commit « Atlas : <titre> ».
- La confirmation : une seule action à la fois ; trente secondes (`DELAI_S = 30.0`) ; seules les phrases des tables `OUI` et `NON` de `confirmation.py` valent oui ou non, comparées sans majuscules, accents ni ponctuation, un « Atlas » au début ou à la fin ignoré ; tout le reste vaut « autre chose ». Les phrases et les lignes pour Claude sont celles du §6 de la spec, mot pour mot.
- Les annonces, mot pour mot : « J'ai écrit le document <titre>, il est dans la page. », « J'ai mis à jour le document <titre>. », « J'ai retiré le document <titre>. », « Le document <titre> revient à sa version précédente. », « J'ai remis le document <titre>. », « J'ai remis la fiche <titre>. », « J'ai remis ton profil. » ; celles de la 2b ne changent pas.
- Les messages des pages (`/ws/web`, protégés par la clé) : `documents`, `lire_document`, `confirmer` ; `liste_documents`, `document`, `documents_changes`, `confirmation`, `confirmation_finie`. Le panneau ne lit que `documents/…` (motif vérifié à l'entrée).
- La page : aucun HTML d'un document n'est jamais interprété ; les liens ne sont permis qu'en `http(s)`, ouverts dans un nouvel onglet (`rel="noopener noreferrer"`).
- Aucun réglage nouveau. Les tests ne touchent jamais la vraie mémoire (`tests/conftest.py`) et n'appellent jamais le vrai Claude.
- Ne jamais lancer ce qui ouvre un micro ni ce qui appelle le vrai Claude (l'essai final consomme l'abonnement de David) : c'est David qui le fait.
- Dépôt public : aucune adresse IP, aucun domaine, nom ou courriel privé, aucun jeton dans ce qui est commité ; la mémoire de David n'y entre jamais.
- Git : ajouter les fichiers par leur chemin, jamais `git add -A` (le dossier `spikes/` n'est pas suivi et reste privé). Messages de commit en français, terminés par la ligne `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Avant chaque commit : `uv run pytest -q`, `uv run ruff check . --extend-exclude spikes`, `uv run ruff format --check . --extend-exclude spikes`, `node --test "tests/web/*.test.mjs"`. Si `ruff format --check` échoue, lancer `uv run ruff format <fichiers>` : la mise en forme fait foi.
- Fichiers de moins de 500 lignes : `memoire.py` finit à 481, `cerveau_claude.py` à 491, `hub.py` à 445 ; les nouveaux styles vont dans `documents.css` pour que `style.css` reste à 434 ; `session.py` (558) ne change pas.
- **Copier le code programmatiquement.** Les fichiers neufs sont donnés en entier, les autres par des diffs unifiés exacts (`git apply` les accepte tels quels, copiés d'un bloc) : ne rien retaper à la main.
- Le code de ce plan a été vérifié tel quel avant d'être écrit ici : appliquées dans l'ordre, les 9 tâches donnent 955 tests Python et 143 tests JavaScript qui passent, un lint propre, et chaque tâche laisse la suite entière au vert. Les tests ont en outre été mis à l'épreuve par mutations : chaque comportement clé, retiré du code, fait échouer au moins un test. Un écart entre le plan et ce que vous observez est donc à signaler, pas à contourner.

## Review Focus

Les cinq situations que la spec implique sans les décrire, les plus susceptibles de surprendre David ; chacune a son test dans la tâche qui en porte le code.

1. **Une fiche retouchée à la main entre la question et le « oui »** : la suppression échoue sans rien perdre ; Atlas dit « Je n'ai pas pu supprimer la fiche … » et l'erreur est notée. Task 2 : `test_une_retouche_a_la_main_ne_se_supprime_pas`, `test_un_fichier_ecrit_a_la_main_et_jamais_commite_ne_se_supprime_pas` ; Task 5 : `test_une_fiche_retouchee_entre_la_question_et_le_oui_reste_a_david`.
2. **Un « oui » qui coupe la fin de la réponse d'Atlas** (Claude parle encore après avoir demandé la suppression) : la question a été posée, le « oui » compte. Task 6 : `test_un_oui_qui_coupe_la_fin_de_la_reponse_compte`.
3. **Une page ouverte, ou reconnectée, pendant une attente** : elle reçoit la question avec ses boutons ; une question qui n'attend plus disparaît à la reconnexion. Task 7 : `test_une_page_ouverte_pendant_une_confirmation_la_recoit_aussi` ; Task 9 : `test_une_page_qui_se_reconnecte_oublie_une_question_qui_n_attend_plus`.
4. **« Annule » juste après une suppression confirmée** : le fichier revient, et Atlas le dit (« J'ai remis … ») ; un fichier recréé à la main entre-temps n'est pas écrasé. Task 2 : `test_annuler_une_suppression_remet_le_fichier`, `test_annuler_une_suppression_ne_remplace_pas_un_fichier_recree_a_la_main` ; Task 5 : `test_annuler_une_suppression_remet_et_le_dit`.
5. **Un document retouché à la main hors du format, ou dans un autre encodage** : il se liste et se lit quand même, sans faire tomber le panneau ni le sommaire. Task 1 : `test_un_document_retouche_a_la_main_hors_format_se_liste_quand_meme`, `test_un_document_dans_un_autre_encodage_se_liste_et_se_lit`.

## Décisions prises en écrivant le plan

La spec fait foi ; voici ce qu'elle laissait ouvert et ce que le plan en a fait.

1. **Les documents restent dans `memoire.py`** (481 lignes, sous la limite) : ils partagent tout le chemin d'écriture des fiches (vérifications, verrou, commit, annulation). Les sortir obligerait à exposer ces rouages ; le prochain ajout à la mémoire (phase 3) devra découper.
2. **`memoire_ecrire` refuse un chemin `documents/…`** et renvoie à `document_ecrire` : un document s'annonce comme un document. `document_ecrire` prend un `nom`, pas un chemin.
3. **La liste des documents** trie par date de modification du fichier (une retouche à la main compte) ; un document hors format se liste par son titre, sans résumé.
4. **Annuler rend un `Defait`** (chemin, titre, nature : création, retouche, suppression), lu dans l'historique git (`--name-status`) ; un commit de suppression s'écrit « Atlas : suppression de <titre> ». L'annonce de « annule » en dépend.
5. **La suppression refuse un fichier retouché à la main** (ou jamais commité) : le travail de David n'est jamais supprimé sans qu'Atlas l'ait écrit.
6. **L'action en attente est une `Suppression`** (la seule action N3 de la 2c) qui sait se dire : question, réponse, lignes pour Claude et pour les pages. Elle s'exécute hors de la boucle du Core, puis `apres` prévient les pages quand c'était un document. La phase 3 généralisera l'action.
7. **La question ne compte que posée** : le cerveau la rend (marqueur `Confirmation`, une `Note` que la session dit sans changement) après ce qui la précède ; une phrase de David arrivée avant fait abandonner l'action (« David a parlé avant la question »).
8. **La fin d'une conversation abandonne l'action et oublie les lignes** ; le résumé du journal reçoit d'abord les lignes que Claude n'a pas encore apprises (un « oui » juste avant la fin arrive ainsi au journal).
9. **Trente secondes comptées dès la mise en attente**, même si la question n'est pas encore posée ; les pages ne voient la fin d'une attente que si elles ont vu la question.
10. **Le hub garde `creer_cerveau(config)` à un argument** et lit les outils par la propriété `CerveauClaude.outils` ; `ouvrir_la_memoire` branche les rappels vers le diffuseur des pages.
11. **Le diffuseur retient la question en cours** comme il retient le mode muet : une page qui s'ouvre la reçoit après l'état ; la page cache la barre à chaque historique reçu (une reconnexion), le Core renvoyant la question si elle attend encore.
12. **`liste_documents` porte `disponible`** (faux sans mémoire) et `document` porte `erreur` : la page dit « La mémoire n'est pas disponible. » ou l'erreur du Core.
13. **La barre de confirmation vit dans `app.js`** (quelques lignes, testées de bout en bout dans `app.test.mjs`) ; la fin d'une attente reste affichée quatre secondes, sans effacer une question suivante.
14. **La mise en forme construit des éléments et du texte**, jamais du HTML : titres de trois niveaux, paragraphes, listes, citations, tableaux (avec ou sans ligne d'en-tête), blocs de code, gras, italique, code, liens `http(s)`.

## Carte des fichiers

| Fichier | Tâche | Rôle |
|---|---|---|
| `src/atlas_core/memoire.py` | 1, 2 | Les documents ; la suppression, et une annulation qui dit ce qu'elle défait |
| `src/atlas_core/cerveau.py`, `src/atlas_core/confirmation.py` | 3, 5 | Le marqueur `Confirmation` ; l'action qui attend le « oui » |
| `src/atlas_core/outils.py` | 4 | Les niveaux, et le serveur « atlas » qui applique leur règle |
| `src/atlas_core/outils_memoire.py`, `src/atlas_core/outils_documents.py` | 2, 5 | Les six outils, chacun avec son niveau |
| `src/atlas_core/cerveau_claude.py`, `src/atlas_core/consignes.py` | 5, 6, 7 | La réponse de David lue avant Claude, la question posée, les lignes de résultat ; les consignes |
| `src/atlas_core/protocole_web.py`, `src/atlas_core/diffuseur.py`, `src/atlas_core/hub.py` | 7 | Les messages des pages, la question retenue, le branchement |
| `src/atlas_web/markdown.js` | 8 | La mise en forme d'un document |
| `src/atlas_web/documents.js`, `documents.css`, `app.js`, `index.html` ; `docs/superpowers/specs/2026-09-22-atlas-design.md` | 9 | Le panneau, la barre de confirmation ; la spec parente |
| `tests/test_memoire_documents.py`, `test_memoire_supprimer.py`, `test_confirmation.py`, `test_outils.py`, `test_outils_documents.py`, `test_cerveau_confirmation.py`, `tests/web/markdown.test.mjs`, `tests/web/documents.test.mjs` (nouveaux) ; `test_memoire_chercher_annuler.py`, `test_session_cerveau.py`, `test_outils_memoire.py`, `test_consignes.py`, `test_protocole_web.py`, `test_diffuseur.py`, `test_hub.py`, `test_hub_web.py`, `tests/web/app.test.mjs` | 1–9 | Tests |

---

### Task 1: Les documents dans la mémoire

Un document est une fiche plus longue, dans `documents/` : même format, mêmes vérifications, commit sous l'auteur
« Atlas ». Il s'écrit par son nom, se lit comme une fiche, entre dans le sommaire et la recherche, et se liste pour
la page du plus récent au plus ancien. `memoire_ecrire` ne peut pas écrire un document (Review Focus 5 : un document
hors format ou dans un autre encodage se liste quand même).

**Files:**
- Modify: `src/atlas_core/memoire.py`
- Create: `tests/test_memoire_documents.py`

**Interfaces:**
- Consumes: la mémoire de la 2b (`Memoire`, `_cible`, `_fichiers`, `verifier_fiche`, `_lire_texte`, `sommaire`).
- Produces: `atlas_core.memoire` : `DOSSIER_DOCUMENTS = "documents"`, `DOCUMENT_MAX = 50_000`,
  `InfoDocument(chemin: str, titre: str, resume: str, modifie: dt.datetime)` (frozen dataclass),
  `verifier_fiche(contenu, nature="fiche")` (`nature="document"` : 50 000 caractères, « Un document … ») ;
  `Memoire.ecrire_document(nom: str, contenu: str) -> tuple[str, bool] | None` (le titre et s'il vient d'être créé,
  ou None si rien n'a changé) ; `Memoire.documents() -> list[InfoDocument]` ; `Memoire.lire` accepte
  `documents/<nom>.md` ; `Memoire.ecrire` refuse `documents/…` (« … document_ecrire … ») ; `sommaire()` et
  `chercher()` couvrent les documents, après les fiches.

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/test_memoire_documents.py` :

```python
"""Les documents de la mémoire : écrits sur demande de David, lus dans la page. Chaque test
travaille dans un vrai dépôt git temporaire."""

import datetime as dt
import os
import subprocess

import pytest

from atlas_core.memoire import DOCUMENT_MAX, ErreurMemoire, InfoDocument, Memoire

OFFRE = (
    "# Offre de lancement\n\n"
    "Trois formules pour les premiers clients, du diagnostic à l'accompagnement.\n\n"
    "## Les formules\n\n"
    "- **Diagnostic** : une journée, un rapport.\n"
    "- **Mise en place** : *quatre semaines*.\n\n"
    "| Formule | Prix |\n"
    "| --- | --- |\n"
    "| Diagnostic | 900 € |\n\n"
    "> À valider avec Paul Durand.\n"
)
PLAN = "# Plan de prospection\n\nLes vingt premières agences à contacter en octobre.\n"


@pytest.fixture
def memoire(tmp_path) -> Memoire:
    ouverte = Memoire.ouvrir(tmp_path / "memoire", secrets=["cle-du-core-tres-secrete"])
    assert ouverte is not None
    return ouverte


def git(memoire: Memoire, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(memoire.racine), *arguments], capture_output=True, text=True, check=True
    ).stdout


def commits(memoire: Memoire) -> int:
    sortie = subprocess.run(
        ["git", "-C", str(memoire.racine), "rev-list", "--count", "HEAD"],
        capture_output=True,
        text=True,
    )
    return int(sortie.stdout) if sortie.returncode == 0 else 0


# --- écrire -----------------------------------------------------------------------


def test_un_document_s_ecrit_et_se_commite_sous_atlas(memoire):
    assert memoire.ecrire_document("offre-de-lancement", OFFRE) == ("Offre de lancement", True)
    assert (memoire.racine / "documents" / "offre-de-lancement.md").read_text() == OFFRE
    assert git(memoire, "log", "-1", "--format=%an <%ae>|%s").strip() == (
        "Atlas <atlas@atlas.local>|Atlas : Offre de lancement"
    )


def test_une_retouche_n_est_pas_une_creation_et_rien_de_neuf_ne_commite_rien(memoire):
    memoire.ecrire_document("offre-de-lancement", OFFRE)
    retouche = OFFRE + "\n## Les prix\n\nÀ revoir en novembre.\n"
    assert memoire.ecrire_document("offre-de-lancement", retouche) == ("Offre de lancement", False)
    assert memoire.ecrire_document("offre-de-lancement", retouche) is None
    assert commits(memoire) == 2


def test_un_document_fait_au_plus_cinquante_mille_caracteres(memoire):
    debut = "# Rapport\n\nUn long rapport.\n\n"
    tout_juste = debut + "x" * (DOCUMENT_MAX - len(debut) - 1) + "\n"
    assert len(tout_juste) == DOCUMENT_MAX
    assert memoire.ecrire_document("rapport", tout_juste) == ("Rapport", True)
    with pytest.raises(ErreurMemoire, match=f"Un document fait au plus {DOCUMENT_MAX} caractères"):
        memoire.ecrire_document("rapport", tout_juste + "x")


@pytest.mark.parametrize(
    "nom",
    ["Offre", "offre_de_lancement", "offre--lancement", "../profil", "sous/dossier", "a" * 61, ""],
)
def test_un_nom_de_document_hors_format_est_refuse(memoire, nom):
    with pytest.raises(ErreurMemoire, match="nom de document"):
        memoire.ecrire_document(nom, OFFRE)
    assert commits(memoire) == 0


def test_un_nom_de_soixante_caracteres_est_accepte_pour_un_document(memoire):
    assert memoire.ecrire_document("a" * 60, OFFRE) == ("Offre de lancement", True)


def test_un_document_mal_forme_est_refuse_et_le_refus_dit_comment_faire(memoire):
    with pytest.raises(ErreurMemoire, match="Un document commence par « # Titre », une ligne vide"):
        memoire.ecrire_document("offre-de-lancement", "Offre de lancement, trois formules.\n")
    assert commits(memoire) == 0


def test_un_secret_dans_un_document_est_refuse(memoire):
    with pytest.raises(ErreurMemoire, match="Refusé"):
        memoire.ecrire_document("acces", PLAN + "\nMot de passe du site : hunter2\n")
    assert not (memoire.racine / "documents").exists()


def test_memoire_ecrire_renvoie_un_document_a_document_ecrire(memoire):
    with pytest.raises(ErreurMemoire, match="document_ecrire"):
        memoire.ecrire("documents/offre-de-lancement.md", OFFRE)
    assert commits(memoire) == 0


# --- lire, chercher, le sommaire ------------------------------------------------------


def test_un_document_se_lit_comme_une_fiche(memoire):
    memoire.ecrire_document("offre-de-lancement", OFFRE)
    assert memoire.lire("documents/offre-de-lancement.md") == OFFRE


def test_les_documents_sont_dans_le_sommaire_et_la_recherche(memoire):
    memoire.ecrire("personnes/paul-durand.md", "# Paul Durand\n\nProspect.\n")
    memoire.ecrire_document("offre-de-lancement", OFFRE)
    assert memoire.sommaire() == [
        "- personnes/paul-durand.md : Prospect.",
        "- documents/offre-de-lancement.md : Trois formules pour les premiers clients, du "
        "diagnostic à l'accompagnement.",
    ]
    assert memoire.chercher("diagnostic |") == [
        "documents/offre-de-lancement.md : | Diagnostic | 900 € |"
    ]


# --- la liste pour la page ------------------------------------------------------------


def _dater(memoire: Memoire, nom: str, moment: dt.datetime) -> None:
    horodatage = moment.timestamp()
    os.utime(memoire.racine / "documents" / f"{nom}.md", (horodatage, horodatage))


def test_la_liste_des_documents_va_du_plus_recent_au_plus_ancien(memoire):
    memoire.ecrire_document("offre-de-lancement", OFFRE)
    memoire.ecrire_document("plan-de-prospection", PLAN)
    memoire.ecrire("projets/site-web.md", "# Site web\n\nMaquette validée.\n")
    _dater(memoire, "offre-de-lancement", dt.datetime(2026, 9, 25, 21, 14))
    _dater(memoire, "plan-de-prospection", dt.datetime(2026, 9, 24, 9, 5))
    assert memoire.documents() == [
        InfoDocument(
            chemin="documents/offre-de-lancement.md",
            titre="Offre de lancement",
            resume="Trois formules pour les premiers clients, du diagnostic à l'accompagnement.",
            modifie=dt.datetime(2026, 9, 25, 21, 14),
        ),
        InfoDocument(
            chemin="documents/plan-de-prospection.md",
            titre="Plan de prospection",
            resume="Les vingt premières agences à contacter en octobre.",
            modifie=dt.datetime(2026, 9, 24, 9, 5),
        ),
    ]


def test_un_document_retouche_a_la_main_hors_format_se_liste_quand_meme(memoire):
    (memoire.racine / "documents").mkdir()
    (memoire.racine / "documents" / "notes.md").write_text("## Notes en vrac\nidée 1\n")
    (memoire.racine / "documents" / "plan.md").write_text("# Plan\n\n## Étapes\n\nUne.\n")
    (memoire.racine / "documents" / "Brouillon.md").write_text("# Brouillon\n\nNom hors format.\n")
    _dater(memoire, "notes", dt.datetime(2026, 9, 25, 10, 0))
    _dater(memoire, "plan", dt.datetime(2026, 9, 24, 10, 0))
    assert [(i.chemin, i.titre, i.resume) for i in memoire.documents()] == [
        ("documents/notes.md", "Notes en vrac", ""),
        ("documents/plan.md", "Plan", ""),
    ]
    assert memoire.sommaire() == [
        "- documents/notes.md : Notes en vrac",
        "- documents/plan.md : Plan",
    ]


def test_un_document_dans_un_autre_encodage_se_liste_et_se_lit(memoire):
    (memoire.racine / "documents").mkdir()
    (memoire.racine / "documents" / "etude.md").write_bytes(
        "# Étude\n\nMarché des agences à Lyon.\n".encode("latin-1")
    )
    [info] = memoire.documents()
    assert (info.titre, info.resume) == ("�tude", "March� des agences � Lyon.")
    assert memoire.lire("documents/etude.md").startswith("# �tude")


def test_sans_document_la_liste_est_vide(memoire):
    assert memoire.documents() == []
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `uv run pytest tests/test_memoire_documents.py -q`
Expected: FAIL — erreur de collecte : `ImportError: cannot import name 'DOCUMENT_MAX' from 'atlas_core.memoire'`.

- [ ] **Step 3: Écrire les documents dans la mémoire**

Modifier `src/atlas_core/memoire.py` :

```diff
--- a/src/atlas_core/memoire.py
+++ b/src/atlas_core/memoire.py
@@ -1,9 +1,10 @@
 """La mémoire d'Atlas : un dépôt git local de fichiers Markdown.
 
 Des fiches — le profil de David, l'entreprise, les projets, les personnes — qu'Atlas tient
-de lui-même, et un journal que le Core écrit seul. Tout passe par ici : chaque écriture est
-vérifiée (chemin, format, secrets), puis commitée sous l'auteur « Atlas ». Le dépôt n'a
-aucun distant et n'est jamais poussé : rien ne quitte la machine.
+de lui-même, les documents qu'il écrit à la demande de David, et un journal que le Core
+écrit seul. Tout passe par ici : chaque écriture est vérifiée (chemin, format, secrets),
+puis commitée sous l'auteur « Atlas ». Le dépôt n'a aucun distant et n'est jamais poussé :
+rien ne quitte la machine.
 """
 
 from __future__ import annotations
@@ -16,7 +17,8 @@ import re
 import subprocess
 import threading
 import unicodedata
-from collections.abc import Iterable
+from collections.abc import Callable, Iterable
+from dataclasses import dataclass
 from pathlib import Path
 
 from .consignes import date_en_lettres, heure_en_chiffres
@@ -52,11 +54,14 @@ _VARIABLES_LOCALES_GIT = frozenset(
 DOSSIERS_FICHES = ("entreprise", "projets", "personnes")
 _NOM = r"[a-z0-9]+(?:-[a-z0-9]+)*"
 _FICHE = re.compile(rf"(?:profil|(?:{'|'.join(DOSSIERS_FICHES)})/(?P<nom>{_NOM}))\.md")
+DOSSIER_DOCUMENTS = "documents"
+_DOCUMENT = re.compile(rf"{DOSSIER_DOCUMENTS}/(?P<nom>{_NOM})\.md")
 _JOURNAL = re.compile(r"journal/\d{4}-\d{2}-\d{2}\.md")
 NOM_MAX = 60
 TITRE_MAX = 100
 RESUME_MAX = 200
 FICHE_MAX = 20_000
+DOCUMENT_MAX = 50_000  # une dizaine de pages
 # Ce qui ressemble à un secret n'entre jamais dans la mémoire (spec parente §13).
 _SECRETS = [
     re.compile(motif)
@@ -90,6 +95,16 @@ class ErreurMemoire(Exception):
     """L'écriture ou la lecture est refusée. Le message, en français, va à Claude."""
 
 
+@dataclass(frozen=True)
+class InfoDocument:
+    """Un document, tel que le panneau « Documents » de la page le liste."""
+
+    chemin: str
+    titre: str
+    resume: str
+    modifie: dt.datetime
+
+
 def _git(racine: Path, *arguments: str, entree: str | None = None) -> str:
     """Lance git dans le dépôt, sans dépendre de la configuration git de la machine ;
     `entree` est passée sur son entrée standard."""
@@ -137,11 +152,24 @@ def _tronquer(texte: str, taille: int) -> str:
     return texte if len(texte) <= taille else texte[:taille].rstrip() + " […]"
 
 
-def verifier_fiche(contenu: str) -> str:
-    """Une fiche : « # Titre », une ligne vide, une phrase de résumé, puis le reste.
-    Rend le titre."""
-    if len(contenu) > FICHE_MAX:
-        raise ErreurMemoire(f"Une fiche fait au plus {FICHE_MAX} caractères.")
+def _titre_et_resume(texte: str) -> tuple[str, str]:
+    """Le titre (la première ligne) et la phrase de résumé, vide si le fichier a été retouché
+    à la main hors du format."""
+    debut = texte.split("\n", 3)
+    titre = debut[0].lstrip("#").strip()
+    au_format = len(debut) > 2 and not debut[1].strip() and debut[2].strip()
+    resume = debut[2].strip() if au_format and not debut[2].startswith("#") else ""
+    return titre, resume
+
+
+def verifier_fiche(contenu: str, nature: str = "fiche") -> str:
+    """Une fiche, ou un document : « # Titre », une ligne vide, une phrase de résumé, puis
+    le reste. Rend le titre."""
+    une, taille = (
+        ("Un document", DOCUMENT_MAX) if nature == "document" else ("Une fiche", FICHE_MAX)
+    )
+    if len(contenu) > taille:
+        raise ErreurMemoire(f"{une} fait au plus {taille} caractères.")
     lignes = contenu.split("\n")
     forme = (
         len(lignes) >= 3
@@ -152,11 +180,11 @@ def verifier_fiche(contenu: str) -> str:
     )
     if not forme:
         raise ErreurMemoire(
-            "Une fiche commence par « # Titre », une ligne vide, puis une phrase de résumé."
+            f"{une} commence par « # Titre », une ligne vide, puis une phrase de résumé."
         )
     titre = lignes[0][2:].strip()
     if not titre or len(titre) > TITRE_MAX:
-        raise ErreurMemoire(f"Le titre d'une fiche fait de 1 à {TITRE_MAX} caractères.")
+        raise ErreurMemoire(f"Le titre fait de 1 à {TITRE_MAX} caractères.")
     if len(lignes[2].strip()) > RESUME_MAX:
         raise ErreurMemoire(f"La phrase de résumé fait au plus {RESUME_MAX} caractères.")
     return titre
@@ -189,11 +217,12 @@ class Memoire:
 
     def _cible(self, chemin: str, ecriture: bool) -> Path:
         """Le fichier désigné, s'il est permis ; sinon `ErreurMemoire`."""
-        fiche = _FICHE.fullmatch(chemin)
+        fiche = _FICHE.fullmatch(chemin) or _DOCUMENT.fullmatch(chemin)
         if not (fiche or (not ecriture and _JOURNAL.fullmatch(chemin))):
             raise ErreurMemoire(
                 f"« {chemin} » n'est pas une fiche : profil.md, ou entreprise/, projets/ ou "
-                "personnes/ suivi d'un nom en minuscules, chiffres et tirets, en .md."
+                "personnes/ suivi d'un nom en minuscules, chiffres et tirets, en .md ; ni un "
+                "document : documents/ suivi d'un tel nom."
             )
         if fiche and fiche["nom"] and len(fiche["nom"]) > NOM_MAX:
             raise ErreurMemoire(f"Un nom de fiche fait au plus {NOM_MAX} caractères.")
@@ -227,26 +256,46 @@ class Memoire:
     def ecrire(self, chemin: str, contenu: str) -> str | None:
         """Crée ou remplace une fiche entière, puis la commite. Rend son titre, ou None si
         elle était déjà ainsi (rien à commiter, rien à annoncer)."""
+        if _DOCUMENT.fullmatch(chemin):
+            raise ErreurMemoire("Un document s'écrit avec document_ecrire, pas comme une fiche.")
+        ecrit = self._ecrire(chemin, contenu, verifier_fiche)
+        return ecrit[0] if ecrit else None
+
+    def ecrire_document(self, nom: str, contenu: str) -> tuple[str, bool] | None:
+        """Crée ou remplace `documents/<nom>.md` en entier, puis le commite. Rend son titre
+        et s'il vient d'être créé, ou None s'il était déjà ainsi."""
+        chemin = f"{DOSSIER_DOCUMENTS}/{nom}.md"
+        if not _DOCUMENT.fullmatch(chemin) or len(nom) > NOM_MAX:
+            raise ErreurMemoire(
+                f"« {nom} » n'est pas un nom de document : des minuscules, des chiffres et des "
+                f"tirets, {NOM_MAX} caractères au plus."
+            )
+        return self._ecrire(chemin, contenu, lambda texte: verifier_fiche(texte, "document"))
+
+    def _ecrire(
+        self, chemin: str, contenu: str, verifier: Callable[[str], str]
+    ) -> tuple[str, bool] | None:
         cible = self._cible(chemin, ecriture=True)
         contenu = contenu.strip("\n") + "\n"
-        titre = verifier_fiche(contenu)
+        titre = verifier(contenu)
         self.verifier_secrets(contenu)
         with self._verrou:
             self._assurer_le_depot()
-            if cible.is_file() and _lire_texte(cible) == contenu:
+            existe = cible.is_file()
+            if existe and _lire_texte(cible) == contenu:
                 return None
             cible.parent.mkdir(parents=True, exist_ok=True)
             cible.write_text(contenu, encoding="utf-8")
             # Le seul fichier écrit : les retouches de David ailleurs restent les siennes.
             _git(self.racine, "add", "--", chemin)
             _git(self.racine, "commit", "-q", "-m", f"{PREFIXE_NOTE}{titre}", "--", chemin)
-        return titre
+        return titre, not existe
 
     def _fichiers(self, avec_journal: bool) -> list[str]:
-        """Les fiches (le profil, puis chaque dossier par ordre alphabétique), puis le
-        journal du plus récent au plus ancien ; seulement ce qui est permis."""
+        """Les fiches (le profil, puis chaque dossier par ordre alphabétique), les documents,
+        puis le journal du plus récent au plus ancien ; seulement ce qui est permis."""
         candidats = ["profil.md"]
-        for dossier in DOSSIERS_FICHES:
+        for dossier in (*DOSSIERS_FICHES, DOSSIER_DOCUMENTS):
             noms = (p.name for p in (self.racine / dossier).glob("*.md"))
             candidats += sorted(f"{dossier}/{nom}" for nom in noms)
         if avec_journal:
@@ -315,21 +364,28 @@ class Memoire:
     # --- l'amorçage et le journal -----------------------------------------------------
 
     def sommaire(self) -> list[str]:
-        """Une ligne par fiche hors profil : son chemin et sa phrase de résumé (son titre,
-        si la fiche a été retouchée à la main hors du format)."""
+        """Une ligne par fiche hors profil, puis par document : son chemin et sa phrase de
+        résumé (son titre, s'il a été retouché à la main hors du format)."""
         lignes = []
         for chemin in self._fichiers(avec_journal=False):
             if chemin == "profil.md":
                 continue
-            debut = _lire_texte(self.racine / chemin).split("\n", 3)
-            au_format = len(debut) > 2 and not debut[1].strip() and debut[2].strip()
-            if au_format and not debut[2].startswith("#"):
-                resume = debut[2].strip()
-            else:
-                resume = debut[0].lstrip("#").strip()
-            lignes.append(f"- {chemin} : {resume}")
+            titre, resume = _titre_et_resume(_lire_texte(self.racine / chemin))
+            lignes.append(f"- {chemin} : {resume or titre}")
         return lignes
 
+    def documents(self) -> list[InfoDocument]:
+        """Les documents, du plus récemment modifié au plus ancien."""
+        infos = []
+        for chemin in self._fichiers(avec_journal=False):
+            if not chemin.startswith(f"{DOSSIER_DOCUMENTS}/"):
+                continue
+            fichier = self.racine / chemin
+            titre, resume = _titre_et_resume(_lire_texte(fichier))
+            modifie = dt.datetime.fromtimestamp(fichier.stat().st_mtime)
+            infos.append(InfoDocument(chemin, titre, resume, modifie))
+        return sorted(infos, key=lambda info: info.modifie, reverse=True)
+
     def amorcage(self, aujourd_hui: dt.date) -> str:
         """Le bloc qui précède la première question d'une conversation : le profil, le
         sommaire des fiches et le journal des derniers jours, chacun plafonné."""
```

- [ ] **Step 4: Vérifier que tout passe**

Run: `uv run pytest -q && uv run ruff check . --extend-exclude spikes && uv run ruff format --check . --extend-exclude spikes && node --test "tests/web/*.test.mjs"`
Expected: 831 tests Python passent, 126 tests JavaScript passent, ruff ne dit rien.

- [ ] **Step 5: Commit**

```bash
git add src/atlas_core/memoire.py tests/test_memoire_documents.py
git commit -F - <<'MSG'
Mémoire : les documents, écrits par leur nom et listés pour la page

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

### Task 2: Supprimer, et une annulation qui dit ce qu'elle défait

Supprimer une fiche ou un document (jamais le journal, jamais un fichier retouché à la main), puis le commiter ; et
« annule » qui remet un fichier supprimé et dit ce que la note avait fait (création, retouche, suppression). La
confirmation de David viendra du Core (Task 3) : ici, la suppression elle-même.

**Files:**
- Modify: `src/atlas_core/memoire.py`
- Modify: `src/atlas_core/outils_memoire.py`
- Modify: `tests/test_memoire_chercher_annuler.py`
- Create: `tests/test_memoire_supprimer.py`

**Interfaces:**
- Consumes: Task 1 (`_titre_et_resume`, `_DOCUMENT`, `Memoire._cible`, `_defaire`).
- Produces: `PREFIXE_SUPPRESSION = "suppression de "` ; `Defait(chemin: str, titre: str, nature: str)` (frozen
  dataclass, `nature` : « creation », « retouche » ou « suppression ») ; `Memoire.titre_de(chemin) -> str` (le titre
  de ce qu'une suppression retirerait, sinon `ErreurMemoire`) ; `Memoire.supprimer(chemin) -> str` (commit
  « Atlas : suppression de <titre> ») ; `Memoire.annuler() -> Defait` (au lieu du titre seul : `outils_memoire.py`
  lit `defait.titre`).

- [ ] **Step 1: Écrire les tests qui échouent**

Modifier `tests/test_memoire_chercher_annuler.py` :

```diff
--- a/tests/test_memoire_chercher_annuler.py
+++ b/tests/test_memoire_chercher_annuler.py
@@ -99,7 +99,7 @@ def test_chercher_ignore_ce_qui_n_est_pas_une_fiche_permise(memoire, tmp_path):
 def test_annuler_retire_la_derniere_note_et_rend_son_titre(memoire):
     memoire.ecrire("personnes/paul-durand.md", PAUL)
     memoire.ecrire("personnes/elise-martin.md", ELISE)
-    assert memoire.annuler() == "Élise Martin"
+    assert memoire.annuler().titre == "Élise Martin"
     assert not (memoire.racine / "personnes" / "elise-martin.md").exists()
     assert memoire.lire("personnes/paul-durand.md") == PAUL
     assert git(memoire, "log", "-1", "--format=%ae|%s").strip() == (
@@ -117,8 +117,8 @@ def test_annuler_une_modification_rend_la_version_d_avant(memoire):
 def test_redire_annuler_remonte_d_une_note(memoire):
     memoire.ecrire("personnes/paul-durand.md", PAUL)
     memoire.ecrire("personnes/elise-martin.md", ELISE)
-    assert memoire.annuler() == "Élise Martin"
-    assert memoire.annuler() == "Paul Durand"
+    assert memoire.annuler().titre == "Élise Martin"
+    assert memoire.annuler().titre == "Paul Durand"
     with pytest.raises(ErreurMemoire, match="plus de note à retirer"):
         memoire.annuler()
 
@@ -142,7 +142,7 @@ def test_ni_le_journal_ni_les_commits_de_david_ne_s_annulent(memoire):
         "Journal : 25 septembre 2026",
         auteur="Atlas|atlas@atlas.local",
     )
-    assert memoire.annuler() == "Paul Durand"
+    assert memoire.annuler().titre == "Paul Durand"
     assert (memoire.racine / "projets" / "site-web.md").exists()
     assert (memoire.racine / "journal" / "2026-09-25.md").exists()
 
```

Créer `tests/test_memoire_supprimer.py` :

```python
"""Supprimer une fiche ou un document, et l'annuler : dans un vrai dépôt git temporaire. La
confirmation de David est l'affaire du Core (confirmation.py) : ici, la suppression elle-même."""

import subprocess

import pytest

from atlas_core.memoire import Defait, ErreurMemoire, Memoire

PAUL = "# Paul Durand\n\nProspect ; rendez-vous le jeudi 2 octobre 2026.\n"
OFFRE = "# Offre de lancement\n\nTrois formules pour les premiers clients.\n"


@pytest.fixture
def memoire(tmp_path) -> Memoire:
    ouverte = Memoire.ouvrir(tmp_path / "memoire")
    assert ouverte is not None
    return ouverte


def git(memoire: Memoire, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(memoire.racine), *arguments], capture_output=True, text=True, check=True
    ).stdout


# --- ce que la suppression retirerait ---------------------------------------------


def test_titre_de_nomme_une_fiche_un_document_ou_le_profil(memoire):
    memoire.ecrire("personnes/paul-durand.md", PAUL)
    memoire.ecrire("profil.md", "# Profil\n\nDavid.\n")
    memoire.ecrire_document("offre-de-lancement", OFFRE)
    assert memoire.titre_de("personnes/paul-durand.md") == "Paul Durand"
    assert memoire.titre_de("profil.md") == "Profil"
    assert memoire.titre_de("documents/offre-de-lancement.md") == "Offre de lancement"
    assert (memoire.racine / "personnes" / "paul-durand.md").exists()


@pytest.mark.parametrize(
    "chemin", ["journal/2026-09-25.md", "../ailleurs.md", "notes.md", "documents/Offre.md"]
)
def test_ni_le_journal_ni_un_autre_fichier_ne_se_suppriment(memoire, chemin):
    (memoire.racine / "journal").mkdir()
    (memoire.racine / "journal" / "2026-09-25.md").write_text("# Journal du 25 septembre 2026\n")
    with pytest.raises(ErreurMemoire, match="n'est pas une fiche"):
        memoire.titre_de(chemin)
    with pytest.raises(ErreurMemoire, match="n'est pas une fiche"):
        memoire.supprimer(chemin)
    assert (memoire.racine / "journal" / "2026-09-25.md").exists()


def test_un_fichier_absent_ne_se_supprime_pas(memoire):
    with pytest.raises(ErreurMemoire, match="projets/site-web.md n'existe pas"):
        memoire.titre_de("projets/site-web.md")
    with pytest.raises(ErreurMemoire, match="projets/site-web.md n'existe pas"):
        memoire.supprimer("projets/site-web.md")


# --- supprimer --------------------------------------------------------------------


def test_supprimer_retire_le_fichier_et_le_commite_sous_atlas(memoire):
    memoire.ecrire("personnes/paul-durand.md", PAUL)
    assert memoire.supprimer("personnes/paul-durand.md") == "Paul Durand"
    assert not (memoire.racine / "personnes" / "paul-durand.md").exists()
    assert git(memoire, "log", "-1", "--format=%an|%s").strip() == (
        "Atlas|Atlas : suppression de Paul Durand"
    )
    assert git(memoire, "status", "--porcelain") == ""


def test_supprimer_un_document(memoire):
    memoire.ecrire_document("offre-de-lancement", OFFRE)
    assert memoire.supprimer("documents/offre-de-lancement.md") == "Offre de lancement"
    assert memoire.documents() == []


def test_une_retouche_a_la_main_ne_se_supprime_pas(memoire):
    memoire.ecrire("personnes/paul-durand.md", PAUL)
    (memoire.racine / "personnes" / "paul-durand.md").write_text(PAUL + "\nNote à la main.\n")
    with pytest.raises(ErreurMemoire, match="retouché à la main"):
        memoire.supprimer("personnes/paul-durand.md")
    assert memoire.lire("personnes/paul-durand.md").endswith("Note à la main.\n")


def test_un_fichier_ecrit_a_la_main_et_jamais_commite_ne_se_supprime_pas(memoire):
    (memoire.racine / "projets").mkdir()
    (memoire.racine / "projets" / "site-web.md").write_text("# Site web\n\nÀ moi.\n")
    with pytest.raises(ErreurMemoire, match="retouché à la main"):
        memoire.supprimer("projets/site-web.md")
    assert (memoire.racine / "projets" / "site-web.md").exists()


def test_supprimer_ne_commite_pas_ce_que_david_a_prepare_ailleurs(memoire):
    memoire.ecrire("personnes/paul-durand.md", PAUL)
    (memoire.racine / "notes.txt").write_text("à moi\n")
    git(memoire, "add", "notes.txt")
    memoire.supprimer("personnes/paul-durand.md")
    assert git(memoire, "status", "--porcelain").strip() == "A  notes.txt"


# --- annuler dit ce qui a été défait ----------------------------------------------


def test_annuler_une_suppression_remet_le_fichier(memoire):
    memoire.ecrire_document("offre-de-lancement", OFFRE)
    memoire.supprimer("documents/offre-de-lancement.md")
    assert memoire.annuler() == Defait(
        "documents/offre-de-lancement.md", "Offre de lancement", "suppression"
    )
    assert memoire.lire("documents/offre-de-lancement.md") == OFFRE
    assert git(memoire, "log", "-1", "--format=%s").strip() == "Annulé : Offre de lancement"


def test_annuler_dit_si_la_note_creait_ou_retouchait(memoire):
    memoire.ecrire_document("offre-de-lancement", OFFRE)
    memoire.ecrire_document("offre-de-lancement", OFFRE + "\nÀ revoir.\n")
    assert memoire.annuler() == Defait(
        "documents/offre-de-lancement.md", "Offre de lancement", "retouche"
    )
    assert memoire.annuler() == Defait(
        "documents/offre-de-lancement.md", "Offre de lancement", "creation"
    )
    assert memoire.documents() == []


def test_annuler_une_suppression_ne_remplace_pas_un_fichier_recree_a_la_main(memoire):
    memoire.ecrire("personnes/paul-durand.md", PAUL)
    memoire.supprimer("personnes/paul-durand.md")
    (memoire.racine / "personnes").mkdir(exist_ok=True)  # git a retiré le dossier vide
    (memoire.racine / "personnes" / "paul-durand.md").write_text("# Paul\n\nÀ moi.\n")
    with pytest.raises(ErreurMemoire, match="modifiée depuis"):
        memoire.annuler()
    assert memoire.lire("personnes/paul-durand.md") == "# Paul\n\nÀ moi.\n"
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `uv run pytest tests/test_memoire_supprimer.py tests/test_memoire_chercher_annuler.py -q`
Expected: FAIL — erreur de collecte : `ImportError: cannot import name 'Defait' from 'atlas_core.memoire'`.

- [ ] **Step 3: Écrire la suppression et l'annulation**

Modifier `src/atlas_core/memoire.py` :

```diff
--- a/src/atlas_core/memoire.py
+++ b/src/atlas_core/memoire.py
@@ -83,6 +83,7 @@ SECRET_MIN = 8  # une clé du Core plus courte ne se cherche pas : trop de faux
 RESULTATS_MAX = 20
 PREFIXE_NOTE = "Atlas : "
 PREFIXE_ANNULE = "Annulé : "
+PREFIXE_SUPPRESSION = "suppression de "
 PREFIXE_JOURNAL = "Journal : "
 # L'amorçage d'une conversation reste court, même quand la mémoire grossit.
 PROFIL_MAX = 4_000
@@ -105,6 +106,16 @@ class InfoDocument:
     modifie: dt.datetime
 
 
+@dataclass(frozen=True)
+class Defait:
+    """Ce qu'« annule » vient de défaire : la note avait créé, retouché ou supprimé ce
+    fichier (`nature` : « creation », « retouche » ou « suppression »)."""
+
+    chemin: str
+    titre: str
+    nature: str
+
+
 def _git(racine: Path, *arguments: str, entree: str | None = None) -> str:
     """Lance git dans le dépôt, sans dépendre de la configuration git de la machine ;
     `entree` est passée sur son entrée standard."""
@@ -323,9 +334,29 @@ class Memoire:
                         return trouvees
         return trouvees
 
-    def annuler(self) -> str:
-        """Défait la dernière écriture d'Atlas encore en place (`git revert`) ; rend son
-        titre. Ni le journal, ni les commits de David ne s'annulent."""
+    def titre_de(self, chemin: str) -> str:
+        """Le titre de la fiche ou du document qu'une suppression retirerait ; sinon
+        `ErreurMemoire` (ni le journal, ni un fichier absent ne se suppriment)."""
+        cible = self._cible(chemin, ecriture=True)
+        if not cible.is_file():
+            raise ErreurMemoire(f"{chemin} n'existe pas.")
+        return _titre_et_resume(_lire_texte(cible))[0] or chemin
+
+    def supprimer(self, chemin: str) -> str:
+        """Supprime une fiche ou un document, puis le commite ; rend son titre. Un fichier
+        retouché à la main depuis la dernière note reste à David."""
+        with self._verrou:
+            titre = self.titre_de(chemin)
+            if _git(self.racine, "status", "--porcelain", "--", chemin).strip():
+                raise ErreurMemoire(f"{chemin} a été retouché à la main : je n'y touche pas.")
+            _git(self.racine, "rm", "-q", "--", chemin)
+            message = f"{PREFIXE_NOTE}{PREFIXE_SUPPRESSION}{titre}"
+            _git(self.racine, "commit", "-q", "-m", message, "--", chemin)
+        return titre
+
+    def annuler(self) -> Defait:
+        """Défait la dernière écriture ou suppression d'Atlas encore en place, et dit ce
+        qu'elle avait fait. Ni le journal, ni les commits de David ne s'annulent."""
         with self._verrou:
             try:
                 historique = _git(self.racine, "log", "--format=%H%x1f%ae%x1f%s%x1f%b%x1e")
@@ -344,10 +375,14 @@ class Memoire:
                     return self._defaire(sha, sujet.removeprefix(PREFIXE_NOTE))
         raise ErreurMemoire("Il n'y a plus de note à retirer.")
 
-    def _defaire(self, sha: str, titre: str) -> str:
+    def _defaire(self, sha: str, titre: str) -> Defait:
         """Applique l'inverse de la note, tout ou rien, sur ses seuls fichiers : le travail
         de David, préparé ou non, n'est jamais touché."""
-        chemins = _git(self.racine, "show", "--name-only", "--format=", sha).split()
+        statut, chemin = _git(self.racine, "show", "--name-status", "--format=", sha).split()[:2]
+        nature = {"A": "creation", "D": "suppression"}.get(statut, "retouche")
+        if nature == "suppression":
+            titre = titre.removeprefix(PREFIXE_SUPPRESSION)
+        chemins = [chemin]
         refus = ErreurMemoire("Je ne peux pas retirer cette note : la fiche a été modifiée depuis.")
         if _git(self.racine, "status", "--porcelain", "--", *chemins).strip():
             raise refus  # une retouche de David sur la fiche, même pas encore commitée
@@ -359,7 +394,7 @@ class Memoire:
         _git(self.racine, "apply", "--index", entree=inverse)
         message = f"{PREFIXE_ANNULE}{titre}\n\nAnnule {sha}"
         _git(self.racine, "commit", "-q", "-m", message, "--", *chemins)
-        return titre
+        return Defait(chemin, titre, nature)
 
     # --- l'amorçage et le journal -----------------------------------------------------
 
```

Modifier `src/atlas_core/outils_memoire.py` :

```diff
--- a/src/atlas_core/outils_memoire.py
+++ b/src/atlas_core/outils_memoire.py
@@ -123,6 +123,6 @@ class OutilsMemoire:
     async def _annuler(self, arguments: dict[str, Any]) -> dict[str, Any]:
         if not self.ecriture_permise:
             return _refus(PENDANT_LE_RESUME)
-        titre = await asyncio.to_thread(self.memoire.annuler)
+        defait = await asyncio.to_thread(self.memoire.annuler)
         self._annonces.append(Note(ANNONCE_RETRAIT))
-        return _texte(f"La note « {titre} » est retirée.")
+        return _texte(f"La note « {defait.titre} » est retirée.")
```

- [ ] **Step 4: Vérifier que tout passe**

Run: `uv run pytest -q && uv run ruff check . --extend-exclude spikes && uv run ruff format --check . --extend-exclude spikes && node --test "tests/web/*.test.mjs"`
Expected: 845 tests Python passent, 126 tests JavaScript passent, ruff ne dit rien.

- [ ] **Step 5: Commit**

```bash
git add src/atlas_core/memoire.py src/atlas_core/outils_memoire.py tests/test_memoire_chercher_annuler.py tests/test_memoire_supprimer.py
git commit -F - <<'MSG'
Mémoire : supprimer une fiche ou un document, et annuler qui dit ce qu'il défait

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

### Task 3: L'action qui attend le « oui » de David

Le cœur du N3 : une action résolue (une `Suppression` qui sait se dire), mise en attente — une seule à la fois,
trente secondes —, la question posée une fois, puis la réponse de David lue sans Claude : oui, non, ou autre chose.
Les lignes qui diront le résultat à Claude, et les rappels qui préviendront les pages. Le marqueur `Confirmation`
est une `Note` : la session le dit sans rien changer.

**Files:**
- Modify: `src/atlas_core/cerveau.py`
- Create: `src/atlas_core/confirmation.py`
- Create: `tests/test_confirmation.py`
- Modify: `tests/test_session_cerveau.py`

**Interfaces:**
- Consumes: `cerveau.Note`.
- Produces: `cerveau.Confirmation(Note)` (la question dans `annonce`) ; `atlas_core.confirmation` : `DELAI_S = 30.0`,
  `RIEN_SUPPRIME`, `OUI`, `NON`, `lire_reponse(texte) -> str` (« oui », « non » ou « autre ») ;
  `Suppression(chemin: str, titre: str, executer: Callable[[], object])` (frozen dataclass ; propriétés `voix`,
  `question`, `faite`, `ratee`, `objet`, `bilan`, `page_faite`) ; `Confirmations(attendre=asyncio.sleep,
  sur_question=None, sur_fin=None)` avec `en_attente: bool`, `mettre_en_attente(action) -> bool`,
  `poser() -> Confirmation | None`, `async trancher(texte) -> tuple[str, bool]` (la phrase pour David, et si sa
  phrase part encore à Claude), `abandonner_si_non_posee()`, `abandonner()`, `prendre_les_lignes() -> list[str]`,
  et les attributs `sur_question`, `sur_fin`.

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/test_confirmation.py` :

```python
"""L'action qui attend le « oui » de David : la lecture de sa réponse, les phrases, le délai.
Une minuterie qu'on fait sonner à la main remplace les trente secondes."""

import asyncio
import threading

import pytest

from atlas_core.cerveau import Confirmation, Note
from atlas_core.confirmation import DELAI_S, Confirmations, Suppression, lire_reponse
from atlas_core.memoire import ErreurMemoire


class Minuterie:
    def __init__(self) -> None:
        self.delais: list[float] = []
        self._sonnerie = asyncio.Event()

    async def __call__(self, delai: float) -> None:
        self.delais.append(delai)
        await self._sonnerie.wait()

    def sonner(self) -> None:
        self._sonnerie.set()


class Temoin:
    """Ce que les pages reçoivent, et les exécutions de l'action."""

    def __init__(self) -> None:
        self.questions: list[str] = []
        self.fins: list[str] = []
        self.executions: list[int] = []

    def executer(self) -> None:
        self.executions.append(threading.get_ident())


def _document(temoin: Temoin) -> Suppression:
    return Suppression("documents/offre-de-lancement.md", "Offre de lancement", temoin.executer)


@pytest.fixture
def temoin() -> Temoin:
    return Temoin()


@pytest.fixture
def minuterie() -> Minuterie:
    return Minuterie()


@pytest.fixture
def confirmations(temoin, minuterie) -> Confirmations:
    return Confirmations(
        attendre=minuterie, sur_question=temoin.questions.append, sur_fin=temoin.fins.append
    )


async def _laisser_tourner() -> None:
    for _ in range(5):
        await asyncio.sleep(0)


# --- la réponse de David ---------------------------------------------------------------


@pytest.mark.parametrize(
    "texte",
    [
        "Oui.",
        "OUI !",
        "ouais",
        "Oui oui",
        "Oui, vas-y.",
        "Vas-y !",
        "Je confirme.",
        "Oui, je confirme.",
        "Confirme",
        "D'accord",
        "D’accord.",
        "Oui, d'accord.",
        "OK",
        "Oui, ok.",
        "C'est bon.",
        "Oui, c'est bon.",
        "Supprime.",
        "Oui, supprime.",
        "Supprime-le.",
        "Supprime-la.",
        "Exactement.",
        "Tout à fait.",
        "Atlas, oui.",
        "Oui, Atlas.",
    ],
)
def test_ces_phrases_valent_oui(texte):
    assert lire_reponse(texte) == "oui"


@pytest.mark.parametrize(
    "texte",
    [
        "Non.",
        "Non non",
        "Non merci.",
        "Annule !",
        "Non, annule.",
        "Laisse tomber.",
        "Non, laisse tomber.",
        "Stop",
        "Arrête.",
        "Surtout pas !",
        "Pas du tout.",
        "Ne supprime pas.",
        "Ne supprime rien.",
        "Atlas, non.",
    ],
)
def test_ces_phrases_valent_non(texte):
    assert lire_reponse(texte) == "non"


@pytest.mark.parametrize(
    "texte",
    [
        "Oui, mais lis-le-moi d'abord.",
        "Qu'est-ce qu'il contient ?",
        "Oui non",
        "Supprime aussi la fiche de Paul.",
        "Atlas",
        "",
    ],
)
def test_tout_le_reste_vaut_autre_chose(texte):
    assert lire_reponse(texte) == "autre"


# --- les phrases d'une suppression ------------------------------------------------------


def test_une_suppression_se_dit_selon_ce_qu_elle_retire(temoin):
    document = _document(temoin)
    fiche = Suppression("personnes/paul-durand.md", "Paul Durand", temoin.executer)
    profil = Suppression("profil.md", "Profil", temoin.executer)
    assert document.question == "Je supprime le document Offre de lancement. Tu confirmes ?"
    assert fiche.question == "Je supprime la fiche Paul Durand. Tu confirmes ?"
    assert profil.question == "Je supprime ton profil. Tu confirmes ?"
    assert document.faite == "C'est fait : le document Offre de lancement est supprimé."
    assert fiche.faite == "C'est fait : la fiche Paul Durand est supprimée."
    assert profil.faite == "C'est fait : ton profil est supprimé."
    assert fiche.ratee == "Je n'ai pas pu supprimer la fiche Paul Durand."
    assert document.objet == "la suppression du document « Offre de lancement »"
    assert fiche.objet == "la suppression de la fiche « Paul Durand »"
    assert profil.objet == "la suppression du profil"
    assert fiche.page_faite == "Supprimé : la fiche Paul Durand."


# --- l'attente -----------------------------------------------------------------------


async def test_une_seule_action_attend_a_la_fois(confirmations, temoin):
    assert confirmations.mettre_en_attente(_document(temoin)) is True
    assert confirmations.mettre_en_attente(_document(temoin)) is False
    assert confirmations.en_attente


async def test_la_question_se_pose_une_fois_et_s_affiche_dans_les_pages(confirmations, temoin):
    assert confirmations.poser() is None  # rien n'attend
    confirmations.mettre_en_attente(_document(temoin))
    question = confirmations.poser()
    assert question == Confirmation("Je supprime le document Offre de lancement. Tu confirmes ?")
    assert isinstance(question, Note)  # la session la dit comme une annonce
    assert confirmations.poser() is None
    assert temoin.questions == [question.annonce]


async def test_oui_execute_hors_de_la_boucle_et_le_dit(confirmations, temoin):
    confirmations.mettre_en_attente(_document(temoin))
    confirmations.poser()
    phrase = await confirmations.trancher("Oui, vas-y.")
    assert phrase == ("C'est fait : le document Offre de lancement est supprimé.", False)
    assert len(temoin.executions) == 1 and temoin.executions[0] != threading.get_ident()
    assert not confirmations.en_attente
    assert temoin.fins == ["Supprimé : le document Offre de lancement."]
    assert confirmations.prendre_les_lignes() == [
        "[Confirmé par David : le document « Offre de lancement » est supprimé.]"
    ]
    assert confirmations.prendre_les_lignes() == []


async def test_non_abandonne_sans_rien_executer(confirmations, temoin):
    confirmations.mettre_en_attente(_document(temoin))
    confirmations.poser()
    assert await confirmations.trancher("Non, laisse tomber.") == (
        "D'accord, je ne supprime rien.",
        False,
    )
    assert temoin.executions == [] and not confirmations.en_attente
    assert temoin.fins == ["Rien n'a été supprimé."]
    assert confirmations.prendre_les_lignes() == ["[Refusé par David : rien n'a été supprimé.]"]


async def test_autre_chose_abandonne_puis_part_a_claude(confirmations, temoin):
    confirmations.mettre_en_attente(_document(temoin))
    confirmations.poser()
    assert await confirmations.trancher("Oui, mais lis-le-moi d'abord.") == (
        "Je ne supprime rien.",
        True,
    )
    assert temoin.executions == [] and temoin.fins == ["Rien n'a été supprimé."]
    assert confirmations.prendre_les_lignes() == [
        "[David a répondu autre chose : la suppression du document « Offre de lancement » est "
        "abandonnée.]"
    ]


async def test_un_echec_apres_le_oui_se_dit_et_se_note(confirmations, caplog):
    def echouer() -> None:
        raise ErreurMemoire("documents/offre-de-lancement.md a été retouché à la main.")

    fins: list[str] = []
    confirmations.sur_fin = fins.append
    confirmations.mettre_en_attente(
        Suppression("documents/offre-de-lancement.md", "Offre de lancement", echouer)
    )
    confirmations.poser()
    assert await confirmations.trancher("oui") == (
        "Je n'ai pas pu supprimer le document Offre de lancement.",
        False,
    )
    assert fins == ["La suppression a échoué."]
    assert confirmations.prendre_les_lignes() == [
        "[La suppression du document « Offre de lancement » a échoué.]"
    ]
    assert "retouché à la main" in caplog.text


async def test_trente_secondes_sans_reponse_abandonnent_en_silence(
    confirmations, temoin, minuterie
):
    confirmations.mettre_en_attente(_document(temoin))
    confirmations.poser()
    await _laisser_tourner()
    assert minuterie.delais == [DELAI_S] and DELAI_S == 30
    minuterie.sonner()
    await _laisser_tourner()
    assert not confirmations.en_attente and temoin.executions == []
    assert temoin.fins == ["Suppression abandonnée : pas de réponse."]
    assert confirmations.prendre_les_lignes() == [
        "[Sans réponse de David : la suppression du document « Offre de lancement » est "
        "abandonnée.]"
    ]


async def test_une_reponse_arrete_la_minuterie(confirmations, temoin, minuterie):
    confirmations.mettre_en_attente(_document(temoin))
    confirmations.poser()
    await _laisser_tourner()
    await confirmations.trancher("non")
    confirmations.prendre_les_lignes()
    minuterie.sonner()
    await _laisser_tourner()
    assert temoin.fins == ["Rien n'a été supprimé."]
    assert confirmations.prendre_les_lignes() == []


async def test_une_question_jamais_posee_s_abandonne_sans_rien_montrer(confirmations, temoin):
    confirmations.mettre_en_attente(_document(temoin))
    confirmations.abandonner_si_non_posee()
    assert not confirmations.en_attente and temoin.fins == []
    assert confirmations.prendre_les_lignes() == [
        "[David a parlé avant la question : la suppression du document « Offre de lancement » "
        "est abandonnée.]"
    ]


async def test_une_question_posee_ne_s_abandonne_pas_ainsi(confirmations, temoin):
    confirmations.mettre_en_attente(_document(temoin))
    confirmations.poser()
    confirmations.abandonner_si_non_posee()
    assert confirmations.en_attente


async def test_la_fin_d_une_conversation_ne_montre_rien_d_une_question_jamais_posee(
    confirmations, temoin
):
    confirmations.mettre_en_attente(_document(temoin))
    confirmations.abandonner()
    assert not confirmations.en_attente and temoin.fins == []


async def test_la_fin_de_la_conversation_abandonne_et_oublie_les_lignes(confirmations, temoin):
    confirmations.mettre_en_attente(_document(temoin))
    confirmations.poser()
    await confirmations.trancher("non")
    confirmations.mettre_en_attente(_document(temoin))
    confirmations.poser()
    confirmations.abandonner()
    assert not confirmations.en_attente and temoin.executions == []
    assert temoin.fins == ["Rien n'a été supprimé.", "Rien n'a été supprimé."]
    assert confirmations.prendre_les_lignes() == []


async def test_une_question_jamais_posee_qui_expire_ne_montre_rien_aux_pages(
    confirmations, temoin, minuterie
):
    confirmations.mettre_en_attente(_document(temoin))
    await _laisser_tourner()
    minuterie.sonner()
    await _laisser_tourner()
    assert not confirmations.en_attente and temoin.fins == []
    assert len(confirmations.prendre_les_lignes()) == 1
```

Modifier `tests/test_session_cerveau.py` :

```diff
--- a/tests/test_session_cerveau.py
+++ b/tests/test_session_cerveau.py
@@ -12,7 +12,7 @@ from test_session_web import (
     FauxPlanificateur,
 )
 
-from atlas_core.cerveau import RECHERCHE, ErreurCerveau, Note
+from atlas_core.cerveau import RECHERCHE, Confirmation, ErreurCerveau, Note
 from atlas_core.protocole import Dire, Erreur, Etat, FinEnonce, Interruption, Reveil
 from atlas_core.protocole_web import Reponse
 from atlas_core.session import PHRASE_ATTENTE, Session
@@ -302,6 +302,25 @@ async def test_sans_voix_une_note_ne_s_annonce_qu_en_texte():
     await s.fermer()
 
 
+QUESTION = Confirmation("Je supprime le document Offre de lancement. Tu confirmes ?")
+
+
+async def test_une_confirmation_se_dit_comme_une_note_et_sans_voix_s_affiche():
+    c, d = Collecteur(), DiffuseurEspion()
+    s = _session(c, d, CerveauScript("D'accord. ", QUESTION))
+    await s.sur_saisie("Supprime l'offre.")
+    await _attendre(lambda: c.etats()[-1:] == ["repos"])
+    assert _dits(c) == ["D'accord.", QUESTION.annonce]
+    await s.fermer()
+    c, d = Collecteur(), DiffuseurEspion()
+    s = _session(c, d, CerveauScript(QUESTION), avec_voix=lambda: False)
+    await s.sur_saisie("Supprime l'offre.")
+    await _attendre(lambda: [e.valeur for e in d.de(Etat)][-1:] == ["repos"])
+    assert _dits(c) == []
+    assert [r.texte for r in d.de(Reponse)] == [QUESTION.annonce]
+    await s.fermer()
+
+
 # --- les erreurs du cerveau ------------------------------------------------------------
 
 
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `uv run pytest tests/test_confirmation.py tests/test_session_cerveau.py -q`
Expected: FAIL — deux erreurs de collecte : `ImportError: cannot import name 'Confirmation' from 'atlas_core.cerveau'`.

- [ ] **Step 3: Écrire la confirmation**

Modifier `src/atlas_core/cerveau.py` :

```diff
--- a/src/atlas_core/cerveau.py
+++ b/src/atlas_core/cerveau.py
@@ -89,6 +89,13 @@ class Note:
     annonce: str
 
 
+@dataclass(frozen=True)
+class Confirmation(Note):
+    """Dans le flux d'une réponse : Atlas demande à David de confirmer une action (N3) ;
+    `annonce` est la question (« Je supprime le document X. Tu confirmes ? »), dite comme
+    une note."""
+
+
 class ErreurCerveau(Exception):
     """Le cerveau n'a pas pu répondre. Le message est en français, prêt à être dit."""
 
```

Créer `src/atlas_core/confirmation.py` :

```python
"""L'action qui attend le « oui » de David (spec 2c §6).

Un outil N3 ne fait rien lui-même : il décrit son action, que le Core met ici en attente.
Atlas pose la question ; la phrase suivante de David, d'où qu'elle vienne, est lue ici avant
Claude. « Oui » : l'action s'exécute. « Non », autre chose, ou trente secondes de silence :
elle est abandonnée. Claude apprend le résultat par une ligne au début de sa question
suivante ; les pages voient la question, puis comment l'attente s'est finie.
"""

from __future__ import annotations

import asyncio
import logging
import re
import unicodedata
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from .cerveau import Confirmation

_journal = logging.getLogger(__name__)

DELAI_S = 30.0
RIEN_SUPPRIME = "Rien n'a été supprimé."
_OUI = (
    "oui",
    "ouais",
    "oui oui",
    "vas-y",
    "oui vas-y",
    "je confirme",
    "oui je confirme",
    "confirme",
    "d'accord",
    "oui d'accord",
    "ok",
    "oui ok",
    "c'est bon",
    "oui c'est bon",
    "supprime",
    "oui supprime",
    "supprime-le",
    "supprime-la",
    "exactement",
    "tout à fait",
)
_NON = (
    "non",
    "non non",
    "non merci",
    "annule",
    "non annule",
    "laisse tomber",
    "non laisse tomber",
    "stop",
    "arrête",
    "surtout pas",
    "pas du tout",
    "ne supprime pas",
    "ne supprime rien",
)


def _normaliser(texte: str) -> str:
    """Sans majuscules, accents ni ponctuation ; un « Atlas » au début ou à la fin ignoré."""
    plie = unicodedata.normalize("NFD", texte.casefold())
    sans_accents = "".join(c for c in plie if not unicodedata.combining(c))
    mots = re.sub(r"[^a-z0-9]+", " ", sans_accents).split()
    if mots and mots[0] == "atlas":
        mots = mots[1:]
    if mots and mots[-1] == "atlas":
        mots = mots[:-1]
    return " ".join(mots)


OUI = frozenset(map(_normaliser, _OUI))
NON = frozenset(map(_normaliser, _NON))


def lire_reponse(texte: str) -> str:
    """« oui », « non », ou « autre » : seule une de ces phrases, exactement, vaut oui ou non.
    Dans le doute, ce n'est pas oui."""
    normal = _normaliser(texte)
    if normal in OUI:
        return "oui"
    if normal in NON:
        return "non"
    return "autre"


@dataclass(frozen=True)
class Suppression:
    """Une suppression résolue — ce qu'elle retire — et la façon de la dire. `executer`
    tourne hors de la boucle du Core, seulement après le « oui »."""

    chemin: str
    titre: str
    executer: Callable[[], object]

    @property
    def _nature(self) -> str:
        if self.chemin == "profil.md":
            return "profil"
        return "document" if self.chemin.startswith("documents/") else "fiche"

    @property
    def voix(self) -> str:
        return {
            "profil": "ton profil",
            "document": f"le document {self.titre}",
            "fiche": f"la fiche {self.titre}",
        }[self._nature]

    @property
    def _supprime(self) -> str:
        return "supprimée" if self._nature == "fiche" else "supprimé"

    @property
    def question(self) -> str:
        return f"Je supprime {self.voix}. Tu confirmes ?"

    @property
    def faite(self) -> str:
        return f"C'est fait : {self.voix} est {self._supprime}."

    @property
    def ratee(self) -> str:
        return f"Je n'ai pas pu supprimer {self.voix}."

    @property
    def objet(self) -> str:
        """Pour Claude : « la suppression du document « X » »."""
        return {
            "profil": "la suppression du profil",
            "document": f"la suppression du document « {self.titre} »",
            "fiche": f"la suppression de la fiche « {self.titre} »",
        }[self._nature]

    @property
    def bilan(self) -> str:
        """Pour Claude, après le oui : « le document « X » est supprimé »."""
        return {
            "profil": "le profil est supprimé",
            "document": f"le document « {self.titre} » est supprimé",
            "fiche": f"la fiche « {self.titre} » est supprimée",
        }[self._nature]

    @property
    def page_faite(self) -> str:
        return f"Supprimé : {self.voix}."


class Confirmations:
    """L'action en attente — une seule à la fois — et les lignes qui diront à Claude comment
    elle s'est finie. `sur_question` et `sur_fin` préviennent les pages."""

    def __init__(
        self,
        attendre: Callable[[float], Awaitable[None]] = asyncio.sleep,
        sur_question: Callable[[str], None] | None = None,
        sur_fin: Callable[[str], None] | None = None,
    ) -> None:
        self._attendre = attendre
        self.sur_question = sur_question or (lambda texte: None)
        self.sur_fin = sur_fin or (lambda texte: None)
        self._action: Suppression | None = None
        self._posee = False
        self._minuterie: asyncio.Task | None = None
        self._lignes: list[str] = []

    @property
    def en_attente(self) -> bool:
        return self._action is not None

    def mettre_en_attente(self, action: Suppression) -> bool:
        """Met l'action de côté ; False si une autre attend déjà la réponse de David."""
        if self._action is not None:
            return False
        self._action, self._posee = action, False
        self._minuterie = asyncio.create_task(self._expirer(action))
        return True

    def poser(self) -> Confirmation | None:
        """La question à dire, une seule fois, quand la réponse d'Atlas en arrive là."""
        if self._action is None or self._posee:
            return None
        self._posee = True
        self.sur_question(self._action.question)
        return Confirmation(self._action.question)

    async def trancher(self, texte: str) -> tuple[str, bool]:
        """Lit la réponse de David à la question posée. Rend la phrase à lui dire, et si sa
        phrase doit encore partir à Claude (« autre chose »)."""
        action = self._action
        assert action is not None, "aucune action n'attend"
        reponse = lire_reponse(texte)
        self._finir()
        if reponse == "non":
            self._conclure("[Refusé par David : rien n'a été supprimé.]", RIEN_SUPPRIME)
            return "D'accord, je ne supprime rien.", False
        if reponse == "autre":
            ligne = f"[David a répondu autre chose : {action.objet} est abandonnée.]"
            self._conclure(ligne, RIEN_SUPPRIME)
            return "Je ne supprime rien.", True
        try:
            await asyncio.to_thread(action.executer)
        except Exception as e:  # noqa: BLE001 — retouché entre-temps, dépôt en panne…
            _journal.warning("%s confirmée n'a pas pu se faire : %s", action.objet, e)
            objet = action.objet[0].upper() + action.objet[1:]
            self._conclure(f"[{objet} a échoué.]", "La suppression a échoué.")
            return action.ratee, False
        self._conclure(f"[Confirmé par David : {action.bilan}.]", action.page_faite)
        return action.faite, False

    def abandonner_si_non_posee(self) -> None:
        """La réponse d'Atlas s'est arrêtée avant la question : David ne l'a pas entendue,
        sa phrase suivante ne peut pas y répondre."""
        action = self._action
        if action is not None and not self._posee:
            self._finir()
            ligne = f"[David a parlé avant la question : {action.objet} est abandonnée.]"
            self._lignes.append(ligne)

    def abandonner(self) -> None:
        """La conversation se termine : l'action en attente est abandonnée, et les lignes
        pour Claude, qui ne valaient que pour elle, oubliées."""
        posee = self._posee
        if self._action is not None:
            self._finir()
            if posee:
                self.sur_fin(RIEN_SUPPRIME)
        self._lignes.clear()

    def prendre_les_lignes(self) -> list[str]:
        lignes, self._lignes = self._lignes, []
        return lignes

    async def _expirer(self, action: Suppression) -> None:
        await self._attendre(DELAI_S)
        if self._action is action:
            self._minuterie = None  # c'est elle qui sonne : rien à annuler
            posee = self._posee
            self._finir()
            ligne = f"[Sans réponse de David : {action.objet} est abandonnée.]"
            self._conclure(ligne, "Suppression abandonnée : pas de réponse." if posee else None)

    def _finir(self) -> None:
        if self._minuterie is not None:
            self._minuterie.cancel()
        self._action, self._posee, self._minuterie = None, False, None

    def _conclure(self, ligne: str, pour_les_pages: str | None) -> None:
        """La ligne pour Claude ; et pour les pages, si elles ont vu la question."""
        self._lignes.append(ligne)
        if pour_les_pages is not None:
            self.sur_fin(pour_les_pages)
```

- [ ] **Step 4: Vérifier que tout passe**

Run: `uv run pytest -q && uv run ruff check . --extend-exclude spikes && uv run ruff format --check . --extend-exclude spikes && node --test "tests/web/*.test.mjs"`
Expected: 904 tests Python passent, 126 tests JavaScript passent, ruff ne dit rien.

- [ ] **Step 5: Commit**

```bash
git add src/atlas_core/cerveau.py src/atlas_core/confirmation.py tests/test_confirmation.py tests/test_session_cerveau.py
git commit -F - <<'MSG'
Confirmation : l'action qui attend le « oui » de David

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

### Task 4: Les niveaux d'autorisation

Chaque outil se déclare avec son niveau, et le serveur « atlas » applique la règle autour de lui : N1 rend son
résultat sans rien dire ; N2 fait annoncer ce qui a changé ; N3 ne fait rien et met son action en attente. Pendant
le résumé, N2 et N3 refusent. Vérifié avec des outils factices, indépendants de la mémoire.

**Files:**
- Create: `src/atlas_core/outils.py`
- Create: `tests/test_outils.py`

**Interfaces:**
- Consumes: Task 3 (`Confirmations.mettre_en_attente`), `memoire.ErreurMemoire`, `cerveau.Note`.
- Produces: `atlas_core.outils` : `SERVEUR = "atlas"`, `PENDANT_LE_RESUME`, `ECHEC`, `EN_ATTENTE`,
  `DEJA_EN_ATTENTE` ; `Niveau` (IntEnum `N1`, `N2`, `N3`) ; `Fait(texte: str, annonce: str | None = None)` ;
  `Outil(nom, description, parametres: dict[str, type], niveau: Niveau, gestionnaire)` (le gestionnaire rend du
  texte en N1, un `Fait` en N2, une `Suppression` en N3) ; `ServeurAtlas(outils: list[Outil], confirmations)` avec
  `declarations`, `confirmations`, `ecriture_permise`, `outils: list[SdkMcpTool]`, `noms`, `serveur()`,
  `prendre_les_annonces() -> list[Note]`.

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/test_outils.py` :

```python
"""Les niveaux d'autorisation : la règle que le Core applique autour de chaque outil, vérifiée
avec des outils factices, appelés comme Claude les appelle (leur gestionnaire)."""

import asyncio

import pytest

from atlas_core.cerveau import Note
from atlas_core.confirmation import Confirmations, Suppression
from atlas_core.memoire import ErreurMemoire
from atlas_core.outils import (
    DEJA_EN_ATTENTE,
    ECHEC,
    EN_ATTENTE,
    PENDANT_LE_RESUME,
    Fait,
    Niveau,
    Outil,
    ServeurAtlas,
)


class Banc:
    """Trois outils factices, un par niveau, qui notent leurs appels."""

    def __init__(self) -> None:
        self.appels: list[str] = []
        self.executions: list[str] = []

    async def lire(self, arguments: dict) -> str:
        self.appels.append("lire")
        return f"contenu de {arguments['chemin']}"

    async def ecrire(self, arguments: dict) -> Fait:
        self.appels.append("ecrire")
        if arguments["texte"] == "pareil":
            return Fait("Rien n'a changé.")
        return Fait("C'est écrit.", annonce="J'ai écrit la fiche Paul Durand.")

    async def supprimer(self, arguments: dict) -> Suppression:
        self.appels.append("supprimer")
        chemin = arguments["chemin"]
        return Suppression(chemin, "Paul Durand", lambda: self.executions.append(chemin))

    def outils(self) -> list[Outil]:
        return [
            Outil("lire", "Lit.", {"chemin": str}, Niveau.N1, self.lire),
            Outil("ecrire", "Écrit.", {"texte": str}, Niveau.N2, self.ecrire),
            Outil("supprimer", "Supprime.", {"chemin": str}, Niveau.N3, self.supprimer),
        ]


@pytest.fixture
def banc() -> Banc:
    return Banc()


@pytest.fixture
def serveur(banc) -> ServeurAtlas:
    return ServeurAtlas(banc.outils(), Confirmations())


async def appeler(serveur: ServeurAtlas, nom: str, **arguments) -> tuple[str, bool]:
    outil = next(o for o in serveur.outils if o.name == nom)
    resultat = await outil.handler(arguments)
    return resultat["content"][0]["text"], resultat.get("is_error", False)


def test_claude_voit_les_outils_sous_le_serveur_atlas(serveur):
    assert serveur.noms == ["mcp__atlas__lire", "mcp__atlas__ecrire", "mcp__atlas__supprimer"]
    assert (serveur.serveur()["type"], serveur.serveur()["name"]) == ("sdk", "atlas")
    ecrire = next(o for o in serveur.outils if o.name == "ecrire")
    assert (ecrire.description, ecrire.input_schema) == ("Écrit.", {"texte": str})


def test_un_outil_se_declare_toujours_avec_son_niveau(serveur):
    with pytest.raises(TypeError):
        Outil("lire", "Lit.", {"chemin": str}, gestionnaire=Banc().lire)  # type: ignore[call-arg]
    assert [(o.nom, o.niveau) for o in serveur.declarations] == [
        ("lire", Niveau.N1),
        ("ecrire", Niveau.N2),
        ("supprimer", Niveau.N3),
    ]


async def test_n1_rend_son_resultat_sans_rien_annoncer(serveur):
    assert await appeler(serveur, "lire", chemin="profil.md") == ("contenu de profil.md", False)
    assert serveur.prendre_les_annonces() == []


async def test_n2_fait_annoncer_ce_qui_a_change_et_seulement_ca(serveur):
    assert await appeler(serveur, "ecrire", texte="neuf") == ("C'est écrit.", False)
    assert await appeler(serveur, "ecrire", texte="pareil") == ("Rien n'a changé.", False)
    assert serveur.prendre_les_annonces() == [Note("J'ai écrit la fiche Paul Durand.")]
    assert serveur.prendre_les_annonces() == []


async def test_n3_ne_fait_rien_et_met_l_action_en_attente(serveur, banc):
    assert await appeler(serveur, "supprimer", chemin="personnes/paul-durand.md") == (
        EN_ATTENTE,
        False,
    )
    assert banc.executions == []
    assert serveur.confirmations.en_attente
    assert serveur.prendre_les_annonces() == []  # la question, c'est le cerveau qui la pose
    assert "N'ajoute rien" in EN_ATTENTE and "ne dis pas que c'est fait" in EN_ATTENTE


async def test_une_seconde_action_n3_est_refusee_tant_que_la_premiere_attend(serveur, banc):
    await appeler(serveur, "supprimer", chemin="personnes/paul-durand.md")
    assert await appeler(serveur, "supprimer", chemin="projets/site-web.md") == (
        DEJA_EN_ATTENTE,
        True,
    )
    serveur.confirmations.poser()
    assert await serveur.confirmations.trancher("oui") == (
        "C'est fait : la fiche Paul Durand est supprimée.",
        False,
    )
    await asyncio.sleep(0)
    assert banc.executions == ["personnes/paul-durand.md"]


async def test_pendant_le_resume_n2_et_n3_refusent_sans_s_executer_mais_n1_lit(serveur, banc):
    serveur.ecriture_permise = False
    assert await appeler(serveur, "ecrire", texte="neuf") == (PENDANT_LE_RESUME, True)
    assert await appeler(serveur, "supprimer", chemin="profil.md") == (PENDANT_LE_RESUME, True)
    assert await appeler(serveur, "lire", chemin="profil.md") == ("contenu de profil.md", False)
    assert banc.appels == ["lire"]
    assert not serveur.confirmations.en_attente


async def test_un_refus_revient_a_claude_et_une_panne_se_note(serveur, banc, caplog):
    async def refuser(arguments: dict) -> Fait:
        raise ErreurMemoire("Refusé : un secret.")

    async def tomber(arguments: dict) -> Fait:
        raise OSError("disque plein")

    banc.ecrire = refuser
    refus = ServeurAtlas(banc.outils(), Confirmations())
    assert await appeler(refus, "ecrire", texte="x") == ("Refusé : un secret.", True)
    banc.ecrire = tomber
    panne = ServeurAtlas(banc.outils(), Confirmations())
    assert await appeler(panne, "ecrire", texte="x") == (ECHEC, True)
    assert "l'outil ecrire a échoué" in caplog.text
    assert refus.prendre_les_annonces() == [] and panne.prendre_les_annonces() == []
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `uv run pytest tests/test_outils.py -q`
Expected: FAIL — erreur de collecte : `ModuleNotFoundError: No module named 'atlas_core.outils'`.

- [ ] **Step 3: Écrire les niveaux**

Créer `src/atlas_core/outils.py` :

```python
"""Les outils d'Atlas et leurs niveaux d'autorisation (spec parente §10, spec 2c §4).

Chaque outil déclare son niveau dans le code, et le Core applique la règle autour de lui :
Claude ne choisit jamais. N1 lit, sans rien dire ; N2 agit, puis le Core fait annoncer ce qui
a été fait ; N3 ne fait rien lui-même : il décrit son action, que le Core met en attente du
« oui » de David (confirmation.py). Tous les outils sont servis à Claude par un seul serveur
MCP, « atlas », qui tourne dans le Core (le SDK de Claude).
"""

from __future__ import annotations

import enum
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from claude_agent_sdk import SdkMcpTool, create_sdk_mcp_server, tool
from claude_agent_sdk.types import McpSdkServerConfig

from .cerveau import Note
from .confirmation import Confirmations
from .memoire import ErreurMemoire

_journal = logging.getLogger(__name__)

SERVEUR = "atlas"
PENDANT_LE_RESUME = "La conversation se résume : rien ne s'écrit maintenant."
ECHEC = "L'outil n'a pas pu faire ça : une erreur est notée dans le journal du Core."
EN_ATTENTE = (
    "En attente de la confirmation de David : Atlas lui pose la question. N'ajoute rien, et "
    "ne dis pas que c'est fait."
)
DEJA_EN_ATTENTE = "Une action attend déjà la réponse de David : attends-la avant une autre."

Gestionnaire = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class Niveau(enum.IntEnum):
    N1 = 1  # lecture, consultation : fait, sans rien dire
    N2 = 2  # modification réversible : fait, puis annoncé
    N3 = 3  # irréversible ou sortant : attend le « oui » de David


@dataclass(frozen=True)
class Fait:
    """Le résultat d'un outil N2 : le texte pour Claude, et l'annonce pour David — None si
    rien n'a changé."""

    texte: str
    annonce: str | None = None


@dataclass(frozen=True)
class Outil:
    """Un outil et son niveau. Son gestionnaire rend du texte (N1), un `Fait` (N2), ou
    l'action à confirmer (N3, une `Suppression`)."""

    nom: str
    description: str
    parametres: dict[str, type]
    niveau: Niveau
    gestionnaire: Callable[[dict[str, Any]], Awaitable[Any]]


def _texte(texte: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": texte}]}


def _refus(texte: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": texte}], "is_error": True}


class ServeurAtlas:
    """Le serveur « atlas » : ses outils, la règle de leur niveau, les annonces à faire, et
    l'action qui attend le « oui » de David."""

    def __init__(self, outils: list[Outil], confirmations: Confirmations) -> None:
        self.declarations = list(outils)
        self.confirmations = confirmations
        self.ecriture_permise = True  # False pendant le résumé d'une conversation
        self._annonces: list[Note] = []
        self.outils: list[SdkMcpTool] = [
            tool(o.nom, o.description, o.parametres)(self._regle(o)) for o in outils
        ]

    @property
    def noms(self) -> list[str]:
        """Les noms sous lesquels Claude voit ces outils."""
        return [f"mcp__{SERVEUR}__{outil.name}" for outil in self.outils]

    def serveur(self) -> McpSdkServerConfig:
        return create_sdk_mcp_server(SERVEUR, tools=self.outils)

    def prendre_les_annonces(self) -> list[Note]:
        """Ce qui a été fait depuis le dernier appel, à annoncer dans l'ordre."""
        annonces, self._annonces = self._annonces, []
        return annonces

    def _regle(self, outil: Outil) -> Gestionnaire:
        async def appliquer(arguments: dict[str, Any]) -> dict[str, Any]:
            if outil.niveau > Niveau.N1 and not self.ecriture_permise:
                return _refus(PENDANT_LE_RESUME)
            try:
                resultat = await outil.gestionnaire(arguments)
            except ErreurMemoire as e:
                return _refus(str(e))  # un refus : Claude le dit à David
            except Exception:
                _journal.exception("l'outil %s a échoué", outil.nom)
                return _refus(ECHEC)
            if outil.niveau == Niveau.N3:
                if not self.confirmations.mettre_en_attente(resultat):
                    return _refus(DEJA_EN_ATTENTE)
                return _texte(EN_ATTENTE)
            if outil.niveau == Niveau.N2:
                if resultat.annonce is not None:
                    self._annonces.append(Note(resultat.annonce))
                return _texte(resultat.texte)
            return _texte(resultat)

        return appliquer
```

- [ ] **Step 4: Vérifier que tout passe**

Run: `uv run pytest -q && uv run ruff check . --extend-exclude spikes && uv run ruff format --check . --extend-exclude spikes && node --test "tests/web/*.test.mjs"`
Expected: 912 tests Python passent, 126 tests JavaScript passent, ruff ne dit rien.

- [ ] **Step 5: Commit**

```bash
git add src/atlas_core/outils.py tests/test_outils.py
git commit -F - <<'MSG'
Outils : les niveaux d'autorisation, appliqués par le Core

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

### Task 5: Les outils de la mémoire et des documents, chacun à son niveau

Les outils de la mémoire passent sur les niveaux (`OutilsMemoire` devient un `ServeurAtlas`), avec deux nouveaux :
`document_ecrire` (N2) et `memoire_supprimer` (N3). « Annule » dit ce qu'il défait ; les pages sont prévenues quand
un document change, y compris après une suppression confirmée (`Suppression.apres`). `outils_memoire.py` est donné
en entier : il est réécrit sur la déclaration des outils.

**Files:**
- Modify: `src/atlas_core/cerveau_claude.py`
- Modify: `src/atlas_core/confirmation.py`
- Create: `src/atlas_core/outils_documents.py`
- Modify: `src/atlas_core/outils_memoire.py`
- Modify: `tests/test_confirmation.py`
- Create: `tests/test_outils_documents.py`
- Modify: `tests/test_outils_memoire.py`

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces: `Suppression.apres: Callable[[], None]` (par défaut rien ; appelé dans la boucle après une exécution
  réussie) ; `atlas_core.outils_documents` : `ECRIRE_DOCUMENT`, `outils_des_documents(memoire, sur_documents) ->
  list[Outil]` ; `atlas_core.outils_memoire` : `ANNONCE_PROFIL`, `ANNONCE_RETRAIT`, `LIRE`, `CHERCHER`, `ECRIRE`,
  `ANNULER`, `SUPPRIMER`, `annonce_de(chemin, titre)`, `annonce_du_retrait(defait) -> str`,
  `OutilsMemoire(memoire, confirmations=None, sur_documents=None)` (un `ServeurAtlas` : `memoire`, `sur_documents`,
  `confirmations`, six outils). `SERVEUR`, `PENDANT_LE_RESUME` et `ECHEC` viennent désormais de `outils` ;
  `cerveau_claude.py` importe `SERVEUR` de là.

- [ ] **Step 1: Écrire les tests qui échouent**

Modifier `tests/test_confirmation.py` :

```diff
--- a/tests/test_confirmation.py
+++ b/tests/test_confirmation.py
@@ -311,3 +311,23 @@ async def test_une_question_jamais_posee_qui_expire_ne_montre_rien_aux_pages(
     await _laisser_tourner()
     assert not confirmations.en_attente and temoin.fins == []
     assert len(confirmations.prendre_les_lignes()) == 1
+
+
+async def test_apres_ne_suit_qu_une_execution_reussie(confirmations, temoin):
+    apres: list[str] = []
+    for reponse, executer in (("oui", temoin.executer), ("non", temoin.executer)):
+        confirmations.mettre_en_attente(
+            Suppression("documents/a.md", "A", executer, apres=lambda: apres.append("vu"))
+        )
+        confirmations.poser()
+        await confirmations.trancher(reponse)
+
+    def echouer() -> None:
+        raise ErreurMemoire("non")
+
+    confirmations.mettre_en_attente(
+        Suppression("documents/a.md", "A", echouer, apres=lambda: apres.append("vu"))
+    )
+    confirmations.poser()
+    await confirmations.trancher("oui")
+    assert apres == ["vu"]
```

Créer `tests/test_outils_documents.py` :

```python
"""Les documents et la suppression, par le serveur « atlas » : appelés comme Claude les
appelle, sur un vrai dépôt git temporaire."""

import subprocess

import pytest

from atlas_core.cerveau import Note
from atlas_core.memoire import Memoire
from atlas_core.outils import EN_ATTENTE, Niveau
from atlas_core.outils_memoire import ANNONCE_RETRAIT, OutilsMemoire

OFFRE = "# Offre de lancement\n\nTrois formules pour les premiers clients.\n"
PAUL = "# Paul Durand\n\nProspect.\n"


class Pages:
    def __init__(self) -> None:
        self.changements = 0

    def documents_changes(self) -> None:
        self.changements += 1


@pytest.fixture
def pages() -> Pages:
    return Pages()


@pytest.fixture
def outils(tmp_path, pages) -> OutilsMemoire:
    return OutilsMemoire(
        Memoire.ouvrir(tmp_path / "memoire"), sur_documents=pages.documents_changes
    )


async def appeler(outils: OutilsMemoire, nom_outil: str, /, **arguments) -> tuple[str, bool]:
    outil = next(o for o in outils.outils if o.name == nom_outil)
    resultat = await outil.handler(arguments)
    return resultat["content"][0]["text"], resultat.get("is_error", False)


def tete(outils: OutilsMemoire) -> str:
    return subprocess.run(
        ["git", "-C", str(outils.memoire.racine), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
    ).stdout


def test_la_description_de_document_ecrire_dit_quand_et_comment(outils):
    ecrire = next(o for o in outils.outils if o.name == "document_ecrire")
    assert "seulement quand David te demande un document" in ecrire.description
    assert "réécris-le en entier" in ecrire.description
    assert "ne l'annonce pas toi-même" in ecrire.description
    assert ecrire.input_schema == {"nom": str, "contenu": str}


# --- écrire un document -----------------------------------------------------------


async def test_ecrire_un_document_s_annonce_et_previent_les_pages(outils, pages):
    assert await appeler(outils, "document_ecrire", nom="offre-de-lancement", contenu=OFFRE) == (
        "C'est écrit dans documents/offre-de-lancement.md.",
        False,
    )
    assert outils.prendre_les_annonces() == [
        Note("J'ai écrit le document Offre de lancement, il est dans la page.")
    ]
    assert pages.changements == 1


async def test_une_retouche_s_annonce_autrement_et_rien_de_neuf_ne_dit_rien(outils, pages):
    await appeler(outils, "document_ecrire", nom="offre-de-lancement", contenu=OFFRE)
    outils.prendre_les_annonces()
    retouche = OFFRE + "\n## Les prix\n\nÀ revoir.\n"
    await appeler(outils, "document_ecrire", nom="offre-de-lancement", contenu=retouche)
    assert outils.prendre_les_annonces() == [
        Note("J'ai mis à jour le document Offre de lancement.")
    ]
    assert await appeler(outils, "document_ecrire", nom="offre-de-lancement", contenu=retouche) == (
        "Le document était déjà ainsi : rien n'a changé.",
        False,
    )
    assert outils.prendre_les_annonces() == [] and pages.changements == 2


async def test_un_document_refuse_revient_a_claude_sans_annonce(outils, pages):
    texte, erreur = await appeler(outils, "document_ecrire", nom="Offre", contenu=OFFRE)
    assert erreur is True and "nom de document" in texte
    texte, erreur = await appeler(
        outils, "memoire_ecrire", chemin="documents/offre-de-lancement.md", contenu=OFFRE
    )
    assert erreur is True and "document_ecrire" in texte
    assert outils.prendre_les_annonces() == [] and pages.changements == 0


# --- supprimer (N3) ---------------------------------------------------------------


async def test_un_outil_n3_ne_change_rien_sans_confirmation(outils):
    outils.memoire.ecrire("personnes/paul-durand.md", PAUL)
    avant = tete(outils)
    for outil in (o for o in outils.declarations if o.niveau == Niveau.N3):
        assert await appeler(outils, outil.nom, chemin="personnes/paul-durand.md") == (
            EN_ATTENTE,
            False,
        )
        outils.confirmations.abandonner()
    assert tete(outils) == avant
    assert outils.memoire.lire("personnes/paul-durand.md") == PAUL


async def test_supprimer_un_document_attend_le_oui_puis_previent_les_pages(outils, pages):
    await appeler(outils, "document_ecrire", nom="offre-de-lancement", contenu=OFFRE)
    outils.prendre_les_annonces()
    assert await appeler(outils, "memoire_supprimer", chemin="documents/offre-de-lancement.md") == (
        EN_ATTENTE,
        False,
    )
    assert pages.changements == 1  # l'écriture ; la suppression attend
    assert outils.confirmations.poser().annonce == (
        "Je supprime le document Offre de lancement. Tu confirmes ?"
    )
    assert await outils.confirmations.trancher("oui") == (
        "C'est fait : le document Offre de lancement est supprimé.",
        False,
    )
    assert outils.memoire.documents() == [] and pages.changements == 2
    assert outils.prendre_les_annonces() == []  # la phrase vient de la confirmation


async def test_supprimer_une_fiche_ne_derange_pas_le_panneau_des_documents(outils, pages):
    outils.memoire.ecrire("personnes/paul-durand.md", PAUL)
    await appeler(outils, "memoire_supprimer", chemin="personnes/paul-durand.md")
    outils.confirmations.poser()
    await outils.confirmations.trancher("oui")
    assert not (outils.memoire.racine / "personnes" / "paul-durand.md").exists()
    assert pages.changements == 0


async def test_une_fiche_retouchee_entre_la_question_et_le_oui_reste_a_david(outils, caplog):
    outils.memoire.ecrire("personnes/paul-durand.md", PAUL)
    await appeler(outils, "memoire_supprimer", chemin="personnes/paul-durand.md")
    outils.confirmations.poser()
    fiche = outils.memoire.racine / "personnes" / "paul-durand.md"
    fiche.write_text(PAUL + "\nNote à la main.\n")
    assert await outils.confirmations.trancher("oui") == (
        "Je n'ai pas pu supprimer la fiche Paul Durand.",
        False,
    )
    assert fiche.read_text().endswith("Note à la main.\n")
    assert "retouché à la main" in caplog.text


@pytest.mark.parametrize(
    ("chemin", "raison"),
    [("projets/site-web.md", "n'existe pas"), ("journal/2026-09-25.md", "n'est pas une fiche")],
)
async def test_une_suppression_impossible_est_refusee_tout_de_suite(outils, chemin, raison):
    texte, erreur = await appeler(outils, "memoire_supprimer", chemin=chemin)
    assert erreur is True and raison in texte
    assert not outils.confirmations.en_attente


# --- annuler dit ce qui a été défait ------------------------------------------------


async def test_annuler_un_document_le_dit_et_previent_les_pages(outils, pages):
    await appeler(outils, "document_ecrire", nom="offre-de-lancement", contenu=OFFRE)
    await appeler(outils, "document_ecrire", nom="offre-de-lancement", contenu=OFFRE + "\nX.\n")
    outils.prendre_les_annonces()
    await appeler(outils, "memoire_annuler")
    await appeler(outils, "memoire_annuler")
    assert outils.prendre_les_annonces() == [
        Note("Le document Offre de lancement revient à sa version précédente."),
        Note("J'ai retiré le document Offre de lancement."),
    ]
    assert pages.changements == 4


@pytest.mark.parametrize(
    ("chemin", "annonce"),
    [
        ("documents/offre-de-lancement.md", "J'ai remis le document Offre de lancement."),
        ("personnes/paul-durand.md", "J'ai remis la fiche Paul Durand."),
        ("profil.md", "J'ai remis ton profil."),
    ],
)
async def test_annuler_une_suppression_remet_et_le_dit(outils, chemin, annonce):
    memoire = outils.memoire
    memoire.ecrire("profil.md", "# Profil\n\nDavid.\n")
    memoire.ecrire("personnes/paul-durand.md", PAUL)
    memoire.ecrire_document("offre-de-lancement", OFFRE)
    await appeler(outils, "memoire_supprimer", chemin=chemin)
    outils.confirmations.poser()
    await outils.confirmations.trancher("oui")
    texte, erreur = await appeler(outils, "memoire_annuler")
    assert (texte, erreur) == (annonce, False)
    assert outils.prendre_les_annonces() == [Note(annonce)]
    assert (memoire.racine / chemin).exists()


async def test_annuler_une_note_de_fiche_reste_comme_avant(outils):
    await appeler(outils, "memoire_ecrire", chemin="personnes/paul-durand.md", contenu=PAUL)
    outils.prendre_les_annonces()
    assert await appeler(outils, "memoire_annuler") == (
        "La note « Paul Durand » est retirée.",
        False,
    )
    assert outils.prendre_les_annonces() == [Note(ANNONCE_RETRAIT)]
```

Modifier `tests/test_outils_memoire.py` :

```diff
--- a/tests/test_outils_memoire.py
+++ b/tests/test_outils_memoire.py
@@ -5,13 +5,8 @@ import pytest
 
 from atlas_core.cerveau import Note
 from atlas_core.memoire import Memoire
-from atlas_core.outils_memoire import (
-    ANNONCE_PROFIL,
-    ANNONCE_RETRAIT,
-    ECHEC,
-    PENDANT_LE_RESUME,
-    OutilsMemoire,
-)
+from atlas_core.outils import ECHEC, PENDANT_LE_RESUME, Niveau
+from atlas_core.outils_memoire import ANNONCE_PROFIL, ANNONCE_RETRAIT, OutilsMemoire
 
 PAUL = "# Paul Durand\n\nProspect ; rendez-vous le jeudi 2 octobre 2026.\n"
 
@@ -27,13 +22,16 @@ async def appeler(outils: OutilsMemoire, nom: str, **arguments) -> tuple[str, bo
     return resultat["content"][0]["text"], resultat.get("is_error", False)
 
 
-def test_claude_voit_quatre_outils_sur_le_serveur_atlas(outils):
-    assert outils.noms == [
-        "mcp__atlas__memoire_lire",
-        "mcp__atlas__memoire_chercher",
-        "mcp__atlas__memoire_ecrire",
-        "mcp__atlas__memoire_annuler",
+def test_claude_voit_six_outils_chacun_avec_son_niveau(outils):
+    assert [(o.nom, o.niveau) for o in outils.declarations] == [
+        ("memoire_lire", Niveau.N1),
+        ("memoire_chercher", Niveau.N1),
+        ("memoire_ecrire", Niveau.N2),
+        ("document_ecrire", Niveau.N2),
+        ("memoire_annuler", Niveau.N2),
+        ("memoire_supprimer", Niveau.N3),
     ]
+    assert outils.noms == [f"mcp__atlas__{o.nom}" for o in outils.declarations]
     serveur = outils.serveur()
     assert (serveur["type"], serveur["name"]) == ("sdk", "atlas")
 
@@ -149,4 +147,4 @@ async def test_une_panne_du_depot_revient_a_claude_et_se_note_au_journal(
         ECHEC,
         True,
     )
-    assert "un outil de la mémoire a échoué" in caplog.text
+    assert "l'outil memoire_ecrire a échoué" in caplog.text
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `uv run pytest tests/test_outils_memoire.py tests/test_outils_documents.py tests/test_confirmation.py -q`
Expected: FAIL — 3 échecs et 15 erreurs : `TypeError: OutilsMemoire.__init__() got an unexpected keyword argument
'sur_documents'` (les 15 erreurs), la liste des six outils et le message de panne, et `TypeError:
Suppression.__init__() got an unexpected keyword argument 'apres'`.

- [ ] **Step 3: Écrire les outils à leur niveau**

Modifier `src/atlas_core/cerveau_claude.py` :

```diff
--- a/src/atlas_core/cerveau_claude.py
+++ b/src/atlas_core/cerveau_claude.py
@@ -41,7 +41,8 @@ from claude_agent_sdk import (
 
 from .cerveau import RECHERCHE, ErreurCerveau, Note, Recherche
 from .consignes import CONSIGNES, CONSIGNES_AVEC_MEMOIRE, DEMANDE_RESUME, RIEN, ligne_de_date
-from .outils_memoire import SERVEUR, OutilsMemoire
+from .outils import SERVEUR
+from .outils_memoire import OutilsMemoire
 
 _journal = logging.getLogger(__name__)
 
```

Modifier `src/atlas_core/confirmation.py` :

```diff
--- a/src/atlas_core/confirmation.py
+++ b/src/atlas_core/confirmation.py
@@ -88,14 +88,20 @@ def lire_reponse(texte: str) -> str:
     return "autre"
 
 
+def _rien() -> None:
+    pass
+
+
 @dataclass(frozen=True)
 class Suppression:
     """Une suppression résolue — ce qu'elle retire — et la façon de la dire. `executer`
-    tourne hors de la boucle du Core, seulement après le « oui »."""
+    tourne hors de la boucle du Core, seulement après le « oui » ; `apres`, dans la boucle,
+    une fois l'exécution réussie (prévenir les pages, par exemple)."""
 
     chemin: str
     titre: str
     executer: Callable[[], object]
+    apres: Callable[[], None] = _rien
 
     @property
     def _nature(self) -> str:
@@ -209,6 +215,7 @@ class Confirmations:
             objet = action.objet[0].upper() + action.objet[1:]
             self._conclure(f"[{objet} a échoué.]", "La suppression a échoué.")
             return action.ratee, False
+        action.apres()
         self._conclure(f"[Confirmé par David : {action.bilan}.]", action.page_faite)
         return action.faite, False
 
```

Créer `src/atlas_core/outils_documents.py` :

```python
"""L'outil des documents : ce que la réflexion de David devient, à sa demande (spec 2c §5).

Un document s'écrit en entier dans `documents/<nom>.md`, comme une fiche mais plus long, et
dans un Markdown structuré que la page met en forme. L'écriture est N2 : faite, puis
annoncée ; les pages sont prévenues pour mettre leur liste à jour.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from .memoire import Memoire
from .outils import Fait, Niveau, Outil

ECRIRE_DOCUMENT = (
    "Crée ou remplace un document entier, documents/<nom>.md, le nom en minuscules, chiffres "
    "et tirets : seulement quand David te demande un document. Le contenu commence par "
    "« # Titre », une ligne vide, puis une phrase de résumé ; ensuite un Markdown structuré : "
    "sous-titres (## et ###), paragraphes, listes à puces ou numérotées, gras, italique, "
    "citations (>), code, tableaux simples, liens https. Pour une retouche, relis le document "
    "avec memoire_lire, puis réécris-le en entier. Atlas annonce l'écriture à David : ne "
    "l'annonce pas toi-même."
)


def outils_des_documents(memoire: Memoire, sur_documents: Callable[[], None]) -> list[Outil]:
    async def ecrire(arguments: dict[str, Any]) -> Fait:
        nom = arguments["nom"]
        ecrit = await asyncio.to_thread(memoire.ecrire_document, nom, arguments["contenu"])
        if ecrit is None:
            return Fait("Le document était déjà ainsi : rien n'a changé.")
        titre, cree = ecrit
        sur_documents()
        if cree:
            annonce = f"J'ai écrit le document {titre}, il est dans la page."
        else:
            annonce = f"J'ai mis à jour le document {titre}."
        return Fait(f"C'est écrit dans documents/{nom}.md.", annonce)

    return [
        Outil("document_ecrire", ECRIRE_DOCUMENT, {"nom": str, "contenu": str}, Niveau.N2, ecrire)
    ]
```

Remplacer tout `src/atlas_core/outils_memoire.py` par :

```python
"""Les outils de la mémoire, que Claude appelle : lire, chercher, écrire une fiche, annuler,
supprimer — et ceux des documents (outils_documents.py).

Chacun déclare son niveau, et le serveur « atlas » (outils.py) applique la règle : lire et
chercher sont N1, écrire et annuler N2 (faits, puis annoncés), supprimer N3 (le « oui » de
David d'abord). Chaque écriture passe par `Memoire`, qui la vérifie et la commite.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from .confirmation import Confirmations, Suppression
from .memoire import DOSSIER_DOCUMENTS, Defait, Memoire
from .outils import Fait, Niveau, Outil, ServeurAtlas
from .outils_documents import outils_des_documents

ANNONCE_PROFIL = "Je le note dans ton profil."
ANNONCE_RETRAIT = "J'ai retiré ma dernière note."

LIRE = (
    "Lit un fichier de ta mémoire : profil.md, une fiche (entreprise/, projets/ ou "
    "personnes/ suivi du nom), un document (documents/ suivi du nom) ou un jour du journal "
    "(journal/AAAA-MM-JJ.md). Lis une fiche ou un document avant de le modifier."
)
CHERCHER = (
    "Cherche un mot ou un nom dans tes fiches, tes documents et ton journal, sans tenir "
    "compte des majuscules ni des accents. Rend au plus vingt lignes, chacune avec son fichier."
)
ECRIRE = (
    "Crée ou remplace une fiche entière de ta mémoire : profil.md, ou entreprise/<nom>.md, "
    "projets/<nom>.md, personnes/<nom>.md, le nom en minuscules, chiffres et tirets. Le "
    "contenu commence par « # Titre », une ligne vide, puis une phrase de résumé ; le reste "
    "est libre. Atlas annonce l'écriture à David : ne l'annonce pas toi-même."
)
ANNULER = (
    "Défait ta dernière note encore en place — une fiche écrite, un document écrit ou "
    "retouché, une suppression —, quand David dit « annule », « oublie ça » ou « ne note pas "
    "ça ». Rappeler cet outil remonte d'une note. Atlas le dit à David."
)
SUPPRIMER = (
    "Supprime une fiche (profil.md, entreprise/, projets/ ou personnes/) ou un document "
    "(documents/), quand David le demande. Rien n'est supprimé tout de suite : Atlas demande "
    "à David de confirmer. N'ajoute rien après l'appel, et ne dis jamais que c'est fait."
)


def annonce_de(chemin: str, titre: str) -> str:
    return ANNONCE_PROFIL if chemin == "profil.md" else f"Je le note dans la fiche {titre}."


def _est_un_document(chemin: str) -> bool:
    return chemin.startswith(f"{DOSSIER_DOCUMENTS}/")


def annonce_du_retrait(defait: Defait) -> str:
    """Ce qu'Atlas dit après « annule », selon ce que la note avait fait."""
    if defait.nature == "suppression":
        if defait.chemin == "profil.md":
            return "J'ai remis ton profil."
        quoi = "le document" if _est_un_document(defait.chemin) else "la fiche"
        return f"J'ai remis {quoi} {defait.titre}."
    if _est_un_document(defait.chemin):
        if defait.nature == "creation":
            return f"J'ai retiré le document {defait.titre}."
        return f"Le document {defait.titre} revient à sa version précédente."
    return ANNONCE_RETRAIT


class OutilsMemoire(ServeurAtlas):
    """Le serveur « atlas » et les outils de la mémoire. `sur_documents` prévient les pages
    quand un document change ; `confirmations` tient l'action qui attend le « oui »."""

    def __init__(
        self,
        memoire: Memoire,
        confirmations: Confirmations | None = None,
        sur_documents: Callable[[], None] | None = None,
    ) -> None:
        self.memoire = memoire
        self.sur_documents = sur_documents or (lambda: None)
        super().__init__(
            [
                Outil("memoire_lire", LIRE, {"chemin": str}, Niveau.N1, self._lire),
                Outil("memoire_chercher", CHERCHER, {"texte": str}, Niveau.N1, self._chercher),
                Outil(
                    "memoire_ecrire",
                    ECRIRE,
                    {"chemin": str, "contenu": str},
                    Niveau.N2,
                    self._ecrire,
                ),
                *outils_des_documents(memoire, lambda: self.sur_documents()),
                Outil("memoire_annuler", ANNULER, {}, Niveau.N2, self._annuler),
                Outil("memoire_supprimer", SUPPRIMER, {"chemin": str}, Niveau.N3, self._supprimer),
            ],
            confirmations or Confirmations(),
        )

    async def _lire(self, arguments: dict[str, Any]) -> str:
        return await asyncio.to_thread(self.memoire.lire, arguments["chemin"])

    async def _chercher(self, arguments: dict[str, Any]) -> str:
        lignes = await asyncio.to_thread(self.memoire.chercher, arguments["texte"])
        return "\n".join(lignes) if lignes else "Rien trouvé."

    async def _ecrire(self, arguments: dict[str, Any]) -> Fait:
        chemin = arguments["chemin"]
        titre = await asyncio.to_thread(self.memoire.ecrire, chemin, arguments["contenu"])
        if titre is None:
            return Fait("La fiche était déjà ainsi : rien n'a changé.")
        return Fait(f"C'est noté dans {chemin}.", annonce_de(chemin, titre))

    async def _annuler(self, arguments: dict[str, Any]) -> Fait:
        defait = await asyncio.to_thread(self.memoire.annuler)
        annonce = annonce_du_retrait(defait)
        if _est_un_document(defait.chemin):
            self.sur_documents()
        if annonce == ANNONCE_RETRAIT:
            return Fait(f"La note « {defait.titre} » est retirée.", annonce)
        return Fait(annonce, annonce)

    async def _supprimer(self, arguments: dict[str, Any]) -> Suppression:
        chemin = arguments["chemin"]
        titre = await asyncio.to_thread(self.memoire.titre_de, chemin)
        apres = (lambda: self.sur_documents()) if _est_un_document(chemin) else (lambda: None)
        return Suppression(chemin, titre, lambda: self.memoire.supprimer(chemin), apres)
```

- [ ] **Step 4: Vérifier que tout passe**

Run: `uv run pytest -q && uv run ruff check . --extend-exclude spikes && uv run ruff format --check . --extend-exclude spikes && node --test "tests/web/*.test.mjs"`
Expected: 928 tests Python passent, 126 tests JavaScript passent, ruff ne dit rien.

- [ ] **Step 5: Commit**

```bash
git add src/atlas_core/cerveau_claude.py src/atlas_core/confirmation.py src/atlas_core/outils_documents.py src/atlas_core/outils_memoire.py tests/test_confirmation.py tests/test_outils_documents.py tests/test_outils_memoire.py
git commit -F - <<'MSG'
Outils : écrire un document (N2), supprimer (N3), annuler qui dit ce qu'il défait

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

### Task 6: Le cerveau et la confirmation

Quand une action attend, la phrase de David est lue avant Claude : « oui » et « non » se tranchent sans lui, autre
chose part à Claude après « Je ne supprime rien. ». La question se pose à sa place dans la réponse ; une question
jamais posée s'abandonne ; la fin d'une conversation abandonne l'action ; le résultat arrive à Claude par une ligne
au début de sa question suivante, ou de la demande de résumé. Les consignes disent les documents et la suppression.

**Files:**
- Modify: `src/atlas_core/cerveau_claude.py`
- Modify: `src/atlas_core/consignes.py`
- Create: `tests/test_cerveau_confirmation.py`
- Modify: `tests/test_consignes.py`

**Interfaces:**
- Consumes: Tasks 3 et 5 (`OutilsMemoire.confirmations`, `Confirmations.poser`, `trancher`,
  `abandonner_si_non_posee`, `abandonner`, `prendre_les_lignes`).
- Produces: `CerveauClaude.repondre` rend la phrase de la confirmation (`str`) ou un marqueur `Confirmation` ;
  `consignes.CONSIGNES_AVEC_MEMOIRE` dit `document_ecrire` et `memoire_supprimer` ; `CONSIGNES` (sans mémoire)
  inchangées.

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/test_cerveau_confirmation.py` :

```python
"""Le cerveau et la confirmation (N3) : la question posée à sa place dans la réponse, la
réponse de David lue avant Claude, la ligne qui dit le résultat à Claude, et l'abandon quand
la question n'a pas été entendue ou que la conversation se termine. Avec la doublure du SDK
et une vraie mémoire sur un dépôt temporaire."""

import asyncio

import pytest
from test_cerveau_claude import (
    BLOQUE,
    MOMENT,
    Fabrique,
    FauxClientClaude,
    Temps,
    debut_texte,
    delta,
    fin,
    reponse,
)
from test_cerveau_journal import Minuterie, resume

from atlas_core.cerveau import Confirmation
from atlas_core.cerveau_claude import CerveauClaude
from atlas_core.confirmation import Confirmations
from atlas_core.consignes import DEMANDE_RESUME
from atlas_core.memoire import Memoire
from atlas_core.outils_memoire import OutilsMemoire

DATE = "[jeudi 24 septembre 2026, 21 h 50]"
OFFRE = "# Offre de lancement\n\nTrois formules pour les premiers clients.\n"
QUESTION = "Je supprime le document Offre de lancement. Tu confirmes ?"
CHEMIN = "documents/offre-de-lancement.md"


async def _jamais(delai: float) -> None:
    await asyncio.Event().wait()  # les trente secondes ne sonnent jamais ici


class Pages:
    def __init__(self) -> None:
        self.fins: list[str] = []


@pytest.fixture
def pages() -> Pages:
    return Pages()


@pytest.fixture
def outils(tmp_path, pages) -> OutilsMemoire:
    memoire = Memoire.ouvrir(tmp_path / "memoire")
    memoire.ecrire_document("offre-de-lancement", OFFRE)
    return OutilsMemoire(memoire, Confirmations(attendre=_jamais, sur_fin=pages.fins.append))


class Supprimer:
    """Claude appelle memoire_supprimer au milieu d'un tour : le SDK exécute son gestionnaire."""

    def __init__(self, outils: OutilsMemoire, chemin: str = CHEMIN) -> None:
        self._outil = next(o for o in outils.outils if o.name == "memoire_supprimer")
        self._chemin = chemin

    async def __call__(self) -> None:
        await self._outil.handler({"chemin": self._chemin})


def _cerveau(outils, *clients, minuterie=None) -> CerveauClaude:
    return CerveauClaude(
        Fabrique(*clients),
        oubli_s=30 * 60,
        horloge=Temps(),
        maintenant=lambda: MOMENT,
        outils=outils,
        attendre=minuterie or _jamais,
    )


async def _tout(cerveau: CerveauClaude, texte: str) -> list:
    async def lire() -> list:
        return [f async for f in cerveau.repondre(texte)]

    fragments = await asyncio.wait_for(lire(), timeout=2)
    for _ in range(5):
        await asyncio.sleep(0)  # l'échéance programmée par la réponse se met à attendre
    return fragments


async def _jusqu_a(condition, message: str) -> None:
    for _ in range(200):  # deux secondes au plus
        if condition():
            return
        await asyncio.sleep(0.01)
    raise AssertionError(message)


def _demande(outils) -> list:
    return [debut_texte(), delta("D'accord."), Supprimer(outils), fin()]


async def test_la_question_se_pose_a_sa_place_dans_la_reponse(outils):
    client = FauxClientClaude(_demande(outils))
    fragments = await _tout(_cerveau(outils, client), "Supprime l'offre de lancement.")
    assert fragments == ["D'accord.", Confirmation(QUESTION)]
    assert outils.memoire.lire(CHEMIN) == OFFRE  # rien n'est encore supprimé


async def test_oui_supprime_sans_passer_par_claude_puis_claude_l_apprend(outils, pages):
    client = FauxClientClaude(_demande(outils), reponse("Très bien."))
    cerveau = _cerveau(outils, client)
    await _tout(cerveau, "Supprime l'offre de lancement.")
    assert await _tout(cerveau, "Oui.") == [
        "C'est fait : le document Offre de lancement est supprimé."
    ]
    assert len(client.questions) == 1
    assert outils.memoire.documents() == []
    assert pages.fins == ["Supprimé : le document Offre de lancement."]
    await _tout(cerveau, "Et maintenant ?")
    assert client.questions[-1] == (
        "[Confirmé par David : le document « Offre de lancement » est supprimé.]\n"
        f"{DATE}\nEt maintenant ?"
    )


async def test_non_ne_supprime_rien_et_claude_l_apprend(outils):
    client = FauxClientClaude(_demande(outils), reponse("Entendu."))
    cerveau = _cerveau(outils, client)
    await _tout(cerveau, "Supprime l'offre de lancement.")
    assert await _tout(cerveau, "Non, laisse tomber.") == ["D'accord, je ne supprime rien."]
    assert outils.memoire.lire(CHEMIN) == OFFRE
    await _tout(cerveau, "Merci.")
    assert client.questions[-1] == f"[Refusé par David : rien n'a été supprimé.]\n{DATE}\nMerci."


async def test_autre_chose_abandonne_puis_part_a_claude_dans_la_meme_reponse(outils):
    client = FauxClientClaude(_demande(outils), reponse("Elle propose trois formules."))
    cerveau = _cerveau(outils, client)
    await _tout(cerveau, "Supprime l'offre de lancement.")
    assert await _tout(cerveau, "Attends, lis-la-moi d'abord.") == [
        "Je ne supprime rien. ",
        "Elle propose trois formules.",
    ]
    assert outils.memoire.lire(CHEMIN) == OFFRE
    assert client.questions[-1] == (
        "[David a répondu autre chose : la suppression du document « Offre de lancement » est "
        f"abandonnée.]\n{DATE}\nAttends, lis-la-moi d'abord."
    )


async def test_un_oui_qui_coupe_la_fin_de_la_reponse_compte(outils):
    client = FauxClientClaude(
        [debut_texte(), delta("D'accord."), Supprimer(outils), delta(" Je"), BLOQUE, fin()],
        reponse("Oui ?"),
    )
    cerveau = _cerveau(outils, client)
    premiere: list = []

    async def lire_la_premiere() -> None:
        async for fragment in cerveau.repondre("Supprime l'offre."):
            premiere.append(fragment)

    tache = asyncio.create_task(lire_la_premiere())
    await _jusqu_a(lambda: Confirmation(QUESTION) in premiere, "la question n'est pas posée")
    assert await _tout(cerveau, "Oui.") == [
        "C'est fait : le document Offre de lancement est supprimé."
    ]
    await tache
    assert outils.memoire.documents() == []
    assert len(client.questions) == 1


async def test_une_question_coupee_avant_d_etre_posee_est_abandonnee(outils, pages):
    client = FauxClientClaude(
        [debut_texte(), delta("Je regarde. "), Supprimer(outils), BLOQUE, delta("x"), fin()],
        reponse("Oui ?"),
    )
    cerveau = _cerveau(outils, client)
    premiere: list = []

    async def lire_la_premiere() -> None:
        async for fragment in cerveau.repondre("Supprime l'offre."):
            premiere.append(fragment)

    tache = asyncio.create_task(lire_la_premiere())
    await _jusqu_a(lambda: outils.confirmations.en_attente, "la suppression n'attend pas")
    assert await _tout(cerveau, "Oui.") == ["Oui ?"]  # pas une réponse : la question n'est pas dite
    await tache
    assert premiere == ["Je regarde. "]
    assert outils.memoire.lire(CHEMIN) == OFFRE and pages.fins == []
    assert client.questions[-1] == (
        "[David a parlé avant la question : la suppression du document « Offre de lancement » "
        f"est abandonnée.]\n{DATE}\nOui."
    )


async def test_la_fin_de_la_conversation_abandonne_l_action_en_attente(outils, pages):
    client = FauxClientClaude(_demande(outils), resume("RIEN"))
    cerveau = _cerveau(outils, client)
    await _tout(cerveau, "Supprime l'offre de lancement.")
    await cerveau.fermer()
    assert not outils.confirmations.en_attente
    assert outils.memoire.lire(CHEMIN) == OFFRE
    assert pages.fins == ["Rien n'a été supprimé."]


async def test_le_resume_apprend_ce_que_david_a_confirme_juste_avant(outils):
    minuterie = Minuterie()
    client = FauxClientClaude(_demande(outils), resume("On a supprimé l'offre."))
    cerveau = _cerveau(outils, client, minuterie=minuterie)
    await _tout(cerveau, "Supprime l'offre de lancement.")
    await _tout(cerveau, "Oui.")
    minuterie.sonner()
    await _jusqu_a(lambda: client.deconnexions, "la conversation ne s'est pas fermée")
    assert client.questions[-1] == (
        "[Confirmé par David : le document « Offre de lancement » est supprimé.]\n" + DEMANDE_RESUME
    )
    assert outils.confirmations.prendre_les_lignes() == []
```

Modifier `tests/test_consignes.py` :

```diff
--- a/tests/test_consignes.py
+++ b/tests/test_consignes.py
@@ -81,6 +81,27 @@ def test_avec_la_memoire_les_consignes_gardent_tout_et_disent_comment_la_tenir()
         assert attendu in texte, attendu
 
 
+def test_avec_la_memoire_les_consignes_disent_les_documents_et_la_suppression():
+    texte = CONSIGNES_AVEC_MEMOIRE.lower()
+    for attendu in (
+        "document_ecrire",
+        "quand david te demande un document",
+        "se relit sans retouche",
+        "rien d'inventé",
+        "jamais l'écrire sans qu'il le demande",
+        "sans le lire",
+        "relis-le avec memoire_lire, puis réécris-le en entier",
+        "le seul endroit où tu écris en markdown",
+        "memoire_supprimer",
+        "atlas demande à david de confirmer",
+        "ne dis jamais que c'est fait",
+        "« [confirmé par david : …] »",
+    ):
+        assert attendu in texte, attendu
+    assert "Tu ne peux rien faire d'autre que réfléchir et chercher sur le web." in CONSIGNES
+    assert "document" not in CONSIGNES.lower()
+
+
 def test_la_demande_de_resume_ne_fait_rien_ecrire_et_admet_rien():
     assert DEMANDE_RESUME.startswith("[Fin de la conversation]")
     assert "n'écris rien dans ta mémoire" in DEMANDE_RESUME
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `uv run pytest tests/test_cerveau_confirmation.py tests/test_consignes.py -q`
Expected: FAIL — 9 échecs : les 8 tests de `test_cerveau_confirmation.py` (la question n'est jamais rendue, la réponse
part à Claude) et `test_avec_la_memoire_les_consignes_disent_les_documents_et_la_suppression`.

- [ ] **Step 3: Écrire la confirmation dans le cerveau, et les consignes**

Modifier `src/atlas_core/cerveau_claude.py` :

```diff
--- a/src/atlas_core/cerveau_claude.py
+++ b/src/atlas_core/cerveau_claude.py
@@ -157,8 +157,20 @@ class CerveauClaude:
         async with self._verrou:
             await self._attendre_le_menage()
             self._interrompu = False
-            question = f"{ligne_de_date(self._maintenant())}\n{texte}"
+            confirmations = self._outils.confirmations if self._outils is not None else None
             try:
+                if confirmations is not None:
+                    # Une action attend le « oui » de David : sa phrase est lue ici, avant
+                    # Claude (spec 2c §6). Une question qu'il n'a pas entendue ne compte pas.
+                    confirmations.abandonner_si_non_posee()
+                    if confirmations.en_attente:
+                        phrase, a_claude = await confirmations.trancher(texte)
+                        if not a_claude:
+                            yield phrase
+                            return
+                        yield phrase + " "
+                lignes = confirmations.prendre_les_lignes() if confirmations is not None else []
+                question = "\n".join([*lignes, ligne_de_date(self._maintenant()), texte])
                 client = await self._poser(question)
                 self._debut_conversation = self._debut_conversation or self._maintenant()
                 if self._fil_perdu:
@@ -235,7 +247,9 @@ class CerveauClaude:
         await self._jeter_le_client()
 
     async def _demander_le_resume(self, client: ClientClaude) -> str:
-        await self._envoyer(client, DEMANDE_RESUME)
+        # Ce que David a confirmé ou refusé juste avant, que Claude n'a pas encore appris.
+        lignes = self._outils.confirmations.prendre_les_lignes()
+        await self._envoyer(client, "\n".join([*lignes, DEMANDE_RESUME]))
         morceaux: list[str] = []
         async with contextlib.aclosing(self._lire_le_tour(client)) as fragments:
             async for fragment in fragments:
@@ -307,6 +321,8 @@ class CerveauClaude:
         client, self._client = self._client, None
         self._tour_ouvert = False
         self._debut_conversation = self._fin_conversation = None
+        if self._outils is not None:
+            self._outils.confirmations.abandonner()  # la conversation se termine
         if client is not None:
             with contextlib.suppress(Exception):
                 await client.disconnect()
@@ -368,6 +384,9 @@ class CerveauClaude:
                     if self._outils is not None and annoncer:
                         for note in self._outils.prendre_les_annonces():
                             yield note
+                        # Une action N3 : sa question, une fois, après ce qui la précède.
+                        if (question := self._outils.confirmations.poser()) is not None:
+                            yield question
         except ErreurCerveau:
             raise
         except Exception as e:  # noqa: BLE001 — le SDK ne sait plus où il en est
```

Modifier `src/atlas_core/consignes.py` :

```diff
--- a/src/atlas_core/consignes.py
+++ b/src/atlas_core/consignes.py
@@ -63,6 +63,18 @@ jamais de mot de passe ni de clé secrète.
 
 Appelle David comme son profil l'indique, et « David » tant que le profil ne dit rien \
 d'autre.
+
+Quand David te demande un document (« fais-en un document »), écris-le avec \
+document_ecrire : un texte complet, qui se relit sans retouche, avec un plan clair, des \
+phrases entières et rien d'inventé. C'est le seul endroit où tu écris en Markdown : tes \
+réponses, elles, restent dites à voix haute. Tu peux proposer d'en faire un, jamais \
+l'écrire sans qu'il le demande. Ensuite, dis en deux ou trois phrases ce qu'il contient, \
+sans le lire. Pour le retoucher, relis-le avec memoire_lire, puis réécris-le en entier.
+
+Pour supprimer une fiche ou un document, appelle memoire_supprimer : Atlas demande à David \
+de confirmer. N'ajoute rien après l'appel, et ne dis jamais que c'est fait. Une ligne \
+entre crochets au début d'une question te dit ce qu'il en est, par exemple « [Confirmé \
+par David : …] » ou « [Refusé par David : …] » : tiens-en compte, sans la répéter.
 """
 
 CONSIGNES = (
```

- [ ] **Step 4: Vérifier que tout passe**

Run: `uv run pytest -q && uv run ruff check . --extend-exclude spikes && uv run ruff format --check . --extend-exclude spikes && node --test "tests/web/*.test.mjs"`
Expected: 937 tests Python passent, 126 tests JavaScript passent, ruff ne dit rien.

- [ ] **Step 5: Commit**

```bash
git add src/atlas_core/cerveau_claude.py src/atlas_core/consignes.py tests/test_cerveau_confirmation.py tests/test_consignes.py
git commit -F - <<'MSG'
Cerveau : la réponse de David lue avant Claude quand une action attend son « oui »

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

### Task 7: Les pages : documents et confirmation par le hub

Le protocole des pages s'enrichit (la liste et le contenu des documents, la question en cours, les boutons) ; le
diffuseur retient la question comme il retient le mode muet ; le hub branche la mémoire vers les pages et sert les
documents, sans mémoire comme avec. Un bouton touché trop tard ne fait rien.

**Files:**
- Modify: `src/atlas_core/cerveau_claude.py`
- Modify: `src/atlas_core/diffuseur.py`
- Modify: `src/atlas_core/hub.py`
- Modify: `src/atlas_core/protocole_web.py`
- Modify: `tests/test_diffuseur.py`
- Modify: `tests/test_hub.py`
- Modify: `tests/test_hub_web.py`
- Modify: `tests/test_protocole_web.py`

**Interfaces:**
- Consumes: Tasks 1, 3, 5, 6 (`Memoire.documents`, `lire`, `Confirmations.sur_question`, `sur_fin`, `en_attente`,
  `OutilsMemoire(memoire, confirmations, sur_documents)`).
- Produces: `protocole_web` : `MOTIF_DOCUMENT`, `ResumeDocument`, `ListeDocuments(disponible=True, documents=[])`,
  `Document(chemin, titre="", contenu="", erreur=None)`, `DocumentsChanges`, `AttenteConfirmation(texte)` (type
  `confirmation`), `FinConfirmation(texte)` (type `confirmation_finie`), `DemandeDocuments`, `LireDocument(chemin)`,
  `Confirmer(oui: bool)` ; `CerveauClaude.outils` (propriété) ; `hub._outils`, `hub.MEMOIRE_ABSENTE`,
  `hub.ouvrir_la_memoire(config)` qui prévient les pages.

- [ ] **Step 1: Écrire les tests qui échouent**

Modifier `tests/test_diffuseur.py` :

```diff
--- a/tests/test_diffuseur.py
+++ b/tests/test_diffuseur.py
@@ -2,7 +2,16 @@ import asyncio
 
 from atlas_core.diffuseur import RETARD_MAX_NIVEAUX, Diffuseur
 from atlas_core.protocole import Erreur, Etat
-from atlas_core.protocole_web import Historique, Latences, Muet, Niveau, Question, Reponse
+from atlas_core.protocole_web import (
+    AttenteConfirmation,
+    FinConfirmation,
+    Historique,
+    Latences,
+    Muet,
+    Niveau,
+    Question,
+    Reponse,
+)
 
 
 class Page:
@@ -210,3 +219,21 @@ async def test_une_page_en_panne_se_retire_seule():
     await _laisser_passer()
     # La file ne doit pas avoir grossi (pas de nouveaux messages)
     assert abonnement._file.qsize() == taille_initiale
+
+
+async def test_une_page_ouverte_pendant_une_confirmation_la_recoit_aussi():
+    d = _diffuseur()
+    d.publier(AttenteConfirmation(texte="Je supprime le document X. Tu confirmes ?"))
+    page = Page()
+    abonnement = d.abonner(page.envoyer)
+    await _laisser_passer()
+    assert page.types() == ["historique", "muet", "etat", "confirmation"]
+    d.publier(FinConfirmation(texte="Rien n'a été supprimé."))
+    tard = Page()
+    abonnement_tard = d.abonner(tard.envoyer)
+    await _laisser_passer()
+    assert tard.types() == ["historique", "muet", "etat"]
+    assert page.types()[-1] == "confirmation_finie"
+    assert d.historique().echanges == []
+    await abonnement.fermer()
+    await abonnement_tard.fermer()
```

Modifier `tests/test_hub.py` :

```diff
--- a/tests/test_hub.py
+++ b/tests/test_hub.py
@@ -16,6 +16,7 @@ from atlas_core.protocole import (
     Reveil,
     encoder_audio_entrant,
 )
+from atlas_core.protocole_web import AttenteConfirmation, DocumentsChanges, FinConfirmation
 
 CLE_AUDIO = "cle-audio-de-test"
 
@@ -186,6 +187,30 @@ def test_la_memoire_refuse_les_cles_du_core(monkeypatch, tmp_path):
             outils.memoire.ecrire("profil.md", f"# Profil\n\nDavid.\n\n{secret}\n")
 
 
+def test_la_memoire_previent_les_pages(monkeypatch, tmp_path):
+    publies: list = []
+    monkeypatch.setattr(hub._regie.diffuseur, "publier", publies.append)
+    outils = hub.ouvrir_la_memoire(replace(hub._config, memoire_dossier=tmp_path / "memoire"))
+    outils.sur_documents()
+    outils.confirmations.sur_question("Je supprime ton profil. Tu confirmes ?")
+    outils.confirmations.sur_fin("Rien n'a été supprimé.")
+    assert publies == [
+        DocumentsChanges(),
+        AttenteConfirmation(texte="Je supprime ton profil. Tu confirmes ?"),
+        FinConfirmation(texte="Rien n'a été supprimé."),
+    ]
+
+
+def test_le_core_garde_les_outils_du_cerveau_le_temps_de_sa_vie(monkeypatch, tmp_path):
+    config = replace(hub._config, cerveau="claude", memoire_dossier=tmp_path / "memoire")
+    monkeypatch.setattr(hub, "_config", config)
+    monkeypatch.setattr(hub, "DOSSIER_CERVEAU", tmp_path / "cerveau")
+    with TestClient(hub.app):
+        assert hub._outils is hub._cerveau.outils
+        assert hub._outils.memoire.racine == tmp_path / "memoire"
+    assert hub._outils is None
+
+
 def test_sans_git_le_cerveau_marche_sans_memoire(monkeypatch, tmp_path):
     monkeypatch.setattr(memoire, "GIT", "git-introuvable")
     monkeypatch.setattr(hub, "DOSSIER_CERVEAU", tmp_path / "cerveau")
```

Modifier `tests/test_hub_web.py` :

```diff
--- a/tests/test_hub_web.py
+++ b/tests/test_hub_web.py
@@ -1,3 +1,4 @@
+import re
 from dataclasses import replace
 
 import pytest
@@ -80,6 +81,93 @@ def test_une_question_tapee_porte_l_identifiant_de_sa_page(regie, page):
     assert regie.saisies == ["quelle heure est-il"] and regie.pages == [page]
 
 
+# --- les documents et la confirmation ----------------------------------------------
+
+OFFRE = "# Offre de lancement\n\nTrois formules pour les premiers clients.\n"
+
+
+@pytest.fixture
+def memoire(regie, monkeypatch, tmp_path):
+    dossier = tmp_path / "memoire"
+    config = replace(hub._config, web_cle=CLE, cerveau="claude", memoire_dossier=dossier)
+    monkeypatch.setattr(hub, "_config", config)
+    monkeypatch.setattr(hub, "DOSSIER_CERVEAU", tmp_path / "cerveau")
+    return dossier
+
+
+def test_une_page_liste_puis_lit_les_documents(memoire):
+    with TestClient(hub.app) as client, client.websocket_connect("/ws/web", headers=ORIGINE) as ws:
+        _entrer(ws)
+        hub._outils.memoire.ecrire_document("offre-de-lancement", OFFRE)
+        ws.send_json({"type": "documents"})
+        liste = ws.receive_json()
+        ws.send_json({"type": "lire_document", "chemin": "documents/offre-de-lancement.md"})
+        document = ws.receive_json()
+        ws.send_json({"type": "lire_document", "chemin": "documents/absent.md"})
+        absent = ws.receive_json()
+    assert (liste["type"], liste["disponible"]) == ("liste_documents", True)
+    [info] = liste["documents"]
+    assert (info["chemin"], info["titre"], info["resume"]) == (
+        "documents/offre-de-lancement.md",
+        "Offre de lancement",
+        "Trois formules pour les premiers clients.",
+    )
+    assert re.fullmatch(r"\d{1,2}(er)? \w+ \d{4}, \d{1,2} h \d{2}", info["modifie"])
+    assert document == {
+        "type": "document",
+        "chemin": "documents/offre-de-lancement.md",
+        "titre": "Offre de lancement",
+        "contenu": OFFRE,
+        "erreur": None,
+    }
+    assert (absent["contenu"], absent["erreur"]) == ("", "documents/absent.md n'existe pas.")
+
+
+def test_une_page_ne_lit_pas_une_fiche_par_le_panneau_des_documents(memoire):
+    with TestClient(hub.app) as client, client.websocket_connect("/ws/web", headers=ORIGINE) as ws:
+        _entrer(ws)
+        ws.send_json({"type": "lire_document", "chemin": "profil.md"})
+        erreur = ws.receive_json()
+    assert (erreur["type"], erreur["code"]) == ("erreur", "message_invalide")
+
+
+def test_sans_memoire_la_page_le_sait(regie, monkeypatch):
+    monkeypatch.setattr(hub, "_config", replace(hub._config, web_cle=CLE, cerveau="bouchon"))
+    with TestClient(hub.app) as client, client.websocket_connect("/ws/web", headers=ORIGINE) as ws:
+        _entrer(ws)
+        ws.send_json({"type": "documents"})
+        liste = ws.receive_json()
+        ws.send_json({"type": "lire_document", "chemin": "documents/offre-de-lancement.md"})
+        document = ws.receive_json()
+    assert liste == {"type": "liste_documents", "disponible": False, "documents": []}
+    assert document["erreur"] == "La mémoire n'est pas disponible."
+
+
+class _Attente:
+    def __init__(self, en_attente: bool) -> None:
+        self.en_attente = en_attente
+
+
+class _Outils:
+    def __init__(self, en_attente: bool) -> None:
+        self.confirmations = _Attente(en_attente)
+
+
+@pytest.mark.parametrize(("en_attente", "saisies"), [(True, ["oui", "non"]), (False, [])])
+def test_les_boutons_repondent_comme_une_saisie_de_leur_page(
+    regie, monkeypatch, en_attente, saisies
+):
+    with TestClient(hub.app) as client, client.websocket_connect("/ws/web", headers=ORIGINE) as ws:
+        ws.send_json({"type": "authentification", "cle": CLE, "page": "iphone-1"})
+        [ws.receive_json() for _ in range(3)]
+        monkeypatch.setattr(hub, "_outils", _Outils(en_attente))
+        ws.send_json({"type": "confirmer", "oui": True})
+        ws.send_json({"type": "confirmer", "oui": False})
+        ws.send_json({"type": "saisie", "texte": ""})  # sa réponse prouve que tout est traité
+        ws.receive_json()
+    assert regie.saisies == saisies and regie.pages == ["iphone-1"] * len(saisies)
+
+
 def test_une_mauvaise_cle_ferme_la_connexion(regie):
     with TestClient(hub.app) as client, client.websocket_connect("/ws/web", headers=ORIGINE) as ws:
         ws.send_json({"type": "authentification", "cle": "pas-la-bonne"})
```

Modifier `tests/test_protocole_web.py` :

```diff
--- a/tests/test_protocole_web.py
+++ b/tests/test_protocole_web.py
@@ -6,12 +6,21 @@ from pydantic import ValidationError
 from atlas_core.protocole import Etat
 from atlas_core.protocole_web import (
     LONGUEUR_MAX_SAISIE,
+    AttenteConfirmation,
     Authentification,
+    Confirmer,
+    DemandeDocuments,
+    Document,
+    DocumentsChanges,
     Echange,
+    FinConfirmation,
     Historique,
     Latences,
+    LireDocument,
+    ListeDocuments,
     Muet,
     Niveau,
+    ResumeDocument,
     Saisie,
     decoder_message_page,
 )
@@ -85,3 +94,65 @@ def test_l_etat_du_protocole_audio_sert_aussi_aux_pages():
         "type": "etat",
         "valeur": "parole",
     }
+
+
+def test_les_messages_des_documents_et_de_la_confirmation_se_decodent():
+    assert decoder_message_page('{"type":"documents"}') == DemandeDocuments()
+    chemin = "documents/offre-de-lancement.md"
+    assert decoder_message_page(
+        json.dumps({"type": "lire_document", "chemin": chemin})
+    ) == LireDocument(chemin=chemin)
+    assert decoder_message_page('{"type":"confirmer","oui":true}') == Confirmer(oui=True)
+    assert decoder_message_page('{"type":"confirmer","oui":false}') == Confirmer(oui=False)
+
+
+@pytest.mark.parametrize(
+    "chemin",
+    [
+        "profil.md",
+        "personnes/paul-durand.md",
+        "documents/../profil.md",
+        "documents/Offre.md",
+        "documents/offre.txt",
+        "../documents/offre.md",
+        "documents/" + "a" * 61 + ".md",
+    ],
+)
+def test_une_page_ne_lit_qu_un_document(chemin):
+    with pytest.raises(ValueError):
+        decoder_message_page(json.dumps({"type": "lire_document", "chemin": chemin}))
+
+
+def test_confirmer_demande_oui_ou_non():
+    for brut in ('{"type":"confirmer"}', '{"type":"confirmer","oui":"peut-être"}'):
+        with pytest.raises(ValueError):
+            decoder_message_page(brut)
+
+
+def test_les_messages_des_documents_et_de_la_confirmation_vers_les_pages():
+    resume = ResumeDocument(
+        chemin="documents/offre-de-lancement.md",
+        titre="Offre de lancement",
+        resume="Trois formules.",
+        modifie="25 septembre 2026, 21 h 14",
+    )
+    assert json.loads(ListeDocuments(documents=[resume]).model_dump_json()) == {
+        "type": "liste_documents",
+        "disponible": True,
+        "documents": [resume.model_dump()],
+    }
+    assert ListeDocuments(disponible=False).model_dump() == {
+        "type": "liste_documents",
+        "disponible": False,
+        "documents": [],
+    }
+    assert Document(chemin="documents/a.md", titre="A", contenu="# A\n").model_dump() == {
+        "type": "document",
+        "chemin": "documents/a.md",
+        "titre": "A",
+        "contenu": "# A\n",
+        "erreur": None,
+    }
+    assert DocumentsChanges().model_dump() == {"type": "documents_changes"}
+    assert AttenteConfirmation(texte="Q ?").model_dump() == {"type": "confirmation", "texte": "Q ?"}
+    assert FinConfirmation(texte="F.").model_dump() == {"type": "confirmation_finie", "texte": "F."}
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `uv run pytest tests/test_protocole_web.py tests/test_diffuseur.py tests/test_hub.py tests/test_hub_web.py -q`
Expected: FAIL — trois erreurs de collecte : `ImportError: cannot import name 'AttenteConfirmation' from
'atlas_core.protocole_web'`.

- [ ] **Step 3: Écrire le protocole, le diffuseur et le hub**

Modifier `src/atlas_core/cerveau_claude.py` :

```diff
--- a/src/atlas_core/cerveau_claude.py
+++ b/src/atlas_core/cerveau_claude.py
@@ -146,6 +146,11 @@ class CerveauClaude:
         self._fil_perdu = False  # la conversation a été perdue : la réponse suivante le dit
         self._menage: asyncio.Task | None = None
 
+    @property
+    def outils(self) -> OutilsMemoire | None:
+        """Les outils d'Atlas et sa mémoire ; None sans mémoire."""
+        return self._outils
+
     async def repondre(self, texte: str) -> AsyncIterator[str | Recherche | Note]:
         if self._echeance is not None and not self._resume_en_cours:
             self._echeance.cancel()  # la conversation continue
```

Modifier `src/atlas_core/diffuseur.py` :

```diff
--- a/src/atlas_core/diffuseur.py
+++ b/src/atlas_core/diffuseur.py
@@ -15,7 +15,17 @@ from collections.abc import Awaitable, Callable
 from pydantic import BaseModel
 
 from .protocole import Erreur, Etat
-from .protocole_web import Echange, Historique, Latences, Muet, Niveau, Question, Reponse
+from .protocole_web import (
+    AttenteConfirmation,
+    Echange,
+    FinConfirmation,
+    Historique,
+    Latences,
+    Muet,
+    Niveau,
+    Question,
+    Reponse,
+)
 
 TAILLE_HISTORIQUE = 50
 # Une page qui n'arrive pas à suivre perd des niveaux (l'orbe saute une image), jamais
@@ -72,13 +82,17 @@ class Diffuseur:
         self._en_cours: Echange | None = None
         self._dernier_etat = Etat(valeur="repos")
         self._muet = False
+        self._confirmation: AttenteConfirmation | None = None  # la question qui attend
         self._heure = heure or _heure_locale
 
     def abonner(self, envoyer: Envoyer) -> Abonnement:
-        """Abonne une page : elle reçoit d'abord l'historique, le mode muet et l'état courant."""
+        """Abonne une page : elle reçoit d'abord l'historique, le mode muet et l'état courant,
+        puis la question qui attend le « oui » de David, s'il y en a une."""
         abonnement = Abonnement(self, envoyer)
         for msg in (self.historique(), Muet(actif=self._muet), self._dernier_etat):
             abonnement.deposer(msg)
+        if self._confirmation is not None:
+            abonnement.deposer(self._confirmation)
         self._abonnements.append(abonnement)
         return abonnement
 
@@ -101,6 +115,10 @@ class Diffuseur:
                 self._en_cours = None
         elif isinstance(msg, Muet):
             self._muet = msg.actif
+        elif isinstance(msg, AttenteConfirmation):
+            self._confirmation = msg
+        elif isinstance(msg, FinConfirmation):
+            self._confirmation = None
         elif isinstance(msg, Question):
             self._en_cours = Echange(heure=self._heure(), source=msg.source, question=msg.texte)
             self._echanges.append(self._en_cours)
```

Modifier `src/atlas_core/hub.py` :

```diff
--- a/src/atlas_core/hub.py
+++ b/src/atlas_core/hub.py
@@ -21,8 +21,10 @@ from atlas_audio.connexion import PeripheriqueEnPanne
 from .cerveau import Cerveau, CerveauBouchon
 from .cerveau_claude import CerveauClaude, options_cerveau, purger_cles_api
 from .config import Config
+from .confirmation import Confirmations
+from .consignes import date_en_lettres, heure_en_chiffres
 from .diffuseur import Diffuseur
-from .memoire import Memoire
+from .memoire import ErreurMemoire, Memoire
 from .outils_memoire import OutilsMemoire
 from .protocole import Bonjour, Erreur, decoder_audio_entrant, decoder_message
 from .protocole_voix import (
@@ -34,7 +36,21 @@ from .protocole_voix import (
     decoder_message_voix,
     verifier_bloc_page,
 )
-from .protocole_web import Authentification, Muet, Saisie, decoder_message_page
+from .protocole_web import (
+    AttenteConfirmation,
+    Authentification,
+    Confirmer,
+    DemandeDocuments,
+    Document,
+    DocumentsChanges,
+    FinConfirmation,
+    LireDocument,
+    ListeDocuments,
+    Muet,
+    ResumeDocument,
+    Saisie,
+    decoder_message_page,
+)
 from .regie import Regie
 from .session import Session, sans_destinataire
 from .synthese import ClientSynthese
@@ -48,6 +64,7 @@ _config = Config.depuis_environnement()
 _reglages = lire_reglages()
 _http: httpx.AsyncClient | None = None
 _cerveau: Cerveau | None = None
+_outils: OutilsMemoire | None = None  # la mémoire et ses outils, le temps de la vie du Core
 
 RACINE_WEB = Path(__file__).resolve().parent.parent / "atlas_web"
 # Le dossier de travail de Claude : vide, à lui seul, hors de tout projet.
@@ -57,6 +74,7 @@ FERMETURE_CLE_ABSENTE = 4000
 FERMETURE_NON_AUTORISE = 4401
 FERMETURE_ORIGINE = 1008  # « policy violation », avant même d'accepter la connexion
 FERMETURE_PANNE = 1011  # « internal error » : la voix d'une page s'est arrêtée, elle se rebranche
+MEMOIRE_ABSENTE = "La mémoire n'est pas disponible."
 
 
 def creer_cerveau(config: Config) -> Cerveau:
@@ -78,17 +96,57 @@ def creer_cerveau(config: Config) -> Cerveau:
 
 def ouvrir_la_memoire(config: Config) -> OutilsMemoire | None:
     """La mémoire d'Atlas et ses outils ; None si elle ne s'ouvre pas (Atlas marche alors
-    sans). Les clés du Core sont des secrets qu'elle refuse d'écrire."""
+    sans). Les clés du Core sont des secrets qu'elle refuse d'écrire. Les pages sont
+    prévenues quand un document change, et de la question qui attend le « oui » de David."""
     secrets = [config.web_cle, config.audio_cle, os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "")]
     memoire = Memoire.ouvrir(config.memoire_dossier, secrets)
-    return OutilsMemoire(memoire) if memoire is not None else None
+    if memoire is None:
+        return None
+
+    def publier(msg) -> None:
+        _regie.diffuseur.publier(msg)
+
+    confirmations = Confirmations(
+        sur_question=lambda texte: publier(AttenteConfirmation(texte=texte)),
+        sur_fin=lambda texte: publier(FinConfirmation(texte=texte)),
+    )
+    return OutilsMemoire(memoire, confirmations, lambda: publier(DocumentsChanges()))
+
+
+async def _liste_documents() -> ListeDocuments:
+    if _outils is None:
+        return ListeDocuments(disponible=False)
+    infos = await asyncio.to_thread(_outils.memoire.documents)
+    return ListeDocuments(
+        documents=[
+            ResumeDocument(
+                chemin=info.chemin,
+                titre=info.titre,
+                resume=info.resume,
+                modifie=f"{date_en_lettres(info.modifie)}, {heure_en_chiffres(info.modifie)}",
+            )
+            for info in infos
+        ]
+    )
+
+
+async def _lire_document(chemin: str) -> Document:
+    if _outils is None:
+        return Document(chemin=chemin, erreur=MEMOIRE_ABSENTE)
+    try:
+        contenu = await asyncio.to_thread(_outils.memoire.lire, chemin)
+    except (ErreurMemoire, OSError) as e:
+        return Document(chemin=chemin, erreur=str(e))
+    titre = contenu.split("\n", 1)[0].lstrip("#").strip()
+    return Document(chemin=chemin, titre=titre, contenu=contenu)
 
 
 @asynccontextmanager
 async def _cycle_de_vie(app: FastAPI):
-    global _http, _cerveau
+    global _http, _cerveau, _outils
     _http = httpx.AsyncClient()
     _cerveau = creer_cerveau(_config)
+    _outils = _cerveau.outils if isinstance(_cerveau, CerveauClaude) else None
     try:
         yield
     finally:
@@ -97,7 +155,7 @@ async def _cycle_de_vie(app: FastAPI):
         try:
             await _cerveau.fermer()
         finally:
-            _cerveau = None
+            _cerveau = _outils = None
             await _http.aclose()
             _http = None
 
@@ -294,6 +352,14 @@ async def ws_web(ws: WebSocket) -> None:
                 await _regie.saisie(msg.texte, demande.page)
             elif isinstance(msg, Muet):
                 await _regie.basculer_muet(msg.actif)
+            elif isinstance(msg, DemandeDocuments):
+                abonnement.envoyer_prive(await _liste_documents())
+            elif isinstance(msg, LireDocument):
+                abonnement.envoyer_prive(await _lire_document(msg.chemin))
+            elif isinstance(msg, Confirmer):
+                # Comme taper « oui » ou « non » depuis cette page ; trop tard, rien.
+                if _outils is not None and _outils.confirmations.en_attente:
+                    await _regie.saisie("oui" if msg.oui else "non", demande.page)
     except WebSocketDisconnect:
         pass
     finally:
```

Modifier `src/atlas_core/protocole_web.py` :

```diff
--- a/src/atlas_core/protocole_web.py
+++ b/src/atlas_core/protocole_web.py
@@ -15,6 +15,9 @@ TAILLE_MAX_CLE = 256
 # L'identifiant qu'une page tire au hasard à son ouverture, le même sur /ws/web et sur
 # /ws/voix : une question tapée trouve ainsi la voix de sa page.
 MOTIF_PAGE = r"^[A-Za-z0-9_-]{1,64}$"
+# Le panneau « Documents » ne lit que des documents : jamais une fiche ni le journal.
+MOTIF_DOCUMENT = r"^documents/[a-z0-9]+(?:-[a-z0-9]+)*\.md$"
+CHEMIN_DOCUMENT_MAX = len("documents/") + 60 + len(".md")  # un nom : 60 au plus (memoire.py)
 
 Source = Literal["voix", "clavier"]
 
@@ -66,6 +69,49 @@ class Historique(BaseModel):
     echanges: list[Echange]
 
 
+class ResumeDocument(BaseModel):
+    chemin: str
+    titre: str
+    resume: str
+    modifie: str  # « 25 septembre 2026, 21 h 14 »
+
+
+class ListeDocuments(BaseModel):
+    """Les documents, du plus récent au plus ancien ; `disponible` est faux sans mémoire."""
+
+    type: Literal["liste_documents"] = "liste_documents"
+    disponible: bool = True
+    documents: list[ResumeDocument] = []
+
+
+class Document(BaseModel):
+    type: Literal["document"] = "document"
+    chemin: str
+    titre: str = ""
+    contenu: str = ""
+    erreur: str | None = None
+
+
+class DocumentsChanges(BaseModel):
+    """À toutes les pages : un document a été écrit, supprimé ou remis."""
+
+    type: Literal["documents_changes"] = "documents_changes"
+
+
+class AttenteConfirmation(BaseModel):
+    """À toutes les pages : Atlas attend le « oui » de David ; `texte` est la question."""
+
+    type: Literal["confirmation"] = "confirmation"
+    texte: str
+
+
+class FinConfirmation(BaseModel):
+    """À toutes les pages : l'attente est finie ; `texte` dit comment."""
+
+    type: Literal["confirmation_finie"] = "confirmation_finie"
+    texte: str
+
+
 # --- page vers Core -----------------------------------------------------
 
 
@@ -88,7 +134,26 @@ class Saisie(BaseModel):
         return texte
 
 
-MessagePage = Annotated[Authentification | Saisie | Muet, Field(discriminator="type")]
+class DemandeDocuments(BaseModel):
+    type: Literal["documents"] = "documents"
+
+
+class LireDocument(BaseModel):
+    type: Literal["lire_document"] = "lire_document"
+    chemin: str = Field(pattern=MOTIF_DOCUMENT, max_length=CHEMIN_DOCUMENT_MAX)
+
+
+class Confirmer(BaseModel):
+    """Les boutons « Confirmer » et « Annuler » : comme taper « oui » ou « non »."""
+
+    type: Literal["confirmer"] = "confirmer"
+    oui: bool
+
+
+MessagePage = Annotated[
+    Authentification | Saisie | Muet | DemandeDocuments | LireDocument | Confirmer,
+    Field(discriminator="type"),
+]
 _adaptateur_page = TypeAdapter(MessagePage)
 
 
```

- [ ] **Step 4: Vérifier que tout passe**

Run: `uv run pytest -q && uv run ruff check . --extend-exclude spikes && uv run ruff format --check . --extend-exclude spikes && node --test "tests/web/*.test.mjs"`
Expected: 955 tests Python passent, 126 tests JavaScript passent, ruff ne dit rien.

- [ ] **Step 5: Commit**

```bash
git add src/atlas_core/cerveau_claude.py src/atlas_core/diffuseur.py src/atlas_core/hub.py src/atlas_core/protocole_web.py tests/test_diffuseur.py tests/test_hub.py tests/test_hub_web.py tests/test_protocole_web.py
git commit -F - <<'MSG'
Hub : les documents et la confirmation servis aux pages

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

### Task 8: La mise en forme d'un document

`markdown.js` met en forme la syntaxe permise à Claude — et rien d'autre — en construisant des éléments et du texte,
jamais du HTML : un document ne peut pas injecter de code dans la page. Un lien qui n'est pas en `http(s)` reste du
texte.

**Files:**
- Create: `src/atlas_web/markdown.js`
- Create: `tests/web/markdown.test.mjs`

**Interfaces:**
- Consumes: rien.
- Produces: `src/atlas_web/markdown.js` : `rendreMarkdown(document, texte) -> Element[]` (les blocs, à mettre dans
  un conteneur par `replaceChildren(...blocs)`).

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/web/markdown.test.mjs` :

````javascript
import assert from "node:assert/strict";
import { test } from "node:test";

import { rendreMarkdown } from "../../src/atlas_web/markdown.js";
import { fauxDocument } from "./faux_dom.mjs";

// Le rendu en texte, pour comparer : un élément devient <tag attr="…">…</tag>, une chaîne
// reste du texte (le vrai navigateur en fait un nœud texte, jamais du HTML).
function rendu(noeud) {
  if (typeof noeud === "string") return noeud;
  const tag = noeud.tagName.toLowerCase();
  const attributs = Object.entries(noeud.attributs)
    .map(([nom, valeur]) => ` ${nom}="${valeur}"`)
    .join("");
  const dedans = noeud.children.length ? noeud.children.map(rendu).join("") : noeud.textContent;
  return `<${tag}${attributs}>${dedans}</${tag}>`;
}

function html(texte) {
  return rendreMarkdown(fauxDocument(), texte).map(rendu).join("");
}

function elements(noeuds) {
  return noeuds.flatMap((n) => (typeof n === "string" ? [] : [n, ...elements(n.children)]));
}

test("les titres ont trois niveaux ; au-delà, c'est du texte", () => {
  assert.equal(html("# Offre\n\n## Formules\n\n### Prix\n\n#### Détail"), "<h1>Offre</h1><h2>Formules</h2><h3>Prix</h3><p>#### Détail</p>");
});

test("un paragraphe réunit ses lignes, une ligne vide les sépare", () => {
  assert.equal(html("Une ligne\nqui continue.\n\nAutre paragraphe."), "<p>Une ligne qui continue.</p><p>Autre paragraphe.</p>");
});

test("les listes à puces et numérotées", () => {
  assert.equal(
    html("- un\n* **deux**\n\n1. premier\n2) second"),
    "<ul><li>un</li><li><strong>deux</strong></li></ul><ol><li>premier</li><li>second</li></ol>",
  );
});

test("une citation réunit ses lignes", () => {
  assert.equal(html("> À valider\n> avec Paul."), "<blockquote><p>À valider avec Paul.</p></blockquote>");
});

test("un tableau, avec ou sans ligne d'en-tête", () => {
  assert.equal(
    html("| Formule | Prix |\n| --- | ---: |\n| Diagnostic | 900 € |"),
    "<table><thead><tr><th>Formule</th><th>Prix</th></tr></thead>" +
      "<tbody><tr><td>Diagnostic</td><td>900 €</td></tr></tbody></table>",
  );
  assert.equal(html("| a | b |\n| c | d |"), "<table><tbody><tr><td>a</td><td>b</td></tr><tr><td>c</td><td>d</td></tr></tbody></table>");
});

test("le gras, l'italique, le code et les liens https", () => {
  assert.equal(
    html("**gras**, *italique*, `code` et [le site](https://example.com/offre)."),
    '<p><strong>gras</strong>, <em>italique</em>, <code>code</code> et <a href="https://example.com/offre" ' +
      'target="_blank" rel="noopener noreferrer">le site</a>.</p>',
  );
});

test("le gras garde sa mise en forme intérieure", () => {
  assert.equal(html("**voir `offre.md`**"), "<p><strong>voir <code>offre.md</code></strong></p>");
});

test("un bloc peut suivre un paragraphe sans ligne vide", () => {
  assert.equal(
    html("Les formules :\n- une\n- deux\nEt la suite.\n## Prix\n> Note"),
    "<p>Les formules :</p><ul><li>une</li><li>deux</li></ul><p>Et la suite.</p><h2>Prix</h2>" +
      "<blockquote><p>Note</p></blockquote>",
  );
});

test("un lien qui n'est pas en http(s) reste du texte", () => {
  for (const adresse of ["javascript:alert", "file:///etc/passwd", "data:text/html,x", "//exemple.fr"]) {
    const [p] = rendreMarkdown(fauxDocument(), `Voir [ici](${adresse}).`);
    assert.deepEqual(p.children, ["Voir ", "ici", "."], adresse);
  }
});

test("le HTML d'un document n'est jamais interprété", () => {
  const blocs = rendreMarkdown(fauxDocument(), "<script>alert(1)</script> **<img src=x onerror=y>**\n\n```\n<b>x</b>\n```");
  const tags = elements(blocs).map((e) => e.tagName);
  assert.deepEqual(tags, ["P", "STRONG", "PRE", "CODE"]);
  assert.deepEqual(blocs[0].children[0], "<script>alert(1)</script> ");
  assert.deepEqual(blocs[0].children[1].children, ["<img src=x onerror=y>"]);
  assert.equal(blocs[1].children[0].textContent, "<b>x</b>");
});

test("un document entier, avec des fins de ligne Windows", () => {
  const offre = [
    "# Offre de lancement",
    "",
    "Trois formules pour les premiers clients.",
    "",
    "## Les formules",
    "",
    "- **Diagnostic** : une journée.",
    "- *Mise en place* : quatre semaines.",
    "",
    "| Formule | Prix |",
    "| --- | --- |",
    "| Diagnostic | 900 € |",
    "",
    "> À valider avec Paul Durand.",
  ].join("\r\n");
  const blocs = rendreMarkdown(fauxDocument(), offre);
  assert.deepEqual(
    blocs.map((b) => b.tagName),
    ["H1", "P", "H2", "UL", "TABLE", "BLOCKQUOTE"],
  );
  assert.equal(rendu(blocs[0]), "<h1>Offre de lancement</h1>");
});
````

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `node --test tests/web/markdown.test.mjs`
Expected: FAIL — `ℹ fail 1` : `ERR_MODULE_NOT_FOUND` (`src/atlas_web/markdown.js` n'existe pas encore).

- [ ] **Step 3: Écrire la mise en forme**

Créer `src/atlas_web/markdown.js` :

````javascript
// La mise en forme d'un document dans la page (spec 2c §5 et §7) : la syntaxe permise à
// Claude, et rien d'autre. Tout passe par des éléments et du texte, jamais par du HTML : un
// document ne peut pas injecter de code dans la page.

const TITRE = /^(#{1,3}) (.*)$/;
const PUCE = /^[-*] (.*)$/;
const NUMERO = /^\d+[.)] (.*)$/;
const CITATION = /^> ?(.*)$/;
const LIGNE_DE_TABLEAU = /^\s*(\|.*)$/;
const SEPARATEUR = /^\|?(\s*:?-{3,}:?\s*\|)*\s*:?-{3,}:?\s*\|?\s*$/;
const CLOTURE = /^```/;
const LIEN_PERMIS = /^https?:\/\//i;
const EN_LIGNE = /(`[^`]+`)|(\*\*[^*]+\*\*)|(\*[^*\s](?:[^*]*[^*\s])?\*)|(\[[^\]]+\]\([^)\s]+\))/g;

function element(document, tag, enfants = []) {
  const el = document.createElement(tag);
  el.append(...enfants);
  return el;
}

// Le texte d'une ligne : chaînes et éléments, dans l'ordre.
function enLigne(document, texte) {
  const morceaux = [];
  let dernier = 0;
  for (const trouve of texte.matchAll(EN_LIGNE)) {
    if (trouve.index > dernier) morceaux.push(texte.slice(dernier, trouve.index));
    const [tout, code, gras, italique, lien] = trouve;
    if (code) {
      const el = document.createElement("code");
      el.textContent = code.slice(1, -1);
      morceaux.push(el);
    } else if (gras) {
      morceaux.push(element(document, "strong", enLigne(document, gras.slice(2, -2))));
    } else if (italique) {
      morceaux.push(element(document, "em", enLigne(document, italique.slice(1, -1))));
    } else {
      const [, libelle, adresse] = lien.match(/^\[([^\]]+)\]\(([^)\s]+)\)$/);
      if (LIEN_PERMIS.test(adresse)) {
        const a = element(document, "a", [libelle]);
        a.setAttribute("href", adresse);
        a.setAttribute("target", "_blank");
        a.setAttribute("rel", "noopener noreferrer");
        morceaux.push(a);
      } else {
        morceaux.push(libelle); // un lien qui n'est pas en http(s) reste du texte
      }
    }
    dernier = trouve.index + tout.length;
  }
  if (dernier < texte.length) morceaux.push(texte.slice(dernier));
  return morceaux;
}

function cellules(ligne) {
  return ligne
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cellule) => cellule.trim());
}

function rangee(document, tag, textes) {
  return element(
    document,
    "tr",
    textes.map((texte) => element(document, tag, enLigne(document, texte))),
  );
}

function tableau(document, lignes) {
  const table = document.createElement("table");
  let corps = lignes;
  if (lignes.length > 1 && SEPARATEUR.test(lignes[1].trim())) {
    table.append(element(document, "thead", [rangee(document, "th", cellules(lignes[0]))]));
    corps = lignes.slice(2);
  }
  table.append(element(document, "tbody", corps.map((l) => rangee(document, "td", cellules(l)))));
  return table;
}

function debutDeBloc(ligne) {
  return [TITRE, PUCE, NUMERO, CITATION, LIGNE_DE_TABLEAU, CLOTURE].some((m) => m.test(ligne));
}

// Les blocs du document, prêts à mettre dans la page : `conteneur.replaceChildren(...blocs)`.
export function rendreMarkdown(document, texte) {
  const lignes = texte.replace(/\r\n?/g, "\n").split("\n");
  const blocs = [];
  let i = 0;
  // Les lignes qui suivent le même motif, réduites à ce qu'il capture.
  const suite = (motif) => {
    const prises = [];
    while (i < lignes.length && motif.test(lignes[i])) prises.push(lignes[i++].match(motif)[1]);
    return prises;
  };
  while (i < lignes.length) {
    const ligne = lignes[i];
    if (!ligne.trim()) {
      i += 1;
    } else if (CLOTURE.test(ligne)) {
      i += 1;
      const code = [];
      while (i < lignes.length && !CLOTURE.test(lignes[i])) code.push(lignes[i++]);
      i += 1;
      const el = document.createElement("code");
      el.textContent = code.join("\n");
      blocs.push(element(document, "pre", [el]));
    } else if (TITRE.test(ligne)) {
      const [, dieses, titre] = ligne.match(TITRE);
      blocs.push(element(document, `h${dieses.length}`, enLigne(document, titre.trim())));
      i += 1;
    } else if (PUCE.test(ligne)) {
      const items = suite(PUCE).map((t) => element(document, "li", enLigne(document, t)));
      blocs.push(element(document, "ul", items));
    } else if (NUMERO.test(ligne)) {
      const items = suite(NUMERO).map((t) => element(document, "li", enLigne(document, t)));
      blocs.push(element(document, "ol", items));
    } else if (CITATION.test(ligne)) {
      const paragraphe = element(document, "p", enLigne(document, suite(CITATION).join(" ").trim()));
      blocs.push(element(document, "blockquote", [paragraphe]));
    } else if (LIGNE_DE_TABLEAU.test(ligne)) {
      blocs.push(tableau(document, suite(LIGNE_DE_TABLEAU)));
    } else {
      const morceaux = [];
      while (i < lignes.length && lignes[i].trim() && !debutDeBloc(lignes[i])) {
        morceaux.push(lignes[i++].trim());
      }
      blocs.push(element(document, "p", enLigne(document, morceaux.join(" "))));
    }
  }
  return blocs;
}
````

- [ ] **Step 4: Vérifier que tout passe**

Run: `uv run pytest -q && uv run ruff check . --extend-exclude spikes && uv run ruff format --check . --extend-exclude spikes && node --test "tests/web/*.test.mjs"`
Expected: 955 tests Python passent, 137 tests JavaScript passent, ruff ne dit rien.

- [ ] **Step 5: Commit**

```bash
git add src/atlas_web/markdown.js tests/web/markdown.test.mjs
git commit -F - <<'MSG'
Page : la mise en forme d'un document, sans jamais de HTML

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

### Task 9: Le panneau « Documents » et la barre de confirmation

Dans la page : une icône ouvre le panneau « Documents » (la liste, puis un document mis en forme, une flèche pour
revenir), qui se met à jour quand un document change ; une barre montre la question qui attend, avec « Confirmer »
et « Annuler », puis comment l'attente s'est finie. Les nouveaux styles vont dans `documents.css`. La spec parente
reçoit ses amendements.

**Files:**
- Modify: `docs/superpowers/specs/2026-09-22-atlas-design.md`
- Modify: `src/atlas_web/app.js`
- Create: `src/atlas_web/documents.css`
- Create: `src/atlas_web/documents.js`
- Modify: `src/atlas_web/index.html`
- Modify: `tests/web/app.test.mjs`
- Create: `tests/web/documents.test.mjs`

**Interfaces:**
- Consumes: Task 7 (les messages `liste_documents`, `document`, `documents_changes`, `confirmation`,
  `confirmation_finie` ; `documents`, `lire_document`, `confirmer`) et Task 8 (`rendreMarkdown`).
- Produces: `src/atlas_web/documents.js` : `MEMOIRE_ABSENTE`, `AUCUN_DOCUMENT`,
  `rendreListeDocuments(document, conteneur, message, surChoix)`, `rendreDocument(document, conteneur, message)` ;
  les identifiants `ouvrir-documents`, `panneau-documents`, `retour-documents`, `liste-documents`,
  `lecture-document`, `confirmation`, `texte-confirmation`, `boutons-confirmation`, `confirmer`,
  `annuler-confirmation`.

- [ ] **Step 1: Écrire les tests qui échouent**

Modifier `tests/web/app.test.mjs` :

```diff
--- a/tests/web/app.test.mjs
+++ b/tests/web/app.test.mjs
@@ -8,29 +8,39 @@ import { fauxElement, fauxStockage } from "./faux_dom.mjs";
 
 // Tous les identifiants cherchés par app.js via $("…") (voir tests/web/page.test.mjs).
 const IDENTIFIANTS = [
+  "annuler-confirmation",
+  "boutons-confirmation",
   "champ",
   "champ-cle",
+  "confirmation",
+  "confirmer",
   "formulaire-cle",
   "galerie-fonds",
   "galerie-orbes",
   "hey-atlas",
+  "lecture-document",
   "libelle-etat",
+  "liste-documents",
   "liste-historique",
   "message-cle",
   "message-voix",
   "micro",
   "muet",
+  "ouvrir-documents",
   "ouvrir-historique",
   "ouvrir-parametres",
   "panneau-cle",
+  "panneau-documents",
   "panneau-historique",
   "panneau-parametres",
   "parler",
   "pastille",
+  "retour-documents",
   "saisie",
   "sous-titres",
   "st-question",
   "st-reponse",
+  "texte-confirmation",
 ];
 
 // Un contexte 2D qui lève sur le moindre appel : simule un dessin cassé, quelle qu'en
@@ -272,3 +282,106 @@ test("au retour sur la page, un son resté coupé se rouvre d'un toucher", async
   assert.equal(contexte.state, "running");
   assert.equal($("message-voix").hidden, true, $("message-voix").textContent);
 });
+
+const OFFRE = {
+  chemin: "documents/offre-de-lancement.md",
+  titre: "Offre de lancement",
+  resume: "Trois formules.",
+  modifie: "25 septembre 2026, 21 h 14",
+};
+
+test("le panneau Documents : la liste, un document, le retour, et les changements", async () => {
+  FauxWebSocket.ouvertes = [];
+  await chargerPage({ stockage: fauxStockage({ "atlas.cle": "cle" }), FabriqueWebSocket: FauxWebSocket });
+  const $ = (id) => document.getElementById(id);
+  const [web] = FauxWebSocket.ouvertes;
+  web.ouvrir();
+  web.recevoir({ type: "historique", echanges: [] }); // la page est en ligne
+  for (const id of ["panneau-documents", "panneau-historique", "panneau-parametres"]) $(id).hidden = true;
+
+  $("ouvrir-documents").declencher("click");
+  assert.equal($("panneau-documents").hidden, false);
+  assert.deepEqual(web.envoyes.at(-1), { type: "documents" });
+  web.recevoir({ type: "liste_documents", disponible: true, documents: [OFFRE] });
+  const [liste] = $("liste-documents").children;
+  liste.children[0].children[0].declencher("click");
+  assert.deepEqual(web.envoyes.at(-1), { type: "lire_document", chemin: OFFRE.chemin });
+
+  web.recevoir({ type: "document", chemin: OFFRE.chemin, titre: "Offre", contenu: "# Offre\n\nTexte.\n", erreur: null });
+  assert.equal($("lecture-document").hidden, false);
+  assert.equal($("liste-documents").hidden, true);
+  assert.equal($("retour-documents").hidden, false);
+  assert.deepEqual(
+    $("lecture-document").children.map((bloc) => bloc.tagName),
+    ["H1", "P"],
+  );
+  web.recevoir({ type: "liste_documents", disponible: true, documents: [] }); // une vieille liste
+  web.recevoir({ type: "document", chemin: "documents/autre.md", titre: "Autre", contenu: "Autre.", erreur: null });
+  assert.equal($("liste-documents").hidden, true);
+  assert.equal($("liste-documents").children[0], liste, "la liste en attente reste celle d'avant");
+  assert.deepEqual(
+    $("lecture-document").children.map((bloc) => bloc.tagName),
+    ["H1", "P"],
+    "le document d'un autre chemin ne remplace pas celui qu'on lit",
+  );
+  web.recevoir({ type: "documents_changes" });
+  assert.deepEqual(web.envoyes.at(-1), { type: "lire_document", chemin: OFFRE.chemin });
+
+  $("retour-documents").declencher("click");
+  assert.equal($("lecture-document").hidden, true);
+  assert.equal($("liste-documents").hidden, false);
+  assert.equal($("retour-documents").hidden, true);
+  assert.deepEqual(web.envoyes.at(-1), { type: "documents" });
+  web.recevoir({ type: "documents_changes" });
+  assert.deepEqual(web.envoyes.at(-1), { type: "documents" });
+
+  $("ouvrir-documents").declencher("click"); // le même bouton ferme
+  assert.equal($("panneau-documents").hidden, true);
+  const envoyes = web.envoyes.length;
+  web.recevoir({ type: "documents_changes" });
+  web.recevoir({ type: "document", chemin: OFFRE.chemin, titre: "Offre", contenu: "# Offre\n", erreur: null });
+  assert.equal(web.envoyes.length, envoyes, "panneau fermé : rien n'est redemandé");
+});
+
+test("la barre de confirmation : la question, les boutons, puis la fin", async (t) => {
+  t.mock.timers.enable({ apis: ["setTimeout"] });
+  FauxWebSocket.ouvertes = [];
+  await chargerPage({ stockage: fauxStockage({ "atlas.cle": "cle" }), FabriqueWebSocket: FauxWebSocket });
+  const $ = (id) => document.getElementById(id);
+  const [web] = FauxWebSocket.ouvertes;
+  web.ouvrir();
+
+  web.recevoir({ type: "confirmation", texte: "Je supprime le document Offre. Tu confirmes ?" });
+  assert.equal($("confirmation").hidden, false);
+  assert.equal($("boutons-confirmation").hidden, false);
+  assert.equal($("texte-confirmation").textContent, "Je supprime le document Offre. Tu confirmes ?");
+  $("confirmer").declencher("click");
+  $("annuler-confirmation").declencher("click");
+  assert.deepEqual(web.envoyes.slice(-2), [
+    { type: "confirmer", oui: true },
+    { type: "confirmer", oui: false },
+  ]);
+
+  web.recevoir({ type: "confirmation_finie", texte: "Rien n'a été supprimé." });
+  assert.equal($("boutons-confirmation").hidden, true);
+  assert.equal($("texte-confirmation").textContent, "Rien n'a été supprimé.");
+  t.mock.timers.tick(3999);
+  assert.equal($("confirmation").hidden, false);
+  web.recevoir({ type: "confirmation", texte: "Je supprime ton profil. Tu confirmes ?" });
+  t.mock.timers.tick(10);
+  assert.equal($("confirmation").hidden, false, "la nouvelle question reste affichée");
+  web.recevoir({ type: "confirmation_finie", texte: "Supprimé : ton profil." });
+  t.mock.timers.tick(4000);
+  assert.equal($("confirmation").hidden, true);
+});
+
+test("une page qui se reconnecte oublie une question qui n'attend plus", async () => {
+  FauxWebSocket.ouvertes = [];
+  await chargerPage({ stockage: fauxStockage({ "atlas.cle": "cle" }), FabriqueWebSocket: FauxWebSocket });
+  const $ = (id) => document.getElementById(id);
+  const [web] = FauxWebSocket.ouvertes;
+  web.ouvrir();
+  web.recevoir({ type: "confirmation", texte: "Je supprime ton profil. Tu confirmes ?" });
+  web.recevoir({ type: "historique", echanges: [] }); // ce que le Core envoie à chaque connexion
+  assert.equal($("confirmation").hidden, true);
+});
```

Créer `tests/web/documents.test.mjs` :

```javascript
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  AUCUN_DOCUMENT,
  MEMOIRE_ABSENTE,
  rendreDocument,
  rendreListeDocuments,
} from "../../src/atlas_web/documents.js";
import { fauxDocument } from "./faux_dom.mjs";

const OFFRE = {
  chemin: "documents/offre-de-lancement.md",
  titre: "Offre de lancement",
  resume: "Trois formules.",
  modifie: "25 septembre 2026, 21 h 14",
};
const NOTES = { chemin: "documents/notes.md", titre: "Notes", resume: "", modifie: "24 septembre 2026, 9 h 05" };

function textes(element) {
  return element.children.map((enfant) => [enfant.className, enfant.textContent]);
}

test("la liste montre chaque document, et un toucher l'ouvre", () => {
  const document = fauxDocument();
  const conteneur = document.createElement("div");
  const choisis = [];
  rendreListeDocuments(document, conteneur, { disponible: true, documents: [OFFRE, NOTES] }, (chemin) =>
    choisis.push(chemin),
  );
  const [liste] = conteneur.children;
  assert.equal(liste.tagName, "OL");
  const [premier, second] = liste.children.map((li) => li.children[0]);
  assert.equal(premier.tagName, "BUTTON");
  assert.deepEqual(textes(premier), [
    ["titre", "Offre de lancement"],
    ["resume", "Trois formules."],
    ["date", "25 septembre 2026, 21 h 14"],
  ]);
  assert.deepEqual(textes(second), [
    ["titre", "Notes"],
    ["date", "24 septembre 2026, 9 h 05"],
  ]);
  second.declencher("click");
  assert.deepEqual(choisis, ["documents/notes.md"]);
});

test("sans document, ou sans mémoire, la liste le dit", () => {
  const document = fauxDocument();
  const conteneur = document.createElement("div");
  rendreListeDocuments(document, conteneur, { disponible: true, documents: [] }, () => {});
  assert.deepEqual(textes(conteneur), [["vide", AUCUN_DOCUMENT]]);
  rendreListeDocuments(document, conteneur, { disponible: false, documents: [] }, () => {});
  assert.deepEqual(textes(conteneur), [["vide", MEMOIRE_ABSENTE]]);
  assert.equal(MEMOIRE_ABSENTE, "La mémoire n'est pas disponible.");
});

test("un document se met en forme, ou dit son erreur", () => {
  const document = fauxDocument();
  const conteneur = document.createElement("article");
  rendreDocument(document, conteneur, { chemin: OFFRE.chemin, contenu: "# Offre\n\nTrois formules.\n", erreur: null });
  assert.deepEqual(
    conteneur.children.map((bloc) => bloc.tagName),
    ["H1", "P"],
  );
  rendreDocument(document, conteneur, { chemin: OFFRE.chemin, contenu: "", erreur: "documents/offre.md n'existe pas." });
  assert.deepEqual(textes(conteneur), [["erreur", "documents/offre.md n'existe pas."]]);
});
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `node --test tests/web/documents.test.mjs tests/web/app.test.mjs`
Expected: FAIL — `ℹ fail 4` : `documents.test.mjs` ne se charge pas (`ERR_MODULE_NOT_FOUND`), et les trois nouveaux
tests de `app.test.mjs` (panneau, barre de confirmation, reconnexion).

- [ ] **Step 3: Écrire le panneau, la barre et les amendements**

Modifier `docs/superpowers/specs/2026-09-22-atlas-design.md` :

```diff
--- a/docs/superpowers/specs/2026-09-22-atlas-design.md
+++ b/docs/superpowers/specs/2026-09-22-atlas-design.md
@@ -367,6 +367,10 @@ sommaire des fiches et cherche dans le texte ; l'index viendra quand la mémoire
 grossi. Le journal s'écrit sans annonce, à la fin de chaque conversation : c'est la seule
 exception à la règle d'écriture. Voir `2026-09-25-phase-2b-memoire-design.md`.
 
+**Amendé le 25/09/2026 (phase 2c).** Le dossier `documents/` reçoit les documents produits
+par la réflexion vocale, écrits à la demande de David ; ils se lisent dans un panneau de la
+page. Voir `2026-09-25-phase-2c-outils-design.md`.
+
 ---
 
 ## 9. Outils
@@ -390,6 +394,9 @@ utilisables depuis d'autres clients MCP.
 **Amendé le 25/09/2026 (phase 2b).** Le serveur MCP d'Atlas (« atlas ») tourne dans le Core
 lui-même, par le SDK de Claude, et non en stdio. Ses quatre premiers outils sont ceux de la
 mémoire ; la phase 2c y ajoute les autres et les niveaux d'autorisation.
+**Amendé le 25/09/2026 (phase 2c).** Une liste explicite d'outils par famille (mémoire,
+documents), chacun avec son niveau déclaré ; la découverte automatique « un fichier par
+outil » attendra que les outils soient plus nombreux.
 
 Familles d'outils en v1 : n8n, mémoire et documents, veille. Home Assistant et agenda/mail
 viennent après la v1.
@@ -411,6 +418,12 @@ La reformulation N3 porte sur l'action résolue, pas sur la demande : « envoyer
 Paul Durand, objet Proposition commerciale » et non « envoyer le mail dont on parlait ».
 C'est ce qui permet à David d'attraper une erreur de compréhension avant qu'elle ne coûte.
 
+**Amendé le 25/09/2026 (phase 2c).** La question N3 est formulée par le Core à partir de
+l'action résolue, jamais par Claude ; la réponse vient de la voix, du clavier ou d'un bouton
+de la page, et elle est lue par le Core avant Claude ; trente secondes sans réponse valent
+non. La première action N3 est la suppression d'une fiche ou d'un document. Voir
+`2026-09-25-phase-2c-outils-design.md`.
+
 ---
 
 ## 11. Supervision n8n
@@ -519,6 +532,8 @@ son plan et sa fusion : 2a, le cerveau branché (`2026-09-24-phase-2a-cerveau-de
 **Amendé le 25/09/2026.** Une étape « la voix dans le navigateur »
 (`2026-09-25-voix-navigateur-design.md`) s'insère entre 2a et 2b : la page de l'iPhone ou
 de l'iPad écoute et répond à voix haute, pas seulement le M5.
+**Amendé le 25/09/2026 (phase 2c).** La phase 2c est décrite par
+`2026-09-25-phase-2c-outils-design.md` : les documents et les niveaux d'autorisation.
 
 **Phase 3 — Les outils.** Registre d'outils, routeur d'intention, Ollama, supervision n8n,
 point quotidien, déclenchement vocal, diagnostic.
```

Modifier `src/atlas_web/app.js` :

```diff
--- a/src/atlas_web/app.js
+++ b/src/atlas_web/app.js
@@ -2,6 +2,7 @@
 
 import { Connexion, identifiantDePage } from "./connexion.js";
 import { dimensionner, rgba } from "./dessin.js";
+import { rendreDocument, rendreListeDocuments } from "./documents.js";
 import { LIBELLES, appliquerMessage, avancer, creerEtat, sceneDe } from "./etat.js";
 import { fonds } from "./fonds/index.js";
 import { rendreHistorique } from "./historique.js";
@@ -16,6 +17,9 @@ const CLE_STOCKAGE = "atlas.cle";
 const CLE_HEY_ATLAS = "atlas.hey_atlas";
 const SEUIL_GLISSEMENT_PX = 60;
 const TOUCHENT_HISTORIQUE = new Set(["question", "reponse", "erreur", "latences", "historique"]);
+const TOUCHENT_DOCUMENTS = new Set(["liste_documents", "document", "documents_changes"]);
+// La fin d'une attente de confirmation reste affichée ce temps-là, puis la barre s'efface.
+const DUREE_FIN_CONFIRMATION_MS = 4000;
 const STATUTS = {
   connexion: "Connexion…",
   hors_ligne: "Hors ligne — nouvelle tentative…",
@@ -69,6 +73,13 @@ const connexion = new Connexion({
     if (TOUCHENT_HISTORIQUE.has(message.type) && !$("panneau-historique").hidden) {
       rendreHistorique(document, $("liste-historique"), etat.historique);
     }
+    if (TOUCHENT_DOCUMENTS.has(message.type)) surDocuments(message);
+    if (message.type === "confirmation" || message.type === "confirmation_finie") {
+      afficherConfirmation(message);
+    }
+    // Une connexion (re)commence toujours par l'historique : une question affichée avant
+    // n'attend peut-être plus ; si elle attend, le Core la renvoie juste après.
+    if (message.type === "historique") $("confirmation").hidden = true;
   },
   surStatut(nouveau) {
     statut = nouveau;
@@ -150,6 +161,63 @@ $("muet").addEventListener("change", () => {
   if (!connexion.envoyer({ type: "muet", actif: $("muet").checked })) $("muet").checked = etat.muet;
 });
 
+// --- La confirmation d'une action (N3) --------------------------------------------
+
+let jetonConfirmation = 0; // la fin d'une attente n'efface pas la question suivante
+
+function afficherConfirmation(message) {
+  const jeton = ++jetonConfirmation;
+  $("texte-confirmation").textContent = message.texte;
+  $("boutons-confirmation").hidden = message.type !== "confirmation";
+  $("confirmation").hidden = false;
+  if (message.type === "confirmation_finie") {
+    setTimeout(() => {
+      if (jeton === jetonConfirmation) $("confirmation").hidden = true;
+    }, DUREE_FIN_CONFIRMATION_MS);
+  }
+}
+
+// Comme taper « oui » ou « non » depuis cette page.
+$("confirmer").addEventListener("click", () => connexion.envoyer({ type: "confirmer", oui: true }));
+$("annuler-confirmation").addEventListener("click", () =>
+  connexion.envoyer({ type: "confirmer", oui: false }),
+);
+
+// --- Les documents ----------------------------------------------------------------
+
+let documentOuvert = null; // le chemin du document lu ; null : la liste
+
+function montrerLaListe() {
+  documentOuvert = null;
+  $("lecture-document").hidden = true;
+  $("liste-documents").hidden = false;
+  $("retour-documents").hidden = true;
+  connexion.envoyer({ type: "documents" });
+}
+
+function lireDocument(chemin) {
+  documentOuvert = chemin;
+  connexion.envoyer({ type: "lire_document", chemin });
+}
+
+function surDocuments(message) {
+  if ($("panneau-documents").hidden) return;
+  if (message.type === "documents_changes") {
+    if (documentOuvert === null) connexion.envoyer({ type: "documents" });
+    else lireDocument(documentOuvert);
+  } else if (message.type === "liste_documents") {
+    if (documentOuvert === null) rendreListeDocuments(document, $("liste-documents"), message, lireDocument);
+  } else if (message.chemin === documentOuvert) {
+    rendreDocument(document, $("lecture-document"), message);
+    $("liste-documents").hidden = true;
+    $("lecture-document").hidden = false;
+    $("retour-documents").hidden = false;
+    $("panneau-documents").scrollTop = 0;
+  }
+}
+
+$("retour-documents").addEventListener("click", montrerLaListe);
+
 // --- Les panneaux -----------------------------------------------------------------
 
 function ouvrirParametres() {
@@ -181,6 +249,7 @@ function ouvrirPanneau(panneau) {
   panneau.hidden = false;
   panneau.scrollTop = 0;
   if (panneau === $("panneau-historique")) rendreHistorique(document, $("liste-historique"), etat.historique);
+  else if (panneau === $("panneau-documents")) montrerLaListe();
   else ouvrirParametres();
 }
 
@@ -189,9 +258,11 @@ function fermerPanneaux() {
   galeries = [];
   $("panneau-historique").hidden = true;
   $("panneau-parametres").hidden = true;
+  $("panneau-documents").hidden = true;
 }
 
 $("ouvrir-historique").addEventListener("click", () => ouvrirPanneau($("panneau-historique")));
+$("ouvrir-documents").addEventListener("click", () => ouvrirPanneau($("panneau-documents")));
 $("ouvrir-parametres").addEventListener("click", () => ouvrirPanneau($("panneau-parametres")));
 for (const bouton of document.querySelectorAll(".panneau .fermer")) {
   bouton.addEventListener("click", fermerPanneaux);
```

Créer `src/atlas_web/documents.css` :

```css
/* Le panneau « Documents » et la confirmation d'une action (N3) : spec 2c §7. */

/* Les documents : la liste, puis la lecture d'un document mis en forme. */
.panneau > header #retour-documents {
  margin-right: 8px;
}

.panneau > header h2 {
  flex: 1;
}

#liste-documents .documents {
  list-style: none;
  margin: 0;
  padding: 0;
}

#liste-documents .document {
  display: block;
  width: 100%;
  padding: 12px 0;
  border-top: 1px solid var(--bord);
  text-align: left;
}

#liste-documents p {
  margin: 2px 0;
}

#liste-documents .titre {
  font-weight: 600;
}

#liste-documents .resume,
#liste-documents .vide {
  color: var(--texte-doux);
}

#liste-documents .date {
  font-size: 12px;
  color: var(--texte-doux);
}

#lecture-document {
  padding-bottom: 12px;
  line-height: 1.55;
}

#lecture-document h1,
#lecture-document h2,
#lecture-document h3 {
  margin: 20px 0 8px;
  font-weight: 600;
  letter-spacing: normal;
  text-transform: none;
  color: var(--texte);
}

#lecture-document h1 {
  font-size: 22px;
}

#lecture-document h2 {
  font-size: 18px;
}

#lecture-document h3 {
  font-size: 16px;
}

#lecture-document blockquote {
  margin: 12px 0;
  padding-left: 12px;
  border-left: 3px solid var(--accent);
  color: var(--texte-doux);
}

#lecture-document code {
  padding: 1px 5px;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.08);
  font-size: 0.92em;
}

#lecture-document pre {
  overflow-x: auto;
  padding: 10px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.06);
}

#lecture-document pre code {
  padding: 0;
  background: none;
}

#lecture-document table {
  display: block;
  overflow-x: auto;
  border-collapse: collapse;
  margin: 12px 0;
}

#lecture-document th,
#lecture-document td {
  padding: 6px 10px;
  border: 1px solid var(--bord);
  text-align: left;
}

#lecture-document a {
  color: var(--accent);
}

#lecture-document .erreur {
  color: var(--erreur);
}

/* La confirmation d'une action (N3) : la question et ses deux boutons, au-dessus de la saisie. */
#confirmation {
  position: fixed;
  left: 50%;
  bottom: calc(max(20px, env(safe-area-inset-bottom)) + 64px);
  width: min(760px, calc(100vw - 32px));
  transform: translateX(-50%);
  padding: 12px 16px;
  border-radius: 16px;
  border: 1px solid rgba(251, 191, 36, 0.5);
  background: var(--verre-fort);
  text-align: center;
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}

#texte-confirmation {
  margin: 0;
}

#boutons-confirmation {
  display: flex;
  justify-content: center;
  gap: 12px;
  margin-top: 10px;
}

#boutons-confirmation button {
  padding: 8px 20px;
  border-radius: 20px;
  border: 1px solid var(--bord);
}

#boutons-confirmation #confirmer {
  background: var(--accent);
  border-color: var(--accent);
  color: #02030a;
}

#boutons-confirmation button:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
```

Créer `src/atlas_web/documents.js` :

```javascript
// Le panneau « Documents » : la liste des documents d'Atlas, puis l'un d'eux mis en forme
// (spec 2c §7). Texte brut, et la mise en forme de markdown.js : jamais de HTML.

import { rendreMarkdown } from "./markdown.js";

export const MEMOIRE_ABSENTE = "La mémoire n'est pas disponible.";
export const AUCUN_DOCUMENT = "Pas encore de document : demande à Atlas d'en faire un.";

function paragraphe(document, classe, texte) {
  const p = document.createElement("p");
  p.className = classe;
  p.textContent = texte;
  return p;
}

// La liste (message `liste_documents`) : un bouton par document ; `surChoix(chemin)` l'ouvre.
export function rendreListeDocuments(document, conteneur, message, surChoix) {
  if (!message.disponible) {
    conteneur.replaceChildren(paragraphe(document, "vide", MEMOIRE_ABSENTE));
    return;
  }
  if (message.documents.length === 0) {
    conteneur.replaceChildren(paragraphe(document, "vide", AUCUN_DOCUMENT));
    return;
  }
  const liste = document.createElement("ol");
  liste.className = "documents";
  liste.append(
    ...message.documents.map((doc) => {
      const bouton = document.createElement("button");
      bouton.type = "button";
      bouton.className = "document";
      bouton.append(paragraphe(document, "titre", doc.titre));
      if (doc.resume) bouton.append(paragraphe(document, "resume", doc.resume));
      bouton.append(paragraphe(document, "date", doc.modifie));
      bouton.addEventListener("click", () => surChoix(doc.chemin));
      const element = document.createElement("li");
      element.append(bouton);
      return element;
    }),
  );
  conteneur.replaceChildren(liste);
}

// Un document (message `document`) : sa mise en forme, ou l'erreur que le Core a rendue.
export function rendreDocument(document, conteneur, message) {
  if (message.erreur) {
    conteneur.replaceChildren(paragraphe(document, "erreur", message.erreur));
    return;
  }
  conteneur.replaceChildren(...rendreMarkdown(document, message.contenu));
}
```

Modifier `src/atlas_web/index.html` :

```diff
--- a/src/atlas_web/index.html
+++ b/src/atlas_web/index.html
@@ -7,6 +7,7 @@
   <title>Atlas</title>
   <link rel="icon" href="data:,">
   <link rel="stylesheet" href="style.css">
+  <link rel="stylesheet" href="documents.css">
   <script type="module" src="app.js"></script>
 </head>
 <body>
@@ -27,6 +28,11 @@
         <path fill="currentColor" d="M12 14a3 3 0 0 0 3-3V5a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3Zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-3.08A7 7 0 0 0 19 11h-2Z"/>
       </svg>
     </button>
+    <button type="button" class="icone" id="ouvrir-documents" aria-label="Documents">
+      <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
+        <path fill="currentColor" d="M6 2h8l6 6v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2Zm7 1.5V9h5.5L13 3.5ZM8 13v2h8v-2H8Zm0 4v2h8v-2H8Z"/>
+      </svg>
+    </button>
     <button type="button" class="icone" id="ouvrir-historique" aria-label="Historique">☰</button>
     <button type="button" class="icone" id="ouvrir-parametres" aria-label="Paramètres">⚙</button>
   </header>
@@ -39,6 +45,14 @@
     <p id="st-reponse"></p>
   </section>
 
+  <section id="confirmation" role="alertdialog" aria-live="assertive" aria-label="Confirmation" hidden>
+    <p id="texte-confirmation"></p>
+    <div id="boutons-confirmation">
+      <button type="button" id="confirmer">Confirmer</button>
+      <button type="button" id="annuler-confirmation">Annuler</button>
+    </div>
+  </section>
+
   <form id="saisie" autocomplete="off">
     <input id="champ" type="text" maxlength="1000" enterkeyhint="send"
            placeholder="Écrire à Atlas…" aria-label="Question pour Atlas">
@@ -52,6 +66,16 @@
     <ol id="liste-historique"></ol>
   </section>
 
+  <section id="panneau-documents" class="panneau" aria-label="Documents" hidden>
+    <header>
+      <button type="button" class="icone" id="retour-documents" aria-label="Retour à la liste" hidden>←</button>
+      <h2>Documents</h2>
+      <button type="button" class="icone fermer" aria-label="Fermer">✕</button>
+    </header>
+    <div id="liste-documents"></div>
+    <article id="lecture-document" hidden></article>
+  </section>
+
   <section id="panneau-parametres" class="panneau" aria-label="Paramètres" hidden>
     <header>
       <h2>Paramètres</h2>
```

- [ ] **Step 4: Vérifier que tout passe**

Run: `uv run pytest -q && uv run ruff check . --extend-exclude spikes && uv run ruff format --check . --extend-exclude spikes && node --test "tests/web/*.test.mjs"`
Expected: 955 tests Python passent, 143 tests JavaScript passent, ruff ne dit rien.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/specs/2026-09-22-atlas-design.md src/atlas_web/app.js src/atlas_web/documents.css src/atlas_web/documents.js src/atlas_web/index.html tests/web/app.test.mjs tests/web/documents.test.mjs
git commit -F - <<'MSG'
Page : le panneau « Documents » et la barre de confirmation ; spec parente

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

## L'essai avec David, sur le M5

Après la Task 9, sur la branche `phase-2c-outils`, avant la PR. C'est David qui lance tout : l'essai consomme un peu
de son abonnement Claude. Les critères sont ceux du §1 de la spec.

1. **Préparer** : `make run-core`, et la page ouverte sur le Mac et sur l'iPhone.
2. **Réflexion vers document** : quelques minutes de réflexion à voix haute sur un sujet de l'entreprise, puis
   « Fais-en un document. » — « J'ai écrit le document …, il est dans la page. » ; le panneau « Documents » le montre,
   et il se relit sans retouche.
3. **Retouche** : « Ajoute une partie sur les prix. » — « J'ai mis à jour le document … » ; puis « Annule. » — « Le
   document … revient à sa version précédente. »
4. **Suppression confirmée** : « Supprime ce document. » — « Je supprime le document …. Tu confirmes ? », et la barre
   apparaît sur les deux pages ; « Oui. » — « C'est fait … » ; puis « Annule. » — « J'ai remis le document … ».
5. **Pas de oui, pas d'action** : redemander la suppression, et répondre « Non. » ; puis ne rien dire trente
   secondes ; puis répondre autre chose (« Lis-le-moi d'abord. ») — le document est toujours là.
6. **Le bouton** : redemander la suppression, et toucher « Confirmer » sur l'iPhone.
7. **Les niveaux** : « Qu'est-ce que tu sais de Paul Durand ? » (une lecture) ne s'annonce pas ; une note s'annonce.
8. `make test` au vert.

Ce qui ne va pas devient une correction sur la branche, avec son test, avant la PR.

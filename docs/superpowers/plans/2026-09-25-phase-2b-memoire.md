# Phase 2b : la mémoire — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Atlas se souvient : un journal de chaque conversation, relu au début des suivantes, et des fiches (profil de David, entreprise, projets, personnes) qu'il tient de lui-même en l'annonçant, dans un dépôt git local jamais poussé.

**Architecture:** `memoire.py` est le dépôt : lire, chercher, écrire une fiche (chemin, format et secrets vérifiés, puis commit sous l'auteur « Atlas »), annuler, le sommaire, l'amorçage et le journal. `outils_memoire.py` sert à Claude quatre outils par un serveur MCP qui tourne dans le Core (le SDK de Claude) et garde les annonces à faire (`Note`). Le cerveau amorce chaque nouvelle conversation avec ce qu'Atlas sait, rend les annonces à leur place dans la réponse, et, passé le délai d'oubli, fait résumer la conversation au journal avant de la fermer ; la session dit les annonces.

**Tech Stack:** Python 3.12+ (venv en 3.13), `claude-agent-sdk` 0.2.159 (`tool`, `create_sdk_mcp_server`), git en ligne de commande (`subprocess`), pydantic v2, FastAPI, pytest (asyncio auto).

**Spec:** `docs/superpowers/specs/2026-09-25-phase-2b-memoire-design.md` (à lire avec ce plan : elle fait foi en cas de doute).

## Global Constraints

- Code, identifiants, messages et commentaires en français, comme le reste du dépôt ; lignes de 100 caractères au plus (ruff).
- Aucune nouvelle dépendance Python ni JavaScript. La mémoire utilise le `git` de la machine, en ligne de commande.
- La mémoire n'est jamais poussée : aucun distant, jamais `git push`. Toute commande git passe par `_git` : l'auteur « Atlas » (`atlas@atlas.local`) imposé par l'environnement du processus git, signature et crochets git de la machine désactivés.
- Chemins écrits par Claude : `profil.md`, ou `entreprise/`, `projets/`, `personnes/` suivi d'un nom `[a-z0-9]+(-[a-z0-9]+)*` de 60 caractères au plus, en `.md`. La lecture accepte aussi `journal/AAAA-MM-JJ.md`. Tout chemin résolu doit rester sous le dossier de la mémoire.
- Une fiche : « # Titre » (100 caractères au plus), une ligne vide, une phrase de résumé (200 au plus), 20 000 caractères au plus en tout.
- Amorçage : le profil (4 000 caractères au plus), le sommaire (150 lignes au plus), le journal des sept derniers jours (6 000 caractères au plus, les plus récents d'abord), entre « [Mémoire d'Atlas] » et « [Fin de la mémoire] ».
- Fin d'une conversation : à `ATLAS_CERVEAU_OUBLI_MIN` minutes (30) après le dernier échange ; le résumé a 60 s à l'échéance, 20 s à l'arrêt du Core ; « RIEN » ne s'écrit pas.
- Les annonces, mot pour mot : « Je le note dans ton profil. », « Je le note dans la fiche <titre>. », « J'ai retiré ma dernière note. ».
- Le serveur d'outils s'appelle `atlas` ; ses outils, pour Claude : `mcp__atlas__memoire_lire`, `mcp__atlas__memoire_chercher`, `mcp__atlas__memoire_ecrire`, `mcp__atlas__memoire_annuler`. Claude garde en plus `WebSearch`, et rien d'autre.
- Réglage : `ATLAS_MEMOIRE_DOSSIER`, `~/.atlas/memoire` par défaut. Les tests ne touchent jamais la vraie mémoire (`tests/conftest.py`), et n'appellent jamais le vrai Claude.
- Ne jamais lancer ce qui ouvre un micro ni ce qui appelle le vrai Claude (l'essai final consomme l'abonnement de David) : c'est David qui le fait.
- Dépôt public : aucune adresse IP, aucun domaine, nom ou courriel privé, aucun jeton dans ce qui est commité ; la mémoire de David n'y entre jamais.
- Git : ajouter les fichiers par leur chemin, jamais `git add -A` (le dossier `spikes/` n'est pas suivi et reste privé). Messages de commit en français, terminés par la ligne `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Avant chaque commit : `uv run pytest -q`, `uv run ruff check . --extend-exclude spikes`, `uv run ruff format --check . --extend-exclude spikes`, `node --test "tests/web/*.test.mjs"` (le dossier privé `spikes/` n'est pas du code du dépôt). Si `ruff format --check` échoue, lancer `uv run ruff format <fichiers>` : la mise en forme fait foi.
- Fichiers de moins de 500 lignes : `cerveau_claude.py` finit à 457, `memoire.py` vers 350 ; `session.py` passe de 552 à 558 (elle dépassait déjà, découpage au backlog).
- **Copier le code programmatiquement.** Les fichiers neufs sont donnés en entier, les autres par des diffs unifiés exacts (`git apply` les accepte tels quels, copiés d'un bloc) : ne rien retaper à la main.
- Le code de ce plan a été vérifié tel quel avant d'être écrit ici : appliquées dans l'ordre, les 9 tâches donnent 799 tests Python et 126 tests JavaScript qui passent, un lint propre, et chaque tâche laisse la suite entière au vert. Les tests ont en outre été mis à l'épreuve par mutations : chaque comportement clé, retiré du code, fait échouer au moins un test. Un écart entre le plan et ce que vous observez est donc à signaler, pas à contourner.

## Review Focus

Les cinq situations que la spec implique sans les décrire, les plus susceptibles de surprendre David ; chacune a son test dans la tâche qui en porte le code.

1. **Une fiche retouchée à la main dans un autre encodage** (un éditeur qui enregistre en Latin-1) : Atlas la lit quand même, octets illisibles remplacés par « � », sans perdre l'amorçage, le sommaire ni la recherche. Task 1 : `test_une_fiche_retouchee_dans_un_autre_encodage_se_lit_quand_meme` ; Task 2 : `test_chercher_passe_une_fiche_retouchee_dans_un_autre_encodage` ; Task 3 : `test_une_fiche_dans_un_autre_encodage_ne_fait_pas_tomber_l_amorcage`.
2. **La configuration git de la machine** : des crochets globaux (vérifications avant commit, message imposé) ne bloquent pas les notes, et une identité imposée par l'environnement (`GIT_AUTHOR_NAME`…) ne les signe pas à la place d'Atlas, ce qui empêcherait « annule » de les retrouver. Task 1 : `test_les_crochets_git_de_la_machine_ne_bloquent_pas_les_notes`, `test_une_identite_git_imposee_par_l_environnement_ne_signe_pas_les_notes`.
3. **Un Core tué en plein commit** laisse `.git/index.lock` : au redémarrage, le verrou est retiré et les notes s'écrivent de nouveau. Task 1 : `test_un_verrou_laisse_par_un_arret_brutal_est_retire_au_demarrage`.
4. **Le dossier de la mémoire supprimé pendant que le Core tourne** (David repart de zéro) : la note suivante recrée le dépôt, le journal aussi. Task 1 : `test_un_depot_supprime_pendant_que_le_core_tourne_renait` ; Task 3 : `test_un_depot_supprime_renait_aussi_pour_le_journal`.
5. **« Oublie ça »** : le résumé du journal ne garde pas ce que David a demandé d'oublier ou de ne pas noter. Task 5 : `test_la_demande_de_resume_ne_fait_rien_ecrire_et_admet_rien`.

## Décisions prises en écrivant le plan

La spec fait foi ; voici ce qu'elle laissait ouvert et ce que le plan en a fait.

1. **Un seul module pour le dépôt** (`memoire.py`, vers 350 lignes) : lire, écrire, chercher, annuler, le sommaire, l'amorçage, le journal. git s'appelle en ligne de commande : signature et crochets de la machine désactivés à chaque appel (`-c commit.gpgsign=false`, `-c core.hooksPath=/dev/null`), et l'auteur « Atlas » imposé par l'environnement du processus (`GIT_AUTHOR_*`, `GIT_COMMITTER_*`), qui passe avant toute configuration. Le rejeu du plan l'a montré : une identité dans l'environnement l'emportait sur `-c user.name`.
2. **Seul le fichier écrit est commité** (`git commit -- chemin`) : les retouches de David, même préparées pour son propre commit, restent les siennes.
3. **Une fiche inchangée** ne fait ni commit ni annonce.
4. **Annuler** relit l'historique : la dernière note d'Atlas (son courriel, et un message « Atlas : … ») qui n'a pas encore été annulée (un commit « Annulé : … » porte « Annule <sha> » dans son corps). `git revert --no-commit`, puis un commit des seuls fichiers touchés ; un échec rend la main (`git revert --abort`) avec un message clair.
5. **Le sommaire exclut le profil**, donné en entier ; une fiche hors format (retouchée à la main) se résume par son titre.
6. **Le journal** : « # Journal du … » à la première écriture du jour, puis une section « ## début – fin » par conversation, dans le fichier du jour de sa fin ; commit « Journal : <date>, <heure> » ; un résumé qui contient un secret n'est pas écrit.
7. **`date_en_lettres` et `heure_en_chiffres`** vivent dans `consignes.py`, et la ligne de date s'en sert.
8. **Les outils** sont des fonctions `tool()` du SDK, servies par `create_sdk_mcp_server("atlas")`. Un refus de la mémoire revient à Claude en erreur lisible ; une autre panne aussi, notée au journal du Core. Les annonces attendent dans `OutilsMemoire`, et le cerveau les rend après chaque message du SDK (`prendre_les_annonces`).
9. **Les consignes sans mémoire restent celles de la 2a, mot pour mot** ; `CONSIGNES_AVEC_MEMOIRE` y ajoute la mémoire et change la phrase des capacités. `DEMANDE_RESUME` et `RIEN` font le résumé.
10. **L'amorçage** part avec la première question envoyée à un client qui ne l'a pas encore reçu, y compris un Claude relancé en pleine conversation ; un amorçage impossible est noté au journal du Core, et la question part sans lui.
11. **Une annonce n'est jamais perdue** : retenue quand la réponse est coupée (une autre question) ou pendant le résumé, elle est dite au début de la réponse suivante.
12. **La fin d'une conversation** :
    - après chaque échange, avec la mémoire et une conversation ouverte, une tâche attend le délai d'oubli (`attendre`, injectable pour les tests) ; elle prend ensuite le verrou, attend le ménage d'une réponse abandonnée, puis résume et ferme ;
    - une question annule l'échéance qui attend encore ; celle qui arrive pendant le résumé l'attend, sans l'interrompre ;
    - une question qui constate l'oubli sans que l'échéance ait sonné résume aussi ;
    - `fermer()` attend un résumé en cours, sinon en fait un (20 s) si le verrou est libre ;
    - une conversation qui se ferme efface « j'ai perdu le fil » et ses heures.
13. **La session** dit une `Note` à sa place, après ce qui la précède (le découpeur est vidé d'abord).
14. **Le Core ouvre la mémoire** en créant le cerveau Claude (pas le bouchon), avec pour secrets `ATLAS_WEB_CLE`, `ATLAS_AUDIO_CLE` et `CLAUDE_CODE_OAUTH_TOKEN` (8 caractères au moins).
15. **`tests/conftest.py` force `ATLAS_MEMOIRE_DOSSIER`** vers un dossier temporaire avant tout import du Core : `make test` exporte le `.env` de la machine.
16. **La machine telle qu'elle est** (Review Focus) :
    - les crochets git désactivés, l'identité d'Atlas imposée ;
    - un `index.lock` orphelin retiré à l'ouverture ;
    - un dépôt disparu recréé à la première écriture ;
    - les octets illisibles remplacés.

## Carte des fichiers

| Fichier | Tâche | Rôle |
|---|---|---|
| `src/atlas_core/memoire.py` | 1, 2, 3 | Le dépôt : écrire et lire ; chercher et annuler ; sommaire, amorçage, journal |
| `src/atlas_core/consignes.py` | 3, 5 | `date_en_lettres`, `heure_en_chiffres` ; les consignes avec mémoire, la demande de résumé |
| `src/atlas_core/cerveau.py`, `src/atlas_core/outils_memoire.py` | 4 | `Note` ; le serveur d'outils « atlas » |
| `src/atlas_core/cerveau_claude.py` | 5, 6, 7 | Les options avec les outils ; l'amorçage et les annonces ; la fin d'une conversation |
| `src/atlas_core/session.py` | 8 | L'annonce d'une note |
| `src/atlas_core/config.py`, `src/atlas_core/hub.py` | 9 | `memoire_dossier` ; la mémoire ouverte pour le cerveau |
| `.env.example`, `scripts/neo/LISEZMOI.md`, `docs/superpowers/specs/2026-09-22-atlas-design.md` | 9 | Réglage, déploiement, spec parente |
| `tests/test_memoire.py`, `test_memoire_chercher_annuler.py`, `test_memoire_amorcage.py`, `test_outils_memoire.py`, `test_consignes.py`, `test_cerveau_claude.py`, `test_cerveau_memoire.py`, `test_cerveau_journal.py`, `test_session_cerveau.py`, `test_config.py`, `test_hub.py`, `conftest.py` | 1–9 | Tests |

---

### Task 1: Le dépôt de la mémoire : écrire et lire

Le cœur de la mémoire : ouvrir le dépôt git local, vérifier ce qu'on y écrit (chemin, format d'une fiche, secrets),
écrire et commiter une fiche sous l'auteur « Atlas », la relire. Avec la machine telle qu'elle est : crochets git
globaux, verrou orphelin, dépôt supprimé, fichier retouché dans un autre encodage (Review Focus 1 à 4).

**Files:**
- Create: `src/atlas_core/memoire.py`
- Create: `tests/test_memoire.py`

**Interfaces:**
- Consumes: rien.
- Produces: `atlas_core.memoire` : `GIT = "git"`, `AUTEUR_NOM`, `AUTEUR_COURRIEL = "atlas@atlas.local"`,
  `DOSSIERS_FICHES`, `NOM_MAX`, `TITRE_MAX`, `RESUME_MAX`, `FICHE_MAX`, `SECRET_MIN` ;
  `ErreurMemoire(Exception)` (message en français, destiné à Claude) ; `_git(racine, *arguments) -> str` ;
  `_lire_texte(fichier: Path) -> str` ; `verifier_fiche(contenu) -> str` (le titre) ;
  `Memoire(racine: Path, secrets=())` avec `Memoire.ouvrir(racine, secrets=()) -> Memoire | None`,
  `racine`, `_cible(chemin, ecriture) -> Path`, `_assurer_le_depot()`, `verifier_secrets(texte)`,
  `lire(chemin) -> str`, `ecrire(chemin, contenu) -> str | None` (le titre, ou None si rien n'a changé).

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/test_memoire.py` :

```python
"""Le dépôt de la mémoire : ouvrir, écrire, lire, et tout ce qu'une écriture refuse. Chaque
test travaille dans un vrai dépôt git temporaire."""

import shutil
import subprocess

import pytest

from atlas_core import memoire as module
from atlas_core.memoire import ErreurMemoire, Memoire

SECRET_DU_CORE = "cle-du-core-tres-secrete"
FICHE = "# Paul Durand\n\nProspect, dirige une agence ; rendez-vous le jeudi 2 octobre 2026.\n"


@pytest.fixture
def memoire(tmp_path) -> Memoire:
    ouverte = Memoire.ouvrir(tmp_path / "memoire", secrets=[SECRET_DU_CORE, "court"])
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


# --- ouvrir ------------------------------------------------------------------


def test_ouvrir_cree_le_dossier_et_son_depot_sans_distant(memoire):
    assert (memoire.racine / ".git").is_dir()
    assert git(memoire, "remote") == ""


def test_rouvrir_garde_ce_qui_est_deja_ecrit(memoire):
    memoire.ecrire("personnes/paul-durand.md", FICHE)
    rouverte = Memoire.ouvrir(memoire.racine)
    assert rouverte.lire("personnes/paul-durand.md") == FICHE
    assert commits(rouverte) == 1


def test_sans_git_atlas_marche_sans_memoire(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(module, "GIT", "git-introuvable")
    assert Memoire.ouvrir(tmp_path / "memoire") is None
    assert "mémoire indisponible" in caplog.text


# --- écrire -------------------------------------------------------------------


def test_ecrire_cree_la_fiche_et_la_commite_sous_atlas(memoire):
    assert memoire.ecrire("personnes/paul-durand.md", FICHE) == "Paul Durand"
    assert (memoire.racine / "personnes" / "paul-durand.md").read_text() == FICHE
    assert git(memoire, "log", "-1", "--format=%an <%ae>|%s").strip() == (
        "Atlas <atlas@atlas.local>|Atlas : Paul Durand"
    )
    assert git(memoire, "status", "--porcelain") == ""


def test_ecrire_remplace_une_fiche_existante(memoire):
    memoire.ecrire("profil.md", "# Profil\n\nDavid, entrepreneur.\n")
    assert memoire.ecrire("profil.md", "# Profil\n\nDavid, entrepreneur ; à appeler Dieu.\n")
    assert memoire.lire("profil.md") == "# Profil\n\nDavid, entrepreneur ; à appeler Dieu.\n"
    assert commits(memoire) == 2


def test_une_fiche_inchangee_ne_fait_ni_commit_ni_annonce(memoire):
    memoire.ecrire("personnes/paul-durand.md", FICHE)
    assert memoire.ecrire("personnes/paul-durand.md", FICHE) is None
    assert commits(memoire) == 1


def test_le_contenu_finit_par_une_seule_fin_de_ligne(memoire):
    memoire.ecrire("projets/site-web.md", "\n# Site web\n\nMaquette validée.\n\n\n")
    assert memoire.lire("projets/site-web.md") == "# Site web\n\nMaquette validée.\n"


def test_seul_le_fichier_ecrit_est_commite(memoire):
    memoire.ecrire("projets/site-web.md", "# Site web\n\nMaquette validée.\n")
    retouche = memoire.racine / "projets" / "site-web.md"
    retouche.write_text("# Site web\n\nMaquette validée par David.\n")  # à la main
    git(memoire, "add", "projets/site-web.md")  # et même préparée pour son propre commit
    memoire.ecrire("personnes/paul-durand.md", FICHE)
    assert git(memoire, "status", "--porcelain").strip() == "M  projets/site-web.md"


@pytest.mark.parametrize(
    "chemin",
    [
        "../ailleurs.md",
        "notes.md",
        "profil",
        "projets/Paul.md",
        "projets/paul_durand.md",
        "projets/paul--durand.md",
        "projets/paul.txt",
        "projets/sous/dossier.md",
        "documents/rapport.md",
        "journal/2026-09-25.md",
        "/tmp/profil.md",
        "projets/" + "a" * 61 + ".md",
    ],
)
def test_une_ecriture_hors_des_fiches_est_refusee(memoire, chemin):
    with pytest.raises(ErreurMemoire):
        memoire.ecrire(chemin, FICHE)
    assert commits(memoire) == 0


def test_un_nom_de_soixante_caracteres_est_accepte(memoire):
    assert memoire.ecrire("projets/" + "a" * 60 + ".md", FICHE) == "Paul Durand"


def test_un_lien_symbolique_qui_sort_de_la_memoire_est_refuse(memoire, tmp_path):
    ailleurs = tmp_path / "ailleurs"
    ailleurs.mkdir()
    (memoire.racine / "projets").symlink_to(ailleurs)
    with pytest.raises(ErreurMemoire, match="sort de la mémoire"):
        memoire.ecrire("projets/site-web.md", FICHE)
    (ailleurs / "site-web.md").write_text(FICHE)
    with pytest.raises(ErreurMemoire, match="sort de la mémoire"):
        memoire.lire("projets/site-web.md")
    assert list(ailleurs.iterdir()) == [ailleurs / "site-web.md"]


@pytest.mark.parametrize(
    "contenu",
    [
        "Paul Durand, prospect.\n",
        "#Paul Durand\n\nProspect.\n",
        "# Paul Durand\nProspect.\n",
        "# Paul Durand\nSous-titre\nProspect.\n",
        "# Paul Durand\n\n\nProspect.\n",
        "# Paul Durand\n\n## Contacts\n",
        "# \n\nProspect.\n",
        "# " + "T" * 101 + "\n\nProspect.\n",
        "# Paul Durand\n\n" + "R" * 201 + "\n",
        "# Paul Durand\n\nProspect.\n\n" + "x" * 20_000,
    ],
)
def test_une_fiche_mal_formee_est_refusee(memoire, contenu):
    with pytest.raises(ErreurMemoire):
        memoire.ecrire("personnes/paul-durand.md", contenu)
    assert not (memoire.racine / "personnes" / "paul-durand.md").exists()


def test_le_refus_du_format_dit_a_claude_comment_faire(memoire):
    with pytest.raises(ErreurMemoire, match="« # Titre », une ligne vide, puis une phrase"):
        memoire.ecrire("personnes/paul-durand.md", "Paul Durand, prospect.\n")


@pytest.mark.parametrize(
    "secret",
    [
        "sk-ant-api03-AbCdEfGhIjKlMnOpQrStUv",
        "sk-proj-AbCdEfGhIjKlMnOpQrStUv",
        "ghp_AbCdEfGhIjKlMnOpQrStUvWxYz0123",
        "github_pat_11ABCDEFG0123456789_abcdefghij",
        "AKIAIOSFODNN7EXAMPLE",
        "xoxb-1234567890-abcdefghij",
        "AIzaSyA-1234567890abcdefghijklmnopqrstuv",
        "-----BEGIN OPENSSH PRIVATE KEY-----",
        "mot de passe : hunter2",
        "Password=azerty",
        "Le mdp est azerty123",
        SECRET_DU_CORE,
    ],
)
def test_un_secret_est_refuse_et_rien_n_est_ecrit(memoire, secret):
    with pytest.raises(ErreurMemoire, match="mot de passe ou à une clé secrète"):
        memoire.ecrire("profil.md", f"# Profil\n\nDavid.\n\nÀ garder : {secret}\n")
    assert not (memoire.racine / "profil.md").exists()
    assert commits(memoire) == 0


def test_parler_d_un_mot_de_passe_sans_le_donner_passe(memoire):
    assert memoire.ecrire("personnes/paul-durand.md", FICHE + "\nIl a oublié son mot de passe.\n")


def test_une_cle_du_core_trop_courte_ne_bloque_pas_les_mots_ordinaires(memoire):
    assert memoire.ecrire("projets/site-web.md", "# Site web\n\nUn court délai.\n")


# --- lire -------------------------------------------------------------------------


def test_lire_rend_une_fiche_ou_dit_qu_elle_manque(memoire):
    memoire.ecrire("personnes/paul-durand.md", FICHE)
    assert memoire.lire("personnes/paul-durand.md") == FICHE
    with pytest.raises(ErreurMemoire, match="projets/site-web.md n'existe pas"):
        memoire.lire("projets/site-web.md")


def test_le_journal_se_lit_mais_ne_s_ecrit_pas_par_les_fiches(memoire):
    (memoire.racine / "journal").mkdir()
    (memoire.racine / "journal" / "2026-09-25.md").write_text("# Journal du 25 septembre 2026\n")
    assert memoire.lire("journal/2026-09-25.md").startswith("# Journal")
    with pytest.raises(ErreurMemoire):
        memoire.lire("journal/hier.md")


# --- la machine telle qu'elle est ----------------------------------------------------


def test_les_crochets_git_de_la_machine_ne_bloquent_pas_les_notes(tmp_path, monkeypatch):
    crochets = tmp_path / "crochets"
    crochets.mkdir()
    for nom in ("pre-commit", "commit-msg"):
        crochet = crochets / nom
        crochet.write_text("#!/bin/sh\nexit 1\n")
        crochet.chmod(0o755)
    configuration = tmp_path / "gitconfig"
    configuration.write_text(f"[core]\n\thooksPath = {crochets}\n[user]\n\tname = David\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(configuration))
    memoire = Memoire.ouvrir(tmp_path / "memoire")
    assert memoire.ecrire("personnes/paul-durand.md", FICHE) == "Paul Durand"
    assert git(memoire, "log", "-1", "--format=%an").strip() == "Atlas"


def test_une_identite_git_imposee_par_l_environnement_ne_signe_pas_les_notes(memoire, monkeypatch):
    for variable in ("GIT_AUTHOR", "GIT_COMMITTER"):
        monkeypatch.setenv(f"{variable}_NAME", "Quelqu'un")
        monkeypatch.setenv(f"{variable}_EMAIL", "quelquun@example.com")
    memoire.ecrire("personnes/paul-durand.md", FICHE)
    assert git(memoire, "log", "-1", "--format=%an <%ae>|%cn").strip() == (
        "Atlas <atlas@atlas.local>|Atlas"
    )


def test_un_verrou_laisse_par_un_arret_brutal_est_retire_au_demarrage(memoire, caplog):
    verrou = memoire.racine / ".git" / "index.lock"
    verrou.write_text("")
    rouverte = Memoire.ouvrir(memoire.racine)
    assert not verrou.exists() and "verrou git laissé" in caplog.text
    assert rouverte.ecrire("personnes/paul-durand.md", FICHE) == "Paul Durand"


def test_un_depot_supprime_pendant_que_le_core_tourne_renait(memoire):
    memoire.ecrire("projets/site-web.md", "# Site web\n\nMaquette validée.\n")
    shutil.rmtree(memoire.racine)
    assert memoire.ecrire("personnes/paul-durand.md", FICHE) == "Paul Durand"
    assert (memoire.racine / ".git").is_dir() and commits(memoire) == 1


def test_une_fiche_retouchee_dans_un_autre_encodage_se_lit_quand_meme(memoire):
    (memoire.racine / "personnes").mkdir()
    (memoire.racine / "personnes" / "rene.md").write_bytes("# René\n\nAmi.\n".encode("latin-1"))
    assert memoire.lire("personnes/rene.md") == "# Ren\ufffd\n\nAmi.\n"
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `uv run pytest tests/test_memoire.py -q`
Expected: FAIL — erreur de collecte : `ImportError: cannot import name 'memoire' from 'atlas_core'`.

- [ ] **Step 3: Écrire le dépôt**

Créer `src/atlas_core/memoire.py` :

```python
"""La mémoire d'Atlas : un dépôt git local de fichiers Markdown.

Des fiches — le profil de David, l'entreprise, les projets, les personnes — qu'Atlas tient
de lui-même, et un journal que le Core écrit seul. Tout passe par ici : chaque écriture est
vérifiée (chemin, format, secrets), puis commitée sous l'auteur « Atlas ». Le dépôt n'a
aucun distant et n'est jamais poussé : rien ne quitte la machine.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import threading
from collections.abc import Iterable
from pathlib import Path

_journal = logging.getLogger(__name__)

GIT = "git"
AUTEUR_NOM = "Atlas"
AUTEUR_COURRIEL = "atlas@atlas.local"

DOSSIERS_FICHES = ("entreprise", "projets", "personnes")
_NOM = r"[a-z0-9]+(?:-[a-z0-9]+)*"
_FICHE = re.compile(rf"(?:profil|(?:{'|'.join(DOSSIERS_FICHES)})/(?P<nom>{_NOM}))\.md")
_JOURNAL = re.compile(r"journal/\d{4}-\d{2}-\d{2}\.md")
NOM_MAX = 60
TITRE_MAX = 100
RESUME_MAX = 200
FICHE_MAX = 20_000
# Ce qui ressemble à un secret n'entre jamais dans la mémoire (spec parente §13).
_SECRETS = [
    re.compile(motif)
    for motif in (
        r"\bsk-(?:ant-)?[A-Za-z0-9_-]{16,}",
        r"\bgh[pousr]_[A-Za-z0-9]{20,}",
        r"\bgithub_pat_[A-Za-z0-9_]{20,}",
        r"\bAKIA[0-9A-Z]{16}\b",
        r"\bxox[abprs]-[A-Za-z0-9-]{10,}",
        r"\bAIza[0-9A-Za-z_-]{35}",
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
        r"(?i)\b(?:mot de passe|mdp|password|passwd)\b\s*(?::|=|est\b)\s*\S+",
    )
]
SECRET_MIN = 8  # une clé du Core plus courte ne se cherche pas : trop de faux refus


class ErreurMemoire(Exception):
    """L'écriture ou la lecture est refusée. Le message, en français, va à Claude."""


def _git(racine: Path, *arguments: str) -> str:
    """Lance git dans le dépôt, sans dépendre de la configuration git de la machine."""
    commande = [
        GIT,
        "-C",
        str(racine),
        "-c",
        "commit.gpgsign=false",
        # Les crochets git de la machine (vérifications, messages imposés) ne concernent pas
        # la mémoire d'Atlas : ils pourraient bloquer chacune de ses notes.
        "-c",
        "core.hooksPath=/dev/null",
        *arguments,
    ]
    # L'auteur par l'environnement, qui passe avant toute configuration : une identité
    # imposée à la machine ferait sinon signer les notes par un autre, et « annule » ne
    # les retrouverait plus.
    identite = {
        "GIT_AUTHOR_NAME": AUTEUR_NOM,
        "GIT_AUTHOR_EMAIL": AUTEUR_COURRIEL,
        "GIT_COMMITTER_NAME": AUTEUR_NOM,
        "GIT_COMMITTER_EMAIL": AUTEUR_COURRIEL,
    }
    environnement = {**os.environ, **identite}
    return subprocess.run(
        commande, capture_output=True, text=True, check=True, env=environnement
    ).stdout


def _lire_texte(fichier: Path) -> str:
    """Un fichier retouché à la main dans un autre encodage se lit quand même : ses octets
    illisibles deviennent « � » au lieu de tout faire échouer."""
    return fichier.read_text(encoding="utf-8", errors="replace")


def verifier_fiche(contenu: str) -> str:
    """Une fiche : « # Titre », une ligne vide, une phrase de résumé, puis le reste.
    Rend le titre."""
    if len(contenu) > FICHE_MAX:
        raise ErreurMemoire(f"Une fiche fait au plus {FICHE_MAX} caractères.")
    lignes = contenu.split("\n")
    forme = (
        len(lignes) >= 3
        and lignes[0].startswith("# ")
        and not lignes[1].strip()
        and lignes[2].strip()
        and not lignes[2].startswith("#")
    )
    if not forme:
        raise ErreurMemoire(
            "Une fiche commence par « # Titre », une ligne vide, puis une phrase de résumé."
        )
    titre = lignes[0][2:].strip()
    if not titre or len(titre) > TITRE_MAX:
        raise ErreurMemoire(f"Le titre d'une fiche fait de 1 à {TITRE_MAX} caractères.")
    if len(lignes[2].strip()) > RESUME_MAX:
        raise ErreurMemoire(f"La phrase de résumé fait au plus {RESUME_MAX} caractères.")
    return titre


class Memoire:
    def __init__(self, racine: Path, secrets: Iterable[str] = ()) -> None:
        self.racine = racine
        self._secrets = [s for s in secrets if len(s) >= SECRET_MIN]
        self._verrou = threading.Lock()  # une écriture à la fois

    @classmethod
    def ouvrir(cls, racine: Path, secrets: Iterable[str] = ()) -> Memoire | None:
        """Crée le dossier et son dépôt au besoin. None si c'est impossible (git absent,
        dossier interdit) : Atlas marche alors sans mémoire, comme en phase 2a."""
        try:
            racine.mkdir(parents=True, exist_ok=True)
            if not (racine / ".git").exists():
                _git(racine, "init", "-q")
            verrou_git = racine / ".git" / "index.lock"
            if verrou_git.exists():
                # Laissé par un Core tué en plein commit : sans ce ménage, plus aucune note
                # ne s'écrirait jamais.
                _journal.warning("verrou git laissé par un arrêt brutal : retiré")
                verrou_git.unlink()
        except (OSError, subprocess.CalledProcessError) as e:
            _journal.warning("mémoire indisponible (%s) : Atlas marche sans elle", e)
            return None
        return cls(racine, secrets)

    def _cible(self, chemin: str, ecriture: bool) -> Path:
        """Le fichier désigné, s'il est permis ; sinon `ErreurMemoire`."""
        fiche = _FICHE.fullmatch(chemin)
        if not (fiche or (not ecriture and _JOURNAL.fullmatch(chemin))):
            raise ErreurMemoire(
                f"« {chemin} » n'est pas une fiche : profil.md, ou entreprise/, projets/ ou "
                "personnes/ suivi d'un nom en minuscules, chiffres et tirets, en .md."
            )
        if fiche and fiche["nom"] and len(fiche["nom"]) > NOM_MAX:
            raise ErreurMemoire(f"Un nom de fiche fait au plus {NOM_MAX} caractères.")
        cible = (self.racine / chemin).resolve()
        if not cible.is_relative_to(self.racine.resolve()):
            raise ErreurMemoire(f"« {chemin} » sort de la mémoire.")
        return cible

    def _assurer_le_depot(self) -> None:
        """Le dossier a pu être supprimé pendant que le Core tournait : il renaît vide."""
        if not (self.racine / ".git").exists():
            _journal.warning("dépôt de la mémoire disparu : recréé")
            self.racine.mkdir(parents=True, exist_ok=True)
            _git(self.racine, "init", "-q")

    def verifier_secrets(self, texte: str) -> None:
        if any(motif.search(texte) for motif in _SECRETS) or any(
            secret in texte for secret in self._secrets
        ):
            raise ErreurMemoire(
                "Refusé : le texte contient ce qui ressemble à un mot de passe ou à une clé "
                "secrète. Rien n'a été écrit."
            )

    def lire(self, chemin: str) -> str:
        cible = self._cible(chemin, ecriture=False)
        if not cible.is_file():
            raise ErreurMemoire(f"{chemin} n'existe pas.")
        return _lire_texte(cible)

    def ecrire(self, chemin: str, contenu: str) -> str | None:
        """Crée ou remplace une fiche entière, puis la commite. Rend son titre, ou None si
        elle était déjà ainsi (rien à commiter, rien à annoncer)."""
        cible = self._cible(chemin, ecriture=True)
        contenu = contenu.strip("\n") + "\n"
        titre = verifier_fiche(contenu)
        self.verifier_secrets(contenu)
        with self._verrou:
            self._assurer_le_depot()
            if cible.is_file() and _lire_texte(cible) == contenu:
                return None
            cible.parent.mkdir(parents=True, exist_ok=True)
            cible.write_text(contenu, encoding="utf-8")
            # Le seul fichier écrit : les retouches de David ailleurs restent les siennes.
            _git(self.racine, "add", "--", chemin)
            _git(self.racine, "commit", "-q", "-m", f"Atlas : {titre}", "--", chemin)
        return titre
```

- [ ] **Step 4: Vérifier que tout passe**

Run: `uv run pytest -q && uv run ruff check . --extend-exclude spikes && uv run ruff format --check . --extend-exclude spikes && node --test "tests/web/*.test.mjs"`
Expected: 710 tests Python passent, 126 tests JavaScript passent, ruff ne dit rien.

- [ ] **Step 5: Commit**

```bash
git add src/atlas_core/memoire.py tests/test_memoire.py
git commit -F - <<'MSG'
Mémoire : le dépôt git local, écrire et lire une fiche vérifiée

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

### Task 2: Chercher dans la mémoire, et annuler une note

Chercher un mot dans les fiches puis le journal, sans tenir compte des majuscules ni des accents ; annuler la dernière
note d'Atlas encore en place, sans jamais toucher au journal ni aux commits de David.

**Files:**
- Modify: `src/atlas_core/memoire.py`
- Create: `tests/test_memoire_chercher_annuler.py`

**Interfaces:**
- Consumes: Task 1 (`Memoire`, `_git`, `_cible`, `_lire_texte`, `ErreurMemoire`, `AUTEUR_COURRIEL`).
- Produces: `RESULTATS_MAX = 20`, `PREFIXE_NOTE = "Atlas : "`, `PREFIXE_ANNULE = "Annulé : "` ; `_plier(texte)` ;
  `Memoire._fichiers(avec_journal: bool) -> list[str]` (les fiches permises, puis le journal du plus récent au plus
  ancien) ; `Memoire.chercher(texte) -> list[str]` (lignes « chemin : ligne ») ; `Memoire.annuler() -> str` (le
  titre de la note retirée). Les commits de notes ont pour message `f"{PREFIXE_NOTE}{titre}"`.

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/test_memoire_chercher_annuler.py` :

```python
"""Chercher dans la mémoire, et annuler une note d'Atlas : dans un vrai dépôt git temporaire."""

import subprocess

import pytest

from atlas_core.memoire import ErreurMemoire, Memoire

PAUL = "# Paul Durand\n\nProspect ; rendez-vous le jeudi 2 octobre 2026.\n"
ELISE = "# Élise Martin\n\nAssociée ; s'occupe des offres.\n"


@pytest.fixture
def memoire(tmp_path) -> Memoire:
    return Memoire.ouvrir(tmp_path / "memoire")


def git(memoire: Memoire, *arguments: str, auteur: str | None = None) -> str:
    identite = []
    if auteur is not None:
        nom, courriel = auteur.split("|")
        identite = ["-c", f"user.name={nom}", "-c", f"user.email={courriel}"]
    return subprocess.run(
        ["git", "-C", str(memoire.racine), *identite, "-c", "commit.gpgsign=false", *arguments],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def commit_de_david(
    memoire: Memoire, chemin: str, contenu: str, message: str = "Ma retouche"
) -> None:
    fichier = memoire.racine / chemin
    fichier.parent.mkdir(parents=True, exist_ok=True)
    fichier.write_text(contenu)
    git(memoire, "add", chemin)
    git(memoire, "commit", "-q", "-m", message, auteur="David|david@example.com")


def journal(memoire: Memoire, jour: str, texte: str) -> None:
    (memoire.racine / "journal").mkdir(exist_ok=True)
    (memoire.racine / "journal" / f"{jour}.md").write_text(texte)


# --- chercher ------------------------------------------------------------------------


def test_chercher_ignore_majuscules_et_accents(memoire):
    memoire.ecrire("personnes/elise-martin.md", ELISE)
    assert memoire.chercher("elise") == ["personnes/elise-martin.md : # Élise Martin"]
    assert memoire.chercher("OFFRES") == [
        "personnes/elise-martin.md : Associée ; s'occupe des offres."
    ]


def test_chercher_passe_les_fiches_puis_le_journal_du_plus_recent_au_plus_ancien(memoire):
    memoire.ecrire("profil.md", "# Profil\n\nDavid parle de Paul.\n")
    memoire.ecrire("personnes/paul-durand.md", PAUL)
    journal(memoire, "2026-09-23", "Paul a rappelé.\n")
    journal(memoire, "2026-09-25", "Relancer Paul.\n")
    assert memoire.chercher("paul") == [
        "profil.md : David parle de Paul.",
        "personnes/paul-durand.md : # Paul Durand",
        "journal/2026-09-25.md : Relancer Paul.",
        "journal/2026-09-23.md : Paul a rappelé.",
    ]


def test_chercher_rend_vingt_lignes_au_plus(memoire):
    lignes = "".join(f"Ligne {i} sur le site.\n" for i in range(30))
    memoire.ecrire("projets/site-web.md", f"# Site web\n\nLe site.\n\n{lignes}")
    assert len(memoire.chercher("site")) == 20


def test_chercher_sans_rien_trouver_rend_une_liste_vide(memoire):
    memoire.ecrire("personnes/paul-durand.md", PAUL)
    assert memoire.chercher("Zoé") == []


def test_chercher_rien_est_refuse(memoire):
    with pytest.raises(ErreurMemoire, match="Rien à chercher"):
        memoire.chercher("  ")


def test_chercher_ignore_ce_qui_n_est_pas_une_fiche_permise(memoire, tmp_path):
    (memoire.racine / "projets").mkdir()
    (memoire.racine / "projets" / "Notes Paul.md").write_text("Paul, notes à la main.\n")
    ailleurs = tmp_path / "ailleurs"
    ailleurs.mkdir()
    (ailleurs / "paul.md").write_text("Paul, hors de la mémoire.\n")
    (memoire.racine / "personnes").symlink_to(ailleurs)
    assert memoire.chercher("paul") == []


# --- annuler --------------------------------------------------------------------------


def test_annuler_retire_la_derniere_note_et_rend_son_titre(memoire):
    memoire.ecrire("personnes/paul-durand.md", PAUL)
    memoire.ecrire("personnes/elise-martin.md", ELISE)
    assert memoire.annuler() == "Élise Martin"
    assert not (memoire.racine / "personnes" / "elise-martin.md").exists()
    assert memoire.lire("personnes/paul-durand.md") == PAUL
    assert git(memoire, "log", "-1", "--format=%ae|%s").strip() == (
        "atlas@atlas.local|Annulé : Élise Martin"
    )


def test_annuler_une_modification_rend_la_version_d_avant(memoire):
    memoire.ecrire("profil.md", "# Profil\n\nDavid.\n")
    memoire.ecrire("profil.md", "# Profil\n\nDavid, à appeler Dieu.\n")
    memoire.annuler()
    assert memoire.lire("profil.md") == "# Profil\n\nDavid.\n"


def test_redire_annuler_remonte_d_une_note(memoire):
    memoire.ecrire("personnes/paul-durand.md", PAUL)
    memoire.ecrire("personnes/elise-martin.md", ELISE)
    assert memoire.annuler() == "Élise Martin"
    assert memoire.annuler() == "Paul Durand"
    with pytest.raises(ErreurMemoire, match="plus de note à retirer"):
        memoire.annuler()


def test_rien_a_annuler_dans_une_memoire_neuve(memoire):
    with pytest.raises(ErreurMemoire, match="plus de note à retirer"):
        memoire.annuler()


def test_ni_le_journal_ni_les_commits_de_david_ne_s_annulent(memoire):
    memoire.ecrire("personnes/paul-durand.md", PAUL)
    # Même écrit à la façon d'Atlas, un commit de David reste le sien.
    commit_de_david(memoire, "projets/site-web.md", "# Site web\n\nÀ moi.\n", "Atlas : Site web")
    journal(memoire, "2026-09-25", "# Journal du 25 septembre 2026\n")
    git(memoire, "add", "journal/2026-09-25.md")
    git(
        memoire,
        "commit",
        "-q",
        "-m",
        "Journal : 25 septembre 2026",
        auteur="Atlas|atlas@atlas.local",
    )
    assert memoire.annuler() == "Paul Durand"
    assert (memoire.racine / "projets" / "site-web.md").exists()
    assert (memoire.racine / "journal" / "2026-09-25.md").exists()


def test_une_fiche_retouchee_depuis_ne_s_annule_pas(memoire):
    memoire.ecrire("personnes/paul-durand.md", PAUL)
    commit_de_david(memoire, "personnes/paul-durand.md", PAUL.replace("jeudi", "vendredi"))
    with pytest.raises(ErreurMemoire, match="modifiée depuis"):
        memoire.annuler()
    assert "vendredi" in memoire.lire("personnes/paul-durand.md")
    assert not (memoire.racine / ".git" / "REVERT_HEAD").exists()
    assert git(memoire, "status", "--porcelain") == ""


def test_une_retouche_pas_encore_commitee_bloque_l_annulation_sans_la_perdre(memoire):
    memoire.ecrire("personnes/paul-durand.md", PAUL)
    (memoire.racine / "personnes" / "paul-durand.md").write_text(PAUL + "\nNote à la main.\n")
    with pytest.raises(ErreurMemoire, match="modifiée depuis"):
        memoire.annuler()
    assert memoire.lire("personnes/paul-durand.md").endswith("Note à la main.\n")


def test_annuler_ne_commite_pas_ce_que_david_a_prepare_ailleurs(memoire):
    memoire.ecrire("personnes/paul-durand.md", PAUL)
    (memoire.racine / "notes.txt").write_text("à moi\n")
    git(memoire, "add", "notes.txt")
    memoire.annuler()
    assert git(memoire, "status", "--porcelain").strip() == "A  notes.txt"


def test_chercher_passe_une_fiche_retouchee_dans_un_autre_encodage(memoire):
    (memoire.racine / "personnes").mkdir()
    (memoire.racine / "personnes" / "rene.md").write_bytes(
        "# René\n\nAmi de Paul.\n".encode("latin-1")
    )
    assert memoire.chercher("paul") == ["personnes/rene.md : Ami de Paul."]
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `uv run pytest tests/test_memoire_chercher_annuler.py -q`
Expected: FAIL — 15 échecs : `AttributeError: 'Memoire' object has no attribute 'chercher'` (7) et
`… 'annuler'` (8).

- [ ] **Step 3: Écrire la recherche et l'annulation**

Modifier `src/atlas_core/memoire.py` :

```diff
--- a/src/atlas_core/memoire.py
+++ b/src/atlas_core/memoire.py
@@ -8,11 +8,13 @@ aucun distant et n'est jamais poussé : rien ne quitte la machine.
 
 from __future__ import annotations
 
+import contextlib
 import logging
 import os
 import re
 import subprocess
 import threading
+import unicodedata
 from collections.abc import Iterable
 from pathlib import Path
 
@@ -45,6 +47,9 @@ _SECRETS = [
     )
 ]
 SECRET_MIN = 8  # une clé du Core plus courte ne se cherche pas : trop de faux refus
+RESULTATS_MAX = 20
+PREFIXE_NOTE = "Atlas : "
+PREFIXE_ANNULE = "Annulé : "
 
 
 class ErreurMemoire(Exception):
@@ -86,6 +91,12 @@ def _lire_texte(fichier: Path) -> str:
     return fichier.read_text(encoding="utf-8", errors="replace")
 
 
+def _plier(texte: str) -> str:
+    """Sans majuscules ni accents : « Élise » se trouve en cherchant « elise »."""
+    decompose = unicodedata.normalize("NFD", texte.casefold())
+    return "".join(c for c in decompose if not unicodedata.combining(c))
+
+
 def verifier_fiche(contenu: str) -> str:
     """Une fiche : « # Titre », une ligne vide, une phrase de résumé, puis le reste.
     Rend le titre."""
@@ -188,5 +199,72 @@ class Memoire:
             cible.write_text(contenu, encoding="utf-8")
             # Le seul fichier écrit : les retouches de David ailleurs restent les siennes.
             _git(self.racine, "add", "--", chemin)
-            _git(self.racine, "commit", "-q", "-m", f"Atlas : {titre}", "--", chemin)
+            _git(self.racine, "commit", "-q", "-m", f"{PREFIXE_NOTE}{titre}", "--", chemin)
+        return titre
+
+    def _fichiers(self, avec_journal: bool) -> list[str]:
+        """Les fiches (le profil, puis chaque dossier par ordre alphabétique), puis le
+        journal du plus récent au plus ancien ; seulement ce qui est permis."""
+        candidats = ["profil.md"]
+        for dossier in DOSSIERS_FICHES:
+            noms = (p.name for p in (self.racine / dossier).glob("*.md"))
+            candidats += sorted(f"{dossier}/{nom}" for nom in noms)
+        if avec_journal:
+            noms = (p.name for p in (self.racine / "journal").glob("*.md"))
+            candidats += sorted((f"journal/{nom}" for nom in noms), reverse=True)
+        permis = []
+        for chemin in candidats:
+            with contextlib.suppress(ErreurMemoire):
+                if self._cible(chemin, ecriture=False).is_file():
+                    permis.append(chemin)
+        return permis
+
+    def chercher(self, texte: str) -> list[str]:
+        """Les lignes qui contiennent le texte, chacune précédée de son fichier : les fiches
+        d'abord, puis le journal du plus récent au plus ancien. Vingt au plus."""
+        cle = _plier(texte.strip())
+        if not cle:
+            raise ErreurMemoire("Rien à chercher.")
+        trouvees: list[str] = []
+        for chemin in self._fichiers(avec_journal=True):
+            for ligne in _lire_texte(self.racine / chemin).splitlines():
+                if cle in _plier(ligne):
+                    trouvees.append(f"{chemin} : {ligne.strip()}")
+                    if len(trouvees) == RESULTATS_MAX:
+                        return trouvees
+        return trouvees
+
+    def annuler(self) -> str:
+        """Défait la dernière écriture d'Atlas encore en place (`git revert`) ; rend son
+        titre. Ni le journal, ni les commits de David ne s'annulent."""
+        with self._verrou:
+            try:
+                historique = _git(self.racine, "log", "--format=%H%x1f%ae%x1f%s%x1f%b%x1e")
+            except subprocess.CalledProcessError:
+                historique = ""  # aucun commit encore
+            annulees: set[str] = set()
+            for entree in historique.split("\x1e"):
+                if not entree.strip():
+                    continue
+                sha, courriel, sujet, corps = entree.strip("\n").split("\x1f", 3)
+                if courriel != AUTEUR_COURRIEL:
+                    continue
+                if sujet.startswith(PREFIXE_ANNULE):
+                    annulees.update(re.findall(r"Annule ([0-9a-f]{40})", corps))
+                elif sujet.startswith(PREFIXE_NOTE) and sha not in annulees:
+                    return self._defaire(sha, sujet.removeprefix(PREFIXE_NOTE))
+        raise ErreurMemoire("Il n'y a plus de note à retirer.")
+
+    def _defaire(self, sha: str, titre: str) -> str:
+        chemins = _git(self.racine, "show", "--name-only", "--format=", sha).split()
+        try:
+            _git(self.racine, "revert", "--no-commit", sha)
+            message = f"{PREFIXE_ANNULE}{titre}\n\nAnnule {sha}"
+            _git(self.racine, "commit", "-q", "-m", message, "--", *chemins)
+        except subprocess.CalledProcessError:
+            with contextlib.suppress(subprocess.CalledProcessError):
+                _git(self.racine, "revert", "--abort")
+            raise ErreurMemoire(
+                "Je ne peux pas retirer cette note : la fiche a été modifiée depuis."
+            ) from None
         return titre
```

- [ ] **Step 4: Vérifier que tout passe**

Run: `uv run pytest -q && uv run ruff check . --extend-exclude spikes && uv run ruff format --check . --extend-exclude spikes && node --test "tests/web/*.test.mjs"`
Expected: 725 tests Python passent, 126 tests JavaScript passent, ruff ne dit rien.

- [ ] **Step 5: Commit**

```bash
git add src/atlas_core/memoire.py tests/test_memoire_chercher_annuler.py
git commit -F - <<'MSG'
Mémoire : chercher dans les fiches et le journal, annuler une note d'Atlas

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

### Task 3: Le sommaire, l'amorçage et le journal

Ce que Claude reçoit au début d'une conversation (le profil, le sommaire des fiches, le journal des sept derniers
jours, chacun plafonné), et l'ajout d'un résumé au journal. Les dates en toutes lettres passent par deux fonctions
de `consignes.py`.

**Files:**
- Modify: `src/atlas_core/consignes.py`
- Modify: `src/atlas_core/memoire.py`
- Modify: `tests/test_consignes.py`
- Create: `tests/test_memoire_amorcage.py`

**Interfaces:**
- Consumes: Tasks 1–2 (`Memoire`, `_fichiers`, `lire`, `_lire_texte`, `_assurer_le_depot`, `verifier_secrets`,
  `_git`).
- Produces: `consignes.date_en_lettres(jour) -> str` (« 1er juin 2026 ») et `consignes.heure_en_chiffres(moment)
  -> str` (« 9 h 05 ») ; `PREFIXE_JOURNAL = "Journal : "`, `PROFIL_MAX`, `SOMMAIRE_MAX`, `JOURNAL_MAX`,
  `JOURS_DE_JOURNAL` ; `Memoire.sommaire() -> list[str]` ; `Memoire.amorcage(aujourd_hui: dt.date) -> str` ;
  `Memoire.ajouter_au_journal(debut: dt.datetime, fin: dt.datetime, resume: str) -> None`.

- [ ] **Step 1: Écrire les tests qui échouent**

Modifier `tests/test_consignes.py` :

```diff
--- a/tests/test_consignes.py
+++ b/tests/test_consignes.py
@@ -2,7 +2,7 @@ import datetime as dt
 
 import pytest
 
-from atlas_core.consignes import CONSIGNES, ligne_de_date
+from atlas_core.consignes import CONSIGNES, date_en_lettres, heure_en_chiffres, ligne_de_date
 
 
 @pytest.mark.parametrize(
@@ -18,6 +18,12 @@ def test_la_ligne_de_date_est_en_francais(moment, attendu):
     assert ligne_de_date(moment) == attendu
 
 
+def test_la_date_et_l_heure_s_ecrivent_comme_dans_la_ligne_de_date():
+    assert date_en_lettres(dt.date(2026, 6, 1)) == "1er juin 2026"
+    assert date_en_lettres(dt.date(2026, 9, 25)) == "25 septembre 2026"
+    assert heure_en_chiffres(dt.datetime(2026, 9, 25, 9, 5)) == "9 h 05"
+
+
 def test_les_consignes_tiennent_les_decisions_de_la_spec():
     texte = CONSIGNES.lower()
     for attendu in (
```

Créer `tests/test_memoire_amorcage.py` :

```python
"""Le sommaire, l'amorçage d'une conversation et le journal : dans un vrai dépôt git temporaire."""

import datetime as dt
import shutil
import subprocess

import pytest

from atlas_core.memoire import ErreurMemoire, Memoire

AUJOURD_HUI = dt.date(2026, 9, 25)
DEBUT = dt.datetime(2026, 9, 25, 14, 5)
FIN = dt.datetime(2026, 9, 25, 14, 32)


@pytest.fixture
def memoire(tmp_path) -> Memoire:
    return Memoire.ouvrir(tmp_path / "memoire", secrets=["cle-du-core-tres-secrete"])


def git(memoire: Memoire, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(memoire.racine), *arguments], capture_output=True, text=True, check=True
    ).stdout


def journal(memoire: Memoire, jour: dt.date, texte: str) -> None:
    (memoire.racine / "journal").mkdir(exist_ok=True)
    (memoire.racine / "journal" / f"{jour:%Y-%m-%d}.md").write_text(texte)


# --- le sommaire ---------------------------------------------------------------------


def test_le_sommaire_donne_une_ligne_par_fiche_hors_profil(memoire):
    memoire.ecrire("profil.md", "# Profil\n\nDavid, entrepreneur.\n")
    memoire.ecrire("personnes/paul-durand.md", "# Paul Durand\n\nProspect.\n")
    memoire.ecrire("projets/site-web.md", "# Site web\n\nMaquette validée.\n")
    memoire.ecrire("entreprise/vision.md", "# Vision\n\nDes assistants sur mesure.\n")
    assert memoire.sommaire() == [
        "- entreprise/vision.md : Des assistants sur mesure.",
        "- projets/site-web.md : Maquette validée.",
        "- personnes/paul-durand.md : Prospect.",
    ]


def test_une_fiche_retouchee_hors_format_se_resume_par_son_titre(memoire):
    (memoire.racine / "projets").mkdir()
    (memoire.racine / "projets" / "site-web.md").write_text("# Site web\n## Tâches\n- héberger\n")
    (memoire.racine / "projets" / "vide.md").write_text("# Vide\n")
    assert memoire.sommaire() == ["- projets/site-web.md : Site web", "- projets/vide.md : Vide"]


# --- l'amorçage ------------------------------------------------------------------------


def test_une_memoire_vide_le_dit(memoire):
    assert memoire.amorcage(AUJOURD_HUI) == (
        "[Mémoire d'Atlas]\nLa mémoire est vide.\n[Fin de la mémoire]"
    )


def test_l_amorcage_donne_le_profil_les_fiches_et_la_semaine_de_journal(memoire):
    memoire.ecrire("profil.md", "# Profil\n\nDavid, à appeler Dieu.\n")
    memoire.ecrire("personnes/paul-durand.md", "# Paul Durand\n\nProspect.\n")
    journal(memoire, AUJOURD_HUI, "# Journal du 25 septembre 2026\n\nLe site.\n")
    journal(memoire, AUJOURD_HUI - dt.timedelta(days=6), "# Journal du 19 septembre 2026\n")
    journal(memoire, AUJOURD_HUI - dt.timedelta(days=7), "# Journal du 18 septembre 2026\n")
    assert memoire.amorcage(AUJOURD_HUI) == (
        "[Mémoire d'Atlas]\n"
        "Profil :\n# Profil\n\nDavid, à appeler Dieu.\n\n"
        "Fiches :\n- personnes/paul-durand.md : Prospect.\n\n"
        "Journal des sept derniers jours :\n"
        "# Journal du 19 septembre 2026\n\n# Journal du 25 septembre 2026\n\nLe site.\n"
        "[Fin de la mémoire]"
    )


def test_un_amorcage_sans_profil_ni_journal_le_dit(memoire):
    memoire.ecrire("projets/site-web.md", "# Site web\n\nMaquette validée.\n")
    amorcage = memoire.amorcage(AUJOURD_HUI)
    assert "Profil :\npas encore de profil." in amorcage
    assert "Journal des sept derniers jours :\nrien." in amorcage


def test_un_amorcage_sans_fiche_le_dit(memoire):
    memoire.ecrire("profil.md", "# Profil\n\nDavid.\n")
    assert "Fiches :\naucune." in memoire.amorcage(AUJOURD_HUI)


def test_un_profil_trop_long_est_coupe(memoire):
    memoire.ecrire("profil.md", "# Profil\n\nDavid.\n\n" + "mot " * 3000)
    profil = memoire.amorcage(AUJOURD_HUI).split("Profil :\n")[1].split("\n\nFiches :")[0]
    assert len(profil) <= 4_000 + len(" […]") and profil.endswith(" […]")


def test_le_sommaire_de_l_amorcage_s_arrete_a_cent_cinquante_fiches(memoire):
    (memoire.racine / "projets").mkdir()
    for i in range(160):
        (memoire.racine / "projets" / f"p{i:03d}.md").write_text(f"# P{i}\n\nProjet {i}.\n")
    fiches = memoire.amorcage(AUJOURD_HUI).split("Fiches :\n")[1].split("\n\n")[0].split("\n")
    assert len(fiches) == 151
    assert fiches[-1] == "- … et 10 autres fiches."


def test_le_journal_garde_les_jours_les_plus_recents_sous_le_plafond(memoire):
    for ecart in range(3):
        jour = AUJOURD_HUI - dt.timedelta(days=ecart)
        journal(memoire, jour, f"# Jour {ecart}\n\n" + "x" * 2_500)
    texte = memoire.amorcage(AUJOURD_HUI).split("Journal des sept derniers jours :\n")[1]
    assert "# Jour 0" in texte and "# Jour 1" in texte and "# Jour 2" not in texte
    assert texte.index("# Jour 1") < texte.index("# Jour 0")


def test_un_seul_jour_trop_long_garde_sa_fin(memoire):
    journal(memoire, AUJOURD_HUI, "# Journal\n\n" + "a" * 7_000 + "\nFIN\n")
    texte = memoire.amorcage(AUJOURD_HUI).split("Journal des sept derniers jours :\n")[1]
    assert texte.startswith("[…] ") and "FIN" in texte and "# Journal" not in texte


# --- le journal ---------------------------------------------------------------------


def test_le_premier_resume_du_jour_ouvre_le_journal_et_se_commite_en_silence(memoire):
    memoire.ajouter_au_journal(DEBUT, FIN, "On a parlé du site web.\n")
    assert memoire.lire("journal/2026-09-25.md") == (
        "# Journal du 25 septembre 2026\n\n## 14 h 05 – 14 h 32\n\nOn a parlé du site web.\n"
    )
    assert git(memoire, "log", "-1", "--format=%ae|%s").strip() == (
        "atlas@atlas.local|Journal : 25 septembre 2026, 14 h 32"
    )


def test_les_resumes_suivants_s_ajoutent_au_meme_jour(memoire):
    memoire.ajouter_au_journal(DEBUT, FIN, "Le site web.")
    memoire.ajouter_au_journal(
        dt.datetime(2026, 9, 25, 18, 0), dt.datetime(2026, 9, 25, 18, 9), "Paul."
    )
    assert memoire.lire("journal/2026-09-25.md") == (
        "# Journal du 25 septembre 2026\n\n## 14 h 05 – 14 h 32\n\nLe site web.\n"
        "\n## 18 h 00 – 18 h 09\n\nPaul.\n"
    )


def test_une_conversation_finie_apres_minuit_va_au_jour_de_sa_fin(memoire):
    memoire.ajouter_au_journal(
        dt.datetime(2026, 9, 25, 23, 50), dt.datetime(2026, 9, 26, 0, 10), "Tard."
    )
    assert memoire.lire("journal/2026-09-26.md").startswith("# Journal du 26 septembre 2026")


def test_un_resume_qui_contient_un_secret_n_est_pas_ecrit(memoire):
    with pytest.raises(ErreurMemoire, match="clé secrète"):
        memoire.ajouter_au_journal(DEBUT, FIN, "David a donné cle-du-core-tres-secrete.")
    assert not (memoire.racine / "journal").exists()


def test_un_journal_qui_sort_de_la_memoire_est_refuse(memoire, tmp_path):
    ailleurs = tmp_path / "ailleurs"
    ailleurs.mkdir()
    (memoire.racine / "journal").symlink_to(ailleurs)
    with pytest.raises(ErreurMemoire, match="sort de la mémoire"):
        memoire.ajouter_au_journal(DEBUT, FIN, "Le site web.")
    assert list(ailleurs.iterdir()) == []


def test_le_journal_ne_s_annule_pas(memoire):
    memoire.ajouter_au_journal(DEBUT, FIN, "Le site web.")
    with pytest.raises(ErreurMemoire, match="plus de note à retirer"):
        memoire.annuler()


def test_une_fiche_dans_un_autre_encodage_ne_fait_pas_tomber_l_amorcage(memoire):
    memoire.ecrire("profil.md", "# Profil\n\nDavid.\n")
    (memoire.racine / "personnes").mkdir()
    (memoire.racine / "personnes" / "rene.md").write_bytes("# René\n\nAmi.\n".encode("latin-1"))
    amorcage = memoire.amorcage(AUJOURD_HUI)
    assert "- personnes/rene.md : Ami." in amorcage and "David." in amorcage


def test_un_depot_supprime_renait_aussi_pour_le_journal(memoire):
    shutil.rmtree(memoire.racine)
    memoire.ajouter_au_journal(DEBUT, FIN, "Le site web.")
    assert (memoire.racine / ".git").is_dir()
    assert git(memoire, "log", "-1", "--format=%s").startswith("Journal : ")
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `uv run pytest tests/test_consignes.py tests/test_memoire_amorcage.py -q`
Expected: FAIL — erreur de collecte : `ImportError: cannot import name 'date_en_lettres' from 'atlas_core.consignes'`.

- [ ] **Step 3: Écrire le sommaire, l'amorçage et le journal**

Modifier `src/atlas_core/consignes.py` :

```diff
--- a/src/atlas_core/consignes.py
+++ b/src/atlas_core/consignes.py
@@ -53,10 +53,18 @@ _MOIS = (
 )
 
 
+def date_en_lettres(jour: dt.date) -> str:
+    """« 24 septembre 2026 », « 1er juin 2026 »."""
+    quantieme = "1er" if jour.day == 1 else str(jour.day)
+    return f"{quantieme} {_MOIS[jour.month - 1]} {jour.year}"
+
+
+def heure_en_chiffres(moment: dt.datetime) -> str:
+    """« 21 h 50 », « 9 h 05 »."""
+    return f"{moment.hour} h {moment.minute:02d}"
+
+
 def ligne_de_date(maintenant: dt.datetime) -> str:
     """« [jeudi 24 septembre 2026, 21 h 50] », « [lundi 1er juin 2026, 9 h 05] »."""
-    jour = "1er" if maintenant.day == 1 else str(maintenant.day)
-    return (
-        f"[{_JOURS[maintenant.weekday()]} {jour} {_MOIS[maintenant.month - 1]} "
-        f"{maintenant.year}, {maintenant.hour} h {maintenant.minute:02d}]"
-    )
+    jour = _JOURS[maintenant.weekday()]
+    return f"[{jour} {date_en_lettres(maintenant)}, {heure_en_chiffres(maintenant)}]"
```

Modifier `src/atlas_core/memoire.py` :

```diff
--- a/src/atlas_core/memoire.py
+++ b/src/atlas_core/memoire.py
@@ -9,6 +9,7 @@ aucun distant et n'est jamais poussé : rien ne quitte la machine.
 from __future__ import annotations
 
 import contextlib
+import datetime as dt
 import logging
 import os
 import re
@@ -18,6 +19,8 @@ import unicodedata
 from collections.abc import Iterable
 from pathlib import Path
 
+from .consignes import date_en_lettres, heure_en_chiffres
+
 _journal = logging.getLogger(__name__)
 
 GIT = "git"
@@ -50,6 +53,12 @@ SECRET_MIN = 8  # une clé du Core plus courte ne se cherche pas : trop de faux
 RESULTATS_MAX = 20
 PREFIXE_NOTE = "Atlas : "
 PREFIXE_ANNULE = "Annulé : "
+PREFIXE_JOURNAL = "Journal : "
+# L'amorçage d'une conversation reste court, même quand la mémoire grossit.
+PROFIL_MAX = 4_000
+SOMMAIRE_MAX = 150
+JOURNAL_MAX = 6_000
+JOURS_DE_JOURNAL = 7
 
 
 class ErreurMemoire(Exception):
@@ -97,6 +106,10 @@ def _plier(texte: str) -> str:
     return "".join(c for c in decompose if not unicodedata.combining(c))
 
 
+def _tronquer(texte: str, taille: int) -> str:
+    return texte if len(texte) <= taille else texte[:taille].rstrip() + " […]"
+
+
 def verifier_fiche(contenu: str) -> str:
     """Une fiche : « # Titre », une ligne vide, une phrase de résumé, puis le reste.
     Rend le titre."""
@@ -268,3 +281,80 @@ class Memoire:
                 "Je ne peux pas retirer cette note : la fiche a été modifiée depuis."
             ) from None
         return titre
+
+    # --- l'amorçage et le journal -----------------------------------------------------
+
+    def sommaire(self) -> list[str]:
+        """Une ligne par fiche hors profil : son chemin et sa phrase de résumé (son titre,
+        si la fiche a été retouchée à la main hors du format)."""
+        lignes = []
+        for chemin in self._fichiers(avec_journal=False):
+            if chemin == "profil.md":
+                continue
+            debut = _lire_texte(self.racine / chemin).split("\n", 3)
+            au_format = len(debut) > 2 and not debut[1].strip() and debut[2].strip()
+            if au_format and not debut[2].startswith("#"):
+                resume = debut[2].strip()
+            else:
+                resume = debut[0].lstrip("#").strip()
+            lignes.append(f"- {chemin} : {resume}")
+        return lignes
+
+    def amorcage(self, aujourd_hui: dt.date) -> str:
+        """Le bloc qui précède la première question d'une conversation : le profil, le
+        sommaire des fiches et le journal des derniers jours, chacun plafonné."""
+        profil = ""
+        with contextlib.suppress(ErreurMemoire):
+            profil = self.lire("profil.md").strip()
+        fiches = self.sommaire()
+        journal = self._journal_recent(aujourd_hui)
+        if not (profil or fiches or journal):
+            corps = "La mémoire est vide."
+        else:
+            if len(fiches) > SOMMAIRE_MAX:
+                reste = len(fiches) - SOMMAIRE_MAX
+                fiches = [*fiches[:SOMMAIRE_MAX], f"- … et {reste} autres fiches."]
+            corps = "\n\n".join(
+                [
+                    "Profil :\n" + (_tronquer(profil, PROFIL_MAX) or "pas encore de profil."),
+                    "Fiches :\n" + ("\n".join(fiches) or "aucune."),
+                    "Journal des sept derniers jours :\n" + (journal or "rien."),
+                ]
+            )
+        return f"[Mémoire d'Atlas]\n{corps}\n[Fin de la mémoire]"
+
+    def _journal_recent(self, aujourd_hui: dt.date) -> str:
+        """Les derniers jours du journal, du plus ancien au plus récent ; les plus récents
+        sont gardés en priorité quand le plafond est atteint."""
+        jours = []
+        for ecart in range(JOURS_DE_JOURNAL):
+            chemin = f"journal/{aujourd_hui - dt.timedelta(days=ecart):%Y-%m-%d}.md"
+            with contextlib.suppress(ErreurMemoire):
+                jours.append(self.lire(chemin).strip())
+        gardes: list[str] = []
+        taille = 0
+        for texte in jours:  # du plus récent au plus ancien
+            if taille + len(texte) > JOURNAL_MAX:
+                if not gardes:
+                    gardes.append("[…] " + texte[-JOURNAL_MAX:])
+                break
+            gardes.append(texte)
+            taille += len(texte)
+        return "\n\n".join(reversed(gardes))
+
+    def ajouter_au_journal(self, debut: dt.datetime, fin: dt.datetime, resume: str) -> None:
+        """Ajoute le résumé d'une conversation au journal du jour où elle s'est terminée,
+        puis le commite, en silence. Un résumé qui contient un secret est refusé."""
+        self.verifier_secrets(resume)
+        chemin = f"journal/{fin:%Y-%m-%d}.md"
+        cible = self._cible(chemin, ecriture=False)
+        with self._verrou:
+            self._assurer_le_depot()
+            cible.parent.mkdir(parents=True, exist_ok=True)
+            entete = "" if cible.exists() else f"# Journal du {date_en_lettres(fin)}\n"
+            heures = f"{heure_en_chiffres(debut)} – {heure_en_chiffres(fin)}"
+            with cible.open("a", encoding="utf-8") as fichier:
+                fichier.write(f"{entete}\n## {heures}\n\n{resume.strip()}\n")
+            _git(self.racine, "add", "--", chemin)
+            message = f"{PREFIXE_JOURNAL}{date_en_lettres(fin)}, {heure_en_chiffres(fin)}"
+            _git(self.racine, "commit", "-q", "-m", message, "--", chemin)
```

- [ ] **Step 4: Vérifier que tout passe**

Run: `uv run pytest -q && uv run ruff check . --extend-exclude spikes && uv run ruff format --check . --extend-exclude spikes && node --test "tests/web/*.test.mjs"`
Expected: 744 tests Python passent, 126 tests JavaScript passent, ruff ne dit rien.

- [ ] **Step 5: Commit**

```bash
git add src/atlas_core/consignes.py src/atlas_core/memoire.py tests/test_consignes.py tests/test_memoire_amorcage.py
git commit -F - <<'MSG'
Mémoire : sommaire, amorçage d'une conversation et journal

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

### Task 4: Les outils de la mémoire

Le serveur d'outils « atlas » que le Core sert à Claude : lire, chercher, écrire une fiche, annuler. Chaque écriture
réussie laisse une annonce (`Note`) que le cerveau fera dire ; pendant le résumé d'une conversation, rien ne s'écrit.

**Files:**
- Modify: `src/atlas_core/cerveau.py`
- Create: `src/atlas_core/outils_memoire.py`
- Create: `tests/test_outils_memoire.py`

**Interfaces:**
- Consumes: Tasks 1–3 (`Memoire.lire`, `chercher`, `ecrire`, `annuler`, `ErreurMemoire`).
- Produces: `cerveau.Note(annonce: str)` (frozen dataclass) ; `Cerveau.repondre` peut rendre des `Note`.
  `atlas_core.outils_memoire` : `SERVEUR = "atlas"`, `ANNONCE_PROFIL`, `ANNONCE_RETRAIT`, `PENDANT_LE_RESUME`,
  `ECHEC`, `annonce_de(chemin, titre) -> str` ; `OutilsMemoire(memoire)` avec `memoire`, `ecriture_permise: bool`,
  `outils: list[SdkMcpTool]`, `noms: list[str]`, `serveur() -> McpSdkServerConfig`,
  `prendre_les_annonces() -> list[Note]`.

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/test_outils_memoire.py` :

```python
"""Les outils de la mémoire, appelés comme Claude les appelle (leur gestionnaire), sur un vrai
dépôt git temporaire."""

import pytest

from atlas_core.cerveau import Note
from atlas_core.memoire import Memoire
from atlas_core.outils_memoire import (
    ANNONCE_PROFIL,
    ANNONCE_RETRAIT,
    ECHEC,
    PENDANT_LE_RESUME,
    OutilsMemoire,
)

PAUL = "# Paul Durand\n\nProspect ; rendez-vous le jeudi 2 octobre 2026.\n"


@pytest.fixture
def outils(tmp_path) -> OutilsMemoire:
    return OutilsMemoire(Memoire.ouvrir(tmp_path / "memoire"))


async def appeler(outils: OutilsMemoire, nom: str, **arguments) -> tuple[str, bool]:
    outil = next(o for o in outils.outils if o.name == nom)
    resultat = await outil.handler(arguments)
    return resultat["content"][0]["text"], resultat.get("is_error", False)


def test_claude_voit_quatre_outils_sur_le_serveur_atlas(outils):
    assert outils.noms == [
        "mcp__atlas__memoire_lire",
        "mcp__atlas__memoire_chercher",
        "mcp__atlas__memoire_ecrire",
        "mcp__atlas__memoire_annuler",
    ]
    serveur = outils.serveur()
    assert (serveur["type"], serveur["name"]) == ("sdk", "atlas")


def test_les_descriptions_disent_a_claude_le_format_et_qui_annonce(outils):
    ecrire = next(o for o in outils.outils if o.name == "memoire_ecrire")
    assert "« # Titre », une ligne vide, puis une phrase de résumé" in ecrire.description
    assert "ne l'annonce pas toi-même" in ecrire.description
    assert ecrire.input_schema == {"chemin": str, "contenu": str}


async def test_ecrire_une_fiche_la_fait_annoncer_par_son_titre(outils):
    texte, erreur = await appeler(
        outils, "memoire_ecrire", chemin="personnes/paul-durand.md", contenu=PAUL
    )
    assert (texte, erreur) == ("C'est noté dans personnes/paul-durand.md.", False)
    assert outils.prendre_les_annonces() == [Note("Je le note dans la fiche Paul Durand.")]
    assert outils.prendre_les_annonces() == []


async def test_ecrire_le_profil_s_annonce_comme_le_profil(outils):
    await appeler(outils, "memoire_ecrire", chemin="profil.md", contenu="# Profil\n\nDavid.\n")
    assert outils.prendre_les_annonces() == [Note(ANNONCE_PROFIL)]


async def test_deux_ecritures_font_deux_annonces_dans_l_ordre(outils):
    await appeler(outils, "memoire_ecrire", chemin="profil.md", contenu="# Profil\n\nDavid.\n")
    await appeler(outils, "memoire_ecrire", chemin="personnes/paul-durand.md", contenu=PAUL)
    assert outils.prendre_les_annonces() == [
        Note(ANNONCE_PROFIL),
        Note("Je le note dans la fiche Paul Durand."),
    ]


async def test_une_fiche_inchangee_ne_s_annonce_pas(outils):
    await appeler(outils, "memoire_ecrire", chemin="personnes/paul-durand.md", contenu=PAUL)
    outils.prendre_les_annonces()
    texte, erreur = await appeler(
        outils, "memoire_ecrire", chemin="personnes/paul-durand.md", contenu=PAUL
    )
    assert (texte, erreur) == ("La fiche était déjà ainsi : rien n'a changé.", False)
    assert outils.prendre_les_annonces() == []


@pytest.mark.parametrize(
    ("chemin", "contenu", "raison"),
    [
        ("personnes/paul-durand.md", "Paul, prospect.", "« # Titre »"),
        ("profil.md", "# Profil\n\nmot de passe : hunter2\n", "clé secrète"),
        ("../ailleurs.md", PAUL, "n'est pas une fiche"),
    ],
)
async def test_un_refus_revient_a_claude_sans_rien_annoncer(outils, chemin, contenu, raison):
    texte, erreur = await appeler(outils, "memoire_ecrire", chemin=chemin, contenu=contenu)
    assert erreur is True and raison in texte
    assert outils.prendre_les_annonces() == []


async def test_lire_rend_la_fiche_ou_un_refus(outils):
    await appeler(outils, "memoire_ecrire", chemin="personnes/paul-durand.md", contenu=PAUL)
    assert await appeler(outils, "memoire_lire", chemin="personnes/paul-durand.md") == (PAUL, False)
    texte, erreur = await appeler(outils, "memoire_lire", chemin="projets/site-web.md")
    assert erreur is True and "n'existe pas" in texte


async def test_chercher_rend_les_lignes_ou_rien_trouve(outils):
    await appeler(outils, "memoire_ecrire", chemin="personnes/paul-durand.md", contenu=PAUL)
    assert await appeler(outils, "memoire_chercher", texte="jeudi") == (
        "personnes/paul-durand.md : Prospect ; rendez-vous le jeudi 2 octobre 2026.",
        False,
    )
    assert await appeler(outils, "memoire_chercher", texte="Zoé") == ("Rien trouvé.", False)


async def test_annuler_s_annonce_et_rien_a_annuler_est_un_refus(outils):
    await appeler(outils, "memoire_ecrire", chemin="personnes/paul-durand.md", contenu=PAUL)
    outils.prendre_les_annonces()
    assert await appeler(outils, "memoire_annuler") == (
        "La note « Paul Durand » est retirée.",
        False,
    )
    assert outils.prendre_les_annonces() == [Note(ANNONCE_RETRAIT)]
    texte, erreur = await appeler(outils, "memoire_annuler")
    assert erreur is True and "plus de note" in texte
    assert outils.prendre_les_annonces() == []


async def test_pendant_le_resume_rien_ne_s_ecrit_mais_tout_se_lit(outils):
    await appeler(outils, "memoire_ecrire", chemin="personnes/paul-durand.md", contenu=PAUL)
    outils.prendre_les_annonces()
    outils.ecriture_permise = False
    assert await appeler(
        outils, "memoire_ecrire", chemin="profil.md", contenu="# Profil\n\nD.\n"
    ) == (
        PENDANT_LE_RESUME,
        True,
    )
    assert await appeler(outils, "memoire_annuler") == (PENDANT_LE_RESUME, True)
    assert not (outils.memoire.racine / "profil.md").exists()
    assert outils.memoire.lire("personnes/paul-durand.md") == PAUL
    assert await appeler(outils, "memoire_lire", chemin="personnes/paul-durand.md") == (PAUL, False)
    assert outils.prendre_les_annonces() == []


async def test_une_panne_du_depot_revient_a_claude_et_se_note_au_journal(
    outils, monkeypatch, caplog
):
    def panne(chemin, contenu):
        raise OSError("disque plein")

    monkeypatch.setattr(outils.memoire, "ecrire", panne)
    assert await appeler(outils, "memoire_ecrire", chemin="profil.md", contenu="# P\n\nD.\n") == (
        ECHEC,
        True,
    )
    assert "un outil de la mémoire a échoué" in caplog.text
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `uv run pytest tests/test_outils_memoire.py -q`
Expected: FAIL — erreur de collecte : `ImportError: cannot import name 'Note' from 'atlas_core.cerveau'`.

- [ ] **Step 3: Écrire les outils**

Modifier `src/atlas_core/cerveau.py` :

```diff
--- a/src/atlas_core/cerveau.py
+++ b/src/atlas_core/cerveau.py
@@ -81,14 +81,23 @@ class Recherche:
 RECHERCHE = Recherche()
 
 
+@dataclass(frozen=True)
+class Note:
+    """Dans le flux d'une réponse : Atlas vient d'écrire dans sa mémoire ; `annonce` est la
+    phrase à dire (« Je le note dans la fiche Paul Durand. »)."""
+
+    annonce: str
+
+
 class ErreurCerveau(Exception):
     """Le cerveau n'a pas pu répondre. Le message est en français, prêt à être dit."""
 
 
 class Cerveau(Protocol):
-    def repondre(self, texte: str) -> AsyncIterator[str | Recherche]:
-        """Rend la réponse en fragments de texte, au fil de l'eau, et signale une recherche
-        sur le web par `RECHERCHE`. Lève `ErreurCerveau` si la réponse est impossible.
+    def repondre(self, texte: str) -> AsyncIterator[str | Recherche | Note]:
+        """Rend la réponse en fragments de texte, au fil de l'eau ; signale une recherche
+        sur le web par `RECHERCHE`, et une écriture dans la mémoire par une `Note`. Lève
+        `ErreurCerveau` si la réponse est impossible.
 
         Fermer le flux avant la fin (`aclose`) abandonne la réponse."""
         ...
```

Créer `src/atlas_core/outils_memoire.py` :

```python
"""Le serveur d'outils d'Atlas : les quatre outils de la mémoire, que Claude appelle.

Il tourne dans le Core, par le SDK de Claude (`create_sdk_mcp_server`). Chaque écriture
passe par `Memoire`, qui la vérifie et la commite ; l'outil garde pour le cerveau la
phrase qui l'annoncera (`Note`). La phase 2c y ajoutera ses outils et ses niveaux
d'autorisation.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from claude_agent_sdk import SdkMcpTool, create_sdk_mcp_server, tool
from claude_agent_sdk.types import McpSdkServerConfig

from .cerveau import Note
from .memoire import ErreurMemoire, Memoire

_journal = logging.getLogger(__name__)

SERVEUR = "atlas"
ANNONCE_PROFIL = "Je le note dans ton profil."
ANNONCE_RETRAIT = "J'ai retiré ma dernière note."
PENDANT_LE_RESUME = "La conversation se résume : rien ne s'écrit maintenant."
ECHEC = "La mémoire n'a pas pu faire ça : une erreur est notée dans le journal du Core."

LIRE = (
    "Lit un fichier de ta mémoire : profil.md, une fiche (entreprise/, projets/ ou "
    "personnes/ suivi du nom) ou un jour du journal (journal/AAAA-MM-JJ.md). Lis une fiche "
    "avant de la modifier."
)
CHERCHER = (
    "Cherche un mot ou un nom dans tes fiches et ton journal, sans tenir compte des "
    "majuscules ni des accents. Rend au plus vingt lignes, chacune avec son fichier."
)
ECRIRE = (
    "Crée ou remplace une fiche entière de ta mémoire : profil.md, ou entreprise/<nom>.md, "
    "projets/<nom>.md, personnes/<nom>.md, le nom en minuscules, chiffres et tirets. Le "
    "contenu commence par « # Titre », une ligne vide, puis une phrase de résumé ; le reste "
    "est libre. Atlas annonce l'écriture à David : ne l'annonce pas toi-même."
)
ANNULER = (
    "Retire ta dernière note encore en place, quand David dit « annule », « oublie ça » ou "
    "« ne note pas ça ». Rappeler cet outil remonte d'une note. Atlas le dit à David."
)

Gestionnaire = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


def annonce_de(chemin: str, titre: str) -> str:
    return ANNONCE_PROFIL if chemin == "profil.md" else f"Je le note dans la fiche {titre}."


def _texte(texte: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": texte}]}


def _refus(texte: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": texte}], "is_error": True}


def _protege(gestionnaire: Gestionnaire) -> Gestionnaire:
    """Un refus de la mémoire revient à Claude, qui le dit à David ; une panne aussi,
    notée en plus dans le journal du Core."""

    async def enveloppe(arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            return await gestionnaire(arguments)
        except ErreurMemoire as e:
            return _refus(str(e))
        except Exception:
            _journal.exception("un outil de la mémoire a échoué")
            return _refus(ECHEC)

    return enveloppe


class OutilsMemoire:
    def __init__(self, memoire: Memoire) -> None:
        self.memoire = memoire
        self.ecriture_permise = True  # False pendant le résumé d'une conversation
        self._annonces: list[Note] = []
        self.outils: list[SdkMcpTool] = [
            tool("memoire_lire", LIRE, {"chemin": str})(_protege(self._lire)),
            tool("memoire_chercher", CHERCHER, {"texte": str})(_protege(self._chercher)),
            tool("memoire_ecrire", ECRIRE, {"chemin": str, "contenu": str})(_protege(self._ecrire)),
            tool("memoire_annuler", ANNULER, {})(_protege(self._annuler)),
        ]

    @property
    def noms(self) -> list[str]:
        """Les noms sous lesquels Claude voit ces outils."""
        return [f"mcp__{SERVEUR}__{outil.name}" for outil in self.outils]

    def serveur(self) -> McpSdkServerConfig:
        return create_sdk_mcp_server(SERVEUR, tools=self.outils)

    def prendre_les_annonces(self) -> list[Note]:
        """Les écritures faites depuis le dernier appel, à annoncer dans l'ordre."""
        annonces, self._annonces = self._annonces, []
        return annonces

    async def _lire(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return _texte(await asyncio.to_thread(self.memoire.lire, arguments["chemin"]))

    async def _chercher(self, arguments: dict[str, Any]) -> dict[str, Any]:
        lignes = await asyncio.to_thread(self.memoire.chercher, arguments["texte"])
        return _texte("\n".join(lignes) if lignes else "Rien trouvé.")

    async def _ecrire(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if not self.ecriture_permise:
            return _refus(PENDANT_LE_RESUME)
        chemin = arguments["chemin"]
        titre = await asyncio.to_thread(self.memoire.ecrire, chemin, arguments["contenu"])
        if titre is None:
            return _texte("La fiche était déjà ainsi : rien n'a changé.")
        self._annonces.append(Note(annonce_de(chemin, titre)))
        return _texte(f"C'est noté dans {chemin}.")

    async def _annuler(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if not self.ecriture_permise:
            return _refus(PENDANT_LE_RESUME)
        titre = await asyncio.to_thread(self.memoire.annuler)
        self._annonces.append(Note(ANNONCE_RETRAIT))
        return _texte(f"La note « {titre} » est retirée.")
```

- [ ] **Step 4: Vérifier que tout passe**

Run: `uv run pytest -q && uv run ruff check . --extend-exclude spikes && uv run ruff format --check . --extend-exclude spikes && node --test "tests/web/*.test.mjs"`
Expected: 758 tests Python passent, 126 tests JavaScript passent, ruff ne dit rien.

- [ ] **Step 5: Commit**

```bash
git add src/atlas_core/cerveau.py src/atlas_core/outils_memoire.py tests/test_outils_memoire.py
git commit -F - <<'MSG'
Mémoire : les quatre outils du serveur « atlas », et l'annonce d'une note

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

### Task 5: Les consignes avec mémoire, et les options de Claude

Ce que Claude doit savoir de sa mémoire (l'amorçage, quand et comment noter, des faits qui restent vrais, « annule »,
comment appeler David, jamais de secret), la demande de résumé, et les options qui lui donnent les quatre outils.
Sans mémoire, les consignes de la 2a restent les mêmes, mot pour mot.

**Files:**
- Modify: `src/atlas_core/cerveau_claude.py`
- Modify: `src/atlas_core/consignes.py`
- Modify: `tests/test_cerveau_claude.py`
- Modify: `tests/test_consignes.py`

**Interfaces:**
- Consumes: Task 4 (`OutilsMemoire.noms`, `serveur()`, `SERVEUR`).
- Produces: `consignes.CONSIGNES` (inchangées), `CONSIGNES_AVEC_MEMOIRE`, `DEMANDE_RESUME`, `RIEN = "RIEN"` ;
  `options_cerveau(modele, dossier, outils: OutilsMemoire | None = None)` : avec les outils,
  `allowed_tools == ["WebSearch", *outils.noms]`, `mcp_servers == {"atlas": outils.serveur()}`,
  `system_prompt == CONSIGNES_AVEC_MEMOIRE` ; `tools == ["WebSearch"]` dans tous les cas.

- [ ] **Step 1: Écrire les tests qui échouent**

Modifier `tests/test_cerveau_claude.py` :

```diff
--- a/tests/test_cerveau_claude.py
+++ b/tests/test_cerveau_claude.py
@@ -4,6 +4,7 @@ messages réalistes (deltas de texte, appel à la recherche web, message de fin,
 import asyncio
 import dataclasses
 import datetime as dt
+import json
 
 import pytest
 from claude_agent_sdk import (
@@ -32,7 +33,9 @@ from atlas_core.cerveau_claude import (
     options_cerveau,
     purger_cles_api,
 )
-from atlas_core.consignes import CONSIGNES
+from atlas_core.consignes import CONSIGNES, CONSIGNES_AVEC_MEMOIRE
+from atlas_core.memoire import Memoire
+from atlas_core.outils_memoire import OutilsMemoire
 
 MOMENT = dt.datetime(2026, 9, 24, 21, 50)
 
@@ -470,6 +473,36 @@ def test_la_ligne_de_commande_du_cli_porte_ces_limites(tmp_path):
     assert "WebFetch" not in " ".join(commande)
 
 
+def test_avec_la_memoire_claude_gagne_ses_quatre_outils_et_rien_d_autre(tmp_path):
+    outils = OutilsMemoire(Memoire.ouvrir(tmp_path / "memoire"))
+    options = options_cerveau("claude-sonnet-5", tmp_path, outils)
+    assert options.tools == ["WebSearch"]
+    assert options.allowed_tools == ["WebSearch", *outils.noms]
+    assert list(options.mcp_servers) == ["atlas"]
+    assert options.mcp_servers["atlas"]["type"] == "sdk"
+    assert options.system_prompt == CONSIGNES_AVEC_MEMOIRE
+    assert options.setting_sources == [] and options.strict_mcp_config is True
+
+
+def test_la_ligne_de_commande_avec_la_memoire_ne_porte_que_le_serveur_atlas(tmp_path):
+    from claude_agent_sdk._internal.transport.subprocess_cli import SubprocessCLITransport
+
+    outils = OutilsMemoire(Memoire.ouvrir(tmp_path / "memoire"))
+    options = options_cerveau("claude-sonnet-5", tmp_path, outils)
+    options = dataclasses.replace(options, cli_path="claude")
+    commande = SubprocessCLITransport(prompt=None, options=options)._build_command()
+
+    def valeur(drapeau: str) -> str:
+        return commande[commande.index(drapeau) + 1]
+
+    assert valeur("--tools") == "WebSearch"
+    assert valeur("--allowedTools").split(",") == ["WebSearch", *outils.noms]
+    assert json.loads(valeur("--mcp-config")) == {
+        "mcpServers": {"atlas": {"type": "sdk", "name": "atlas"}}
+    }
+    assert "--strict-mcp-config" in commande
+
+
 def test_les_cles_d_api_sont_retirees_mais_pas_le_jeton_d_abonnement():
     environnement = {
         "ANTHROPIC_API_KEY": "sk-secret",
```

Modifier `tests/test_consignes.py` :

```diff
--- a/tests/test_consignes.py
+++ b/tests/test_consignes.py
@@ -2,7 +2,15 @@ import datetime as dt
 
 import pytest
 
-from atlas_core.consignes import CONSIGNES, date_en_lettres, heure_en_chiffres, ligne_de_date
+from atlas_core.consignes import (
+    CONSIGNES,
+    CONSIGNES_AVEC_MEMOIRE,
+    DEMANDE_RESUME,
+    RIEN,
+    date_en_lettres,
+    heure_en_chiffres,
+    ligne_de_date,
+)
 
 
 @pytest.mark.parametrize(
@@ -39,5 +47,42 @@ def test_les_consignes_tiennent_les_decisions_de_la_spec():
 
 
 def test_les_consignes_ne_revelent_rien_de_prive():
-    for interdit in ("@", "http", "192.168"):
-        assert interdit not in CONSIGNES.lower(), interdit
+    for consignes in (CONSIGNES, CONSIGNES_AVEC_MEMOIRE, DEMANDE_RESUME):
+        for interdit in ("@", "http", "192.168"):
+            assert interdit not in consignes.lower(), interdit
+
+
+def test_sans_memoire_claude_ne_parle_pas_de_memoire():
+    assert "mémoire" not in CONSIGNES.lower()
+    assert "Tu ne peux rien faire d'autre que réfléchir et chercher sur le web." in CONSIGNES
+
+
+def test_avec_la_memoire_les_consignes_gardent_tout_et_disent_comment_la_tenir():
+    texte = CONSIGNES_AVEC_MEMOIRE.lower()
+    for attendu in (
+        "tutoies",
+        "deux à quatre phrases",
+        "cite le site par son nom",
+        "ne prétends jamais",
+        "[mémoire d'atlas]",
+        "memoire_lire",
+        "memoire_chercher",
+        "memoire_ecrire",
+        "memoire_annuler",
+        "« # titre », une ligne vide, puis une phrase de résumé",
+        "relis une fiche avant de la modifier",
+        "date de naissance approximative",
+        "une date plutôt que « jeudi »",
+        "n'annonce pas que tu notes",
+        "ne note jamais de mot de passe",
+        "comme son profil l'indique",
+        "réfléchir, chercher sur le web et tenir ta mémoire",
+    ):
+        assert attendu in texte, attendu
+
+
+def test_la_demande_de_resume_ne_fait_rien_ecrire_et_admet_rien():
+    assert DEMANDE_RESUME.startswith("[Fin de la conversation]")
+    assert "n'écris rien dans ta mémoire" in DEMANDE_RESUME
+    assert "Ne garde pas ce que David t'a demandé d'oublier" in DEMANDE_RESUME
+    assert DEMANDE_RESUME.endswith(f"réponds seulement : {RIEN}.")
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `uv run pytest tests/test_consignes.py tests/test_cerveau_claude.py -q`
Expected: FAIL — deux erreurs de collecte : `ImportError: cannot import name 'CONSIGNES_AVEC_MEMOIRE' from
'atlas_core.consignes'`.

- [ ] **Step 3: Écrire les consignes et les options**

Modifier `src/atlas_core/cerveau_claude.py` :

```diff
--- a/src/atlas_core/cerveau_claude.py
+++ b/src/atlas_core/cerveau_claude.py
@@ -37,7 +37,8 @@ from claude_agent_sdk import (
 )
 
 from .cerveau import RECHERCHE, ErreurCerveau, Recherche
-from .consignes import CONSIGNES, ligne_de_date
+from .consignes import CONSIGNES, CONSIGNES_AVEC_MEMOIRE, ligne_de_date
+from .outils_memoire import SERVEUR, OutilsMemoire
 
 _journal = logging.getLogger(__name__)
 
@@ -58,15 +59,18 @@ _ERREURS_ASSISTANT = {
 }
 
 
-def options_cerveau(modele: str, dossier: Path) -> ClaudeAgentOptions:
-    """Claude enfermé dans son rôle : la recherche web pour seul outil, aucun réglage ni
-    `CLAUDE.md` de la machine, aucun serveur MCP, un dossier de travail vide."""
+def options_cerveau(
+    modele: str, dossier: Path, outils: OutilsMemoire | None = None
+) -> ClaudeAgentOptions:
+    """Claude enfermé dans son rôle : la recherche web, et les outils de sa mémoire s'il en
+    a une ; aucun réglage ni `CLAUDE.md` de la machine, aucun autre serveur MCP, un
+    dossier de travail vide."""
     return ClaudeAgentOptions(
         tools=[OUTIL_RECHERCHE],
-        allowed_tools=[OUTIL_RECHERCHE],
-        system_prompt=CONSIGNES,
+        allowed_tools=[OUTIL_RECHERCHE, *(outils.noms if outils else [])],
+        system_prompt=CONSIGNES_AVEC_MEMOIRE if outils else CONSIGNES,
         setting_sources=[],
-        mcp_servers={},
+        mcp_servers={SERVEUR: outils.serveur()} if outils else {},
         strict_mcp_config=True,
         include_partial_messages=True,
         model=modele,
```

Modifier `src/atlas_core/consignes.py` :

```diff
--- a/src/atlas_core/consignes.py
+++ b/src/atlas_core/consignes.py
@@ -1,14 +1,16 @@
-"""Les consignes d'Atlas (l'invite système de Claude) et la ligne de date.
+"""Les consignes d'Atlas (l'invite système de Claude), la demande de résumé et la ligne de
+date.
 
 Claude ne sait pas l'heure qu'il est : chaque question part précédée d'une ligne de
-contexte, « [jeudi 24 septembre 2026, 21 h 50] ».
+contexte, « [jeudi 24 septembre 2026, 21 h 50] ». Avec la mémoire, la première question
+d'une conversation part en plus précédée de ce qu'Atlas sait déjà (voir `memoire.py`).
 """
 
 from __future__ import annotations
 
 import datetime as dt
 
-CONSIGNES = """\
+_ESSENTIEL = """\
 Tu es Atlas, l'assistant vocal de David. Tu parles français et tu tutoies David.
 
 Tout ce que tu écris est lu à voix haute par une synthèse vocale. Écris donc seulement \
@@ -29,13 +31,63 @@ Tu peux chercher sur le web, quand la question porte sur l'actualité, la mété
 horaires ou un fait dont tu n'es pas sûr. N'annonce pas ta recherche : Atlas prévient \
 David pour toi. Quand tu t'appuies sur une page, cite le site par son nom, par exemple \
 « d'après Météo-France », jamais par son adresse.
+"""
+
+_NE_PRETENDS_PAS = """\
+Ne prétends jamais avoir fait une action, comme envoyer un message, régler un minuteur ou \
+allumer une lumière : si on te le demande, dis simplement que tu ne sais pas encore le \
+faire. Si tu ne sais pas quelque chose, dis-le.
+"""
 
-Tu ne peux rien faire d'autre que réfléchir et chercher sur le web. Ne prétends jamais \
-avoir fait une action, comme envoyer un message, régler un minuteur ou allumer une \
-lumière : si on te le demande, dis simplement que tu ne sais pas encore le faire. Si tu \
-ne sais pas quelque chose, dis-le.
+_MEMOIRE = """
+Tu as une mémoire, faite de fichiers : le profil de David (profil.md), et des fiches sur \
+l'entreprise (entreprise/), les projets (projets/) et les personnes (personnes/). La \
+première question de chaque conversation commence, avant la ligne de date, par un bloc \
+entre « [Mémoire d'Atlas] » et « [Fin de la mémoire] » : le profil, le sommaire de tes \
+fiches et le journal des derniers jours. C'est ce que tu sais déjà. Pour le détail, lis \
+une fiche avec memoire_lire, ou cherche avec memoire_chercher.
+
+Note de toi-même ce qui mérite d'être gardé : une décision, un fait durable sur David, \
+un projet ou une personne, une préférence de David ; pas les banalités, ni ce qui ne sert \
+qu'à la question du moment. Écris avec memoire_ecrire des fiches courtes, qui commencent \
+par « # Titre », une ligne vide, puis une phrase de résumé. Relis une fiche avant de la \
+modifier : l'écriture la remplace en entier.
+
+Écris les faits sous une forme qui reste vraie : une date de naissance approximative \
+plutôt qu'un âge (« né vers mars 2025 »), une date plutôt que « jeudi » (« le jeudi \
+2 octobre 2026 »). Tu calcules les âges et les délais avec la date du jour.
+
+N'annonce pas que tu notes : Atlas le dit pour toi. Si David dit « annule », « oublie \
+ça » ou « ne note pas ça » juste après une note, appelle memoire_annuler. Ne note \
+jamais de mot de passe ni de clé secrète.
+
+Appelle David comme son profil l'indique, et « David » tant que le profil ne dit rien \
+d'autre.
 """
 
+CONSIGNES = (
+    _ESSENTIEL
+    + "\nTu ne peux rien faire d'autre que réfléchir et chercher sur le web. "
+    + _NE_PRETENDS_PAS
+)
+CONSIGNES_AVEC_MEMOIRE = (
+    _ESSENTIEL
+    + _MEMOIRE
+    + "\nTu ne peux rien faire d'autre que réfléchir, chercher sur le web et tenir ta "
+    + "mémoire. "
+    + _NE_PRETENDS_PAS
+)
+
+# Le résumé d'une conversation qui se termine, pour le journal (spec 2b §7).
+RIEN = "RIEN"
+DEMANDE_RESUME = (
+    "[Fin de la conversation] La conversation est terminée ; ceci n'est pas une question "
+    "de David. Résume-la pour ton journal, en quelques phrases : ce qui s'est dit, ce qui "
+    "a été décidé, ce qui reste à faire. Ne garde pas ce que David t'a demandé d'oublier "
+    "ou de ne pas noter. N'invente rien et n'écris rien dans ta mémoire. "
+    f"S'il n'y a rien à garder, réponds seulement : {RIEN}."
+)
+
 _JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
 _MOIS = (
     "janvier",
```

- [ ] **Step 4: Vérifier que tout passe**

Run: `uv run pytest -q && uv run ruff check . --extend-exclude spikes && uv run ruff format --check . --extend-exclude spikes && node --test "tests/web/*.test.mjs"`
Expected: 763 tests Python passent, 126 tests JavaScript passent, ruff ne dit rien.

- [ ] **Step 5: Commit**

```bash
git add src/atlas_core/cerveau_claude.py src/atlas_core/consignes.py tests/test_cerveau_claude.py tests/test_consignes.py
git commit -F - <<'MSG'
Cerveau : consignes de la mémoire, demande de résumé, outils dans les options

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

### Task 6: Le cerveau : l'amorçage et les annonces

La première question de chaque conversation part avec ce qu'Atlas sait déjà ; les écritures dans la mémoire sont
rendues à leur place dans la réponse, et une réponse coupée garde les siennes pour la suivante. La doublure du SDK
apprend à exécuter un appel d'outil au milieu d'un tour.

**Files:**
- Modify: `src/atlas_core/cerveau_claude.py`
- Modify: `tests/test_cerveau_claude.py`
- Create: `tests/test_cerveau_memoire.py`

**Interfaces:**
- Consumes: Tasks 3–5 (`Memoire.amorcage`, `OutilsMemoire.prendre_les_annonces`, `Note`).
- Produces: `CerveauClaude(fabrique, oubli_s=…, horloge=…, maintenant=…, outils: OutilsMemoire | None = None)` ;
  `repondre` rend `str | Recherche | Note`. Dans `tests/test_cerveau_claude.py`, la doublure `FauxClientClaude`
  exécute tout élément appelable d'un tour (un outil) ; `tests/test_cerveau_memoire.py` fournit `AppelOutil`,
  repris par la Task 7.

- [ ] **Step 1: Écrire les tests qui échouent**

Modifier `tests/test_cerveau_claude.py` :

```diff
--- a/tests/test_cerveau_claude.py
+++ b/tests/test_cerveau_claude.py
@@ -140,6 +140,9 @@ class FauxClientClaude:
                 continue
             if isinstance(message, BaseException):
                 raise message
+            if callable(message):
+                await message()  # un outil que Claude appelle : le SDK l'exécute
+                continue
             yield message
             if isinstance(message, ResultMessage):
                 return
```

Créer `tests/test_cerveau_memoire.py` :

```python
"""Le cerveau avec sa mémoire : l'amorçage des conversations et l'annonce des écritures, avec
la doublure du SDK de `test_cerveau_claude.py` et une vraie mémoire sur un dépôt temporaire."""

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

from atlas_core.cerveau import Note
from atlas_core.cerveau_claude import CerveauClaude
from atlas_core.memoire import Memoire
from atlas_core.outils_memoire import ANNONCE_PROFIL, OutilsMemoire

DATE = "[jeudi 24 septembre 2026, 21 h 50]"
PROFIL = "# Profil\n\nDavid, à appeler Dieu.\n"


@pytest.fixture
def outils(tmp_path) -> OutilsMemoire:
    outils = OutilsMemoire(Memoire.ouvrir(tmp_path / "memoire"))
    outils.memoire.ecrire("profil.md", PROFIL)
    return outils


class AppelOutil:
    """Claude appelle un outil au milieu d'un tour : le SDK exécute son gestionnaire."""

    def __init__(self, outils: OutilsMemoire, nom: str, **arguments) -> None:
        self._outil = next(o for o in outils.outils if o.name == nom)
        self._arguments = arguments

    async def __call__(self) -> None:
        await self._outil.handler(self._arguments)


def _cerveau(outils, *clients, temps=None) -> CerveauClaude:
    return CerveauClaude(
        Fabrique(*clients),
        oubli_s=30 * 60,
        horloge=temps or Temps(),
        maintenant=lambda: MOMENT,
        outils=outils,
    )


async def _tout(cerveau: CerveauClaude, texte: str) -> list:
    async def lire() -> list:
        return [f async for f in cerveau.repondre(texte)]

    return await asyncio.wait_for(lire(), timeout=2)


# --- l'amorçage ----------------------------------------------------------------------


async def test_la_premiere_question_d_une_conversation_part_avec_la_memoire(outils):
    client = FauxClientClaude(reponse("Oui."), reponse("Bien sûr."))
    cerveau = _cerveau(outils, client)
    await _tout(cerveau, "Tu te souviens de moi ?")
    await _tout(cerveau, "Et de mon nom ?")
    amorcage = outils.memoire.amorcage(MOMENT.date())
    assert amorcage.startswith("[Mémoire d'Atlas]") and "à appeler Dieu" in amorcage
    assert client.questions == [
        f"{amorcage}\n{DATE}\nTu te souviens de moi ?",
        f"{DATE}\nEt de mon nom ?",
    ]


async def test_une_conversation_neuve_repart_avec_la_memoire_du_moment(outils):
    temps = Temps()
    ancien = FauxClientClaude(reponse("Un."))
    neuf = FauxClientClaude(reponse("Deux."))
    cerveau = _cerveau(outils, ancien, neuf, temps=temps)
    await _tout(cerveau, "un")
    outils.memoire.ecrire("personnes/paul-durand.md", "# Paul Durand\n\nProspect.\n")
    temps.t += 30 * 60
    await _tout(cerveau, "deux")
    assert neuf.questions[0].startswith("[Mémoire d'Atlas]")
    assert "- personnes/paul-durand.md : Prospect." in neuf.questions[0]


async def test_un_claude_relance_en_pleine_conversation_recoit_la_memoire(outils):
    mort = FauxClientClaude(reponse("Un."))
    relance = FauxClientClaude(reponse("Deux."))
    cerveau = _cerveau(outils, mort, relance)
    await _tout(cerveau, "un")
    mort.echec_question = OSError("processus mort")
    await _tout(cerveau, "deux")
    assert relance.questions[0].startswith("[Mémoire d'Atlas]")


async def test_une_memoire_illisible_n_empeche_pas_de_repondre(outils, monkeypatch, caplog):
    def illisible(aujourd_hui):
        raise OSError("disque débranché")

    monkeypatch.setattr(outils.memoire, "amorcage", illisible)
    client = FauxClientClaude(reponse("Oui."))
    assert await _tout(_cerveau(outils, client), "Tu m'entends ?") == ["Oui."]
    assert client.questions == [f"{DATE}\nTu m'entends ?"]
    assert "amorçage de la mémoire impossible" in caplog.text


# --- les annonces ------------------------------------------------------------------


async def test_une_ecriture_s_annonce_a_sa_place_dans_la_reponse(outils):
    tour = [
        debut_texte(),
        delta("D'accord."),
        AppelOutil(
            outils, "memoire_ecrire", chemin="profil.md", contenu=PROFIL + "\nDeux enfants.\n"
        ),
        debut_texte(),
        delta("Autre chose ?"),
        fin(),
    ]
    fragments = await _tout(_cerveau(outils, FauxClientClaude(tour)), "Note mes enfants.")
    assert fragments == ["D'accord.", Note(ANNONCE_PROFIL), " Autre chose ?"]


async def test_une_ecriture_refusee_ne_s_annonce_pas(outils):
    tour = [
        AppelOutil(outils, "memoire_ecrire", chemin="profil.md", contenu="mot de passe : x"),
        debut_texte(),
        delta("Je ne peux pas noter ça."),
        fin(),
    ]
    fragments = await _tout(_cerveau(outils, FauxClientClaude(tour)), "Note mon mot de passe.")
    assert fragments == ["Je ne peux pas noter ça."]


async def test_une_note_d_une_reponse_abandonnee_s_annonce_au_debut_de_la_suivante(outils):
    fiche = "# Paul Durand\n\nProspect.\n"
    client = FauxClientClaude(
        [
            debut_texte(),
            delta("Je le note, "),
            AppelOutil(outils, "memoire_ecrire", chemin="personnes/paul-durand.md", contenu=fiche),
            BLOQUE,
            delta("jamais lu"),
            fin(),
        ],
        reponse("Oui."),
    )
    cerveau = _cerveau(outils, client)
    flux = cerveau.repondre("Note Paul.")
    assert await anext(flux) == "Je le note, "
    await flux.aclose()  # la session lâche la réponse ; le ménage lit le reste
    fragments = await _tout(cerveau, "Tu as noté ?")
    assert fragments == [Note("Je le note dans la fiche Paul Durand."), "Oui."]


async def test_une_note_d_une_reponse_coupee_par_une_autre_question_passe_a_celle_ci(outils):
    ecriture = AppelOutil(
        outils, "memoire_ecrire", chemin="profil.md", contenu=PROFIL + "\nDeux enfants.\n"
    )
    client = FauxClientClaude(
        [debut_texte(), delta("Première "), ecriture, BLOQUE, delta("jamais"), fin()],
        reponse("Seconde."),
    )
    cerveau = _cerveau(outils, client)
    premiere: list = []

    async def lire_la_premiere() -> None:
        async for fragment in cerveau.repondre("une"):
            premiere.append(fragment)

    tache = asyncio.create_task(lire_la_premiere())
    while not premiere:
        await asyncio.sleep(0)
    assert await _tout(cerveau, "deux") == [Note(ANNONCE_PROFIL), "Seconde."]
    await tache
    assert premiere == ["Première "]


async def test_sans_memoire_le_cerveau_ne_recoit_ni_amorcage_ni_outils():
    client = FauxClientClaude(reponse("Oui."))
    cerveau = CerveauClaude(Fabrique(client), maintenant=lambda: MOMENT)
    assert await _tout(cerveau, "Tu m'entends ?") == ["Oui."]
    assert client.questions == [f"{DATE}\nTu m'entends ?"]
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `uv run pytest tests/test_cerveau_claude.py tests/test_cerveau_memoire.py -q`
Expected: FAIL — 8 échecs : `TypeError: CerveauClaude.__init__() got an unexpected keyword argument 'outils'`.

- [ ] **Step 3: Écrire l'amorçage et les annonces**

Modifier `src/atlas_core/cerveau_claude.py` :

```diff
--- a/src/atlas_core/cerveau_claude.py
+++ b/src/atlas_core/cerveau_claude.py
@@ -36,7 +36,7 @@ from claude_agent_sdk import (
     ToolUseBlock,
 )
 
-from .cerveau import RECHERCHE, ErreurCerveau, Recherche
+from .cerveau import RECHERCHE, ErreurCerveau, Note, Recherche
 from .consignes import CONSIGNES, CONSIGNES_AVEC_MEMOIRE, ligne_de_date
 from .outils_memoire import SERVEUR, OutilsMemoire
 
@@ -118,8 +118,11 @@ class CerveauClaude:
         oubli_s: float = 30 * 60,
         horloge: Callable[[], float] = time.monotonic,
         maintenant: Callable[[], dt.datetime] = dt.datetime.now,
+        outils: OutilsMemoire | None = None,
     ) -> None:
         self._fabrique = fabrique
+        self._outils = outils
+        self._client_amorce: ClientClaude | None = None  # sa conversation a reçu la mémoire
         self._oubli_s = oubli_s
         self._horloge = horloge
         self._maintenant = maintenant
@@ -131,7 +134,7 @@ class CerveauClaude:
         self._fil_perdu = False  # la conversation a été perdue : la réponse suivante le dit
         self._menage: asyncio.Task | None = None
 
-    async def repondre(self, texte: str) -> AsyncIterator[str | Recherche]:
+    async def repondre(self, texte: str) -> AsyncIterator[str | Recherche | Note]:
         if self._verrou.locked():
             # Une question à la fois : celle-ci, d'où qu'elle vienne, coupe celle en cours.
             await self._interrompre_le_tour()
@@ -180,6 +183,11 @@ class CerveauClaude:
         return client
 
     async def _envoyer(self, client: ClientClaude, question: str) -> None:
+        amorcer = self._outils is not None and client is not self._client_amorce
+        if amorcer:
+            # La première question d'une conversation part avec ce qu'Atlas sait déjà.
+            amorcage = await self._amorcage()
+            question = f"{amorcage}\n{question}" if amorcage else question
         # Ouvert avant l'envoi : une question annulée pendant l'écriture laisse peut-être
         # un tour en route chez Claude, que le ménage doit alors refermer.
         self._tour_ouvert = True
@@ -188,6 +196,16 @@ class CerveauClaude:
         except Exception:
             self._tour_ouvert = False
             raise
+        if amorcer:
+            self._client_amorce = client
+
+    async def _amorcage(self) -> str:
+        try:
+            memoire = self._outils.memoire
+            return await asyncio.to_thread(memoire.amorcage, self._maintenant().date())
+        except Exception:  # noqa: BLE001 — une mémoire illisible n'empêche pas de répondre
+            _journal.exception("amorçage de la mémoire impossible")
+            return ""
 
     async def _client_pret(self) -> ClientClaude:
         dernier = self._dernier_echange
@@ -216,7 +234,7 @@ class CerveauClaude:
 
     # --- un tour de conversation ---------------------------------------------
 
-    async def _lire_le_tour(self, client: ClientClaude) -> AsyncIterator[str | Recherche]:
+    async def _lire_le_tour(self, client: ClientClaude) -> AsyncIterator[str | Recherche | Note]:
         recherches: set[str] = set()
         texte_rendu = False
         separer = False
@@ -263,6 +281,12 @@ class CerveauClaude:
                         self._tour_ouvert = False
                         if message.is_error and not self._interrompu:
                             raise ErreurCerveau(self._message_resultat(message))
+                    # Une écriture dans la mémoire s'annonce à sa place dans la réponse. Une
+                    # réponse coupée garde ses annonces pour le début de la suivante : une
+                    # écriture ne passe jamais en silence.
+                    if self._outils is not None and not self._interrompu:
+                        for note in self._outils.prendre_les_annonces():
+                            yield note
         except ErreurCerveau:
             raise
         except Exception as e:  # noqa: BLE001 — le SDK ne sait plus où il en est
```

- [ ] **Step 4: Vérifier que tout passe**

Run: `uv run pytest -q && uv run ruff check . --extend-exclude spikes && uv run ruff format --check . --extend-exclude spikes && node --test "tests/web/*.test.mjs"`
Expected: 772 tests Python passent, 126 tests JavaScript passent, ruff ne dit rien.

- [ ] **Step 5: Commit**

```bash
git add src/atlas_core/cerveau_claude.py tests/test_cerveau_claude.py tests/test_cerveau_memoire.py
git commit -F - <<'MSG'
Cerveau : amorçage de chaque conversation et annonces des notes

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

### Task 7: Le cerveau : la fin d'une conversation

Passé le délai d'oubli, une tâche de fond fait résumer la conversation au journal, puis la ferme ; une question la
repousse, ou attend le résumé en cours ; l'arrêt du Core résume aussi. Le délai du résumé, une panne de Claude et
« RIEN » ne cassent rien.

**Files:**
- Modify: `src/atlas_core/cerveau_claude.py`
- Create: `tests/test_cerveau_journal.py`

**Interfaces:**
- Consumes: Tasks 3, 5, 6 (`Memoire.ajouter_au_journal`, `DEMANDE_RESUME`, `RIEN`, `OutilsMemoire.ecriture_permise`,
  l'amorçage, `AppelOutil`).
- Produces: `DELAI_RESUME_S = 60.0`, `DELAI_RESUME_ARRET_S = 20.0` ; `CerveauClaude(…, attendre=asyncio.sleep)` ;
  `_a_l_echeance()`, `_clore_la_conversation(delai)`, `_demander_le_resume(client) -> str` ; `fermer()` résume.

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/test_cerveau_journal.py` :

```python
"""La fin d'une conversation : le résumé au journal à l'échéance de l'oubli, et à l'arrêt du
Core. La doublure du SDK de `test_cerveau_claude.py`, une vraie mémoire sur un dépôt
temporaire, et une minuterie qu'on fait sonner à la main."""

import asyncio
import datetime as dt

import pytest
from test_cerveau_claude import (
    BLOQUE,
    Fabrique,
    FauxClientClaude,
    Temps,
    debut_recherche,
    debut_texte,
    delta,
    fin,
    reponse,
)
from test_cerveau_memoire import AppelOutil

from atlas_core import cerveau_claude
from atlas_core.cerveau import Note
from atlas_core.cerveau_claude import PHRASE_FIL_PERDU, CerveauClaude
from atlas_core.consignes import DEMANDE_RESUME
from atlas_core.memoire import Memoire
from atlas_core.outils_memoire import ANNONCE_PROFIL, OutilsMemoire

JOURNAL = "journal/2026-09-24.md"


class Moment:
    def __init__(self) -> None:
        self.t = dt.datetime(2026, 9, 24, 21, 50)

    def __call__(self) -> dt.datetime:
        return self.t


class Minuterie:
    """Les attentes du cerveau : chacune ne finit que quand le test la fait sonner."""

    def __init__(self) -> None:
        self.delais: list[float] = []
        self._sonneries: list[asyncio.Event] = []

    async def __call__(self, delai: float) -> None:
        self.delais.append(delai)
        sonnerie = asyncio.Event()
        self._sonneries.append(sonnerie)
        await sonnerie.wait()

    def sonner(self, rang: int = -1) -> None:
        self._sonneries[rang].set()


class Attente:
    """Claude met du temps à écrire : le tour reprend quand le test le libère."""

    def __init__(self) -> None:
        self._libre = asyncio.Event()

    async def __call__(self) -> None:
        await self._libre.wait()

    def liberer(self) -> None:
        self._libre.set()


def resume(texte: str) -> list:
    return [debut_texte(), delta(texte), fin()]


@pytest.fixture
def outils(tmp_path) -> OutilsMemoire:
    return OutilsMemoire(Memoire.ouvrir(tmp_path / "memoire"))


def _cerveau(outils, *clients, minuterie=None, moment=None, temps=None) -> CerveauClaude:
    return CerveauClaude(
        Fabrique(*clients),
        oubli_s=30 * 60,
        horloge=temps or Temps(),
        maintenant=moment or Moment(),
        outils=outils,
        attendre=minuterie or Minuterie(),
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


# --- à l'échéance --------------------------------------------------------------------


async def test_a_l_echeance_la_conversation_se_resume_au_journal_puis_se_ferme(outils):
    moment, minuterie = Moment(), Minuterie()
    client = FauxClientClaude(reponse("Midi."), reponse("Oui."), resume("On a parlé du site."))
    cerveau = _cerveau(outils, client, minuterie=minuterie, moment=moment)
    await _tout(cerveau, "Quelle heure est-il ?")
    moment.t += dt.timedelta(minutes=12)
    await _tout(cerveau, "Et le site ?")
    assert minuterie.delais == [30 * 60, 30 * 60]
    minuterie.sonner()
    await _jusqu_a(lambda: client.deconnexions == 1, "la conversation ne s'est pas fermée")
    assert client.questions[-1] == DEMANDE_RESUME
    assert outils.memoire.lire(JOURNAL) == (
        "# Journal du 24 septembre 2026\n\n## 21 h 50 – 22 h 02\n\nOn a parlé du site.\n"
    )


async def test_rien_a_garder_rien_n_est_ecrit(outils):
    minuterie = Minuterie()
    client = FauxClientClaude(reponse("Midi."), resume("RIEN."))
    cerveau = _cerveau(outils, client, minuterie=minuterie)
    await _tout(cerveau, "Quelle heure est-il ?")
    minuterie.sonner()
    await _jusqu_a(lambda: client.deconnexions == 1, "la conversation ne s'est pas fermée")
    assert not (outils.memoire.racine / "journal").exists()


async def test_la_conversation_suivante_part_du_journal(outils):
    minuterie = Minuterie()
    ancien = FauxClientClaude(reponse("Midi."), resume("On a parlé de l'heure."))
    neuf = FauxClientClaude(reponse("Oui."))
    cerveau = _cerveau(outils, ancien, neuf, minuterie=minuterie)
    await _tout(cerveau, "Quelle heure est-il ?")
    minuterie.sonner()
    await _jusqu_a(lambda: ancien.deconnexions == 1, "la conversation ne s'est pas fermée")
    await _tout(cerveau, "De quoi on a parlé ?")
    assert neuf.questions[0].startswith("[Mémoire d'Atlas]")
    assert "On a parlé de l'heure." in neuf.questions[0]


async def test_une_question_avant_l_echeance_la_repousse(outils):
    minuterie = Minuterie()
    client = FauxClientClaude(reponse("Un."), reponse("Deux."), resume("Deux questions."))
    cerveau = _cerveau(outils, client, minuterie=minuterie)
    await _tout(cerveau, "un")
    await _tout(cerveau, "deux")
    minuterie.sonner(0)  # la première échéance, annulée par la deuxième question
    for _ in range(50):
        await asyncio.sleep(0)
    assert DEMANDE_RESUME not in client.questions
    minuterie.sonner(1)
    await _jusqu_a(lambda: client.deconnexions == 1, "la conversation ne s'est pas fermée")


async def test_une_question_pendant_le_resume_l_attend_sans_le_couper(outils):
    minuterie, attente = Minuterie(), Attente()
    ancien = FauxClientClaude(
        reponse("Midi."), [debut_texte(), delta("On a parlé de l'heure."), attente, fin()]
    )
    neuf = FauxClientClaude(reponse("Deux."))
    cerveau = _cerveau(outils, ancien, neuf, minuterie=minuterie)
    await _tout(cerveau, "Quelle heure est-il ?")
    minuterie.sonner()
    await _jusqu_a(lambda: DEMANDE_RESUME in ancien.questions, "le résumé n'est pas demandé")
    question = asyncio.create_task(_tout(cerveau, "deux"))
    for _ in range(50):
        await asyncio.sleep(0)
    assert not question.done() and ancien.interruptions == 0
    attente.liberer()
    assert await question == ["Deux."]
    assert "On a parlé de l'heure." in outils.memoire.lire(JOURNAL)


async def test_pendant_le_resume_claude_ne_peut_rien_ecrire(outils):
    minuterie = Minuterie()
    ecriture = AppelOutil(outils, "memoire_ecrire", chemin="profil.md", contenu="# P\n\nD.\n")
    client = FauxClientClaude(reponse("Midi."), [ecriture, debut_texte(), delta("L'heure."), fin()])
    cerveau = _cerveau(outils, client, minuterie=minuterie)
    await _tout(cerveau, "Quelle heure est-il ?")
    minuterie.sonner()
    await _jusqu_a(lambda: client.deconnexions == 1, "la conversation ne s'est pas fermée")
    assert not (outils.memoire.racine / "profil.md").exists()
    assert outils.ecriture_permise is True


async def test_une_note_en_attente_n_est_pas_mangee_par_le_resume(outils):
    minuterie = Minuterie()
    ecriture = AppelOutil(outils, "memoire_ecrire", chemin="profil.md", contenu="# P\n\nD.\n")
    ancien = FauxClientClaude(
        [debut_texte(), delta("Je le note, "), ecriture, BLOQUE, delta("x"), fin()],
        resume("Le profil."),
    )
    neuf = FauxClientClaude(reponse("Oui."))
    cerveau = _cerveau(outils, ancien, neuf, minuterie=minuterie)
    flux = cerveau.repondre("Note ça.")
    assert await anext(flux) == "Je le note, "
    await flux.aclose()  # réponse lâchée : son annonce attend la suivante
    await _jusqu_a(lambda: minuterie.delais, "l'échéance n'est pas programmée")
    minuterie.sonner()
    await _jusqu_a(lambda: ancien.deconnexions == 1, "la conversation ne s'est pas fermée")
    assert await _tout(cerveau, "Tu as noté ?") == [Note(ANNONCE_PROFIL), "Oui."]


async def test_un_resume_trop_long_est_abandonne(outils, monkeypatch, caplog):
    monkeypatch.setattr(cerveau_claude, "DELAI_RESUME_S", 0.05)
    minuterie = Minuterie()
    ancien = FauxClientClaude(reponse("Midi."), [BLOQUE, fin()])
    neuf = FauxClientClaude(reponse("Oui."))
    cerveau = _cerveau(outils, ancien, neuf, minuterie=minuterie)
    await _tout(cerveau, "Quelle heure est-il ?")
    minuterie.sonner()
    await _jusqu_a(lambda: ancien.deconnexions == 1, "la conversation ne s'est pas fermée")
    assert "résumé de la conversation perdu (TimeoutError)" in caplog.text
    assert not (outils.memoire.racine / "journal").exists()
    assert await _tout(cerveau, "Tu es là ?") == ["Oui."]


async def test_une_panne_de_claude_pendant_le_resume_ne_fait_pas_dire_fil_perdu(outils, caplog):
    minuterie = Minuterie()
    # Le flux se tarit sans message de fin : Claude s'est arrêté en plein résumé.
    ancien = FauxClientClaude(reponse("Midi."), [debut_texte(), delta("On a par")])
    neuf = FauxClientClaude(reponse("Oui."))
    cerveau = _cerveau(outils, ancien, neuf, minuterie=minuterie)
    await _tout(cerveau, "Quelle heure est-il ?")
    minuterie.sonner()
    await _jusqu_a(lambda: ancien.deconnexions == 1, "la conversation ne s'est pas fermée")
    assert "résumé de la conversation perdu (ErreurCerveau)" in caplog.text
    fragments = await _tout(cerveau, "Tu es là ?")
    assert fragments == ["Oui."] and PHRASE_FIL_PERDU + " " not in fragments


async def test_une_recherche_pendant_le_resume_n_entre_pas_au_journal(outils):
    minuterie = Minuterie()
    client = FauxClientClaude(
        reponse("Midi."), [debut_recherche("t9"), debut_texte(), delta("Le site."), fin()]
    )
    cerveau = _cerveau(outils, client, minuterie=minuterie)
    await _tout(cerveau, "Quelle heure est-il ?")
    minuterie.sonner()
    await _jusqu_a(lambda: client.deconnexions == 1, "la conversation ne s'est pas fermée")
    assert outils.memoire.lire(JOURNAL).endswith("\n\nLe site.\n")


async def test_chaque_conversation_a_ses_propres_heures_au_journal(outils):
    moment, minuterie = Moment(), Minuterie()
    ancien = FauxClientClaude(reponse("Un."), resume("La première."))
    neuf = FauxClientClaude(reponse("Deux."), resume("La seconde."))
    cerveau = _cerveau(outils, ancien, neuf, minuterie=minuterie, moment=moment)
    await _tout(cerveau, "un")
    minuterie.sonner()
    await _jusqu_a(lambda: ancien.deconnexions == 1, "la première ne s'est pas fermée")
    moment.t += dt.timedelta(hours=1)
    await _tout(cerveau, "deux")
    minuterie.sonner()
    await _jusqu_a(lambda: neuf.deconnexions == 1, "la seconde ne s'est pas fermée")
    assert "## 22 h 50 – 22 h 50\n\nLa seconde." in outils.memoire.lire(JOURNAL)


async def test_le_resume_attend_le_menage_d_une_reponse_abandonnee(outils, monkeypatch):
    monkeypatch.setattr(cerveau_claude, "DELAI_MENAGE_S", 0.2)
    minuterie = Minuterie()
    client = FauxClientClaude(
        [debut_texte(), delta("Une longue "), BLOQUE, delta("x"), fin()], resume("Rien.")
    )
    client.interruption_sans_effet = True  # le ménage ne finira pas : la conversation se perd
    cerveau = _cerveau(outils, client, minuterie=minuterie)
    flux = cerveau.repondre("Raconte.")
    assert await anext(flux) == "Une longue "
    await flux.aclose()
    await _jusqu_a(lambda: minuterie.delais, "l'échéance n'est pas programmée")
    minuterie.sonner()  # le ménage lit encore : le résumé ne doit pas croiser sa lecture
    await _jusqu_a(lambda: client.deconnexions == 1, "la conversation ne s'est pas fermée")
    for _ in range(20):
        await asyncio.sleep(0.01)
    assert DEMANDE_RESUME not in client.questions


async def test_l_oubli_constate_a_la_question_suivante_resume_aussi(outils):
    temps = Temps()
    ancien = FauxClientClaude(reponse("Midi."), resume("On a parlé de l'heure."))
    neuf = FauxClientClaude(reponse("Oui."))
    cerveau = _cerveau(outils, ancien, neuf, temps=temps)  # la minuterie ne sonne jamais
    await _tout(cerveau, "Quelle heure est-il ?")
    temps.t += 30 * 60
    assert await _tout(cerveau, "De quoi on a parlé ?") == ["Oui."]
    assert "On a parlé de l'heure." in outils.memoire.lire(JOURNAL)
    assert "On a parlé de l'heure." in neuf.questions[0]


# --- à l'arrêt du Core ----------------------------------------------------------------


async def test_a_l_arret_du_core_la_conversation_se_resume(outils):
    moment, minuterie = Moment(), Minuterie()
    client = FauxClientClaude(reponse("Midi."), resume("On a parlé de l'heure."))
    cerveau = _cerveau(outils, client, minuterie=minuterie, moment=moment)
    await _tout(cerveau, "Quelle heure est-il ?")
    await cerveau.fermer()
    assert client.questions[-1] == DEMANDE_RESUME and client.deconnexions == 1
    assert "On a parlé de l'heure." in outils.memoire.lire(JOURNAL)


async def test_l_arret_pendant_un_resume_le_laisse_finir(outils):
    minuterie, attente = Minuterie(), Attente()
    client = FauxClientClaude(
        reponse("Midi."), [debut_texte(), delta("On a parlé de l'heure."), attente, fin()]
    )
    cerveau = _cerveau(outils, client, minuterie=minuterie)
    await _tout(cerveau, "Quelle heure est-il ?")
    minuterie.sonner()
    await _jusqu_a(lambda: DEMANDE_RESUME in client.questions, "le résumé n'est pas demandé")
    arret = asyncio.create_task(cerveau.fermer())
    for _ in range(20):
        await asyncio.sleep(0)
    attente.liberer()
    await arret
    assert "On a parlé de l'heure." in outils.memoire.lire(JOURNAL)
    assert client.questions.count(DEMANDE_RESUME) == 1


async def test_une_conversation_sans_question_ne_se_resume_pas(outils):
    fabrique = Fabrique(FauxClientClaude())
    cerveau = CerveauClaude(fabrique, outils=outils, attendre=Minuterie())
    await cerveau.fermer()
    assert fabrique.creations == 0


async def test_sans_memoire_ni_echeance_ni_resume():
    minuterie = Minuterie()
    client = FauxClientClaude(reponse("Midi."))
    cerveau = CerveauClaude(Fabrique(client), attendre=minuterie)
    await _tout(cerveau, "Quelle heure est-il ?")
    await cerveau.fermer()
    assert minuterie.delais == [] and client.questions == [client.questions[0]]
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `uv run pytest tests/test_cerveau_journal.py -q`
Expected: FAIL — 17 échecs : `TypeError: CerveauClaude.__init__() got an unexpected keyword argument 'attendre'`
(16), et `AttributeError: … has no attribute 'DELAI_RESUME_S'`.

- [ ] **Step 3: Écrire la fin d'une conversation**

Modifier `src/atlas_core/cerveau_claude.py` :

```diff
--- a/src/atlas_core/cerveau_claude.py
+++ b/src/atlas_core/cerveau_claude.py
@@ -9,6 +9,9 @@ Une question à la fois. Une réponse abandonnée en route (interruption, questi
 réveil) laisse un tour ouvert chez Claude : une tâche de ménage l'interrompt et en vide
 les derniers messages, et la question suivante attend ce ménage avant de partir. La
 session, elle, n'attend rien : sa voix se tait tout de suite.
+
+Avec la mémoire, chaque conversation commence par ce qu'Atlas sait déjà, et finit, passé
+le délai d'oubli, par un résumé au journal.
 """
 
 from __future__ import annotations
@@ -19,7 +22,7 @@ import datetime as dt
 import logging
 import shutil
 import time
-from collections.abc import AsyncIterator, Callable, MutableMapping
+from collections.abc import AsyncIterator, Awaitable, Callable, MutableMapping
 from pathlib import Path
 from typing import Any, Protocol
 
@@ -37,13 +40,15 @@ from claude_agent_sdk import (
 )
 
 from .cerveau import RECHERCHE, ErreurCerveau, Note, Recherche
-from .consignes import CONSIGNES, CONSIGNES_AVEC_MEMOIRE, ligne_de_date
+from .consignes import CONSIGNES, CONSIGNES_AVEC_MEMOIRE, DEMANDE_RESUME, RIEN, ligne_de_date
 from .outils_memoire import SERVEUR, OutilsMemoire
 
 _journal = logging.getLogger(__name__)
 
 OUTIL_RECHERCHE = "WebSearch"  # le seul outil de Claude en 2a (pas de WebFetch : spec D3)
 DELAI_MENAGE_S = 15.0
+DELAI_RESUME_S = 60.0  # le résumé d'une conversation, à l'échéance de l'oubli
+DELAI_RESUME_ARRET_S = 20.0  # le même, à l'arrêt du Core
 PHRASE_FIL_PERDU = "Je reprends de zéro, j'ai perdu le fil."
 
 ABSENT = "Claude Code n'est pas installé sur cette machine."
@@ -119,10 +124,16 @@ class CerveauClaude:
         horloge: Callable[[], float] = time.monotonic,
         maintenant: Callable[[], dt.datetime] = dt.datetime.now,
         outils: OutilsMemoire | None = None,
+        attendre: Callable[[float], Awaitable[None]] = asyncio.sleep,
     ) -> None:
         self._fabrique = fabrique
         self._outils = outils
+        self._attendre = attendre
         self._client_amorce: ClientClaude | None = None  # sa conversation a reçu la mémoire
+        self._echeance: asyncio.Task | None = None  # le résumé qui attend le délai d'oubli
+        self._resume_en_cours = False
+        self._debut_conversation: dt.datetime | None = None  # sa première question
+        self._fin_conversation: dt.datetime | None = None  # la fin de son dernier échange
         self._oubli_s = oubli_s
         self._horloge = horloge
         self._maintenant = maintenant
@@ -135,8 +146,12 @@ class CerveauClaude:
         self._menage: asyncio.Task | None = None
 
     async def repondre(self, texte: str) -> AsyncIterator[str | Recherche | Note]:
-        if self._verrou.locked():
+        if self._echeance is not None and not self._resume_en_cours:
+            self._echeance.cancel()  # la conversation continue
+            self._echeance = None
+        if self._verrou.locked() and not self._resume_en_cours:
             # Une question à la fois : celle-ci, d'où qu'elle vienne, coupe celle en cours.
+            # Un résumé en cours, lui, se finit : elle l'attend.
             await self._interrompre_le_tour()
         async with self._verrou:
             await self._attendre_le_menage()
@@ -144,6 +159,7 @@ class CerveauClaude:
             question = f"{ligne_de_date(self._maintenant())}\n{texte}"
             try:
                 client = await self._poser(question)
+                self._debut_conversation = self._debut_conversation or self._maintenant()
                 if self._fil_perdu:
                     self._fil_perdu = False
                     yield PHRASE_FIL_PERDU + " "
@@ -152,18 +168,71 @@ class CerveauClaude:
                         yield fragment
             finally:
                 self._dernier_echange = self._horloge()
+                self._fin_conversation = self._maintenant()
                 if self._tour_ouvert and self._client is not None:
                     # Réponse lâchée en route (ou coupée par une erreur) : le tour doit
                     # finir chez Claude avant la question suivante, sans retenir la session.
                     self._menage = asyncio.create_task(self._vider_le_tour(self._client))
+                if self._outils is not None and self._client is not None:
+                    self._echeance = asyncio.create_task(self._a_l_echeance())
 
     async def fermer(self) -> None:
+        echeance, self._echeance = self._echeance, None
+        if echeance is not None:
+            if not self._resume_en_cours:
+                echeance.cancel()
+            with contextlib.suppress(asyncio.CancelledError, Exception):
+                await echeance  # un résumé en cours se finit (son délai le borne)
         menage, self._menage = self._menage, None
         if menage is not None:
             with contextlib.suppress(Exception):
                 await menage
+        if not self._verrou.locked():
+            await self._clore_la_conversation(DELAI_RESUME_ARRET_S)
+        await self._jeter_le_client()
+
+    # --- la fin d'une conversation -------------------------------------------------
+
+    async def _a_l_echeance(self) -> None:
+        try:
+            await self._attendre(self._oubli_s)
+            async with self._verrou:
+                await self._attendre_le_menage()
+                await self._clore_la_conversation(DELAI_RESUME_S)
+        finally:
+            if self._echeance is asyncio.current_task():
+                self._echeance = None
+
+    async def _clore_la_conversation(self, delai: float) -> None:
+        """Résume la conversation au journal, sans rien en dire, puis la ferme. Sans
+        mémoire, ou sans rien à résumer, elle se ferme simplement."""
+        client, debut, fin = self._client, self._debut_conversation, self._fin_conversation
+        if client is not None and self._outils is not None and debut and fin:
+            self._resume_en_cours = True
+            self._outils.ecriture_permise = False
+            try:
+                async with asyncio.timeout(delai):
+                    resume = await self._demander_le_resume(client)
+                if resume and resume.rstrip(".").upper() != RIEN:
+                    memoire = self._outils.memoire
+                    await asyncio.to_thread(memoire.ajouter_au_journal, debut, fin, resume)
+            except Exception as e:  # noqa: BLE001 — délai, Claude, dépôt : le résumé est perdu
+                _journal.warning("résumé de la conversation perdu (%s)", type(e).__name__)
+            finally:
+                self._outils.ecriture_permise = True
+                self._resume_en_cours = False
+        self._fil_perdu = False  # la conversation se ferme : rien n'est perdu à dire
         await self._jeter_le_client()
 
+    async def _demander_le_resume(self, client: ClientClaude) -> str:
+        await self._envoyer(client, DEMANDE_RESUME)
+        morceaux: list[str] = []
+        async with contextlib.aclosing(self._lire_le_tour(client)) as fragments:
+            async for fragment in fragments:
+                if isinstance(fragment, str):
+                    morceaux.append(fragment)
+        return "".join(morceaux).strip()
+
     # --- le client SDK -------------------------------------------------------
 
     async def _poser(self, question: str) -> ClientClaude:
@@ -212,8 +281,7 @@ class CerveauClaude:
         if dernier is not None and self._horloge() - dernier >= self._oubli_s:
             # L'oubli est voulu : la conversation repart de zéro sans rien en dire.
             _journal.info("longtemps sans échange : nouvelle conversation")
-            self._fil_perdu = False
-            await self._jeter_le_client()
+            await self._clore_la_conversation(DELAI_RESUME_S)
         if self._client is None:
             client = self._fabrique()
             try:
@@ -228,6 +296,7 @@ class CerveauClaude:
     async def _jeter_le_client(self) -> None:
         client, self._client = self._client, None
         self._tour_ouvert = False
+        self._debut_conversation = self._fin_conversation = None
         if client is not None:
             with contextlib.suppress(Exception):
                 await client.disconnect()
@@ -284,7 +353,9 @@ class CerveauClaude:
                     # Une écriture dans la mémoire s'annonce à sa place dans la réponse. Une
                     # réponse coupée garde ses annonces pour le début de la suivante : une
                     # écriture ne passe jamais en silence.
-                    if self._outils is not None and not self._interrompu:
+                    # Le résumé non plus ne les annonce pas : elles attendent la réponse suivante.
+                    annoncer = not (self._interrompu or self._resume_en_cours)
+                    if self._outils is not None and annoncer:
                         for note in self._outils.prendre_les_annonces():
                             yield note
         except ErreurCerveau:
```

- [ ] **Step 4: Vérifier que tout passe**

Run: `uv run pytest -q && uv run ruff check . --extend-exclude spikes && uv run ruff format --check . --extend-exclude spikes && node --test "tests/web/*.test.mjs"`
Expected: 789 tests Python passent, 126 tests JavaScript passent, ruff ne dit rien.

- [ ] **Step 5: Commit**

```bash
git add src/atlas_core/cerveau_claude.py tests/test_cerveau_journal.py
git commit -F - <<'MSG'
Cerveau : résumé de la conversation au journal, à l'échéance et à l'arrêt

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

### Task 8: La session annonce les notes

Une `Note` du cerveau devient une phrase dite (et affichée) à sa place dans la réponse, après ce qui la précède.

**Files:**
- Modify: `src/atlas_core/session.py`
- Modify: `tests/test_session_cerveau.py`

**Interfaces:**
- Consumes: Task 4 (`Note`).
- Produces: rien de neuf ; `Session._repondre` traite `Note` comme `Recherche`.

- [ ] **Step 1: Écrire les tests qui échouent**

Modifier `tests/test_session_cerveau.py` :

```diff
--- a/tests/test_session_cerveau.py
+++ b/tests/test_session_cerveau.py
@@ -1,4 +1,5 @@
-"""La session face au vrai cerveau : recherche web, erreurs dites, mise en voix, fantômes."""
+"""La session face au vrai cerveau : recherche web, notes annoncées, erreurs dites, mise en
+voix, fantômes."""
 
 import asyncio
 from collections.abc import AsyncIterator
@@ -11,7 +12,7 @@ from test_session_web import (
     FauxPlanificateur,
 )
 
-from atlas_core.cerveau import RECHERCHE, ErreurCerveau
+from atlas_core.cerveau import RECHERCHE, ErreurCerveau, Note
 from atlas_core.protocole import Dire, Erreur, Etat, FinEnonce, Interruption, Reveil
 from atlas_core.protocole_web import Reponse
 from atlas_core.session import PHRASE_ATTENTE, Session
@@ -267,6 +268,40 @@ async def test_le_texte_avant_une_recherche_est_dit_avant_l_attente():
     await s.fermer()
 
 
+# --- les notes de la mémoire ------------------------------------------------------------
+
+PROFIL = Note("Je le note dans ton profil.")
+PAUL = Note("Je le note dans la fiche Paul Durand.")
+
+
+async def test_une_note_s_annonce_a_sa_place_dans_la_reponse():
+    c, d = Collecteur(), DiffuseurEspion()
+    s = _session(c, d, CerveauScript("D'accord.", PROFIL, " Autre chose ?"))
+    await s.sur_saisie("Appelle-moi Dieu.")
+    await _attendre(lambda: c.etats()[-1:] == ["repos"])
+    assert _dits(c) == ["D'accord.", "Je le note dans ton profil.", "Autre chose ?"]
+    await s.fermer()
+
+
+async def test_deux_notes_font_deux_annonces():
+    c, d = Collecteur(), DiffuseurEspion()
+    s = _session(c, d, CerveauScript(PROFIL, PAUL, "C'est noté. "))
+    await s.sur_saisie("Note tout ça.")
+    await _attendre(lambda: c.etats()[-1:] == ["repos"])
+    assert _dits(c) == [PROFIL.annonce, PAUL.annonce, "C'est noté."]
+    await s.fermer()
+
+
+async def test_sans_voix_une_note_ne_s_annonce_qu_en_texte():
+    c, d = Collecteur(), DiffuseurEspion()
+    s = _session(c, d, CerveauScript(PAUL, "Voilà. "), avec_voix=lambda: False)
+    await s.sur_saisie("Note Paul.")
+    await _attendre(lambda: [e.valeur for e in d.de(Etat)][-1:] == ["repos"])
+    assert _dits(c) == []
+    assert [r.texte for r in d.de(Reponse)] == [PAUL.annonce, "Voilà."]
+    await s.fermer()
+
+
 # --- les erreurs du cerveau ------------------------------------------------------------
 
 
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `uv run pytest tests/test_session_cerveau.py -q`
Expected: FAIL — 3 échecs : les réponses n'arrivent pas (`TypeError: can only concatenate str (not "Note") to str`
dans le découpeur, journalisé comme « échec du tour de parole »).

- [ ] **Step 3: Écrire l'annonce**

Modifier `src/atlas_core/session.py` :

```diff
--- a/src/atlas_core/session.py
+++ b/src/atlas_core/session.py
@@ -22,7 +22,7 @@ import logging
 import time
 from collections.abc import Awaitable, Callable
 
-from .cerveau import Cerveau, ErreurCerveau, Recherche
+from .cerveau import Cerveau, ErreurCerveau, Note, Recherche
 from .diffuseur import Diffuseur
 from .etat import MachineEtat, Valeur
 from .mise_en_voix import est_hallucination, nettoyer
@@ -389,6 +389,12 @@ class Session:
                             await self._phrase(phrase)
                         await self._chercher()
                         continue
+                    if isinstance(fragment, Note):
+                        # Atlas vient d'écrire dans sa mémoire : il le dit à cet endroit.
+                        for phrase in decoupeur.vider():
+                            await self._phrase(phrase)
+                        await self._phrase(fragment.annonce)
+                        continue
                     for phrase in decoupeur.ajouter(fragment):
                         await self._phrase(phrase)
         except ErreurCerveau as e:
```

- [ ] **Step 4: Vérifier que tout passe**

Run: `uv run pytest -q && uv run ruff check . --extend-exclude spikes && uv run ruff format --check . --extend-exclude spikes && node --test "tests/web/*.test.mjs"`
Expected: 792 tests Python passent, 126 tests JavaScript passent, ruff ne dit rien.

- [ ] **Step 5: Commit**

```bash
git add src/atlas_core/session.py tests/test_session_cerveau.py
git commit -F - <<'MSG'
Session : une note de la mémoire s'annonce à sa place dans la réponse

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

### Task 9: La mémoire dans le Core, et la documentation

Le réglage du dossier, la mémoire ouverte à la création du cerveau Claude (ses clés comme secrets), le garde-fou qui
empêche les tests de toucher la vraie mémoire, et la documentation : `.env.example`, le déploiement sur le néo, la
spec parente.

**Files:**
- Modify: `.env.example`
- Modify: `docs/superpowers/specs/2026-09-22-atlas-design.md`
- Modify: `scripts/neo/LISEZMOI.md`
- Modify: `src/atlas_core/config.py`
- Modify: `src/atlas_core/hub.py`
- Create: `tests/conftest.py`
- Modify: `tests/test_config.py`
- Modify: `tests/test_hub.py`

**Interfaces:**
- Consumes: Tasks 1, 4, 6, 7 (`Memoire.ouvrir`, `OutilsMemoire`, `CerveauClaude(…, outils=…)`,
  `options_cerveau(…, outils)`).
- Produces: `config.MEMOIRE_PAR_DEFAUT`, `Config.memoire_dossier: Path` (`ATLAS_MEMOIRE_DOSSIER`) ;
  `hub.ouvrir_la_memoire(config) -> OutilsMemoire | None` ; `creer_cerveau` passe les outils au cerveau et aux
  options.

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/conftest.py` :

```python
"""Réglages communs aux tests.

La mémoire d'Atlas est un dépôt git sur la machine du Core : les tests, qui démarrent le
Core, ne doivent jamais toucher la vraie. Le dossier est forcé avant tout import du Core
(`make test` exporte le .env de la machine, qui pourrait en nommer un autre).
"""

import os
import tempfile

os.environ["ATLAS_MEMOIRE_DOSSIER"] = os.path.join(
    tempfile.mkdtemp(prefix="atlas-tests-"), "memoire"
)
```

Modifier `tests/test_config.py` :

```diff
--- a/tests/test_config.py
+++ b/tests/test_config.py
@@ -1,6 +1,8 @@
+from pathlib import Path
+
 import pytest
 
-from atlas_core.config import Config
+from atlas_core.config import MEMOIRE_PAR_DEFAUT, Config
 
 
 def test_la_cle_web_vient_de_l_environnement(monkeypatch):
@@ -91,3 +93,16 @@ def test_un_reglage_de_la_voix_des_pages_invalide_est_refuse(monkeypatch, nom, b
     monkeypatch.setenv(nom, brute)
     with pytest.raises(ValueError, match=nom):
         Config.depuis_environnement()
+
+
+def test_la_memoire_vit_par_defaut_dans_le_dossier_d_atlas(monkeypatch):
+    monkeypatch.delenv("ATLAS_MEMOIRE_DOSSIER", raising=False)
+    assert Config.depuis_environnement().memoire_dossier == MEMOIRE_PAR_DEFAUT
+    assert MEMOIRE_PAR_DEFAUT == Path.home() / ".atlas" / "memoire"
+    monkeypatch.setenv("ATLAS_MEMOIRE_DOSSIER", "  ")
+    assert Config.depuis_environnement().memoire_dossier == MEMOIRE_PAR_DEFAUT
+
+
+def test_le_dossier_de_la_memoire_se_regle_et_accepte_le_tilde(monkeypatch):
+    monkeypatch.setenv("ATLAS_MEMOIRE_DOSSIER", "~/atlas-memoire")
+    assert Config.depuis_environnement().memoire_dossier == Path.home() / "atlas-memoire"
```

Modifier `tests/test_hub.py` :

```diff
--- a/tests/test_hub.py
+++ b/tests/test_hub.py
@@ -1,12 +1,13 @@
 import json
 import os
 from dataclasses import replace
+from pathlib import Path
 
 import pytest
 from fastapi.testclient import TestClient
 from starlette.websockets import WebSocketDisconnect
 
-from atlas_core import hub
+from atlas_core import hub, memoire
 from atlas_core.cerveau import CerveauBouchon
 from atlas_core.cerveau_claude import CerveauClaude
 from atlas_core.protocole import (
@@ -129,7 +130,12 @@ def test_le_bouchon_se_choisit_par_la_configuration():
 def test_le_cerveau_claude_ne_demarre_rien_avant_la_premiere_question(monkeypatch, tmp_path):
     dossier = tmp_path / "cerveau"
     monkeypatch.setattr(hub, "DOSSIER_CERVEAU", dossier)
-    config = replace(hub._config, cerveau="claude", cerveau_modele="claude-sonnet-5")
+    config = replace(
+        hub._config,
+        cerveau="claude",
+        cerveau_modele="claude-sonnet-5",
+        memoire_dossier=tmp_path / "memoire",
+    )
 
     cerveau = hub.creer_cerveau(config)
 
@@ -140,12 +146,61 @@ def test_le_cerveau_claude_ne_demarre_rien_avant_la_premiere_question(monkeypatc
     assert client.options.cwd == dossier and client.options.model == "claude-sonnet-5"
 
 
-def test_les_cles_d_api_sont_retirees_de_l_environnement_du_core(monkeypatch):
+def test_les_cles_d_api_sont_retirees_de_l_environnement_du_core(monkeypatch, tmp_path):
     monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ne-doit-pas-servir")
-    hub.creer_cerveau(replace(hub._config, cerveau="claude"))
+    hub.creer_cerveau(replace(hub._config, cerveau="claude", memoire_dossier=tmp_path / "m"))
     assert "ANTHROPIC_API_KEY" not in os.environ
 
 
+def test_les_tests_n_ouvrent_jamais_la_vraie_memoire():
+    assert hub._config.memoire_dossier != Path.home() / ".atlas" / "memoire"
+
+
+def test_le_cerveau_claude_recoit_la_memoire_et_ses_outils(monkeypatch, tmp_path):
+    monkeypatch.setattr(hub, "DOSSIER_CERVEAU", tmp_path / "cerveau")
+    dossier = tmp_path / "memoire"
+    cerveau = hub.creer_cerveau(replace(hub._config, cerveau="claude", memoire_dossier=dossier))
+    assert (dossier / ".git").is_dir()
+    assert cerveau._outils.memoire.racine == dossier
+    options = cerveau._fabrique().options
+    assert list(options.mcp_servers) == ["atlas"]
+    assert options.allowed_tools == ["WebSearch", *cerveau._outils.noms]
+
+
+def test_la_memoire_refuse_les_cles_du_core(monkeypatch, tmp_path):
+    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "jeton-d-abonnement-de-test")
+    config = replace(
+        hub._config,
+        cerveau="claude",
+        memoire_dossier=tmp_path / "memoire",
+        web_cle="cle-des-pages-de-test",
+        audio_cle="cle-audio-de-test-longue",
+    )
+    outils = hub.ouvrir_la_memoire(config)
+    for secret in (
+        "cle-des-pages-de-test",
+        "cle-audio-de-test-longue",
+        "jeton-d-abonnement-de-test",
+    ):
+        with pytest.raises(memoire.ErreurMemoire, match="clé secrète"):
+            outils.memoire.ecrire("profil.md", f"# Profil\n\nDavid.\n\n{secret}\n")
+
+
+def test_sans_git_le_cerveau_marche_sans_memoire(monkeypatch, tmp_path):
+    monkeypatch.setattr(memoire, "GIT", "git-introuvable")
+    monkeypatch.setattr(hub, "DOSSIER_CERVEAU", tmp_path / "cerveau")
+    config = replace(hub._config, cerveau="claude", memoire_dossier=tmp_path / "memoire")
+    cerveau = hub.creer_cerveau(config)
+    assert cerveau._outils is None
+    assert cerveau._fabrique().options.mcp_servers == {}
+
+
+def test_le_bouchon_n_ouvre_pas_la_memoire(tmp_path):
+    dossier = tmp_path / "memoire"
+    hub.creer_cerveau(replace(hub._config, cerveau="bouchon", memoire_dossier=dossier))
+    assert not dossier.exists()
+
+
 def test_la_voix_et_le_clavier_partagent_le_meme_cerveau(monkeypatch):
     monkeypatch.setattr(hub, "_config", replace(hub._config, cerveau="bouchon"))
 
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `uv run pytest tests/test_config.py tests/test_hub.py -q`
Expected: FAIL — erreur de collecte : `ImportError: cannot import name 'MEMOIRE_PAR_DEFAUT' from 'atlas_core.config'`.

- [ ] **Step 3: Écrire le câblage et la documentation**

Modifier `.env.example` :

```diff
--- a/.env.example
+++ b/.env.example
@@ -69,9 +69,12 @@ ATLAS_VOIX_BARGEIN_DBFS=-40
 ATLAS_CERVEAU=claude
 # Modèle de Claude. Vide : claude-sonnet-5.
 ATLAS_CERVEAU_MODELE=claude-sonnet-5
-# Au-delà de ce nombre de minutes sans échange, la question suivante ouvre une
-# conversation neuve.
+# Au-delà de ce nombre de minutes sans échange, la conversation se résume dans le journal
+# de la mémoire, et la question suivante en ouvre une neuve.
 ATLAS_CERVEAU_OUBLI_MIN=30
+# La mémoire d'Atlas : un dépôt git local (profil, fiches, journal), jamais poussé. Vide :
+# ~/.atlas/memoire. Sans git, Atlas marche sans mémoire.
+ATLAS_MEMOIRE_DOSSIER=
 # Sur le néo seulement (voir scripts/neo/LISEZMOI.md) : le jeton d'abonnement que donne
 # « claude setup-token », à décommenter là-bas. C'est un secret : la vraie valeur ne va
 # que dans le .env du néo, jamais dans ce fichier.
```

Modifier `docs/superpowers/specs/2026-09-22-atlas-design.md` :

```diff
--- a/docs/superpowers/specs/2026-09-22-atlas-design.md
+++ b/docs/superpowers/specs/2026-09-22-atlas-design.md
@@ -220,6 +220,10 @@ machine ; le serveur MCP d'Atlas arrive en 2c. La rotation de contexte avec rés
 ci-dessous arrive en 2b : d'ici là, le compactage automatique de Claude Code gère un
 contexte qui se remplit, et la conversation repart de zéro après
 `ATLAS_CERVEAU_OUBLI_MIN` minutes sans échange. Voir `2026-09-24-phase-2a-cerveau-design.md`.
+**Amendé le 25/09/2026 (phase 2b).** La rotation de contexte se fait à l'échéance de
+l'oubli : la conversation se résume dans le journal, puis la suivante repart amorcée avec
+le profil, le sommaire des fiches et le journal récent. Le compactage de Claude Code gère
+une conversation qui dure. Voir `2026-09-25-phase-2b-memoire-design.md`.
 
 **Rotation de contexte.** Quand le contexte approche de sa limite, le Core fait produire
 au Brain un résumé de la session, l'écrit dans `journal/AAAA-MM-JJ.md`, tue le process et
@@ -357,6 +361,12 @@ reconstructible à tout moment.
 annoncée à voix haute (« je note ça dans projets/x.md »). Les écritures mémoire sont de
 niveau N2 : il fait, et il annonce.
 
+**Amendé le 25/09/2026 (phase 2b).** Le dépôt est local, dans `~/.atlas/memoire` sur la
+machine du Core, et n'est jamais poussé. Pas d'index vectoriel en 2b : Atlas voit le
+sommaire des fiches et cherche dans le texte ; l'index viendra quand la mémoire aura
+grossi. Le journal s'écrit sans annonce, à la fin de chaque conversation : c'est la seule
+exception à la règle d'écriture. Voir `2026-09-25-phase-2b-memoire-design.md`.
+
 ---
 
 ## 9. Outils
@@ -377,6 +387,9 @@ def lancer_workflow(nom: str) -> str:
 Le Core expose ces outils au process Claude par **un serveur MCP local en stdio** — natif
 pour Claude Code, donc on ne réimplémente pas le tool-calling, et les mêmes outils restent
 utilisables depuis d'autres clients MCP.
+**Amendé le 25/09/2026 (phase 2b).** Le serveur MCP d'Atlas (« atlas ») tourne dans le Core
+lui-même, par le SDK de Claude, et non en stdio. Ses quatre premiers outils sont ceux de la
+mémoire ; la phase 2c y ajoute les autres et les niveaux d'autorisation.
 
 Familles d'outils en v1 : n8n, mémoire et documents, veille. Home Assistant et agenda/mail
 viennent après la v1.
@@ -502,7 +515,7 @@ Markdown et index, serveur MCP local, permissions.
 et le document produit se relit sans retouche.
 **Amendé le 24/09/2026.** La phase 2 est découpée en trois étapes, chacune avec sa spec,
 son plan et sa fusion : 2a, le cerveau branché (`2026-09-24-phase-2a-cerveau-design.md`) ;
-2b, la mémoire ; 2c, outils et permissions.
+2b, la mémoire (`2026-09-25-phase-2b-memoire-design.md`) ; 2c, outils et permissions.
 **Amendé le 25/09/2026.** Une étape « la voix dans le navigateur »
 (`2026-09-25-voix-navigateur-design.md`) s'insère entre 2a et 2b : la page de l'iPhone ou
 de l'iPad écoute et répond à voix haute, pas seulement le M5.
```

Modifier `scripts/neo/LISEZMOI.md` :

````diff
--- a/scripts/neo/LISEZMOI.md
+++ b/scripts/neo/LISEZMOI.md
@@ -157,3 +157,21 @@ Sur l'iPhone, l'iPad ou le Mac : `https://atlas.example.com/`, avec la clé
 - Chaque appareil répond pour lui-même, et le client du M5 marche toujours à côté.
 - Les dix premières secondes de voix d'Atlas après l'allumage du micro, on ne le coupe
   qu'en touchant l'orbe : l'annulation d'écho du navigateur s'installe.
+
+## 11. La mémoire d'Atlas
+
+Atlas tient sa mémoire dans `~/.atlas/memoire` sur la machine du Core : son profil de toi,
+ses fiches (entreprise, projets, personnes) et le journal de vos conversations. C'est un
+dépôt git local, qui n'a aucun distant et n'est jamais poussé ; sa sauvegarde est celle de
+la machine. Tu peux lire et corriger les fichiers à la main.
+
+Pour passer du M5 au néo, Core arrêté des deux côtés, copie-la avant de démarrer le Core
+sur le néo :
+
+```bash
+# sur le M5
+rsync -a ~/.atlas/memoire/ neo.local:.atlas/memoire/
+```
+
+Sans `git` sur la machine, Atlas marche sans mémoire ; le journal du Core le dit au
+démarrage.
````

Modifier `src/atlas_core/config.py` :

```diff
--- a/src/atlas_core/config.py
+++ b/src/atlas_core/config.py
@@ -9,9 +9,11 @@ from __future__ import annotations
 import math
 import os
 from dataclasses import dataclass
+from pathlib import Path
 
 CERVEAUX = ("claude", "bouchon")
 MODELE_PAR_DEFAUT = "claude-sonnet-5"
+MEMOIRE_PAR_DEFAUT = Path.home() / ".atlas" / "memoire"
 
 
 @dataclass(frozen=True)
@@ -29,6 +31,7 @@ class Config:
     # d'énergie de la coupure à la voix, l'écho résiduel n'étant pas celui du Mac.
     voix_marge_s: float = 0.2
     voix_bargein_dbfs: float = -40.0
+    memoire_dossier: Path = MEMOIRE_PAR_DEFAUT  # le dépôt git local de la mémoire, jamais poussé
 
     @staticmethod
     def depuis_environnement() -> Config:
@@ -44,6 +47,7 @@ class Config:
             audio_cle=os.environ.get("ATLAS_AUDIO_CLE", "").strip(),
             voix_marge_s=_lire_nombre("ATLAS_VOIX_MARGE_S", "0.2", 0.0, 2.0),
             voix_bargein_dbfs=_lire_nombre("ATLAS_VOIX_BARGEIN_DBFS", "-40", -120.0, 0.0),
+            memoire_dossier=_lire_dossier_memoire(),
         )
 
 
@@ -79,3 +83,8 @@ def _lire_nombre(nom: str, defaut: str, mini: float, maxi: float) -> float:
     if not math.isfinite(valeur) or not (mini <= valeur <= maxi):
         raise ValueError(f"{nom} invalide : {brute!r} doit être entre {mini:g} et {maxi:g}")
     return valeur
+
+
+def _lire_dossier_memoire() -> Path:
+    brute = os.environ.get("ATLAS_MEMOIRE_DOSSIER", "").strip()
+    return Path(brute).expanduser() if brute else MEMOIRE_PAR_DEFAUT
```

Modifier `src/atlas_core/hub.py` :

```diff
--- a/src/atlas_core/hub.py
+++ b/src/atlas_core/hub.py
@@ -22,6 +22,8 @@ from .cerveau import Cerveau, CerveauBouchon
 from .cerveau_claude import CerveauClaude, options_cerveau, purger_cles_api
 from .config import Config
 from .diffuseur import Diffuseur
+from .memoire import Memoire
+from .outils_memoire import OutilsMemoire
 from .protocole import Bonjour, Erreur, decoder_audio_entrant, decoder_message
 from .protocole_voix import (
     AuthentificationVoix,
@@ -64,12 +66,22 @@ def creer_cerveau(config: Config) -> Cerveau:
     retirees = purger_cles_api(os.environ)
     if retirees:
         _journal.warning("retiré de l'environnement, pour Claude : %s", ", ".join(retirees))
+    outils = ouvrir_la_memoire(config)
 
     def fabrique() -> ClaudeSDKClient:
         DOSSIER_CERVEAU.mkdir(parents=True, exist_ok=True)
-        return ClaudeSDKClient(options=options_cerveau(config.cerveau_modele, DOSSIER_CERVEAU))
+        options = options_cerveau(config.cerveau_modele, DOSSIER_CERVEAU, outils)
+        return ClaudeSDKClient(options=options)
 
-    return CerveauClaude(fabrique, oubli_s=config.cerveau_oubli_min * 60)
+    return CerveauClaude(fabrique, oubli_s=config.cerveau_oubli_min * 60, outils=outils)
+
+
+def ouvrir_la_memoire(config: Config) -> OutilsMemoire | None:
+    """La mémoire d'Atlas et ses outils ; None si elle ne s'ouvre pas (Atlas marche alors
+    sans). Les clés du Core sont des secrets qu'elle refuse d'écrire."""
+    secrets = [config.web_cle, config.audio_cle, os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "")]
+    memoire = Memoire.ouvrir(config.memoire_dossier, secrets)
+    return OutilsMemoire(memoire) if memoire is not None else None
 
 
 @asynccontextmanager
```

Vérifier qu'aucune donnée privée n'est entrée dans la documentation : `git diff | grep -nE
"[0-9]{1,3}(\.[0-9]{1,3}){3}|\.com"` ne montre rien de privé.

- [ ] **Step 4: Vérifier que tout passe**

Run: `uv run pytest -q && uv run ruff check . --extend-exclude spikes && uv run ruff format --check . --extend-exclude spikes && node --test "tests/web/*.test.mjs"`
Expected: 799 tests Python passent, 126 tests JavaScript passent, ruff ne dit rien.

- [ ] **Step 5: Commit**

```bash
git add .env.example docs/superpowers/specs/2026-09-22-atlas-design.md scripts/neo/LISEZMOI.md src/atlas_core/config.py src/atlas_core/hub.py tests/conftest.py tests/test_config.py tests/test_hub.py
git commit -F - <<'MSG'
Core : la mémoire ouverte pour le cerveau ; réglage, déploiement et spec parente

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

## L'essai avec David, sur le M5

Après la Task 9, sur la branche `phase-2b-memoire`, avant la PR. C'est David qui lance tout : l'essai consomme un peu
de son abonnement Claude. Les critères sont ceux du §1 de la spec.

1. **Préparer** : dans le `.env` du M5, `ATLAS_CERVEAU_OUBLI_MIN=2` le temps de l'essai (pour ne pas attendre trente
   minutes). Puis `make run-core`, et la page ouverte sur l'iPhone (ou `make run-audio`).
2. **Se présenter** : « Appelle-moi Dieu. » — Atlas dit « Je le note dans ton profil. », et t'appelle Dieu tout de
   suite.
3. **Un fait qui dure** : « J'ai deux enfants, de 18 mois et 4 ans et demi. » — annoncé ; le profil
   (`~/.atlas/memoire/profil.md`) porte des dates de naissance approximatives, pas des âges.
4. **Une fiche** : « Note que mon rendez-vous avec Paul Durand est jeudi. » — « Je le note dans la fiche Paul
   Durand. » ; `personnes/paul-durand.md` porte la date en entier.
5. **Annuler** : « Annule. » — « J'ai retiré ma dernière note. » ; la fiche de Paul a disparu.
6. **Un secret** : « Note mon mot de passe : … » — refusé, et Atlas le dit ; rien d'écrit.
7. **Le fil** : deux minutes de silence, puis `git -C ~/.atlas/memoire log --oneline` montre « Journal : … » ; une
   nouvelle question (« Comment je m'appelle ? Quel âge ont mes enfants ? De quoi on a parlé ? ») reçoit des
   réponses justes.
8. **Rien ne sort** : `git -C ~/.atlas/memoire remote` ne montre rien.
9. **Remettre** `ATLAS_CERVEAU_OUBLI_MIN=30`, et `make test` au vert.

Ce qui ne va pas devient une correction sur la branche, avec son test, avant la PR.

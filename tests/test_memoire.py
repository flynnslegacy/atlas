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
        # Les formes naturelles, qualifiées, que Claude écrirait :
        "Mot de passe Gmail : hunter2",
        "Le mot de passe du wifi : Soleil2024",
        "Le mot de passe de sa boîte mail est hunter2",
        "MDP Netflix = azerty",
        "Password for NAS: hunter2",
        "Code wifi : 1234-5678",
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


def test_un_depot_git_nomme_par_l_environnement_ne_detourne_pas_les_notes(tmp_path, monkeypatch):
    # Le Core lancé depuis un crochet git, par exemple : git y exporte GIT_DIR et consorts.
    ailleurs = tmp_path / "ailleurs"
    subprocess.run(["git", "init", "-q", str(ailleurs)], check=True)
    with monkeypatch.context() as environnement:
        environnement.setenv("GIT_DIR", str(ailleurs / ".git"))
        environnement.setenv("GIT_WORK_TREE", str(ailleurs))
        environnement.setenv("GIT_INDEX_FILE", str(ailleurs / ".git" / "index"))
        memoire = Memoire.ouvrir(tmp_path / "memoire")
        assert memoire is not None
        assert memoire.ecrire("personnes/paul-durand.md", FICHE) == "Paul Durand"
    assert git(memoire, "show", "--name-only", "--format=", "HEAD").split() == [
        "personnes/paul-durand.md"
    ]
    autre = subprocess.run(
        ["git", "-C", str(ailleurs), "rev-parse", "--verify", "-q", "HEAD"], capture_output=True
    )
    assert autre.returncode != 0, "une note est partie dans un autre dépôt"
    assert not (ailleurs / "personnes").exists()


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

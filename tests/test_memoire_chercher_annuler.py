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

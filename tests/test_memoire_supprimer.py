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

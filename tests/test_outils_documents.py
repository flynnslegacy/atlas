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

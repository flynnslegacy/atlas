"""Les outils de la mémoire, appelés comme Claude les appelle (leur gestionnaire), sur un vrai
dépôt git temporaire."""

import pytest

from atlas_core.cerveau import Note
from atlas_core.memoire import Memoire
from atlas_core.outils import ECHEC, PENDANT_LE_RESUME, Niveau
from atlas_core.outils_memoire import ANNONCE_PROFIL, ANNONCE_RETRAIT, OutilsMemoire

PAUL = "# Paul Durand\n\nProspect ; rendez-vous le jeudi 2 octobre 2026.\n"


@pytest.fixture
def outils(tmp_path) -> OutilsMemoire:
    return OutilsMemoire(Memoire.ouvrir(tmp_path / "memoire"))


async def appeler(outils: OutilsMemoire, nom: str, **arguments) -> tuple[str, bool]:
    outil = next(o for o in outils.outils if o.name == nom)
    resultat = await outil.handler(arguments)
    return resultat["content"][0]["text"], resultat.get("is_error", False)


def test_claude_voit_six_outils_chacun_avec_son_niveau(outils):
    assert [(o.nom, o.niveau) for o in outils.declarations] == [
        ("memoire_lire", Niveau.N1),
        ("memoire_chercher", Niveau.N1),
        ("memoire_ecrire", Niveau.N2),
        ("document_ecrire", Niveau.N2),
        ("memoire_annuler", Niveau.N2),
        ("memoire_supprimer", Niveau.N3),
    ]
    assert outils.noms == [f"mcp__atlas__{o.nom}" for o in outils.declarations]
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
    assert "l'outil memoire_ecrire a échoué" in caplog.text

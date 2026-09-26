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

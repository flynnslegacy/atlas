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

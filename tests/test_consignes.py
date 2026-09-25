import datetime as dt

import pytest

from atlas_core.consignes import (
    CONSIGNES,
    CONSIGNES_AVEC_MEMOIRE,
    DEMANDE_RESUME,
    RIEN,
    date_en_lettres,
    heure_en_chiffres,
    ligne_de_date,
)


@pytest.mark.parametrize(
    ("moment", "attendu"),
    [
        (dt.datetime(2026, 9, 24, 21, 50), "[jeudi 24 septembre 2026, 21 h 50]"),
        (dt.datetime(2026, 6, 1, 9, 5), "[lundi 1er juin 2026, 9 h 05]"),
        (dt.datetime(2027, 2, 14, 0, 0), "[dimanche 14 février 2027, 0 h 00]"),
        (dt.datetime(2026, 8, 15, 12, 30), "[samedi 15 août 2026, 12 h 30]"),
    ],
)
def test_la_ligne_de_date_est_en_francais(moment, attendu):
    assert ligne_de_date(moment) == attendu


def test_la_date_et_l_heure_s_ecrivent_comme_dans_la_ligne_de_date():
    assert date_en_lettres(dt.date(2026, 6, 1)) == "1er juin 2026"
    assert date_en_lettres(dt.date(2026, 9, 25)) == "25 septembre 2026"
    assert heure_en_chiffres(dt.datetime(2026, 9, 25, 9, 5)) == "9 h 05"


def test_les_consignes_tiennent_les_decisions_de_la_spec():
    texte = CONSIGNES.lower()
    for attendu in (
        "atlas",
        "david",
        "tutoies",
        "voix haute",
        "deux à quatre phrases",
        "cite le site par son nom",
        "ne prétends jamais",
    ):
        assert attendu in texte, attendu


def test_les_consignes_ne_revelent_rien_de_prive():
    for consignes in (CONSIGNES, CONSIGNES_AVEC_MEMOIRE, DEMANDE_RESUME):
        for interdit in ("@", "http", "192.168"):
            assert interdit not in consignes.lower(), interdit


def test_sans_memoire_claude_ne_parle_pas_de_memoire():
    assert "mémoire" not in CONSIGNES.lower()
    assert "Tu ne peux rien faire d'autre que réfléchir et chercher sur le web." in CONSIGNES


def test_avec_la_memoire_les_consignes_gardent_tout_et_disent_comment_la_tenir():
    texte = CONSIGNES_AVEC_MEMOIRE.lower()
    for attendu in (
        "tutoies",
        "deux à quatre phrases",
        "cite le site par son nom",
        "ne prétends jamais",
        "[mémoire d'atlas]",
        "memoire_lire",
        "memoire_chercher",
        "memoire_ecrire",
        "memoire_annuler",
        "« # titre », une ligne vide, puis une phrase de résumé",
        "relis une fiche avant de la modifier",
        "date de naissance approximative",
        "une date plutôt que « jeudi »",
        "n'annonce pas que tu notes",
        "ne note jamais de mot de passe",
        "comme son profil l'indique",
        "réfléchir, chercher sur le web et tenir ta mémoire",
    ):
        assert attendu in texte, attendu


def test_la_demande_de_resume_ne_fait_rien_ecrire_et_admet_rien():
    assert DEMANDE_RESUME.startswith("[Fin de la conversation]")
    assert "n'écris rien dans ta mémoire" in DEMANDE_RESUME
    assert "Ne garde pas ce que David t'a demandé d'oublier" in DEMANDE_RESUME
    assert DEMANDE_RESUME.endswith(f"réponds seulement : {RIEN}.")

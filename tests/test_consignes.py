import datetime as dt

import pytest

from atlas_core.consignes import CONSIGNES, date_en_lettres, heure_en_chiffres, ligne_de_date


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
    for interdit in ("@", "http", "192.168"):
        assert interdit not in CONSIGNES.lower(), interdit

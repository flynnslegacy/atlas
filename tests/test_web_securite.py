import pytest

from atlas_core.web import cle_valide, origine_autorisee, politique_securite


@pytest.mark.parametrize(
    "origine,hote,attendu",
    [
        ("http://atlas.local:8080", "atlas.local:8080", True),
        ("http://ATLAS.local:8080", "atlas.local:8080", True),
        ("https://atlas.local:8080", "atlas.local:8080", True),
        ("http://ailleurs.example", "atlas.local:8080", False),
        ("http://atlas.local:9999", "atlas.local:8080", False),
        (None, "atlas.local:8080", False),
        ("http://atlas.local:8080", None, False),
        ("", "", False),
    ],
)
def test_l_origine_doit_etre_la_page_du_core(origine, hote, attendu):
    assert origine_autorisee(origine, hote) is attendu


def test_la_cle_est_comparee_exactement():
    assert cle_valide("abc", "abc") is True
    assert cle_valide("abd", "abc") is False
    assert cle_valide("", "abc") is False


def test_une_cle_attendue_vide_ne_valide_jamais_rien():
    assert cle_valide("", "") is False


def test_la_politique_autorise_la_connexion_au_meme_hote():
    politique = politique_securite("atlas.local:8080")
    assert politique.startswith("default-src 'self'; ")
    assert "connect-src 'self' ws://atlas.local:8080 wss://atlas.local:8080;" in politique
    assert "frame-ancestors 'none'" in politique


def test_un_hote_bizarre_n_entre_pas_dans_la_politique():
    politique = politique_securite("x; script-src *")
    assert "script-src" not in politique
    assert "connect-src 'self';" in politique

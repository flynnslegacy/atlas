import pytest

from atlas_core.protocole_voix import (
    AuthentificationVoix,
    HeyAtlas,
    Parler,
    Pret,
    Reprise,
    Vider,
    decoder_message_voix,
    verifier_bloc_page,
)
from atlas_core.protocole_web import Authentification, decoder_message_page


def test_l_authentification_porte_la_cle_la_page_et_hey_atlas():
    msg = decoder_message_voix(
        '{"type":"authentification","cle":"c","page":"a1-B_2","hey_atlas":true}'
    )
    assert msg == AuthentificationVoix(cle="c", page="a1-B_2", hey_atlas=True)


def test_hey_atlas_est_eteint_par_defaut():
    msg = decoder_message_voix('{"type":"authentification","cle":"c","page":"p"}')
    assert msg.hey_atlas is False


@pytest.mark.parametrize(
    ("brut", "attendu"),
    [
        ('{"type":"parler"}', Parler()),
        ('{"type":"hey_atlas","actif":false}', HeyAtlas(actif=False)),
        ('{"type":"reprise"}', Reprise()),
    ],
)
def test_les_messages_de_la_page_se_decodent(brut, attendu):
    assert decoder_message_voix(brut) == attendu


@pytest.mark.parametrize(
    "brut",
    [
        '{"type":"authentification","cle":"c"}',
        '{"type":"authentification","cle":"c","page":"../etc"}',
        '{"type":"authentification","cle":"c","page":""}',
        '{"type":"authentification","cle":"' + "x" * 300 + '","page":"p"}',
        '{"type":"saisie","texte":"bonjour"}',
        "pas du json",
    ],
)
def test_un_message_invalide_leve_value_error(brut):
    with pytest.raises(ValueError, match="message de voix invalide"):
        decoder_message_voix(brut)


def test_le_core_confirme_et_vide():
    assert Pret().model_dump_json() == '{"type":"pret"}'
    assert Vider().model_dump_json() == '{"type":"vider"}'


def test_un_bloc_de_micro_fait_exactement_640_octets():
    assert verifier_bloc_page(b"\x00" * 640) == b"\x00" * 640
    for taille in (0, 639, 641, 1280):
        with pytest.raises(ValueError, match="attendu 640"):
            verifier_bloc_page(b"\x00" * taille)


def test_l_authentification_des_pages_peut_porter_l_identifiant():
    assert decoder_message_page('{"type":"authentification","cle":"c"}') == Authentification(
        cle="c"
    )
    avec = decoder_message_page('{"type":"authentification","cle":"c","page":"p1"}')
    assert avec.page == "p1"
    with pytest.raises(ValueError):
        decoder_message_page('{"type":"authentification","cle":"c","page":"a b"}')

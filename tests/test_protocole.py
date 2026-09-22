import pytest

from atlas_core.protocole import (
    TAILLE_BLOC_OCTETS,
    Etat,
    decoder_audio_entrant,
    decoder_audio_sortant,
    decoder_message,
    encoder_audio_entrant,
    encoder_audio_sortant,
)


def test_decoder_un_message_bonjour():
    msg = decoder_message(
        '{"type":"bonjour","client":"m5","frequence":16000,"capacites":["aec","vad"]}'
    )
    assert msg.client == "m5"
    assert "aec" in msg.capacites


def test_un_type_inconnu_est_refuse():
    with pytest.raises(ValueError):
        decoder_message('{"type":"nimporte_quoi"}')


def test_un_etat_invalide_est_refuse():
    with pytest.raises(ValueError):
        Etat(valeur="en_train_de_cuire")


def test_aller_retour_audio_entrant():
    pcm = b"\x01\x02" * 320
    assert decoder_audio_entrant(encoder_audio_entrant(pcm)) == pcm


def test_aller_retour_audio_sortant_preserve_l_identifiant():
    pcm = b"\x03\x04" * 320
    id_lu, pcm_lu = decoder_audio_sortant(encoder_audio_sortant(4242, pcm))
    assert id_lu == 4242
    assert pcm_lu == pcm


def test_un_bloc_de_mauvaise_taille_est_refuse():
    with pytest.raises(ValueError):
        encoder_audio_entrant(b"\x00" * 639)


def test_une_trame_sortante_lue_comme_entrante_est_refusee():
    with pytest.raises(ValueError):
        decoder_audio_entrant(encoder_audio_sortant(1, b"\x00" * TAILLE_BLOC_OCTETS))


def test_une_trame_sortante_trop_courte_est_refusee():
    with pytest.raises(ValueError):
        decoder_audio_sortant(bytes([0x02, 0x00, 0x00]))


def test_le_mauvais_octet_de_type_est_refuse_a_taille_egale():
    trame = bytes([0x02]) + b"\x00" * TAILLE_BLOC_OCTETS
    with pytest.raises(ValueError):
        decoder_audio_entrant(trame)

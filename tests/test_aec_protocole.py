import struct

import pytest

from helios_audio.aec import TAILLE_BLOC, trame_lecture, trame_vidage


def test_une_trame_de_lecture_porte_son_bloc():
    pcm = b"\x01\x02" * 320
    trame = trame_lecture(pcm)
    assert trame[0] == 0x01
    assert struct.unpack(">I", trame[1:5])[0] == TAILLE_BLOC
    assert trame[5:] == pcm


def test_une_trame_de_vidage_est_vide():
    trame = trame_vidage()
    assert trame[0] == 0x02
    assert struct.unpack(">I", trame[1:5])[0] == 0
    assert len(trame) == 5


def test_un_bloc_de_mauvaise_taille_est_refuse():
    with pytest.raises(ValueError):
        trame_lecture(b"\x00" * 100)

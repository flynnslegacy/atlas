import numpy as np

from scripts.mot_reveil.audio import (
    FREQUENCE,
    couper_silences,
    ecrire_wav,
    en_blocs,
    fenetres,
    lire_wav,
    ramener_16k,
)
from scripts.mot_reveil.convertir import convertir_dossier


def _ton(duree_s, amplitude=0.5, frequence=FREQUENCE):
    t = np.arange(int(duree_s * frequence)) / frequence
    return (amplitude * np.sin(2 * np.pi * 440 * t)).astype(np.float32)


def test_ecrire_puis_lire_garde_16k_mono(tmp_path):
    chemin = tmp_path / "sous" / "x.wav"
    ecrire_wav(chemin, _ton(0.5))
    audio, frequence = lire_wav(chemin)
    assert frequence == 16000
    assert audio.shape == (8000,)
    assert np.max(np.abs(audio - _ton(0.5))) < 1e-3


def test_ecrire_ecrete_au_lieu_de_deborder(tmp_path):
    ecrire_wav(tmp_path / "x.wav", np.array([2.0, -2.0], dtype=np.float32))
    audio, _ = lire_wav(tmp_path / "x.wav")
    assert audio.max() <= 1.0 and audio.min() >= -1.0
    assert abs(audio[0]) > 0.99


def test_ramener_16k_change_la_frequence_pas_la_duree():
    audio = ramener_16k(_ton(1.0, frequence=22050), 22050)
    assert abs(audio.size - 16000) <= 2
    assert audio.dtype == np.float32


def test_ramener_16k_laisse_le_16k_intact():
    x = _ton(0.1)
    assert np.array_equal(ramener_16k(x, 16000), x)


def test_couper_silences_garde_la_voix_et_une_marge():
    silence = np.zeros(8000, dtype=np.float32)
    coupe = couper_silences(np.concatenate([silence, _ton(0.5), silence]), marge_s=0.1)
    assert coupe.size == 8000 + 2 * 1600


def test_couper_silences_rend_vide_sur_du_silence():
    assert couper_silences(np.zeros(16000, dtype=np.float32)).size == 0


def test_fenetres_jette_le_reste():
    assert fenetres(np.zeros(16000 * 5 + 100, dtype=np.float32), 2.0).shape == (2, 32000)


def test_en_blocs_fait_des_blocs_de_640_octets():
    blocs = en_blocs(np.zeros(16000, dtype=np.float32))
    assert len(blocs) == 50
    assert all(len(b) == 640 for b in blocs)


def test_convertir_dossier_ramene_tout_a_16k(tmp_path):
    import soundfile as sf

    source = tmp_path / "source"
    source.mkdir()
    sf.write(str(source / "a.wav"), _ton(1.0, frequence=44100), 44100, subtype="PCM_16")
    assert convertir_dossier(source, tmp_path / "cible") == 1
    audio, frequence = lire_wav(tmp_path / "cible" / "a.wav")
    assert frequence == 16000
    assert abs(audio.size - 16000) <= 2

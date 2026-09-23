import json

import numpy as np
import pytest

from scripts.mot_reveil import evaluer
from scripts.mot_reveil import preparer as module_preparer
from scripts.mot_reveil.audio import ecrire_wav
from scripts.mot_reveil.configuration import configuration
from scripts.mot_reveil.preparer import COPIES_DAVID, preparer
from scripts.mot_reveil.repartition import est_test

CLES_TRAIN_PY = {
    "model_name",
    "target_phrase",
    "custom_negative_phrases",
    "n_samples",
    "n_samples_val",
    "tts_batch_size",
    "output_dir",
    "piper_sample_generator_path",
    "rir_paths",
    "background_paths",
    "background_paths_duplication_rate",
    "augmentation_rounds",
    "augmentation_batch_size",
    "feature_data_files",
    "batch_n_per_class",
    "model_type",
    "layer_size",
    "steps",
    "max_negative_weight",
    "target_false_positives_per_hour",
    "false_positive_validation_data_path",
}


def test_configuration_a_les_cles_de_train_py(tmp_path):
    config = configuration(tmp_path, {"ACAV100M_sample": "a.npy", "negatifs_david": "d.npy"}, 1000)
    assert set(config) == CLES_TRAIN_PY
    assert config["model_name"] == "hey_atlas"
    assert config["output_dir"] == str(tmp_path / "entrainement")
    assert set(config["batch_n_per_class"]) == {
        "ACAV100M_sample",
        "negatifs_david",
        "adversarial_negative",
        "positive",
    }


def test_la_part_de_test_est_la_meme_que_sur_le_mac():
    assert module_preparer.UNE_SUR_DAVID == evaluer.UNE_SUR_DAVID


def _travail(racine):
    un = np.full(12000, 0.2, dtype=np.float32)
    for i in range(100):
        ecrire_wav(racine / "retenus" / "positifs" / f"piper_p{i}.wav", un)
        ecrire_wav(racine / "retenus" / "negatifs" / f"piper_n{i}.wav", un)
    noms_david = [f"bureau_{i:03d}.wav" for i in range(12)]
    for nom in noms_david:
        ecrire_wav(racine / "david" / "positifs" / nom, un)
    for i in range(6):
        ecrire_wav(racine / "david" / "atlas_seul" / f"atlas_{i:02d}.wav", un)
    for i in range(6):
        ecrire_wav(
            racine / "david" / "parole" / f"parole_{i:02d}.wav", np.full(96000, 0.1, np.float32)
        )
        ecrire_wav(
            racine / "david" / "bureau" / f"bureau_{i:02d}.wav", np.full(96000, 0.01, np.float32)
        )
    ecrire_wav(racine / "david" / "faux_reveils" / "alerte_0001_0.61.wav", un)
    return noms_david


def _extraire(fenetres):
    return np.zeros((len(fenetres), 16, 96), dtype=np.float32)


def test_preparer_assemble_le_dossier_de_train_py(tmp_path):
    noms_david = _travail(tmp_path)
    bilan = preparer(tmp_path, _extraire)
    racine = tmp_path / "entrainement" / "hey_atlas"
    positifs = {p.name for p in (racine / "positive_train").glob("*.wav")}
    assert any((racine / "positive_test").glob("*.wav"))
    # Les enregistrements de David réservés au test ne sont jamais entraînés…
    for nom in noms_david:
        present = any(p.startswith(f"david_{nom[:-4]}__") for p in positifs)
        assert present == (not est_test(nom, 3))
    # … et les autres sont dupliqués.
    un_garde = next(n for n in noms_david if not est_test(n, 3))
    assert sum(p.startswith(f"david_{un_garde[:-4]}__") for p in positifs) == COPIES_DAVID
    negatifs = {p.name for p in (racine / "negative_train").glob("*.wav")}
    assert any(n.startswith("faux_alerte_0001") for n in negatifs)
    assert np.load(tmp_path / "donnees" / "traits_david.npy").shape[1:] == (16, 96)
    assert any((tmp_path / "donnees" / "fonds" / "bureau_david").glob("*.wav"))
    config = json.loads((tmp_path / "entrainement" / "hey_atlas.yml").read_text())
    assert config["feature_data_files"]["negatifs_david"].endswith("traits_david.npy")
    assert bilan["positive_train"] == len(positifs)


def test_preparer_refuse_un_test_positif_vide(tmp_path):
    (tmp_path / "retenus" / "positifs").mkdir(parents=True)
    with pytest.raises(SystemExit, match="positive_test"):
        preparer(tmp_path, _extraire)


def test_preparer_purge_les_bureau_supprimes_a_la_source(tmp_path):
    """Un fond de bureau retiré de la source ne doit pas survivre à la prochaine préparation."""
    _travail(tmp_path)
    preparer(tmp_path, _extraire)
    fonds = tmp_path / "donnees" / "fonds" / "bureau_david"
    noms_bureau = [f"bureau_{i:02d}.wav" for i in range(6)]
    garde = next(n for n in noms_bureau if not est_test(n, 3))
    assert (fonds / garde).exists()
    (tmp_path / "david" / "bureau" / garde).unlink()
    preparer(tmp_path, _extraire)
    assert not (fonds / garde).exists()


def test_preparer_purge_les_traits_orphelins(tmp_path):
    """Sans parole ni bureau à traiter, un traits_david.npy d'avant reste orphelin sans purge."""
    _travail(tmp_path)
    preparer(tmp_path, _extraire)
    chemin_traits = tmp_path / "donnees" / "traits_david.npy"
    assert chemin_traits.exists()
    for chemin in (tmp_path / "david" / "parole").glob("*.wav"):
        chemin.unlink()
    for chemin in (tmp_path / "david" / "bureau").glob("*.wav"):
        chemin.unlink()
    preparer(tmp_path, _extraire)
    assert not chemin_traits.exists()
    config = json.loads((tmp_path / "entrainement" / "hey_atlas.yml").read_text())
    assert "negatifs_david" not in config["feature_data_files"]

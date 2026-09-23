"""La configuration de train.py (openWakeWord, commit 368c037).

Écrite en JSON, qui est du YAML valide : train.py la lit avec yaml.load. Les clés
viennent de examples/custom_model.yml au même commit. target_phrase, n_samples,
n_samples_val, tts_batch_size et custom_negative_phrases ne servent qu'à
--generate_clips, que nous ne lançons pas.
"""

from __future__ import annotations

import json
from pathlib import Path


def configuration(travail: Path, traits: dict[str, str], pas: int, psg: str = "/opt/psg") -> dict:
    donnees = travail / "donnees"
    lots = {"ACAV100M_sample": 1024, "adversarial_negative": 50, "positive": 50}
    lots.update({cle: 64 for cle in traits if cle != "ACAV100M_sample"})
    return {
        "model_name": "hey_atlas",
        "target_phrase": ["eille atlasse"],
        "custom_negative_phrases": [],
        "n_samples": 1,
        "n_samples_val": 1,
        "tts_batch_size": 1,
        "output_dir": str(travail / "entrainement"),
        "piper_sample_generator_path": psg,
        "rir_paths": [str(donnees / "rir")],
        "background_paths": [
            str(donnees / "fonds" / "esc50"),
            str(donnees / "fonds" / "bureau_david"),
        ],
        "background_paths_duplication_rate": [1, 3],
        "augmentation_rounds": 1,
        "augmentation_batch_size": 16,
        "feature_data_files": traits,
        "batch_n_per_class": lots,
        "model_type": "dnn",
        "layer_size": 32,
        "steps": pas,
        "max_negative_weight": 1500,
        "target_false_positives_per_hour": 0.2,
        "false_positive_validation_data_path": str(donnees / "validation_set_features.npy"),
    }


def ecrire(config: dict, chemin: Path) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")

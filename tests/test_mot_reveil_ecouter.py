import json

from scripts.mot_reveil.ecouter import choisir, ecouter
from scripts.mot_reveil.generer_qwen import DESCRIPTIONS

MANIFESTE = {
    "piper_pos_000000": {"voix": "fr_FR-tom-medium", "texte": "Eille Atlasse"},
    "piper_pos_000001": {"voix": "fr_FR-siwis-medium", "texte": "Eille Atlasse"},
    "piper_pos_000002": {"voix": "fr_FR-tom-medium", "texte": "Eille Atlasse !"},
    "piper_pos_000003": {"voix": "fr_FR-tom-medium", "texte": "Eille Atlasse ?"},
}


def test_choisir_prend_les_premiers_extraits_de_chaque_voix():
    assert choisir(MANIFESTE, 2) == [
        ("fr_FR-siwis-medium", ["piper_pos_000001"]),
        ("fr_FR-tom-medium", ["piper_pos_000000", "piper_pos_000002"]),
    ]


def test_ecouter_annonce_chaque_voix_qwen_avec_sa_description(tmp_path, capsys):
    positifs = tmp_path / "positifs"
    positifs.mkdir()
    manifeste = {"qwen_pos_000000": {"voix": "voix_07", "texte": "Hey Atlas"}}
    (positifs / "manifeste.json").write_text(json.dumps(manifeste))
    joues = []
    ecouter(tmp_path, par_voix=3, jouer=joues.append)
    assert joues == [positifs / "qwen_pos_000000.wav"]
    sortie = capsys.readouterr().out
    assert "voix_07" in sortie and DESCRIPTIONS[7] in sortie

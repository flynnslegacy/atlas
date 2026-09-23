from collections import Counter

import numpy as np

from scripts.mot_reveil import generer_qwen
from scripts.mot_reveil.audio import lire_wav
from scripts.mot_reveil.generer_qwen import (
    DESCRIPTIONS,
    TEXTE_REFERENCE,
    cloner,
    concevoir,
    planifier_qwen,
)
from scripts.mot_reveil.phrases import NEGATIVES_QWEN, POSITIVES_QWEN


def test_planifier_qwen_repartit_a_parts_egales():
    taches = planifier_qwen(15, ["x", "y", "z"], 900, "qwen_pos")
    assert Counter(t.voix for t in taches) == {v: 60 for v in range(15)}
    assert Counter(t.texte for t in taches) == {"x": 300, "y": 300, "z": 300}
    assert taches[0].nom == "qwen_pos_000000"


class FauxModele:
    def __init__(self):
        self.invites = 0
        self.textes = []

    def generate_voice_design(self, text, language, instruct):
        assert language == "French"
        return [np.full(24000, 0.3, dtype=np.float32)], 24000

    def create_voice_clone_prompt(self, ref_audio, ref_text, x_vector_only_mode):
        assert ref_text == TEXTE_REFERENCE and not x_vector_only_mode
        self.invites += 1
        return object()

    def generate_voice_clone(self, text, language, voice_clone_prompt, max_new_tokens):
        self.textes.append(text)
        return [np.full(24000, 0.3, dtype=np.float32)], 24000


def test_concevoir_ecrit_une_reference_et_son_texte_par_voix(tmp_path):
    assert concevoir(FauxModele(), tmp_path, DESCRIPTIONS[:3]) == 3
    assert (tmp_path / "voix_02.txt").read_text() == TEXTE_REFERENCE
    audio, frequence = lire_wav(tmp_path / "voix_00.wav")
    assert frequence == 24000  # fréquence native gardée : matière première du clonage
    assert concevoir(FauxModele(), tmp_path, DESCRIPTIONS[:3]) == 0


def test_cloner_calcule_une_invite_par_voix_et_ecrit_du_16k(tmp_path):
    concevoir(FauxModele(), tmp_path / "ref", DESCRIPTIONS[:2])
    modele = FauxModele()
    taches = planifier_qwen(2, ["Eille Atlasse"], 6, "qwen_pos")
    assert cloner(modele, tmp_path / "ref", taches, tmp_path / "sortie") == 6
    assert modele.invites == 2
    audio, frequence = lire_wav(tmp_path / "sortie" / "qwen_pos_000000.wav")
    assert frequence == 16000 and audio.size > 15000


def test_cloner_fait_lire_a_qwen_l_orthographe_usuelle(tmp_path, monkeypatch):
    # « Eille Atlasse » est écrit pour espeak (Piper) : Qwen le prononce de travers.
    concevoir(FauxModele(), tmp_path / "references", DESCRIPTIONS[:1])
    modele = FauxModele()
    monkeypatch.setattr(generer_qwen, "charger", lambda nom: modele)
    generer_qwen.main(["cloner", "--sortie", str(tmp_path), "--essai"])
    assert set(modele.textes) == set(POSITIVES_QWEN) | set(NEGATIVES_QWEN)

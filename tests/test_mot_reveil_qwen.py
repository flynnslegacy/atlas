import json
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
    voix = [f"voix_{i:02d}" for i in range(15)]
    taches = planifier_qwen(voix, ["x", "y", "z"], 900, "qwen_pos")
    assert Counter(t.voix for t in taches) == {v: 60 for v in voix}
    assert Counter(t.texte for t in taches) == {"x": 300, "y": 300, "z": 300}
    # Le nom porte la voix : écarter une voix ne réattribue jamais un fichier existant.
    assert [t.nom for t in taches[:2]] == ["qwen_pos_voix_00_00000", "qwen_pos_voix_01_00000"]
    assert taches[15].nom == "qwen_pos_voix_00_00001"


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
    taches = planifier_qwen(["voix_00", "voix_01"], ["Hey Atlas"], 6, "qwen_pos")
    assert cloner(modele, tmp_path / "ref", taches, tmp_path / "sortie") == 6
    assert modele.invites == 2
    audio, frequence = lire_wav(tmp_path / "sortie" / "qwen_pos_voix_00_00000.wav")
    assert frequence == 16000 and audio.size > 15000
    manifeste = json.loads((tmp_path / "sortie" / "manifeste.json").read_text())
    assert manifeste["qwen_pos_voix_01_00000"] == {"voix": "voix_01", "texte": "Hey Atlas"}


def test_cloner_fait_lire_a_qwen_l_orthographe_usuelle(tmp_path, monkeypatch):
    # « Eille Atlasse » est écrit pour espeak (Piper) : Qwen le prononce de travers.
    concevoir(FauxModele(), tmp_path / "references", DESCRIPTIONS[:1])
    modele = FauxModele()
    monkeypatch.setattr(generer_qwen, "charger", lambda nom: modele)
    generer_qwen.main(["cloner", "--sortie", str(tmp_path), "--positifs", "4", "--negatifs", "21"])
    assert set(modele.textes) == set(POSITIVES_QWEN) | set(NEGATIVES_QWEN)


def test_une_quarantaine_de_voix_distinctes():
    # Qwen remplace les 125 locuteurs de la voix Piper mls, écartée à l'écoute.
    assert len(DESCRIPTIONS) == 40 and len(set(DESCRIPTIONS)) == 40


def test_l_essai_fait_dire_hey_atlas_une_fois_par_voix_restante(tmp_path, monkeypatch):
    """David écoute un positif par voix, et écarte une voix ratée en retirant sa référence."""
    references = tmp_path / "references"
    concevoir(FauxModele(), references, DESCRIPTIONS[:3])
    (references / "voix_01.wav").unlink()  # écartée à l'écoute de la référence
    (references / "voix_01.txt").unlink()
    monkeypatch.setattr(generer_qwen, "charger", lambda nom: FauxModele())
    generer_qwen.main(["cloner", "--sortie", str(tmp_path), "--essai"])
    manifeste = json.loads((tmp_path / "essai" / "positifs" / "manifeste.json").read_text())
    assert sorted(v["voix"] for v in manifeste.values()) == ["voix_00", "voix_02"]
    assert len(list((tmp_path / "essai" / "negatifs").glob("*.wav"))) == 30
    assert not (tmp_path / "positifs").exists()  # l'essai n'entre jamais dans l'entraînement


class ModeleQuiTombe(FauxModele):
    """Tombe (docker stop, mémoire pleine…) au deuxième extrait."""

    def generate_voice_clone(self, text, language, voice_clone_prompt, max_new_tokens):
        if self.textes:
            raise RuntimeError("arrêt brutal")
        return super().generate_voice_clone(text, language, voice_clone_prompt, max_new_tokens)


def test_cloner_complete_le_manifeste_apres_un_arret_brutal(tmp_path):
    """Sinon l'extrait écrit avant l'arrêt, sauté à la reprise, ne serait jamais écouté."""
    concevoir(FauxModele(), tmp_path / "ref", DESCRIPTIONS[:3])
    taches = planifier_qwen(["voix_00", "voix_01", "voix_02"], ["Hey Atlas"], 3, "qwen_pos")
    try:
        cloner(ModeleQuiTombe(), tmp_path / "ref", taches, tmp_path / "sortie")
    except RuntimeError:
        pass
    assert cloner(FauxModele(), tmp_path / "ref", taches, tmp_path / "sortie") == 2
    manifeste = json.loads((tmp_path / "sortie" / "manifeste.json").read_text())
    assert sorted(v["voix"] for v in manifeste.values()) == ["voix_00", "voix_01", "voix_02"]

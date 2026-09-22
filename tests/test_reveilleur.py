import pytest

from helios_audio.reveilleur import PredicteurOpenWakeWord, ReveilleurMotCle

BLOC = b"\x00" * 640


class PredicteurScript:
    def __init__(self, scores: list[float]) -> None:
        self._scores = list(scores)

    def score(self, bloc: bytes) -> float:
        return self._scores.pop(0) if self._scores else 0.0


def _compter(r: ReveilleurMotCle, n: int) -> int:
    return sum(1 for _ in range(n) if r.examiner(BLOC))


def test_un_score_au_dessus_du_seuil_reveille():
    r = ReveilleurMotCle(PredicteurScript([0.9]), seuil=0.5)
    assert r.examiner(BLOC) is True


def test_un_score_sous_le_seuil_ne_reveille_pas():
    r = ReveilleurMotCle(PredicteurScript([0.3]), seuil=0.5)
    assert r.examiner(BLOC) is False


def test_la_periode_refractaire_evite_le_double_declenchement():
    # 2000 ms de refractaire = 100 blocs de 20 ms
    r = ReveilleurMotCle(PredicteurScript([0.9] * 50), seuil=0.5, refractaire_ms=2000)
    assert _compter(r, 50) == 1


def test_apres_la_periode_refractaire_il_reveille_de_nouveau():
    scores = [0.9] + [0.0] * 100 + [0.9]
    r = ReveilleurMotCle(PredicteurScript(scores), seuil=0.5, refractaire_ms=2000)
    assert _compter(r, 102) == 2


def test_un_modele_de_reveil_absent_est_nomme_et_renvoie_a_la_procedure(tmp_path):
    absent = tmp_path / "hey_helios.onnx"
    with pytest.raises(FileNotFoundError) as erreur:
        PredicteurOpenWakeWord(chemin=str(absent))
    assert str(absent) in str(erreur.value)
    assert "scripts/entrainer_mot_reveil.md" in str(erreur.value)


def test_des_modeles_de_traits_absents_disent_comment_les_telecharger(tmp_path, monkeypatch):
    import openwakeword
    from onnxruntime.capi.onnxruntime_pybind11_state import NoSuchFile

    def modele_sans_traits(*args, **kwargs):
        raise NoSuchFile("Load model from .../resources/models/melspectrogram.onnx failed")

    monkeypatch.setattr(openwakeword, "Model", modele_sans_traits)
    present = tmp_path / "hey_helios.onnx"
    present.write_bytes(b"")

    with pytest.raises(FileNotFoundError) as erreur:
        PredicteurOpenWakeWord(chemin=str(present))
    assert "openwakeword.utils.download_models()" in str(erreur.value)

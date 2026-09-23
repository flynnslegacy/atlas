import json

import numpy as np
import pytest

from scripts.mot_reveil.veille import Veilleur
from scripts.mot_reveil.veiller import seuils_veille, veiller

BLOC = np.full(320, 500, dtype="<i2").tobytes()


def test_seuils_veille_calcule_le_defaut_a_60_pourcent_plafonne_a_0_3():
    assert seuils_veille(0.5, None) == 0.3  # 0,6 * 0,5 = 0,3
    assert seuils_veille(0.2, None) == 0.12  # 0,6 * 0,2 = 0,12 < 0,3
    assert seuils_veille(1.0, None) == 0.3  # 0,6 * 1,0 = 0,6 > 0,3 : plafonné


def test_seuils_veille_accepte_un_seuil_journal_strictement_inferieur():
    assert seuils_veille(0.5, 0.2) == 0.2


def test_seuils_veille_refuse_un_seuil_journal_pas_strictement_inferieur():
    with pytest.raises(SystemExit):
        seuils_veille(0.5, 0.5)
    with pytest.raises(SystemExit):
        seuils_veille(0.5, 0.6)


def test_pas_d_alerte_sous_le_seuil():
    v = Veilleur(seuil_journal=0.3)
    assert all(v.ajouter(BLOC, 0.1) is None for _ in range(500))


def test_une_alerte_garde_avant_et_apres():
    v = Veilleur(seuil_journal=0.3, avant_s=1.5, apres_s=1.5)
    alertes = [v.ajouter(BLOC, 0.8 if i == 200 else 0.0) for i in range(400)]
    trouvees = [a for a in alertes if a is not None]
    assert len(trouvees) == 1
    alerte = trouvees[0]
    assert alerte.score == 0.8
    assert abs(alerte.instant_s - 201 * 0.02) < 1e-9
    assert alerte.audio.size == (75 + 1 + 75) * 320


def test_le_score_maximal_est_retenu_et_la_refractaire_evite_les_doublons():
    v = Veilleur(seuil_journal=0.3, avant_s=0.2, apres_s=0.2, refractaire_s=1.0)
    scores = [0.0] * 300
    scores[10], scores[12], scores[40] = 0.5, 0.9, 0.7  # 40 tombe dans la réfractaire
    alertes = [a for a in (v.ajouter(BLOC, s) for s in scores) if a is not None]
    assert [a.score for a in alertes] == [0.9]


class FauxPeripherique:
    async def lire_bloc(self):
        return BLOC


class FauxPredicteur:
    def __init__(self, scores):
        self._scores = iter(scores)

    def score(self, bloc):
        return next(self._scores)


async def test_veiller_ecrit_les_alertes_et_le_journal(tmp_path):
    scores = [0.0] * 400
    scores[100] = 0.6
    scores[300] = 0.35
    alertes = await veiller(
        FauxPeripherique(),
        FauxPredicteur(scores),
        Veilleur(),
        tmp_path,
        seuil_reel=0.5,
        blocs_max=400,
    )
    assert len(alertes) == 2
    assert sum(a["faux_reveil"] for a in alertes) == 1
    assert len(list(tmp_path.glob("*_alerte_*.wav"))) == 2
    journal = json.loads((tmp_path / "journal.json").read_text())
    assert journal["faux_reveils"] == 1


async def test_veiller_prefixe_les_alertes_par_le_dossier_de_session(tmp_path):
    """Plusieurs journées copiées dans un même faux_reveils/ ne doivent pas s'écraser."""
    scores = [0.0] * 200
    scores[100] = 0.6
    session = tmp_path / "20260923-1200"
    alertes = await veiller(
        FauxPeripherique(),
        FauxPredicteur(scores),
        Veilleur(),
        session,
        seuil_reel=0.5,
        blocs_max=200,
    )
    assert len(alertes) == 1
    assert alertes[0]["fichier"].startswith("20260923-1200_alerte_")
    assert list(session.glob("20260923-1200_alerte_*.wav"))
    assert not list(session.glob("alerte_*.wav"))

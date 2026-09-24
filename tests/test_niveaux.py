import asyncio
import struct
import time

from atlas_core.niveaux import INTERVALLE_S, CalendrierNiveaux, niveau


def _pcm(amplitude: int, echantillons: int = 320) -> bytes:
    """Un créneau ±amplitude : sa valeur efficace vaut exactement l'amplitude."""
    return struct.pack(f"<{echantillons}h", *([amplitude, -amplitude] * (echantillons // 2)))


def test_le_silence_vaut_zero():
    assert niveau(b"\x00" * 640) == 0.0


def test_un_morceau_vide_vaut_zero():
    assert niveau(b"") == 0.0


def test_un_signal_fort_vaut_un():
    assert niveau(_pcm(32000)) == 1.0


def test_moins_35_dbfs_vaut_la_moitie():
    amplitude = round(32768 * 10 ** (-35 / 20))
    assert abs(niveau(_pcm(amplitude)) - 0.5) < 0.01


class FaussePoignee:
    def __init__(self, delai: float, rappel, valeur: float) -> None:
        self.delai, self.rappel, self.valeur = delai, rappel, valeur
        self.annulee = False

    def cancel(self) -> None:
        self.annulee = True


class FauxPlanificateur:
    def __init__(self) -> None:
        self.prevues: list[FaussePoignee] = []

    def __call__(self, delai, rappel, valeur) -> FaussePoignee:
        poignee = FaussePoignee(delai, rappel, valeur)
        self.prevues.append(poignee)
        return poignee


def _calendrier(horloge: list[float]):
    plan = FauxPlanificateur()
    return CalendrierNiveaux(lambda v: None, horloge=lambda: horloge[0], planifier=plan), plan


def test_les_niveaux_sont_cales_sur_la_lecture_et_limites_a_15_par_seconde():
    horloge = [100.0]
    calendrier, plan = _calendrier(horloge)
    for _ in range(50):  # une seconde de voix arrivée d'un coup : la synthèse est en avance
        calendrier.ajouter(_pcm(3000))
    delais = [p.delai for p in plan.prevues]
    assert delais[0] == 0.0
    assert 12 <= len(delais) <= 15
    assert all(b - a >= INTERVALLE_S - 1e-9 for a, b in zip(delais, delais[1:], strict=False))
    assert delais[-1] < 1.0


def test_apres_un_silence_la_lecture_repart_du_present():
    horloge = [0.0]
    calendrier, plan = _calendrier(horloge)
    calendrier.ajouter(_pcm(3000))
    horloge[0] = 5.0
    calendrier.ajouter(_pcm(3000))
    assert [p.delai for p in plan.prevues] == [0.0, 0.0]


def test_annuler_arrete_les_niveaux_prevus_et_remet_la_lecture_a_zero():
    horloge = [0.0]
    calendrier, plan = _calendrier(horloge)
    for _ in range(20):
        calendrier.ajouter(_pcm(3000))
    calendrier.annuler()
    assert plan.prevues and all(p.annulee for p in plan.prevues)
    calendrier.ajouter(_pcm(3000))
    assert plan.prevues[-1].delai == 0.0


def test_apres_lecture_appelle_tout_de_suite_sans_lecture_en_cours():
    horloge = [0.0]
    calendrier, plan = _calendrier(horloge)
    appels = []
    calendrier.apres_lecture(lambda: appels.append(True))
    assert appels == [True]
    assert plan.prevues == []


def test_apres_lecture_programme_a_la_fin_de_la_lecture_puis_annule():
    horloge = [0.0]
    calendrier, plan = _calendrier(horloge)
    calendrier.ajouter(_pcm(3000))  # de la lecture reste programmée
    appels = []
    calendrier.apres_lecture(lambda: appels.append(True))
    assert appels == []
    assert plan.prevues[-1].delai > 0.0
    calendrier.annuler()
    assert plan.prevues[-1].annulee


async def test_par_defaut_le_niveau_est_publie_par_la_boucle():
    recus: list[float] = []
    calendrier = CalendrierNiveaux(recus.append, horloge=time.monotonic)
    calendrier.ajouter(_pcm(32000))
    await asyncio.sleep(0.01)
    assert recus == [1.0]

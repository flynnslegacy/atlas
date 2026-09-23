import asyncio
from collections import Counter

import numpy as np

from scripts.mot_reveil.audio import lire_wav
from scripts.mot_reveil.enregistrer import enregistrer_avec_delai, seance
from scripts.mot_reveil.seance import Prise, plan_seance


def test_plan_de_seance():
    prises = plan_seance()
    compte = Counter(p.dossier for p in prises)
    assert compte == {"positifs": 108, "atlas_seul": 10, "parole": 10, "bureau": 12}
    assert len({(p.dossier, p.nom) for p in prises}) == len(prises)
    assert all("Hey Atlas" in p.consigne for p in prises if p.dossier == "positifs")
    assert {p.nom.split("_")[0] for p in prises if p.dossier == "positifs"} == {
        "bureau",
        "m150",
        "m300",
    }


def test_plan_de_seance_donne_le_temps_de_rejoindre_la_distance():
    delais = {p.nom.split("_")[0]: p.delai_s for p in plan_seance() if p.dossier == "positifs"}
    assert delais == {"bureau": 0.0, "m150": 3.0, "m300": 5.0}


class FauxPeripherique:
    """Comme le vrai micro, lire_bloc rend la main à la boucle : sans cela, l'attente
    d'Entrée (un fil) ne pourrait jamais se terminer."""

    def __init__(self):
        self.lus = 0

    async def lire_bloc(self):
        await asyncio.sleep(0)
        self.lus += 1
        return (np.full(320, 1000, dtype="<i2")).tobytes()


async def test_seance_enregistre_et_reprend(tmp_path):
    prises = [
        Prise("positifs", "bureau_001", "dis-le", 0.2),
        Prise("parole", "parole_01", "parle", 0.4),
    ]
    p = FauxPeripherique()
    assert await seance(p, prises, tmp_path, demander=lambda message: "") == 2
    audio, frequence = lire_wav(tmp_path / "positifs" / "bureau_001.wav")
    assert frequence == 16000 and audio.size == 3200
    # Relancée, la séance ne refait rien.
    assert await seance(p, prises, tmp_path, demander=lambda message: "") == 0


async def test_enregistrer_avec_delai_lit_exactement_le_delai_puis_la_duree():
    p = FauxPeripherique()
    prise = Prise("positifs", "m150_001", "dis-le", 0.2, 0.4)
    audio = await enregistrer_avec_delai(p, prise)
    assert p.lus == 20 + 10  # 0,4 s / 20 ms puis 0,2 s / 20 ms
    assert audio.size == 3200  # seule la duree_s est enregistrée : le délai n'y fuit pas


async def test_seance_laisse_le_delai_s_ecouler_sans_le_mettre_dans_le_wav(tmp_path):
    prise = Prise("positifs", "m300_001", "dis-le", 0.2, 0.6)
    p = FauxPeripherique()
    assert await seance(p, [prise], tmp_path, demander=lambda message: "") == 1
    audio, frequence = lire_wav(tmp_path / "positifs" / "m300_001.wav")
    assert frequence == 16000 and audio.size == 3200  # 0,2 s à 16 000 Hz, jamais le délai

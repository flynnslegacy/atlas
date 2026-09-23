import asyncio
from collections import Counter

import numpy as np

from scripts.mot_reveil.audio import lire_wav
from scripts.mot_reveil.enregistrer import seance
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

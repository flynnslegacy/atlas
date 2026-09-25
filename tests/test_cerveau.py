import datetime as dt

import pytest

from atlas_core.cerveau import CerveauBouchon


async def _texte(cerveau, demande: str) -> str:
    return "".join([f async for f in cerveau.repondre(demande)])


async def test_il_donne_l_heure():
    reponse = await _texte(CerveauBouchon(heure=lambda: (14, 32)), "quelle heure est-il")
    assert "quatorze heures trente-deux" in reponse


@pytest.mark.parametrize(
    ("heure", "attendu"),
    [
        ((14, 32), "Il est quatorze heures trente-deux."),
        ((1, 5), "Il est une heure cinq."),
        ((0, 0), "Il est minuit."),
        ((12, 10), "Il est midi dix."),
    ],
)
async def test_l_heure_se_dit_en_bon_francais(heure, attendu):
    reponse = await _texte(CerveauBouchon(heure=lambda: heure), "quelle heure est-il")
    assert reponse.strip() == attendu


async def test_l_heure_et_les_minutes_viennent_d_une_seule_lecture(monkeypatch):
    # Lire l'horloge deux fois à 10 h 59 min 59,9 s donnerait « dix heures » et
    # « zéro » minute : une heure fausse d'une heure.
    lectures = iter([dt.datetime(2026, 9, 22, 10, 59), dt.datetime(2026, 9, 22, 11, 0)])

    class HorlogeQuiTourne(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return next(lectures)

    monkeypatch.setattr(dt, "datetime", HorlogeQuiTourne)
    reponse = await _texte(CerveauBouchon(), "quelle heure est-il")
    assert reponse.strip() == "Il est dix heures cinquante-neuf."


async def test_il_repond_bonjour():
    assert "Bonjour" in await _texte(CerveauBouchon(), "bonjour Atlas")


async def test_il_assume_de_ne_pas_savoir():
    reponse = await _texte(CerveauBouchon(), "explique-moi la mécanique quantique")
    assert "phase un" in reponse


async def test_il_rend_plusieurs_fragments():
    fragments = [f async for f in CerveauBouchon().repondre("bonjour")]
    assert len(fragments) > 1, "le cerveau doit streamer, sinon on ne teste pas le découpage"


async def test_le_bouchon_se_ferme_sans_rien_faire():
    await CerveauBouchon().fermer()

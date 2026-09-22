from helios_core.cerveau import CerveauBouchon


async def _texte(cerveau, demande: str) -> str:
    return "".join([f async for f in cerveau.repondre(demande)])


async def test_il_donne_l_heure():
    reponse = await _texte(CerveauBouchon(heure=lambda: (14, 32)), "quelle heure est-il")
    assert "quatorze heures trente-deux" in reponse


async def test_il_repond_bonjour():
    assert "Bonjour" in await _texte(CerveauBouchon(), "bonjour Helios")


async def test_il_assume_de_ne_pas_savoir():
    reponse = await _texte(CerveauBouchon(), "explique-moi la mécanique quantique")
    assert "phase un" in reponse


async def test_il_rend_plusieurs_fragments():
    fragments = [f async for f in CerveauBouchon().repondre("bonjour")]
    assert len(fragments) > 1, "le cerveau doit streamer, sinon on ne teste pas le découpage"

"""Le client audio pendant une réponse de Claude : barge-in entre deux phrases, ordre de
l'interruption, clé du Core."""

import pytest
from test_client_audio import (
    BLOC_FORT,
    FausseHorloge,
    FauxPeripherique,
    FauxTransport,
    _client,
    _jouer,
)

from atlas_audio.client import lire_cle_audio
from atlas_core.protocole import Etat, Interruption, Reveil, StopAudio


def _interrompu(t: FauxTransport) -> bool:
    return any(isinstance(m, Interruption) for m in t.json)


async def test_le_bargein_reste_arme_dans_un_blanc_entre_deux_phrases():
    h = FausseHorloge()
    t, p = FauxTransport(), FauxPeripherique([BLOC_FORT] * 6)
    c = _client(t, p, parole=[True] * 6, reveil_au=None, horloge=h)
    await c.sur_message(Etat(valeur="parole"))
    await _jouer(c, id_enonce=1, blocs=1)
    h.avancer(2.0)  # la phrase suivante tarde : plus aucun son ne joue

    await c.boucle_capture()

    assert _interrompu(t), "« attends » dans le blanc entre deux phrases coupe Atlas"


async def test_une_reponse_muette_n_arme_pas_le_bargein():
    h = FausseHorloge()
    t, p = FauxTransport(), FauxPeripherique([BLOC_FORT] * 6)
    c = _client(t, p, parole=[True] * 6, reveil_au=0, horloge=h)
    await c.sur_message(Etat(valeur="parole"))  # muet : aucune phrase n'est dite

    await c.boucle_capture()

    assert not _interrompu(t)
    assert isinstance(t.json[0], Reveil), "le mot de réveil reste écouté"


async def test_la_reflexion_d_une_recherche_desarme_le_bargein():
    h = FausseHorloge()
    t, p = FauxTransport(), FauxPeripherique([BLOC_FORT] * 6)
    c = _client(t, p, parole=[True] * 6, reveil_au=0, horloge=h)
    await c.sur_message(Etat(valeur="parole"))
    await _jouer(c, id_enonce=1, blocs=1)  # « Je regarde ça. »
    await c.sur_message(Etat(valeur="reflexion"))
    h.avancer(2.0)

    await c.boucle_capture()

    assert not _interrompu(t)
    assert isinstance(t.json[0], Reveil), "pendant la recherche, « Hey Atlas » reprend la main"


async def test_la_fin_de_la_reponse_desarme_le_bargein_une_fois_le_son_joue():
    h = FausseHorloge()
    t, p = FauxTransport(), FauxPeripherique([BLOC_FORT] * 6)
    c = _client(t, p, parole=[True] * 6, reveil_au=None, horloge=h)
    await _jouer(c, id_enonce=1, blocs=1)
    await c.sur_message(Etat(valeur="repos"))
    h.avancer(2.0)

    await c.boucle_capture()

    assert not _interrompu(t)


async def test_une_phrase_en_vol_d_une_reponse_coupee_n_arme_pas_le_bargein():
    h = FausseHorloge()
    t, p = FauxTransport(), FauxPeripherique([BLOC_FORT] * 6)
    c = _client(t, p, parole=[True] * 6, reveil_au=0, horloge=h)
    await _jouer(c, id_enonce=1, blocs=1)
    await c.sur_message(StopAudio(id_enonce=1))  # une question tapée coupe la réponse
    await _jouer(c, id_enonce=1, blocs=1, rang=2)  # sa phrase suivante était en vol
    h.avancer(2.0)

    await c.boucle_capture()

    assert isinstance(t.json[0], Reveil), "le micro est rendu au mot de réveil"


class PeripheriqueQuiNote(FauxPeripherique):
    def __init__(self, blocs, journal: list) -> None:
        super().__init__(blocs)
        self.journal = journal

    async def vider(self) -> None:
        await super().vider()
        self.journal.append("vider")


async def test_l_interruption_part_au_core_avant_le_vidage_du_son():
    t = FauxTransport()
    p = PeripheriqueQuiNote([BLOC_FORT] * 6, t.flux)
    c = _client(t, p, parole=[True] * 6, reveil_au=None)
    await _jouer(c, id_enonce=1, blocs=1)

    await c.boucle_capture()

    ordre = [x for x in t.flux if x in ("interruption", "vider")]
    assert ordre[:2] == ["interruption", "vider"]


def test_la_cle_du_client_vient_de_l_environnement(monkeypatch):
    monkeypatch.setenv("ATLAS_AUDIO_CLE", "  cle-audio  ")
    assert lire_cle_audio() == "cle-audio"


@pytest.mark.parametrize("valeur", [None, "", "   "])
def test_sans_cle_le_client_refuse_de_demarrer(monkeypatch, valeur):
    if valeur is None:
        monkeypatch.delenv("ATLAS_AUDIO_CLE", raising=False)
    else:
        monkeypatch.setenv("ATLAS_AUDIO_CLE", valeur)
    with pytest.raises(ValueError, match="ATLAS_AUDIO_CLE"):
        lire_cle_audio()

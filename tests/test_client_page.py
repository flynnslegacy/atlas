"""Le client audio au service d'une page : marge de sortie, amorçage de l'annuleur
d'écho du navigateur, et l'orbe touchée."""

from test_client_audio import (
    BLOC,
    BLOC_FORT,
    DetecteurScript,
    FausseHorloge,
    FauxPeripherique,
    FauxTransport,
    ReveilleurScript,
    _client,
    _jouer,
)

from atlas_audio.client import ClientAudio
from atlas_audio.vad import Endpointeur
from atlas_core.protocole import Etat, Interruption, Reveil, decoder_audio_entrant


def _client_page(t, p, parole, horloge, amorcage_s=0.0, marge_sortie_s=0.15, reveil_au=None):
    return ClientAudio(
        transport=t,
        peripherique=p,
        detecteur=DetecteurScript(parole),
        endpointeur=Endpointeur(silence_ms=60, parole_min_ms=40),
        reveilleur=ReveilleurScript(reveil_au),
        bargein=Endpointeur(silence_ms=60, parole_min_ms=40),
        horloge=horloge,
        amorcage_s=amorcage_s,
        marge_sortie_s=marge_sortie_s,
    )


def _interrompu(t: FauxTransport) -> bool:
    return any(isinstance(m, Interruption) for m in t.json)


async def test_la_marge_de_sortie_se_regle():
    h = FausseHorloge()
    t, p = FauxTransport(), FauxPeripherique([BLOC] * 6)
    c = _client_page(t, p, parole=[False] * 6, horloge=h, marge_sortie_s=0.5, reveil_au=0)
    await _jouer(c, id_enonce=1, blocs=10)  # 0,2 s de son
    await c.sur_message(Etat(valeur="repos"))
    h.avancer(0.2 + 0.4)  # au-delà de 0,15 s de marge, en deçà de 0,5 s

    await c.boucle_capture()

    assert t.json == [], "le mot de réveil n'est pas encore écouté : Atlas parle encore"
    p.ajouter([BLOC] * 2)
    h.avancer(0.2)
    await c.boucle_capture()
    assert isinstance(t.json[0], Reveil)


async def test_la_voix_ne_coupe_pas_atlas_pendant_l_amorcage():
    h = FausseHorloge()
    t, p = FauxTransport(), FauxPeripherique([BLOC_FORT] * 6)
    c = _client_page(t, p, parole=[True] * 20, horloge=h, amorcage_s=1.0)
    await _jouer(c, id_enonce=1, blocs=100)  # 2 s de voix, dont la première seconde amorce

    await c.boucle_capture()
    assert not _interrompu(t), "pendant la première seconde jouée, l'écho n'est pas une coupure"

    h.avancer(1.1)  # la seconde amorcée a fini de jouer
    p.ajouter([BLOC_FORT] * 6)
    await c.boucle_capture()
    assert _interrompu(t)


async def test_reamorcer_rouvre_l_amorcage():
    h = FausseHorloge()
    t, p = FauxTransport(), FauxPeripherique([])
    c = _client_page(t, p, parole=[True] * 20, horloge=h, amorcage_s=0.2)
    await _jouer(c, id_enonce=1, blocs=10)
    h.avancer(0.3)  # l'amorçage est passé
    c.reamorcer()  # la page revient d'une interruption d'iOS
    await _jouer(c, id_enonce=1, blocs=50, rang=2)
    p.ajouter([BLOC_FORT] * 6)

    await c.boucle_capture()

    assert not _interrompu(t)


async def test_toucher_l_orbe_au_repos_ouvre_l_ecoute_des_ce_bloc():
    t, p = FauxTransport(), FauxPeripherique([BLOC_FORT, BLOC, BLOC])
    c = _client(t, p, parole=[True, True, True], reveil_au=None)
    c.demander_la_parole()

    await c.boucle_capture()

    assert t.types()[0] == "reveil"
    assert decoder_audio_entrant(t.binaire[0]) == BLOC_FORT, "le premier mot n'est pas perdu"
    assert len(t.binaire) == 3


async def test_toucher_l_orbe_pendant_qu_atlas_parle_le_coupe():
    h = FausseHorloge()
    t, p = FauxTransport(), FauxPeripherique([BLOC, BLOC])
    c = _client_page(t, p, parole=[False, False], horloge=h, amorcage_s=10.0)
    await _jouer(c, id_enonce=1, blocs=50)
    c.demander_la_parole()  # même pendant l'amorçage : toucher coupe toujours

    await c.boucle_capture()

    assert t.types()[0] == "interruption"
    assert p.vidages == 1
    assert len(t.binaire) == 2, "l'écoute est ouverte : les blocs partent au Core"


async def test_toucher_l_orbe_pendant_l_ecoute_ne_rouvre_rien():
    t, p = FauxTransport(), FauxPeripherique([BLOC] * 4)
    c = _client(t, p, parole=[True] * 4, reveil_au=0)  # « Hey Atlas » au premier bloc
    await c.boucle_capture()
    c.demander_la_parole()
    p.ajouter([BLOC] * 2)

    await c.boucle_capture()

    assert t.types().count("reveil") == 1

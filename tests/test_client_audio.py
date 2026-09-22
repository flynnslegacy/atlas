import asyncio

from helios_audio.client import ClientAudio, Reglages, lire_reglages
from helios_core.protocole import (
    Dire,
    Etat,
    FinEnonce,
    Interruption,
    StopAudio,
    decoder_audio_entrant,
    encoder_audio_sortant,
)

BLOC = b"\x00" * 640


class FauxTransport:
    def __init__(self) -> None:
        self.json: list = []
        self.binaire: list[bytes] = []

    async def envoyer_json(self, msg) -> None:
        self.json.append(msg)

    async def envoyer_binaire(self, trame: bytes) -> None:
        self.binaire.append(trame)

    def types(self) -> list[str]:
        return [m.type for m in self.json]


class FausseHorloge:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def avancer(self, secondes: float) -> None:
        self.t += secondes


class FauxPeripherique:
    def __init__(self, blocs: list[bytes]) -> None:
        self._blocs = list(blocs)
        self.joues: list[bytes] = []
        self.vidages = 0

    def ajouter(self, blocs: list[bytes]) -> None:
        self._blocs.extend(blocs)

    async def lire_bloc(self) -> bytes:
        if not self._blocs:
            raise asyncio.CancelledError
        return self._blocs.pop(0)

    async def jouer(self, pcm: bytes) -> None:
        self.joues.append(pcm)

    async def vider(self) -> None:
        self.vidages += 1

    async def fermer(self) -> None:
        pass


class DetecteurScript:
    """Rend les valeurs d'une liste, puis False."""

    def __init__(self, suite: list[bool]) -> None:
        self._suite = list(suite)

    def parle(self, bloc: bytes) -> bool:
        return self._suite.pop(0) if self._suite else False


class ReveilleurScript:
    def __init__(self, a_declencher_au_bloc: int | None = 0) -> None:
        self._cible = a_declencher_au_bloc
        self._n = -1

    def examiner(self, bloc: bytes) -> bool:
        self._n += 1
        return self._n == self._cible


def _client(transport, peripherique, parole: list[bool], reveil_au=0, horloge=None):
    from helios_audio.vad import Endpointeur

    return ClientAudio(
        transport=transport,
        peripherique=peripherique,
        detecteur=DetecteurScript(parole),
        endpointeur=Endpointeur(silence_ms=60, parole_min_ms=40),
        reveilleur=ReveilleurScript(reveil_au),
        bargein=Endpointeur(silence_ms=60, parole_min_ms=40),
        horloge=horloge or FausseHorloge(),
    )


async def _jouer(client, id_enonce: int, blocs: int, rang: int = 1) -> None:
    """Le Core annonce une phrase et en livre l'audio d'un coup, sans attendre."""
    await client.sur_message(Dire(id_enonce=id_enonce, rang=rang, texte="Phrase."))
    for _ in range(blocs):
        await client.sur_trame(encoder_audio_sortant(id_enonce, BLOC))


async def test_le_reveil_est_annonce_puis_l_audio_part():
    t, p = FauxTransport(), FauxPeripherique([BLOC] * 6)
    c = _client(t, p, parole=[True] * 6)
    await c.boucle_capture()

    assert t.types()[0] == "reveil"
    assert len(t.binaire) == 5, "le bloc du réveil n'est pas envoyé, les suivants oui"
    assert decoder_audio_entrant(t.binaire[0]) == BLOC


async def test_le_silence_declenche_la_fin_d_enonce():
    t, p = FauxTransport(), FauxPeripherique([BLOC] * 10)
    c = _client(t, p, parole=[True] * 4 + [False] * 6)
    await c.boucle_capture()

    assert any(isinstance(m, FinEnonce) for m in t.json)


async def test_avant_le_reveil_rien_ne_part():
    t, p = FauxTransport(), FauxPeripherique([BLOC] * 4)
    c = _client(t, p, parole=[True] * 4, reveil_au=None)
    await c.boucle_capture()

    assert t.json == [] and t.binaire == []


async def test_l_audio_recu_est_joue():
    t, p = FauxTransport(), FauxPeripherique([])
    c = _client(t, p, parole=[])
    await c.sur_message(Dire(id_enonce=1, rang=1, texte="Bonjour."))
    await c.sur_trame(encoder_audio_sortant(1, BLOC))
    assert p.joues == [BLOC]


async def test_un_stop_audio_vide_le_peripherique():
    t, p = FauxTransport(), FauxPeripherique([])
    c = _client(t, p, parole=[])
    await c.sur_message(StopAudio(id_enonce=1))
    assert p.vidages == 1


async def test_une_trame_perimee_n_est_pas_jouee():
    t, p = FauxTransport(), FauxPeripherique([])
    c = _client(t, p, parole=[])
    await c.sur_message(Dire(id_enonce=2, rang=1, texte="Deux."))
    await c.sur_trame(encoder_audio_sortant(1, BLOC))  # énoncé précédent
    assert p.joues == []


async def test_parler_pendant_la_parole_declenche_l_interruption():
    t, p = FauxTransport(), FauxPeripherique([BLOC] * 6)
    c = _client(t, p, parole=[True] * 6, reveil_au=None)
    await _jouer(c, id_enonce=1, blocs=1)
    await c.boucle_capture()

    assert any(isinstance(m, Interruption) for m in t.json)
    assert p.vidages >= 1


async def test_apres_le_bargein_une_trame_deja_en_vol_n_est_pas_jouee():
    t, p = FauxTransport(), FauxPeripherique([BLOC] * 6)
    c = _client(t, p, parole=[True] * 6, reveil_au=None)
    await _jouer(c, id_enonce=1, blocs=1)
    await c.boucle_capture()  # détecte le barge-in et coupe l'énoncé 1

    # Trame de la réponse coupée, remise après le vidage : elle ne doit pas sonner.
    await c.sur_trame(encoder_audio_sortant(1, BLOC))
    assert p.joues == [BLOC], "seule la trame jouée avant la coupure a sonné"


async def test_apres_un_stop_audio_une_trame_deja_en_vol_n_est_pas_jouee():
    t, p = FauxTransport(), FauxPeripherique([])
    c = _client(t, p, parole=[])
    await c.sur_message(Dire(id_enonce=1, rang=1, texte="Un."))
    await c.sur_message(StopAudio(id_enonce=1))

    # Trame de la réponse coupée, remise après le vidage : elle ne doit pas sonner.
    await c.sur_trame(encoder_audio_sortant(1, BLOC))
    assert p.joues == []


async def test_le_bargein_reste_arme_apres_le_repos_tant_que_l_audio_se_joue():
    h = FausseHorloge()
    t, p = FauxTransport(), FauxPeripherique([BLOC] * 6)
    c = _client(t, p, parole=[True] * 6, reveil_au=None, horloge=h)
    await _jouer(c, id_enonce=1, blocs=100)  # deux secondes d'audio livrées d'un coup
    await c.sur_message(Etat(valeur="repos"))  # le Core a fini d'ENVOYER, pas de jouer
    h.avancer(0.5)

    await c.boucle_capture()

    assert any(isinstance(m, Interruption) for m in t.json)


async def test_le_bargein_se_desarme_quand_l_audio_a_fini_de_jouer():
    h = FausseHorloge()
    t, p = FauxTransport(), FauxPeripherique([BLOC] * 6)
    c = _client(t, p, parole=[True] * 6, reveil_au=None, horloge=h)
    await _jouer(c, id_enonce=1, blocs=100)
    await c.sur_message(Etat(valeur="repos"))
    h.avancer(3.0)  # au-delà des deux secondes d'audio et de la marge de sortie

    await c.boucle_capture()

    assert not any(isinstance(m, Interruption) for m in t.json)
    assert p.vidages == 0


def test_lire_reglages_rend_les_defauts_sans_variable(monkeypatch):
    monkeypatch.delenv("HELIOS_REVEIL_SEUIL", raising=False)
    monkeypatch.delenv("HELIOS_SILENCE_MS", raising=False)
    monkeypatch.delenv("HELIOS_BARGEIN_MS", raising=False)

    assert lire_reglages() == Reglages(seuil_reveil=0.5, silence_ms=400, bargein_ms=300)


def test_lire_reglages_prend_les_variables_d_environnement(monkeypatch):
    monkeypatch.setenv("HELIOS_REVEIL_SEUIL", "0.7")
    monkeypatch.setenv("HELIOS_SILENCE_MS", "600")
    monkeypatch.setenv("HELIOS_BARGEIN_MS", "250")

    assert lire_reglages() == Reglages(seuil_reveil=0.7, silence_ms=600, bargein_ms=250)

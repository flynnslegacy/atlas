import asyncio
import logging

import pytest

from atlas_audio.client import ClientAudio, Reglages, lire_reglages
from atlas_audio.vad import Endpointeur
from atlas_core.protocole import (
    Dire,
    Erreur,
    Etat,
    FinEnonce,
    Interruption,
    StopAudio,
    decoder_audio_entrant,
    encoder_audio_sortant,
)

BLOC = b"\x00" * 640
# ~0 dBFS : nettement au-dessus du seuil de barge-in par défaut (-40 dBFS), pour les
# tests qui doivent ressembler à de la vraie parole plutôt qu'à de l'écho résiduel.
BLOC_FORT = b"\xff\x7f" * 320


class FauxTransport:
    def __init__(self) -> None:
        self.json: list = []
        self.binaire: list[bytes] = []
        self.flux: list = []  # messages et blocs, dans l'ordre d'envoi

    async def envoyer_json(self, msg) -> None:
        self.json.append(msg)
        self.flux.append(msg.type)

    async def envoyer_binaire(self, trame: bytes) -> None:
        self.binaire.append(trame)
        self.flux.append(decoder_audio_entrant(trame))

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


async def test_un_echo_calme_pendant_la_parole_ne_declenche_pas_l_interruption():
    # Spike S2 : l'écho résiduel d'Atlas pendant que l'annulateur d'écho converge
    # ressemble à de la parole pour le détecteur, mais reste sous le seuil d'énergie.
    t, p = FauxTransport(), FauxPeripherique([BLOC] * 6)
    c = _client(t, p, parole=[True] * 6, reveil_au=None)
    await _jouer(c, id_enonce=1, blocs=1)
    await c.boucle_capture()

    assert not any(isinstance(m, Interruption) for m in t.json)
    assert p.vidages == 0


async def test_parler_fort_pendant_la_parole_declenche_l_interruption(caplog):
    t, p = FauxTransport(), FauxPeripherique([BLOC_FORT] * 6)
    c = _client(t, p, parole=[True] * 6, reveil_au=None)
    await _jouer(c, id_enonce=1, blocs=1)

    with caplog.at_level(logging.INFO, logger="atlas_audio.client"):
        await c.boucle_capture()

    assert any(isinstance(m, Interruption) for m in t.json)
    assert p.vidages >= 1
    assert "interruption détectée (" in caplog.text
    assert "dBFS sur 300 ms)" in caplog.text


async def test_apres_le_bargein_une_trame_deja_en_vol_n_est_pas_jouee():
    t, p = FauxTransport(), FauxPeripherique([BLOC_FORT] * 6)
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
    t, p = FauxTransport(), FauxPeripherique([BLOC_FORT] * 6)
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


async def test_une_phrase_en_vol_de_la_reponse_coupee_ne_revient_jamais():
    t, p = FauxTransport(), FauxPeripherique([BLOC_FORT] * 2)
    c = _client(t, p, parole=[True] * 2 + [True] * 4, reveil_au=None)
    await _jouer(c, id_enonce=3, blocs=1)
    await c.boucle_capture()  # barge-in sur l'énoncé 3
    assert [type(m) for m in t.json] == [Interruption]

    # La phrase suivante de la réponse coupée était déjà en vol.
    await _jouer(c, id_enonce=3, blocs=5, rang=2)
    assert p.joues == [BLOC], "aucune trame de l'énoncé 3 ne sonne après la coupure"

    # Le barge-in n'est pas ré-armé : la parole qui suit est capturée, pas prise
    # pour une seconde interruption.
    p.ajouter([BLOC] * 4)
    await c.boucle_capture()
    assert sum(isinstance(m, Interruption) for m in t.json) == 1

    # La réponse suivante, elle, est jouée normalement.
    await _jouer(c, id_enonce=4, blocs=2)
    assert p.joues == [BLOC] * 3


async def test_une_nouvelle_phrase_du_meme_enonce_ne_remet_pas_le_bargein_a_zero():
    t, p = FauxTransport(), FauxPeripherique([BLOC_FORT])
    c = _client(t, p, parole=[True, True], reveil_au=None)  # seuil : deux blocs
    await _jouer(c, id_enonce=1, blocs=1)
    await c.boucle_capture()  # un bloc de parole : pas encore d'interruption
    assert t.json == []

    await _jouer(c, id_enonce=1, blocs=1, rang=2)
    p.ajouter([BLOC_FORT])
    await c.boucle_capture()  # le second bloc atteint le seuil

    assert any(isinstance(m, Interruption) for m in t.json)


def _bloc(n: int) -> bytes:
    return bytes([n]) * 640


async def test_la_parole_qui_declenche_le_bargein_part_vers_le_core():
    # Seuil de barge-in : deux blocs. « Non » tient dans les blocs 3 et 4.
    blocs = [_bloc(n) for n in range(1, 6)]
    t, p = FauxTransport(), FauxPeripherique(blocs)
    c = _client(t, p, parole=[False, False, True, True, True], reveil_au=None)
    await _jouer(c, id_enonce=1, blocs=1)

    await c.boucle_capture()

    # D'abord l'interruption, puis le pré-roulement, puis la suite de la capture.
    assert t.flux == ["interruption", *blocs]


async def test_le_pre_roulement_rejoue_porte_le_verdict_brut_pas_filtre():
    # Le bloc calme est de la vraie parole pour le détecteur (verdict brut) mais reste
    # sous le seuil d'énergie : seul le bloc fort qui suit arme le barge-in. Si la
    # capture qui suit l'interruption rejouait le verdict FILTRÉ par la porte au lieu
    # du brut, le bloc calme compterait comme du silence, l'énoncé ne serait jamais
    # vu comme commencé, et les trois blocs de silence plus bas ne le clôtureraient
    # jamais avec un FinEnonce.
    t = FauxTransport()
    p = FauxPeripherique([BLOC, BLOC_FORT])
    c = ClientAudio(
        transport=t,
        peripherique=p,
        detecteur=DetecteurScript([True, True]),
        endpointeur=Endpointeur(silence_ms=60, parole_min_ms=40),  # 3 blocs, 2 blocs
        reveilleur=ReveilleurScript(None),
        bargein=Endpointeur(silence_ms=60, parole_min_ms=20),  # un seul bloc fort suffit
        horloge=FausseHorloge(),
    )
    await _jouer(c, id_enonce=1, blocs=1)
    await c.boucle_capture()  # le bloc fort seul arme et déclenche l'interruption

    assert any(isinstance(m, Interruption) for m in t.json)

    p.ajouter([BLOC] * 3)  # silence, hors lecture désormais : capture normale
    await c.boucle_capture()

    assert any(isinstance(m, FinEnonce) for m in t.json), (
        "le bloc calme du pré-roulement doit compter comme parole (verdict brut) une "
        "fois rejoué dans la capture"
    )


async def test_une_nouvelle_phrase_reinitialise_la_fenetre_d_energie():
    # Un bloc fort à la fin de la surveillance d'un énoncé ne doit pas faire passer la
    # porte à de la parole calme sur l'énoncé suivant : la fenêtre d'énergie doit
    # repartir de zéro à chaque nouvel énoncé, comme le pré-roulement et l'endpointeur
    # de barge-in.
    t, p = FauxTransport(), FauxPeripherique([BLOC_FORT])
    c = _client(t, p, parole=[False, True, True], reveil_au=None)
    await _jouer(c, id_enonce=1, blocs=1)
    await c.boucle_capture()  # un bloc fort, mais pas de la parole pour le détecteur

    await _jouer(c, id_enonce=2, blocs=1, rang=1)  # nouvel énoncé : tout se réinitialise
    p.ajouter([BLOC, BLOC])
    await c.boucle_capture()  # deux blocs calmes, scriptés comme de la parole

    assert not any(isinstance(m, Interruption) for m in t.json), (
        "l'énergie du bloc fort de l'énoncé précédent ne doit pas faire passer la "
        "porte à de la parole calme du nouvel énoncé"
    )


async def test_la_parole_calme_hors_lecture_compte_normalement():
    # La porte d'énergie ne s'applique qu'à la surveillance du barge-in : hors lecture,
    # une parole calme doit démarrer et clore un énoncé comme avant.
    t, p = FauxTransport(), FauxPeripherique([BLOC] * 10)
    c = _client(t, p, parole=[True] * 4 + [False] * 6, reveil_au=0)
    await c.boucle_capture()

    assert any(isinstance(m, FinEnonce) for m in t.json)
    assert len(t.binaire) >= 4, "les blocs de parole calme doivent partir vers le Core"


async def test_le_mot_de_reveil_ne_part_pas_vers_le_core():
    t, p = FauxTransport(), FauxPeripherique([_bloc(n) for n in range(1, 4)])
    c = _client(t, p, parole=[True] * 3, reveil_au=0)

    await c.boucle_capture()

    assert t.flux == ["reveil", _bloc(2), _bloc(3)]


async def test_une_capture_sans_parole_se_clot_au_bout_de_cinq_secondes():
    t, p = FauxTransport(), FauxPeripherique([BLOC] * (1 + 250 + 10))
    c = _client(t, p, parole=[], reveil_au=0)  # un faux réveil, puis personne ne parle

    await c.boucle_capture()

    assert t.types() == ["reveil", "fin_enonce"]
    assert len(t.binaire) == 250, "cinq secondes de blocs, puis le micro se ferme"


async def test_une_capture_continue_se_clot_au_bout_de_trente_secondes():
    t, p = FauxTransport(), FauxPeripherique([BLOC] * (1 + 1500 + 10))
    c = _client(t, p, parole=[True] * 1600, reveil_au=0)  # la pièce ne se tait jamais

    await c.boucle_capture()

    assert t.types() == ["reveil", "fin_enonce"]
    assert len(t.binaire) == 1500, "trente secondes de blocs, puis le micro se ferme"


async def test_une_erreur_du_core_est_journalisee(caplog):
    t, p = FauxTransport(), FauxPeripherique([])
    c = _client(t, p, parole=[])

    with caplog.at_level(logging.WARNING, logger="atlas_audio.client"):
        await c.sur_message(Erreur(code="tour", message="Je n'ai pas pu répondre : voix absente"))

    assert "tour" in caplog.text
    assert "voix absente" in caplog.text


def test_lire_reglages_rend_les_defauts_sans_variable(monkeypatch):
    monkeypatch.delenv("ATLAS_REVEIL_SEUIL", raising=False)
    monkeypatch.delenv("ATLAS_SILENCE_MS", raising=False)
    monkeypatch.delenv("ATLAS_BARGEIN_MS", raising=False)
    monkeypatch.delenv("ATLAS_BARGEIN_DBFS", raising=False)

    assert lire_reglages() == Reglages(
        seuil_reveil=0.5, silence_ms=400, bargein_ms=300, bargein_dbfs=-40.0
    )


def test_lire_reglages_prend_les_variables_d_environnement(monkeypatch):
    monkeypatch.setenv("ATLAS_REVEIL_SEUIL", "0.7")
    monkeypatch.setenv("ATLAS_SILENCE_MS", "600")
    monkeypatch.setenv("ATLAS_BARGEIN_MS", "250")
    monkeypatch.setenv("ATLAS_BARGEIN_DBFS", "-35")

    assert lire_reglages() == Reglages(
        seuil_reveil=0.7, silence_ms=600, bargein_ms=250, bargein_dbfs=-35.0
    )


def test_lire_reglages_bargein_dbfs_accepte_les_bornes(monkeypatch):
    monkeypatch.setenv("ATLAS_BARGEIN_DBFS", "-120")
    assert lire_reglages().bargein_dbfs == -120.0

    monkeypatch.setenv("ATLAS_BARGEIN_DBFS", "0")
    assert lire_reglages().bargein_dbfs == 0.0


def test_lire_reglages_bargein_dbfs_malforme_leve(monkeypatch):
    monkeypatch.setenv("ATLAS_BARGEIN_DBFS", "pas-un-nombre")
    with pytest.raises(ValueError, match="ATLAS_BARGEIN_DBFS"):
        lire_reglages()


def test_lire_reglages_bargein_dbfs_non_fini_leve(monkeypatch):
    monkeypatch.setenv("ATLAS_BARGEIN_DBFS", "nan")
    with pytest.raises(ValueError, match="ATLAS_BARGEIN_DBFS"):
        lire_reglages()


def test_lire_reglages_bargein_dbfs_hors_bornes_leve(monkeypatch):
    monkeypatch.setenv("ATLAS_BARGEIN_DBFS", "5")
    with pytest.raises(ValueError, match="ATLAS_BARGEIN_DBFS"):
        lire_reglages()

    monkeypatch.setenv("ATLAS_BARGEIN_DBFS", "-125")
    with pytest.raises(ValueError, match="ATLAS_BARGEIN_DBFS"):
        lire_reglages()

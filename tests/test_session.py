import asyncio
from collections.abc import AsyncIterator

from helios_core.protocole import (
    Dire,
    Erreur,
    Etat,
    FinEnonce,
    Interruption,
    Reveil,
    StopAudio,
    Transcription,
    decoder_audio_sortant,
)
from helios_core.session import Session


class Collecteur:
    def __init__(self) -> None:
        self.json: list = []
        self.binaire: list[bytes] = []

    async def envoyer_json(self, msg) -> None:
        self.json.append(msg)

    async def envoyer_binaire(self, trame: bytes) -> None:
        self.binaire.append(trame)

    def types(self) -> list[str]:
        return [m.type for m in self.json]

    def premier(self, classe):
        return next(m for m in self.json if isinstance(m, classe))


class FausseTranscription:
    def __init__(self, texte: str) -> None:
        self.texte = texte

    async def transcrire(self, pcm: bytes) -> str:
        return self.texte


class TranscriptionLente:
    """Reste en réflexion assez longtemps pour être interrompue en cours de route."""

    async def transcrire(self, pcm: bytes) -> str:
        await asyncio.sleep(0.2)
        return "peu importe"


class TranscriptionQuiEchoue:
    async def transcrire(self, pcm: bytes) -> str:
        raise RuntimeError("panne du service de transcription")


class FausseSynthese:
    def __init__(self, blocs: int = 3, lenteur: float = 0.0) -> None:
        self.blocs, self.lenteur = blocs, lenteur

    async def synthetiser(self, texte: str) -> AsyncIterator[bytes]:
        for _ in range(self.blocs):
            if self.lenteur:
                await asyncio.sleep(self.lenteur)
            yield b"\x00" * 640


class CerveauFixe:
    def __init__(self, phrase: str = "Il est midi. Tu déjeunes ?") -> None:
        self.phrase = phrase

    async def repondre(self, texte: str) -> AsyncIterator[str]:
        for mot in self.phrase.split(" "):
            yield mot + " "
            await asyncio.sleep(0)


class CerveauLent:
    async def repondre(self, texte: str) -> AsyncIterator[str]:
        for i in range(50):
            yield f"phrase numéro {i}. "
            await asyncio.sleep(0.02)


def _session(collecteur, cerveau=None, synthese=None, texte="quelle heure est-il"):
    return Session(
        envoyer_json=collecteur.envoyer_json,
        envoyer_binaire=collecteur.envoyer_binaire,
        transcription=FausseTranscription(texte),
        synthese=synthese or FausseSynthese(),
        cerveau=cerveau or CerveauFixe(),
    )


async def _tour(session, collecteur, blocs: int = 5) -> None:
    await session.sur_message(Reveil(confiance=0.9, horodatage=0.0))
    for _ in range(blocs):
        await session.sur_audio(b"\x00" * 640)
    await session.sur_message(FinEnonce(duree_ms=blocs * 20))
    # Laisse la boucle événementielle donner la main à la tâche de fond du tour :
    # rien, dans cet appel, ne suspend réellement sinon (contrairement à un vrai
    # serveur, où lire le message client suivant est toujours une attente réelle).
    await asyncio.sleep(0.01)


async def test_un_tour_complet_dit_les_deux_phrases():
    c = Collecteur()
    s = _session(c)
    await _tour(s, c)
    await s.fermer()

    dires = [m for m in c.json if isinstance(m, Dire)]
    assert [d.texte for d in dires] == ["Il est midi.", "Tu déjeunes ?"]
    assert c.premier(Transcription).texte == "quelle heure est-il"
    assert c.types()[-1] == "etat" and c.json[-1].valeur == "repos"


async def test_les_trames_audio_portent_l_identifiant_de_l_enonce():
    c = Collecteur()
    s = _session(c)
    await _tour(s, c)
    await s.fermer()

    identifiants = {decoder_audio_sortant(t)[0] for t in c.binaire}
    assert identifiants == {1}
    assert len(c.binaire) == 2 * 3  # deux phrases, trois blocs chacune


async def test_un_enonce_vide_ne_fait_pas_parler():
    c = Collecteur()
    s = _session(c, texte="   ")
    await _tour(s, c)
    await s.fermer()

    assert not [m for m in c.json if isinstance(m, Dire)]
    assert c.binaire == []
    assert c.json[-1].valeur == "repos"


async def test_l_audio_recu_hors_ecoute_est_ignore():
    c = Collecteur()
    s = _session(c)
    await s.sur_audio(b"\x00" * 640)  # aucun réveil : on est au repos
    await s.sur_message(FinEnonce(duree_ms=20))
    await s.fermer()
    assert not [m for m in c.json if isinstance(m, Dire)]


async def test_l_interruption_envoie_stop_audio_et_repasse_en_ecoute():
    c = Collecteur()
    s = _session(c, cerveau=CerveauLent(), synthese=FausseSynthese(blocs=2, lenteur=0.01))
    await _tour(s, c)
    await asyncio.sleep(0.15)

    avant = len(c.binaire)
    await s.sur_message(Interruption(horodatage=1.0))
    await asyncio.sleep(0.15)

    assert any(isinstance(m, StopAudio) for m in c.json)
    assert len(c.binaire) == avant, "plus aucune trame ne doit partir après l'interruption"
    assert [m for m in c.json if isinstance(m, Etat)][-1].valeur == "ecoute"
    await s.fermer()


async def test_un_reveil_pendant_la_parole_interrompt():
    c = Collecteur()
    s = _session(c, cerveau=CerveauLent(), synthese=FausseSynthese(blocs=2, lenteur=0.01))
    await _tour(s, c)
    await asyncio.sleep(0.15)

    await s.sur_message(Reveil(confiance=0.9, horodatage=2.0))
    await asyncio.sleep(0.05)
    assert any(isinstance(m, StopAudio) for m in c.json)
    await s.fermer()


async def test_deux_tours_incrementent_l_identifiant():
    c = Collecteur()
    s = _session(c)
    await _tour(s, c)
    await _tour(s, c)
    await s.fermer()
    assert {decoder_audio_sortant(t)[0] for t in c.binaire} == {1, 2}


async def test_une_interruption_pendant_la_reflexion_mene_au_repos():
    c = Collecteur()
    s = Session(
        envoyer_json=c.envoyer_json,
        envoyer_binaire=c.envoyer_binaire,
        transcription=TranscriptionLente(),
        synthese=FausseSynthese(),
        cerveau=CerveauFixe(),
    )
    await s.sur_message(Reveil(confiance=0.9, horodatage=0.0))
    await s.sur_audio(b"\x00" * 640)
    await s.sur_message(FinEnonce(duree_ms=20))
    await asyncio.sleep(0.05)  # la transcription est toujours en cours : on est en réflexion

    # « reflexion → ecoute » n'existe pas dans la machine à états : si _interrompre
    # visait ecoute ici, ceci lèverait TransitionInterdite au lieu de passer.
    await s.sur_message(Interruption(horodatage=1.0))

    assert [m for m in c.json if isinstance(m, Etat)][-1].valeur == "repos"
    assert not [m for m in c.json if isinstance(m, Dire)]
    await s.fermer()


async def test_une_interruption_au_repos_repasse_en_ecoute():
    c = Collecteur()
    s = _session(c)
    # Aucun tour en cours : la session est déjà au repos quand l'interruption arrive
    # (le cas de quelqu'un qui coupe Helios juste à la fin de sa phrase).
    await s.sur_message(Interruption(horodatage=1.0))

    assert [m for m in c.json if isinstance(m, Etat)][-1].valeur == "ecoute"

    # L'audio suivant doit maintenant être mis en tampon.
    await s.sur_audio(b"\x00" * 640)
    await s.sur_message(FinEnonce(duree_ms=20))
    await asyncio.sleep(0.01)
    assert [d.texte for d in c.json if isinstance(d, Dire)]
    await s.fermer()


async def test_un_echec_de_transcription_produit_une_erreur_et_revient_au_repos():
    c = Collecteur()
    s = Session(
        envoyer_json=c.envoyer_json,
        envoyer_binaire=c.envoyer_binaire,
        transcription=TranscriptionQuiEchoue(),
        synthese=FausseSynthese(),
        cerveau=CerveauFixe(),
    )
    await _tour(s, c)
    await s.fermer()

    assert any(isinstance(m, Erreur) for m in c.json)
    assert [m for m in c.json if isinstance(m, Etat)][-1].valeur == "repos"
    assert not [m for m in c.json if isinstance(m, Dire)]


async def test_une_synthese_muette_produit_une_erreur_et_revient_au_repos():
    c = Collecteur()
    s = _session(c, synthese=FausseSynthese(blocs=0))
    await _tour(s, c)
    await s.fermer()

    erreur = c.premier(Erreur)
    assert "aucun audio" in erreur.message
    assert [m for m in c.json if isinstance(m, Etat)][-1].valeur == "repos"

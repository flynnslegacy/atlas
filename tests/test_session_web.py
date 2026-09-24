import asyncio
from collections.abc import AsyncIterator

from atlas_core.diffuseur import Diffuseur
from atlas_core.protocole import (
    Dire,
    Erreur,
    Etat,
    FinEnonce,
    Interruption,
    Reveil,
    StopAudio,
    Transcription,
)
from atlas_core.protocole_web import Latences, Niveau, Question, Reponse
from atlas_core.session import Session


class Collecteur:
    def __init__(self) -> None:
        self.json: list = []
        self.binaire: list[bytes] = []

    async def envoyer_json(self, msg) -> None:
        self.json.append(msg)

    async def envoyer_binaire(self, trame: bytes) -> None:
        self.binaire.append(trame)

    def etats(self) -> list[str]:
        return [m.valeur for m in self.json if isinstance(m, Etat)]

    def de(self, classe) -> list:
        return [m for m in self.json if isinstance(m, classe)]


class DiffuseurEspion(Diffuseur):
    def __init__(self) -> None:
        super().__init__(heure=lambda: "12:00")
        self.publies: list = []

    def publier(self, msg) -> None:
        self.publies.append(msg)
        super().publier(msg)

    def de(self, classe) -> list:
        return [m for m in self.publies if isinstance(m, classe)]


class Temps:
    """Une horloge qu'on avance à la main."""

    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


class FausseTranscription:
    def __init__(self, texte: str = "quelle heure est-il", temps=None, duree: float = 0.0):
        self.texte, self.temps, self.duree = texte, temps, duree
        self.appels = 0

    async def transcrire(self, pcm: bytes) -> str:
        self.appels += 1
        if self.temps:
            self.temps.t += self.duree
        return self.texte


class TranscriptionSansMessage:
    async def transcrire(self, pcm: bytes) -> str:
        raise TimeoutError()


class FausseSynthese:
    def __init__(self, blocs: int = 3, lenteur: float = 0.0, temps=None, duree_premier=0.0):
        self.blocs, self.lenteur = blocs, lenteur
        self.temps, self.duree_premier = temps, duree_premier
        self.appels = 0

    async def synthetiser(self, texte: str) -> AsyncIterator[bytes]:
        self.appels += 1
        for i in range(self.blocs):
            if self.lenteur:
                await asyncio.sleep(self.lenteur)
            if i == 0 and self.temps:
                self.temps.t += self.duree_premier
            yield b"\x00" * 640


class CerveauFixe:
    def __init__(self, phrase: str = "Il est midi. Tu déjeunes ?", temps=None, duree=0.0):
        self.phrase, self.temps, self.duree = phrase, temps, duree

    async def repondre(self, texte: str) -> AsyncIterator[str]:
        if self.temps:
            self.temps.t += self.duree
        for mot in self.phrase.split(" "):
            yield mot + " "
            await asyncio.sleep(0)


class FaussePoignee:
    def __init__(self) -> None:
        self.annulee = False

    def cancel(self) -> None:
        self.annulee = True


class FauxPlanificateur:
    def __init__(self) -> None:
        self.prevues: list[FaussePoignee] = []

    def __call__(self, delai, rappel, valeur) -> FaussePoignee:
        self.prevues.append(FaussePoignee())
        return self.prevues[-1]


def _session(collecteur, diffuseur=None, **options) -> Session:
    return Session(
        envoyer_json=collecteur.envoyer_json,
        envoyer_binaire=collecteur.envoyer_binaire,
        transcription=options.pop("transcription", FausseTranscription()),
        synthese=options.pop("synthese", FausseSynthese()),
        cerveau=options.pop("cerveau", CerveauFixe()),
        diffuseur=diffuseur,
        planifier=options.pop("planifier", FauxPlanificateur()),
        **options,
    )


async def _tour_a_la_voix(session, blocs: int = 5) -> None:
    await session.sur_message(Reveil(confiance=0.9, horodatage=0.0))
    for _ in range(blocs):
        await session.sur_audio(b"\x00" * 640)
    await session.sur_message(FinEnonce(duree_ms=blocs * 20))
    await asyncio.sleep(0.01)


async def test_un_tour_a_la_voix_est_publie_pour_les_pages():
    c, d = Collecteur(), DiffuseurEspion()
    s = _session(c, d)
    await _tour_a_la_voix(s)
    await s.fermer()
    sans_niveaux = [m.type for m in d.publies if not isinstance(m, Niveau)]
    assert sans_niveaux == [
        "etat",
        "etat",
        "question",
        "etat",
        "reponse",
        "reponse",
        "latences",
        "etat",
    ]
    question = d.de(Question)[0]
    assert (question.texte, question.source) == ("quelle heure est-il", "voix")
    assert [r.texte for r in d.de(Reponse)] == ["Il est midi.", "Tu déjeunes ?"]
    assert c.etats() == ["ecoute", "reflexion", "parole", "repos"]


async def test_les_trois_delais_sont_mesures():
    temps = Temps()
    c, d = Collecteur(), DiffuseurEspion()
    s = _session(
        c,
        d,
        horloge=temps,
        transcription=FausseTranscription(temps=temps, duree=0.42),
        cerveau=CerveauFixe(temps=temps, duree=1.2),
        synthese=FausseSynthese(temps=temps, duree_premier=0.3),
    )
    await _tour_a_la_voix(s)
    await s.fermer()
    assert d.de(Latences) == [
        Latences(transcription_ms=420, reflexion_ms=1200, premiere_voix_ms=1920)
    ]


async def test_l_ecoute_publie_au_plus_15_niveaux_par_seconde():
    temps = Temps()
    c, d = Collecteur(), DiffuseurEspion()
    s = _session(c, d, horloge=temps)
    await s.sur_message(Reveil(confiance=0.9, horodatage=0.0))
    for _ in range(10):  # 200 ms de voix
        temps.t += 0.02
        await s.sur_audio(b"\x00" * 640)
    assert len(d.de(Niveau)) == 3
    await s.fermer()


async def test_la_voix_d_atlas_programme_des_niveaux_que_l_interruption_annule():
    c, d = Collecteur(), DiffuseurEspion()
    plan = FauxPlanificateur()
    s = _session(c, d, planifier=plan, synthese=FausseSynthese(blocs=40, lenteur=0.001))
    await s.sur_message(Reveil(confiance=0.9, horodatage=0.0))
    await s.sur_audio(b"\x00" * 640)
    await s.sur_message(FinEnonce(duree_ms=20))
    await asyncio.sleep(0.02)
    assert plan.prevues
    await s.sur_message(Interruption(horodatage=0.0))
    assert all(p.annulee for p in plan.prevues)
    await s.fermer()


async def test_une_question_tapee_au_repos_est_repondue_sans_transcription():
    c, d = Collecteur(), DiffuseurEspion()
    transcription = FausseTranscription()
    s = _session(c, d, transcription=transcription)
    await s.sur_saisie("quelle heure est-il")
    await asyncio.sleep(0.01)
    await s.fermer()
    assert transcription.appels == 0 and not c.de(Transcription)
    assert c.etats() == ["reflexion", "parole", "repos"]
    assert d.de(Question)[0].source == "clavier"
    assert c.binaire, "Atlas répond à voix haute"
    assert d.de(Latences)[0].transcription_ms is None


async def test_une_question_tapee_pendant_la_parole_coupe_et_repond():
    c = Collecteur()
    s = _session(c, synthese=FausseSynthese(blocs=10, lenteur=0.005))
    await _tour_a_la_voix(s)
    await s.sur_saisie("bonjour")
    await asyncio.sleep(0.2)
    await s.fermer()
    assert c.de(StopAudio)[0].id_enonce == 1
    assert {m.id_enonce for m in c.de(Dire)} == {1, 2}
    assert c.etats()[-3:] == ["reflexion", "parole", "repos"]


async def test_une_question_tapee_pendant_l_ecoute_abandonne_la_capture():
    c = Collecteur()
    transcription = FausseTranscription()
    s = _session(c, transcription=transcription)
    await s.sur_message(Reveil(confiance=0.9, horodatage=0.0))
    await s.sur_audio(b"\x00" * 640)
    await s.sur_saisie("bonjour")
    await s.sur_message(FinEnonce(duree_ms=20))
    await asyncio.sleep(0.02)
    await s.fermer()
    assert transcription.appels == 0
    assert c.etats() == ["ecoute", "reflexion", "parole", "repos"]


async def test_sans_voix_la_reponse_est_seulement_ecrite():
    c, d = Collecteur(), DiffuseurEspion()
    synthese = FausseSynthese()
    s = _session(c, d, synthese=synthese, avec_voix=lambda: False)
    await s.sur_saisie("quelle heure est-il")
    await asyncio.sleep(0.01)
    await s.fermer()
    assert synthese.appels == 0
    assert not c.binaire and not c.de(Dire)
    assert [r.texte for r in d.de(Reponse)] == ["Il est midi.", "Tu déjeunes ?"]
    assert d.de(Latences)[0].premiere_voix_ms is None


async def test_taire_coupe_la_voix_et_laisse_finir_le_texte():
    voix = {"active": True}
    c, d = Collecteur(), DiffuseurEspion()
    s = _session(
        c, d, avec_voix=lambda: voix["active"], synthese=FausseSynthese(blocs=20, lenteur=0.005)
    )
    await s.sur_saisie("quelle heure est-il")
    await asyncio.sleep(0.03)
    voix["active"] = False
    await s.taire()
    trames = len(c.binaire)
    await asyncio.sleep(0.2)
    await s.fermer()
    assert c.de(StopAudio)[-1].id_enonce == 1
    assert len(c.binaire) <= trames + 1
    assert [r.texte for r in d.de(Reponse)] == ["Il est midi.", "Tu déjeunes ?"]
    assert c.etats()[-1] == "repos"


async def test_le_client_audio_qui_part_laisse_finir_la_reponse_ecrite():
    c, d = Collecteur(), DiffuseurEspion()
    s = _session(c, d, synthese=FausseSynthese(blocs=20, lenteur=0.005))
    await s.sur_saisie("quelle heure est-il")
    await asyncio.sleep(0.03)
    await s.fermer()
    trames = len(c.binaire)
    await asyncio.sleep(0.3)
    assert len(c.binaire) == trames
    assert [r.texte for r in d.de(Reponse)] == ["Il est midi.", "Tu déjeunes ?"]
    assert d.de(Latences) and d.publies[-1] == Etat(valeur="repos")


async def test_fermer_pendant_un_tour_a_la_voix_l_annule():
    c, d = Collecteur(), DiffuseurEspion()
    s = _session(c, d, synthese=FausseSynthese(blocs=20, lenteur=0.005))
    await _tour_a_la_voix(s)
    await s.fermer()
    await asyncio.sleep(0.05)
    assert not d.de(Latences)


async def test_une_erreur_sans_message_donne_au_moins_son_type():
    c, d = Collecteur(), DiffuseurEspion()
    s = _session(c, d, transcription=TranscriptionSansMessage())
    await _tour_a_la_voix(s)
    await s.fermer()
    assert d.de(Erreur)[0].message == "Je n'ai pas pu répondre : TimeoutError"
    assert c.de(Erreur)[0].message == "Je n'ai pas pu répondre : TimeoutError"
    assert c.etats()[-1] == "repos"

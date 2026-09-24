import asyncio
from collections.abc import AsyncIterator

from atlas_core.diffuseur import Diffuseur
from atlas_core.protocole import (
    Abandon,
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
    def __init__(self, delai: float, rappel, valeur: float) -> None:
        self.delai, self.rappel, self.valeur = delai, rappel, valeur
        self.annulee = False

    def cancel(self) -> None:
        self.annulee = True


class FauxPlanificateur:
    def __init__(self) -> None:
        self.prevues: list[FaussePoignee] = []

    def __call__(self, delai, rappel, valeur) -> FaussePoignee:
        poignee = FaussePoignee(delai, rappel, valeur)
        self.prevues.append(poignee)
        return poignee

    def jouer(self) -> None:
        """Simule l'écoulement du temps : déclenche, dans l'ordre, les rappels dont la
        poignée n'a pas été annulée."""
        for poignee in self.prevues:
            if not poignee.annulee:
                poignee.rappel(poignee.valeur)


class CollecteurQuiPart:
    """Un client audio qui répond normalement, jusqu'à ce qu'il « parte » (WebSocket
    fermée : Starlette lève alors une exception sur tout envoi ultérieur)."""

    def __init__(self) -> None:
        self.parti = False
        self.json: list = []
        self.binaire: list[bytes] = []

    async def envoyer_json(self, msg) -> None:
        if self.parti:
            raise RuntimeError("client audio parti")
        self.json.append(msg)

    async def envoyer_binaire(self, trame: bytes) -> None:
        if self.parti:
            raise RuntimeError("client audio parti")
        self.binaire.append(trame)


class CerveauAttend:
    """N'émet sa première phrase qu'une fois l'événement mis : pour observer combien de
    temps la session reste en « reflexion »."""

    def __init__(self, evenement: asyncio.Event, phrase: str = "Il est midi. Tu déjeunes ?"):
        self._evenement = evenement
        self.phrase = phrase

    async def repondre(self, texte: str) -> AsyncIterator[str]:
        await self._evenement.wait()
        for mot in self.phrase.split(" "):
            yield mot + " "
            await asyncio.sleep(0)


class CollecteurQuiCede(Collecteur):
    """Comme un vrai envoi WebSocket : chaque envoi rend la main à la boucle événementielle,
    pour que deux appels concurrents (`asyncio.gather`) s'entrelacent vraiment, au lieu de
    s'exécuter chacun d'un bloc entre deux points de reprise."""

    async def envoyer_json(self, msg) -> None:
        self.json.append(msg)
        await asyncio.sleep(0)

    async def envoyer_binaire(self, trame: bytes) -> None:
        self.binaire.append(trame)
        await asyncio.sleep(0)


class CollecteurRetenu(Collecteur):
    """Retient le 3ᵉ envoi binaire jusqu'à ce que le test le libère : la tâche reste
    suspendue *dans* l'envoi d'une trame, comme un vrai `taire()` reçu en pleine écriture
    WebSocket, plutôt qu'entre deux trames."""

    def __init__(self) -> None:
        super().__init__()
        self.en_envoi = asyncio.Event()
        self.reprendre = asyncio.Event()

    async def envoyer_binaire(self, trame: bytes) -> None:
        self.binaire.append(trame)
        if len(self.binaire) == 3:
            self.en_envoi.set()
            await self.reprendre.wait()


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
    plan = FauxPlanificateur()
    s = _session(c, d, planifier=plan)
    await _tour_a_la_voix(s)
    plan.jouer()  # le repos des pages arrive après la lecture, pas avant
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


async def test_le_muet_desactive_en_pleine_reponse_ne_reprend_pas_la_voix():
    # Le muet est activé puis désactivé pendant une réponse à la voix : sans le drapeau,
    # la synthèse reprendrait à la phrase suivante alors que plus personne n'écoute.
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
    dires = len(c.de(Dire))
    voix["active"] = True  # le muet est désactivé avant la fin de la réponse
    await asyncio.sleep(0.2)
    await s.fermer()
    assert len(c.binaire) == trames, "plus aucune trame pour ce tour, même voix réactivée"
    assert len(c.de(Dire)) == dires, "plus aucun Dire pour ce tour, même voix réactivée"
    assert [r.texte for r in d.de(Reponse)] == ["Il est midi.", "Tu déjeunes ?"]
    # Le tour suivant a de nouveau la voix.
    c.binaire.clear()
    await s.sur_saisie("il fait quel temps")
    await asyncio.sleep(0.03)
    await s.fermer()
    assert c.binaire, "la réponse suivante doit de nouveau être parlée"


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


# --- fix round 1 : appels simultanés, client audio injoignable, timing des pages -----


async def test_deux_questions_tapees_en_meme_temps_ne_laissent_qu_une_reponse():
    # Un collecteur dont les envois rendent la main (comme un vrai WebSocket) : sans le
    # verrou, `gather` entrelace vraiment les deux `sur_saisie` et laisse deux réponses.
    c, d = CollecteurQuiCede(), DiffuseurEspion()
    s = _session(c, d, avec_voix=lambda: False)
    await asyncio.gather(s.sur_saisie("quelle heure est-il"), s.sur_saisie("il fait quel temps"))
    await asyncio.sleep(0.02)
    await s.fermer()
    assert not d.de(Erreur)
    assert len(d.de(Latences)) == 1
    assert len(d.de(Reponse)) == 2
    assert d.de(Etat)[-1].valeur == "repos"


async def test_une_question_tapee_et_un_reveil_simultanes_restent_coherents():
    # Idem : un collecteur qui rend la main pour que le Reveil s'entrelace vraiment
    # avec la saisie, au lieu de s'exécuter après elle sans jamais céder la main.
    c, d = CollecteurQuiCede(), DiffuseurEspion()
    s = _session(c, d, avec_voix=lambda: False)
    await asyncio.gather(
        s.sur_saisie("quelle heure est-il"),
        s.sur_message(Reveil(confiance=0.9, horodatage=0.0)),
    )
    await asyncio.sleep(0.02)
    # Avant fermer() : une fois fermée, la session republie « repos » aux pages (voir
    # le test dédié), ce qui n'est pas ce qu'on observe ici.
    assert not d.de(Erreur)
    assert d.de(Etat)[-1].valeur == "ecoute"
    await s.fermer()


async def test_un_client_audio_injoignable_laisse_finir_la_reponse_ecrite():
    c, d = CollecteurQuiPart(), DiffuseurEspion()
    s = _session(c, d, synthese=FausseSynthese(blocs=20, lenteur=0.005))
    await s.sur_saisie("quelle heure est-il")
    await asyncio.sleep(0.03)
    c.parti = True
    await asyncio.sleep(0.2)
    await s.fermer()
    assert not d.de(Erreur)
    assert [r.texte for r in d.de(Reponse)] == ["Il est midi.", "Tu déjeunes ?"]
    assert len(d.de(Latences)) == 1
    assert d.de(Etat)[-1].valeur == "repos"


async def test_fermer_juste_apres_une_question_tapee_la_laisse_finir():
    c, d = Collecteur(), DiffuseurEspion()
    s = _session(c, d)
    await s.sur_saisie("quelle heure est-il")
    await s.fermer()
    await asyncio.sleep(0.02)
    assert [r.texte for r in d.de(Reponse)] == ["Il est midi.", "Tu déjeunes ?"]
    assert d.de(Etat)[-1].valeur == "repos"


async def test_fermer_pendant_l_ecoute_ou_la_parole_remet_les_pages_au_repos():
    # Après un Reveil (écoute), sans qu'aucun tour n'ait commencé.
    c1, d1 = Collecteur(), DiffuseurEspion()
    s1 = _session(c1, d1)
    await s1.sur_message(Reveil(confiance=0.9, horodatage=0.0))
    await s1.fermer()
    assert d1.de(Etat)[-1].valeur == "repos"

    # En pleine parole, pendant un tour à la voix.
    c2, d2 = Collecteur(), DiffuseurEspion()
    s2 = _session(c2, d2, synthese=FausseSynthese(blocs=20, lenteur=0.005))
    await _tour_a_la_voix(s2)
    await s2.fermer()
    assert d2.de(Etat)[-1].valeur == "repos"


async def test_les_pages_restent_en_parole_jusqu_a_la_fin_de_la_lecture():
    c, d = Collecteur(), DiffuseurEspion()
    plan = FauxPlanificateur()
    s = _session(c, d, planifier=plan)
    await _tour_a_la_voix(s)
    assert c.etats()[-1] == "repos"
    assert d.de(Etat)[-1].valeur == "parole"
    plan.jouer()
    assert d.de(Etat)[-1].valeur == "repos"
    await s.fermer()


async def test_un_reveil_avant_la_fin_de_la_lecture_annule_le_repos_prevu():
    c, d = Collecteur(), DiffuseurEspion()
    plan = FauxPlanificateur()
    s = _session(c, d, planifier=plan)
    await _tour_a_la_voix(s)
    await s.sur_message(Reveil(confiance=0.9, horodatage=1.0))
    assert d.de(Etat)[-1].valeur == "ecoute"
    plan.jouer()
    assert d.de(Etat)[-1].valeur == "ecoute"
    await s.fermer()


async def test_la_reflexion_dure_jusqu_a_la_premiere_phrase():
    c, d = Collecteur(), DiffuseurEspion()
    evenement = asyncio.Event()
    s = _session(c, d, cerveau=CerveauAttend(evenement), avec_voix=lambda: False)
    await s.sur_saisie("quelle heure est-il")
    await asyncio.sleep(0.01)
    assert d.de(Etat)[-1].valeur == "reflexion"
    evenement.set()
    await asyncio.sleep(0.01)
    assert [e.valeur for e in d.de(Etat)][-2:] == ["parole", "repos"]
    await s.fermer()


async def test_taire_pendant_l_envoi_ne_programme_plus_de_niveau():
    # Un collecteur qui retient la 3e trame : la tâche est suspendue *dans* l'envoi
    # quand `taire()` coupe la voix, pour prouver que rien n'est programmé après.
    voix = {"active": True}
    c, d = CollecteurRetenu(), DiffuseurEspion()
    plan = FauxPlanificateur()
    s = _session(
        c,
        d,
        avec_voix=lambda: voix["active"],
        planifier=plan,
        synthese=FausseSynthese(blocs=20),
    )
    await s.sur_saisie("quelle heure est-il")
    await c.en_envoi.wait()
    nombre_avant = len(plan.prevues)
    voix["active"] = False
    await s.taire()
    c.reprendre.set()
    await asyncio.sleep(0.05)
    await s.fermer()
    assert len(plan.prevues) == nombre_avant


# --- fix round 2 : en_lecture() gardée, _ecrit_en_cours, taire() en fin de lecture ----


async def test_une_question_tapee_pendant_la_fin_de_la_lecture_coupe_la_voix():
    c, d = Collecteur(), DiffuseurEspion()
    plan = FauxPlanificateur()
    s = _session(c, d, planifier=plan)
    await _tour_a_la_voix(s)
    # Le client a déjà tout reçu (la machine est au repos)...
    assert c.etats()[-1] == "repos"
    # ...mais la lecture, elle, n'est pas finie : `plan` ne l'a pas simulée.
    await s.sur_saisie("bonjour")
    assert c.de(StopAudio), "la lecture n'est pas finie côté client : il faut couper le son"
    await s.fermer()


async def test_une_question_tapee_annulee_avant_de_commencer_ne_trompe_pas_fermer():
    c, d = Collecteur(), DiffuseurEspion()
    s = _session(c, d, synthese=FausseSynthese(blocs=20, lenteur=0.005))
    # Dans le même tour de boucle : la question tapée n'a pas encore fait son premier pas
    # quand le Reveil l'annule. Sans le correctif, `_ecrit_en_cours` reste vrai alors
    # qu'aucune tâche n'a jamais rien écrit (son `finally` n'a jamais tourné).
    await asyncio.gather(
        s.sur_saisie("quelle heure est-il"),
        s.sur_message(Reveil(confiance=0.9, horodatage=0.0)),
    )
    # Un vrai tour à la voix, ensuite : sans le correctif, `fermer()` croit qu'une
    # réponse tapée est en cours et ne l'annule pas.
    for _ in range(5):
        await s.sur_audio(b"\x00" * 640)
    await s.sur_message(FinEnonce(duree_ms=100))
    await asyncio.sleep(0.01)  # le tour a démarré, sans avoir eu le temps de finir
    await s.fermer()
    await asyncio.sleep(0.1)
    assert not d.de(Latences)


async def test_taire_pendant_la_fin_de_la_lecture_coupe_la_voix_et_remet_les_pages_au_repos():
    c, d = Collecteur(), DiffuseurEspion()
    plan = FauxPlanificateur()
    s = _session(c, d, planifier=plan)
    await _tour_a_la_voix(s)
    assert c.etats()[-1] == "repos"
    assert d.de(Etat)[-1].valeur == "parole"  # les pages n'ont pas encore vu le repos
    await s.taire()
    assert c.de(StopAudio), "la voix doit être coupée même si la machine est au repos"
    assert d.de(Etat)[-1].valeur == "repos"
    await s.fermer()


async def test_un_abandon_pendant_l_ecoute_revient_au_repos_sans_transcrire():
    c, d = Collecteur(), DiffuseurEspion()
    transcription = FausseTranscription()
    s = _session(c, d, transcription=transcription)
    await s.sur_message(Reveil(confiance=0.9, horodatage=0.0))
    for _ in range(5):
        await s.sur_audio(b"\x00" * 640)
    await s.sur_message(Abandon())
    await asyncio.sleep(0.01)
    assert transcription.appels == 0, "rien n'a été dit : rien ne part à Whisper"
    assert c.etats() == ["ecoute", "repos"]
    assert d.de(Etat)[-1].valeur == "repos"
    assert not d.de(Question)
    await s.fermer()


async def test_un_abandon_hors_ecoute_est_ignore():
    c, d = Collecteur(), DiffuseurEspion()
    s = _session(c, d, synthese=FausseSynthese(blocs=20, lenteur=0.005))
    await s.sur_message(Reveil(confiance=0.9, horodatage=0.0))
    await s.sur_audio(b"\x00" * 640)
    await s.sur_message(FinEnonce(duree_ms=20))
    await asyncio.sleep(0.01)  # le tour est en cours : réflexion ou parole
    etats_avant = list(c.etats())
    await s.sur_message(Abandon())
    assert c.etats() == etats_avant, "un abandon tardif ne doit pas couper la réponse"
    await s.fermer()

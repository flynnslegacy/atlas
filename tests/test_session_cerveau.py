"""La session face au vrai cerveau : recherche web, erreurs dites, mise en voix, fantômes."""

import asyncio
from collections.abc import AsyncIterator

from test_session_web import (
    Collecteur,
    DiffuseurEspion,
    FausseSynthese,
    FausseTranscription,
    FauxPlanificateur,
)

from atlas_core.cerveau import RECHERCHE, ErreurCerveau
from atlas_core.protocole import Dire, Erreur, Etat, FinEnonce, Interruption, Reveil
from atlas_core.protocole_web import Reponse
from atlas_core.session import PHRASE_ATTENTE, Session


class CerveauScript:
    """Rejoue une suite : du texte, `RECHERCHE`, un `asyncio.Event` qui fait attendre
    jusqu'à ce que le test le mette, ou une exception à lever."""

    def __init__(self, *suite) -> None:
        self.suite = suite
        self.questions: list[str] = []
        self.ferme = False  # le flux est fermé, jusqu'au bout ou abandonné en route
        self.complet = False  # le flux est allé jusqu'au bout

    async def repondre(self, texte: str) -> AsyncIterator:
        self.questions.append(texte)
        try:
            for element in self.suite:
                if isinstance(element, asyncio.Event):
                    await element.wait()
                elif isinstance(element, BaseException):
                    raise element
                else:
                    yield element
                    await asyncio.sleep(0)
            self.complet = True
        finally:
            self.ferme = True

    async def fermer(self) -> None:
        pass


class CollecteurQuiRetientLaReflexion(Collecteur):
    """L'envoi de « reflexion » reste suspendu jusqu'à ce que le test le libère."""

    def __init__(self) -> None:
        super().__init__()
        self.liberer = asyncio.Event()

    async def envoyer_json(self, msg) -> None:
        if isinstance(msg, Etat) and msg.valeur == "reflexion" and "parole" in self.etats():
            await self.liberer.wait()
        self.json.append(msg)


def _session(collecteur, diffuseur, cerveau, **options) -> Session:
    return Session(
        envoyer_json=collecteur.envoyer_json,
        envoyer_binaire=collecteur.envoyer_binaire,
        transcription=options.pop("transcription", FausseTranscription()),
        synthese=FausseSynthese(),
        cerveau=cerveau,
        diffuseur=diffuseur,
        planifier=options.pop("planifier", FauxPlanificateur()),
        **options,
    )


async def _attendre(condition, message: str = "") -> None:
    for _ in range(1000):
        if condition():
            return
        await asyncio.sleep(0)
    raise AssertionError(message or "la condition n'est jamais devenue vraie")


def _dits(c: Collecteur) -> list[str]:
    return [m.texte for m in c.de(Dire)]


# --- la recherche web -----------------------------------------------------------


async def test_une_recherche_dit_la_phrase_d_attente_puis_repasse_en_reflexion():
    c, d, plan = Collecteur(), DiffuseurEspion(), FauxPlanificateur()
    resultats = asyncio.Event()
    s = _session(c, d, CerveauScript(RECHERCHE, resultats, "Il pleut. "), planifier=plan)

    await s.sur_saisie("Il pleut à Paris ?")
    await _attendre(lambda: _dits(c) == [PHRASE_ATTENTE])
    assert c.etats() == ["reflexion", "parole"]

    plan.jouer()  # la phrase d'attente a fini de jouer
    await _attendre(lambda: c.etats()[-1] == "reflexion", "l'orbe doit repasser en réflexion")
    assert d.de(Etat)[-1].valeur == "reflexion"

    resultats.set()
    await _attendre(lambda: c.etats()[-1] == "repos")
    assert c.etats() == ["reflexion", "parole", "reflexion", "parole", "repos"]
    assert _dits(c) == [PHRASE_ATTENTE, "Il pleut."]
    assert [m.rang for m in c.de(Dire)] == [1, 2]
    assert len({m.id_enonce for m in c.de(Dire)}) == 1, "une seule réponse, un seul énoncé"
    await s.fermer()


async def test_la_reflexion_part_au_client_avant_la_reprise_de_la_parole():
    c, d, plan = CollecteurQuiRetientLaReflexion(), DiffuseurEspion(), FauxPlanificateur()
    resultats = asyncio.Event()
    s = _session(c, d, CerveauScript(RECHERCHE, resultats, "Il pleut. "), planifier=plan)
    await s.sur_saisie("Il pleut ?")
    await _attendre(lambda: _dits(c) == [PHRASE_ATTENTE])
    plan.jouer()
    resultats.set()
    await asyncio.sleep(0.01)
    assert c.etats() == ["reflexion", "parole"], "« parole » ne double pas « reflexion »"

    c.liberer.set()
    await _attendre(lambda: c.etats()[-1:] == ["repos"])
    assert c.etats() == ["reflexion", "parole", "reflexion", "parole", "repos"]
    await s.fermer()


async def test_la_phrase_d_attente_n_est_dite_qu_une_fois_par_question():
    c, d, plan = Collecteur(), DiffuseurEspion(), FauxPlanificateur()
    cerveau = CerveauScript(RECHERCHE, "Voyons. ", RECHERCHE, "Il pleut. ")
    s = _session(c, d, cerveau, planifier=plan)

    await s.sur_saisie("Il pleut ?")
    await _attendre(lambda: c.etats()[-1:] == ["repos"])
    assert _dits(c) == [PHRASE_ATTENTE, "Voyons.", "Il pleut."]

    await s.sur_saisie("Et demain ?")
    await _attendre(lambda: len(_dits(c)) == 6)
    assert _dits(c)[3] == PHRASE_ATTENTE, "chaque question a sa phrase d'attente"
    await s.fermer()


async def test_une_reponse_arrivee_avant_la_fin_de_l_attente_reste_en_parole():
    c, d, plan = Collecteur(), DiffuseurEspion(), FauxPlanificateur()
    suite = asyncio.Event()
    cerveau = CerveauScript(RECHERCHE, "Il pleut. ", suite, "Et demain aussi. ")
    s = _session(c, d, cerveau, planifier=plan)
    await s.sur_saisie("Il pleut ?")
    await _attendre(lambda: _dits(c) == [PHRASE_ATTENTE, "Il pleut."])

    plan.jouer()  # l'attente finit de jouer alors qu'Atlas a déjà repris la parole
    await asyncio.sleep(0.01)
    assert c.etats() == ["reflexion", "parole"], "pas de réflexion en pleine réponse"

    suite.set()
    await _attendre(lambda: c.etats()[-1:] == ["repos"])
    assert c.etats() == ["reflexion", "parole", "repos"]
    await s.fermer()


async def test_sans_voix_la_recherche_passe_aussi_en_reflexion():
    c, d = Collecteur(), DiffuseurEspion()
    resultats = asyncio.Event()
    s = _session(c, d, CerveauScript(RECHERCHE, resultats, "Il pleut. "), avec_voix=lambda: False)
    await s.sur_saisie("Il pleut ?")
    await _attendre(lambda: [e.valeur for e in d.de(Etat)] == ["reflexion", "parole", "reflexion"])
    assert [r.texte for r in d.de(Reponse)] == [PHRASE_ATTENTE]

    resultats.set()
    await _attendre(lambda: [e.valeur for e in d.de(Etat)][-1:] == ["repos"])
    assert [e.valeur for e in d.de(Etat)] == ["reflexion", "parole", "reflexion", "parole", "repos"]
    await s.fermer()


async def test_hey_atlas_pendant_la_recherche_abandonne_la_reponse():
    c, d, plan = Collecteur(), DiffuseurEspion(), FauxPlanificateur()
    cerveau = CerveauScript(RECHERCHE, asyncio.Event(), "jamais dit. ")
    s = _session(c, d, cerveau, planifier=plan)
    await s.sur_saisie("Il pleut ?")
    await _attendre(lambda: _dits(c) == [PHRASE_ATTENTE])
    plan.jouer()
    await _attendre(lambda: c.etats()[-1] == "reflexion")

    await s.sur_message(Reveil(confiance=0.9, horodatage=0.0))

    assert c.etats()[-2:] == ["repos", "ecoute"]
    assert cerveau.ferme, "le flux du cerveau est fermé : Claude sera interrompu"
    await s.fermer()


async def test_couper_la_phrase_d_attente_annule_le_retour_en_reflexion():
    c, d, plan = Collecteur(), DiffuseurEspion(), FauxPlanificateur()
    s = _session(c, d, CerveauScript(RECHERCHE, asyncio.Event()), planifier=plan)
    await s.sur_saisie("Il pleut ?")
    await _attendre(lambda: _dits(c) == [PHRASE_ATTENTE])

    await s.sur_message(Interruption(horodatage=0.0))  # barge-in pendant l'attente
    plan.jouer()
    await asyncio.sleep(0.01)

    assert c.etats() == ["reflexion", "parole", "ecoute"]
    await s.fermer()


async def test_le_muet_n_interrompt_pas_claude():
    c, d, plan = Collecteur(), DiffuseurEspion(), FauxPlanificateur()
    suite = asyncio.Event()
    cerveau = CerveauScript("Un. ", suite, "Deux. ")
    s = _session(c, d, cerveau, planifier=plan)
    await s.sur_saisie("Compte.")
    await _attendre(lambda: _dits(c) == ["Un."])

    await s.taire()
    suite.set()
    await _attendre(lambda: [e.valeur for e in d.de(Etat)][-1:] == ["repos"])

    assert cerveau.complet, "la réponse va jusqu'au bout, en texte seulement"
    assert [r.texte for r in d.de(Reponse)] == ["Un.", "Deux."]
    assert _dits(c) == ["Un."]
    await s.fermer()


# --- les erreurs du cerveau ------------------------------------------------------------


async def test_une_erreur_du_cerveau_est_dite_puis_affichee_en_rouge():
    c, d, plan = Collecteur(), DiffuseurEspion(), FauxPlanificateur()
    limite = "J'ai atteint la limite de l'abonnement Claude pour le moment."
    s = _session(c, d, CerveauScript("Je commence. ", ErreurCerveau(limite)), planifier=plan)
    await s.sur_saisie("Raconte.")
    await _attendre(lambda: c.etats()[-1:] == ["repos"])
    plan.jouer()

    assert _dits(c) == ["Je commence.", limite], "ce qui était commencé, puis l'erreur"
    assert c.de(Erreur) == [Erreur(code="cerveau", message=limite)]
    assert [r.texte for r in d.de(Reponse)] == ["Je commence."]
    assert d.de(Erreur) == [Erreur(code="cerveau", message=limite)]
    assert c.etats() == ["reflexion", "parole", "repos"]
    await s.fermer()


async def test_sans_voix_une_erreur_du_cerveau_s_affiche_tout_de_suite():
    c, d = Collecteur(), DiffuseurEspion()
    s = _session(
        c,
        d,
        CerveauScript(ErreurCerveau("Je n'arrive pas à joindre Claude.")),
        avec_voix=lambda: False,
    )
    await s.sur_saisie("Bonjour")
    await _attendre(lambda: [e.valeur for e in d.de(Etat)][-1:] == ["repos"])
    assert [e.message for e in d.de(Erreur)] == ["Je n'arrive pas à joindre Claude."]
    await s.fermer()


# --- la mise en voix et les fantômes de Whisper -------------------------------------


async def test_les_phrases_sont_nettoyees_avant_d_etre_dites_et_affichees():
    c, d, plan = Collecteur(), DiffuseurEspion(), FauxPlanificateur()
    cerveau = CerveauScript("Il fait **beau**. ", "** ", "Tout est sur https://x.fr. ")
    s = _session(c, d, cerveau, planifier=plan)
    await s.sur_saisie("Quel temps ?")
    await _attendre(lambda: c.etats()[-1:] == ["repos"])
    plan.jouer()

    assert _dits(c) == ["Il fait beau.", "Tout est sur un lien."]
    assert [r.texte for r in d.de(Reponse)] == ["Il fait beau.", "Tout est sur un lien."]
    assert [m.rang for m in c.de(Dire)] == [1, 2], "une phrase vide ne compte pas"
    await s.fermer()


async def test_une_phrase_fantome_de_whisper_ne_derange_pas_le_cerveau():
    c, d = Collecteur(), DiffuseurEspion()
    cerveau = CerveauScript("Jamais. ")
    s = _session(c, d, cerveau, transcription=FausseTranscription("Merci."))
    await s.sur_message(Reveil(confiance=0.9, horodatage=0.0))
    await s.sur_audio(b"\x00" * 640)
    await s.sur_message(FinEnonce(duree_ms=20))
    await _attendre(lambda: c.etats()[-1:] == ["repos"])

    assert cerveau.questions == []
    assert c.etats() == ["ecoute", "reflexion", "repos"]
    await s.fermer()

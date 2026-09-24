import asyncio

from atlas_core.diffuseur import RETARD_MAX_NIVEAUX, Diffuseur
from atlas_core.protocole import Erreur, Etat
from atlas_core.protocole_web import Historique, Latences, Muet, Niveau, Question, Reponse


class Page:
    def __init__(self) -> None:
        self.recus: list = []

    async def envoyer(self, msg) -> None:
        self.recus.append(msg)

    def types(self) -> list[str]:
        return [m.type for m in self.recus]


async def _laisser_passer() -> None:
    for _ in range(10):
        await asyncio.sleep(0)


def _diffuseur() -> Diffuseur:
    return Diffuseur(heure=lambda: "14:31")


async def test_une_page_recoit_d_abord_l_historique_le_muet_et_l_etat():
    d = _diffuseur()
    d.publier(Etat(valeur="ecoute"))
    page = Page()
    abonnement = d.abonner(page.envoyer)
    await _laisser_passer()
    assert page.types() == ["historique", "muet", "etat"]
    assert page.recus[2].valeur == "ecoute"
    await abonnement.fermer()


async def test_les_messages_arrivent_dans_l_ordre_a_toutes_les_pages():
    d = _diffuseur()
    pages = [Page(), Page()]
    abonnements = [d.abonner(p.envoyer) for p in pages]
    d.publier(Etat(valeur="parole"))
    d.publier(Reponse(texte="Il est midi."))
    await _laisser_passer()
    for p in pages:
        assert p.types()[3:] == ["etat", "reponse"]
    for a in abonnements:
        await a.fermer()


def test_l_historique_garde_question_reponse_et_latences():
    d = _diffuseur()
    d.publier(Question(texte="quelle heure est-il", source="voix"))
    d.publier(Reponse(texte="Il est midi."))
    d.publier(Reponse(texte="Tu déjeunes ?"))
    d.publier(Latences(transcription_ms=420, reflexion_ms=12, premiere_voix_ms=900))
    d.publier(Etat(valeur="repos"))
    (e,) = d.historique().echanges
    assert (e.heure, e.source, e.question) == ("14:31", "voix", "quelle heure est-il")
    assert e.reponse == "Il est midi. Tu déjeunes ?"
    assert e.latences.transcription_ms == 420 and e.erreur is None


def test_une_erreur_s_attache_a_l_echange_en_cours_ou_en_cree_un():
    d = _diffuseur()
    d.publier(Question(texte="bonjour", source="clavier"))
    d.publier(Erreur(code="tour", message="Je n'ai pas pu répondre : panne"))
    d.publier(Etat(valeur="repos"))
    d.publier(Erreur(code="tour", message="Je n'ai pas pu répondre : TimeoutError"))
    premier, second = d.historique().echanges
    assert premier.question == "bonjour" and premier.erreur.endswith("panne")
    assert second.question == "" and second.erreur.endswith("TimeoutError")


def test_a_une_erreur_apres_l_ecoute_ne_touche_pas_l_echange_termine():
    d = _diffuseur()
    d.publier(Question(texte="quelle heure est-il", source="voix"))
    d.publier(Reponse(texte="Il est midi."))
    d.publier(Latences(transcription_ms=420, reflexion_ms=12, premiere_voix_ms=900))
    d.publier(Etat(valeur="repos"))
    d.publier(Etat(valeur="ecoute"))
    d.publier(Etat(valeur="reflexion"))
    d.publier(Erreur(code="tour", message="Je n'ai pas pu répondre : ConnectError"))
    premier, second = d.historique().echanges
    assert premier.question == "quelle heure est-il"
    assert premier.reponse == "Il est midi." and premier.erreur is None
    assert second.question == "" and second.erreur.endswith("ConnectError")


def test_b_une_coupure_pendant_la_reponse_n_empeche_pas_une_nouvelle_erreur():
    d = _diffuseur()
    d.publier(Question(texte="quelle heure est-il", source="voix"))
    d.publier(Etat(valeur="parole"))
    d.publier(Reponse(texte="Il est"))
    d.publier(Etat(valeur="ecoute"))  # coupure : l'échange n'est plus en cours
    d.publier(Etat(valeur="reflexion"))
    d.publier(Erreur(code="tour", message="Je n'ai pas pu répondre : ConnectError"))
    premier, second = d.historique().echanges
    assert premier.question == "quelle heure est-il"
    assert premier.reponse == "Il est" and premier.erreur is None
    assert second.question == "" and second.erreur.endswith("ConnectError")


def test_l_historique_est_limite():
    d = Diffuseur(taille_historique=3, heure=lambda: "09:00")
    for i in range(5):
        d.publier(Question(texte=f"q{i}", source="voix"))
        d.publier(Etat(valeur="repos"))
    assert [e.question for e in d.historique().echanges] == ["q2", "q3", "q4"]


def test_l_historique_rendu_est_une_copie():
    d = _diffuseur()
    d.publier(Question(texte="q", source="voix"))
    copie = d.historique()
    d.publier(Reponse(texte="r"))
    assert isinstance(copie, Historique) and copie.echanges[0].reponse == ""


async def test_le_muet_publie_est_rappele_aux_nouvelles_pages():
    d = _diffuseur()
    d.publier(Muet(actif=True))
    page = Page()
    abonnement = d.abonner(page.envoyer)
    await _laisser_passer()
    assert page.recus[1] == Muet(actif=True)
    await abonnement.fermer()


async def test_une_page_lente_perd_des_niveaux_mais_jamais_le_reste():
    d = _diffuseur()
    feu_vert = asyncio.Event()
    recus: list = []

    async def envoyer_lentement(msg) -> None:
        await feu_vert.wait()
        recus.append(msg)

    abonnement = d.abonner(envoyer_lentement)
    await _laisser_passer()
    for _ in range(100):
        d.publier(Niveau(valeur=0.5))
    d.publier(Etat(valeur="parole"))
    d.publier(Reponse(texte="Il est midi."))
    feu_vert.set()
    await _laisser_passer()
    await asyncio.sleep(0.01)
    niveaux = [m for m in recus if isinstance(m, Niveau)]
    assert len(niveaux) <= RETARD_MAX_NIVEAUX
    assert [m.type for m in recus][-2:] == ["etat", "reponse"]
    await abonnement.fermer()


async def test_une_page_fermee_ne_recoit_plus_rien():
    d = _diffuseur()
    page = Page()
    abonnement = d.abonner(page.envoyer)
    await _laisser_passer()
    await abonnement.fermer()
    d.publier(Reponse(texte="trop tard"))
    await _laisser_passer()
    assert page.types() == ["historique", "muet", "etat"]


async def test_un_envoi_prive_ne_va_qu_a_sa_page():
    d = _diffuseur()
    a, b = Page(), Page()
    abonnement_a, abonnement_b = d.abonner(a.envoyer), d.abonner(b.envoyer)
    abonnement_a.envoyer_prive(Erreur(code="message_invalide", message="non"))
    await _laisser_passer()
    assert "erreur" in a.types() and "erreur" not in b.types()
    await abonnement_a.fermer()
    await abonnement_b.fermer()


async def test_une_page_en_panne_ne_gene_ni_les_autres_ni_le_core():
    d = _diffuseur()

    async def envoyer_en_panne(msg) -> None:
        raise ConnectionError("page fermée")

    saine = Page()
    en_panne = d.abonner(envoyer_en_panne)
    abonnement = d.abonner(saine.envoyer)
    await _laisser_passer()
    d.publier(Reponse(texte="toujours là"))
    await _laisser_passer()
    assert saine.types()[-1] == "reponse"
    await en_panne.fermer()
    await abonnement.fermer()


async def test_une_page_en_panne_se_retire_seule():
    d = _diffuseur()

    async def envoyer_en_panne(msg) -> None:
        raise ConnectionError("page fermée")

    abonnement = d.abonner(envoyer_en_panne)
    await _laisser_passer()
    # La page en panne doit s'être retirée toute seule
    assert abonnement not in d._abonnements
    # Mémoriser la taille de file avant les nouveaux messages
    taille_initiale = abonnement._file.qsize()
    # Les messages publiés après ne doivent plus arriver à cette page
    d.publier(Etat(valeur="parole"))
    d.publier(Question(texte="test", source="voix"))
    d.publier(Etat(valeur="repos"))
    await _laisser_passer()
    # La file ne doit pas avoir grossi (pas de nouveaux messages)
    assert abonnement._file.qsize() == taille_initiale

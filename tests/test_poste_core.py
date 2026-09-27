"""Le poste vu du Core : une action part avec son identifiant et attend sa réponse, dans un
délai ; le poste peut être absent, muet, ou répondre qu'il n'a pas pu."""

import asyncio

import pytest

from atlas_core.poste import ABSENT, MUET, ErreurPoste, Poste
from atlas_core.protocole_poste import ActionPoste, Capturer, Ouvrir, ResultatPoste


class FauxMac:
    """Le bout de la connexion côté Mac : il note les actions reçues."""

    def __init__(self) -> None:
        self.actions: list[ActionPoste] = []
        self.coupe = False

    async def envoyer(self, action: ActionPoste) -> None:
        if self.coupe:
            raise ConnectionError("connexion perdue")
        self.actions.append(action)


async def _attendre_une_action(mac: FauxMac, nombre: int = 1) -> None:
    for _ in range(100):
        if len(mac.actions) >= nombre:
            return
        await asyncio.sleep(0)
    raise AssertionError("aucune action n'est partie")


async def test_sans_poste_une_action_dit_que_le_mac_n_est_pas_connecte():
    poste = Poste()
    assert not poste.connecte
    with pytest.raises(ErreurPoste, match=ABSENT):
        await poste.demander(Ouvrir(app="Safari"))
    assert ABSENT == "Ton Mac n'est pas connecté."


async def test_une_action_part_avec_son_identifiant_et_revient_avec_sa_reponse():
    poste, mac = Poste(), FauxMac()
    poste.rattacher(mac.envoyer)
    demande = asyncio.create_task(poste.demander(Capturer()))
    await _attendre_une_action(mac)
    poste.recevoir(ResultatPoste(id=999, ok=True))  # une réponse inconnue est ignorée
    poste.recevoir(
        ResultatPoste(id=mac.actions[0].id, ok=True, image="AAA", largeur=1280, hauteur=800)
    )
    resultat = await demande
    assert (resultat.image, resultat.largeur) == ("AAA", 1280)
    suivante = asyncio.create_task(poste.demander(Ouvrir(app="Notes")))
    await _attendre_une_action(mac, 2)
    assert mac.actions[1].id == mac.actions[0].id + 1
    poste.recevoir(ResultatPoste(id=mac.actions[1].id, ok=True))
    await suivante


async def test_deux_gestes_en_meme_temps_recoivent_chacun_leur_reponse():
    # Claude appelle parfois deux outils à la fois.
    poste, mac = Poste(), FauxMac()
    poste.rattacher(mac.envoyer)
    capture = asyncio.create_task(poste.demander(Capturer()))
    ouverture = asyncio.create_task(poste.demander(Ouvrir(app="Notes")))
    await _attendre_une_action(mac, 2)
    ids = {action.geste.nom: action.id for action in mac.actions}
    poste.recevoir(ResultatPoste(id=ids["ouvrir"], ok=False, erreur="Je ne trouve pas Notes."))
    poste.recevoir(ResultatPoste(id=ids["capturer"], ok=True, image="AAA", largeur=1, hauteur=1))
    assert (await capture).image == "AAA"
    with pytest.raises(ErreurPoste, match="Je ne trouve pas Notes."):
        await ouverture


async def test_un_echec_du_mac_revient_avec_son_explication():
    poste, mac = Poste(), FauxMac()
    poste.rattacher(mac.envoyer)
    demande = asyncio.create_task(poste.demander(Ouvrir(app="Spotifi")))
    await _attendre_une_action(mac)
    poste.recevoir(
        ResultatPoste(id=mac.actions[0].id, ok=False, erreur="Je ne trouve pas l'app Spotifi.")
    )
    with pytest.raises(ErreurPoste, match="Je ne trouve pas l'app Spotifi."):
        await demande
    sans_explication = asyncio.create_task(poste.demander(Ouvrir(app="Notes")))
    await _attendre_une_action(mac, 2)
    poste.recevoir(ResultatPoste(id=mac.actions[1].id, ok=False))
    with pytest.raises(ErreurPoste, match=MUET):
        await sans_explication


@pytest.mark.parametrize(
    ("geste", "delai_s", "delai_capture_s"),
    [(Capturer(), 60, 0.02), (Ouvrir(app="Safari"), 0.02, 60)],
)
async def test_un_mac_muet_se_dit_apres_le_delai_de_son_geste(geste, delai_s, delai_capture_s):
    poste, mac = Poste(delai_s=delai_s, delai_capture_s=delai_capture_s), FauxMac()
    poste.rattacher(mac.envoyer)
    with pytest.raises(ErreurPoste, match=MUET):
        await asyncio.wait_for(poste.demander(geste), timeout=2)
    assert MUET == "Le poste ne répond pas."


async def test_la_reponse_d_une_action_abandonnee_est_ignoree():
    poste, mac = Poste(), FauxMac()
    poste.rattacher(mac.envoyer)
    demande = asyncio.create_task(poste.demander(Ouvrir(app="Safari")))
    await _attendre_une_action(mac)
    demande.cancel()  # la réponse de Claude est coupée pendant que le Mac agit…
    poste.recevoir(ResultatPoste(id=mac.actions[0].id, ok=True))  # … et le Mac répond quand même
    with pytest.raises(asyncio.CancelledError):
        await demande


async def test_un_envoi_qui_echoue_dit_que_le_mac_n_est_pas_connecte():
    poste, mac = Poste(), FauxMac()
    mac.coupe = True
    poste.rattacher(mac.envoyer)
    with pytest.raises(ErreurPoste, match=ABSENT):
        await poste.demander(Ouvrir(app="Safari"))


async def test_un_nouveau_poste_remplace_l_ancien_et_l_ancien_ne_le_detache_pas():
    poste, ancien, nouveau = Poste(), FauxMac(), FauxMac()
    jeton_ancien = poste.rattacher(ancien.envoyer)
    en_route = asyncio.create_task(poste.demander(Ouvrir(app="Safari")))
    await _attendre_une_action(ancien)
    poste.rattacher(nouveau.envoyer)
    with pytest.raises(ErreurPoste, match=ABSENT):
        await en_route  # l'action partie vers l'ancien ne reviendra jamais
    poste.detacher(jeton_ancien)
    assert poste.connecte
    demande = asyncio.create_task(poste.demander(Ouvrir(app="Notes")))
    await _attendre_une_action(nouveau)
    poste.recevoir(ResultatPoste(id=nouveau.actions[0].id, ok=True))
    await demande


async def test_un_poste_qui_part_laisse_ses_actions_en_route_sans_reponse():
    poste, mac = Poste(), FauxMac()
    jeton = poste.rattacher(mac.envoyer)
    en_route = asyncio.create_task(poste.demander(Ouvrir(app="Safari")))
    await _attendre_une_action(mac)
    poste.detacher(jeton)
    assert not poste.connecte
    with pytest.raises(ErreurPoste, match=ABSENT):
        await en_route

"""Les messages entre le poste et le Core : chaque geste est fermé, et vérifié ici."""

import json

import pytest

from atlas_core.protocole_poste import (
    COORDONNEE_MAX,
    TEXTE_MAX,
    ActionPoste,
    BonjourPoste,
    Capturer,
    Cliquer,
    Defiler,
    DefiPoste,
    Ouvrir,
    PretPoste,
    ReponsePoste,
    ResultatPoste,
    Taper,
    Touches,
    cle_de_session,
    decoder_message_poste,
    decoder_message_vers_poste,
    est_signe,
    nouveau_nonce,
    preuve_du_core,
    preuve_du_poste,
    preuve_valide,
    signer,
    verifier_touches,
)

NONCE_POSTE, NONCE_CORE = "a" * 32, "b" * 32


def test_le_poste_se_presente_puis_repond_aux_actions():
    bonjour = decoder_message_poste(json.dumps({"type": "bonjour", "nonce": NONCE_POSTE}))
    assert bonjour == BonjourPoste(nonce=NONCE_POSTE)
    preuve = preuve_du_poste("cle", NONCE_POSTE, NONCE_CORE)
    assert decoder_message_poste(json.dumps({"type": "reponse", "preuve": preuve})) == (
        ReponsePoste(preuve=preuve)
    )
    brut = '{"type":"resultat","id":3,"ok":true,"image":"AAA","largeur":1280,"hauteur":800}'
    assert decoder_message_poste(brut) == ResultatPoste(
        id=3, ok=True, image="AAA", largeur=1280, hauteur=800
    )
    echec = decoder_message_poste('{"type":"resultat","id":4,"ok":false,"erreur":"non"}')
    assert (echec.ok, echec.erreur, echec.image) == (False, "non", None)


def test_le_core_accepte_puis_envoie_des_gestes():
    assert decoder_message_vers_poste('{"type":"pret"}') == PretPoste()
    action = ActionPoste(id=1, geste=Cliquer(x=10, y=20, bouton="droit", double=True))
    assert decoder_message_vers_poste(action.model_dump_json()) == action
    assert json.loads(ActionPoste(id=2, geste=Capturer()).model_dump_json()) == {
        "type": "action",
        "id": 2,
        "geste": {"nom": "capturer"},
        "preuve": "",
    }
    defi = DefiPoste(nonce=NONCE_CORE, preuve=preuve_du_core("cle", NONCE_POSTE, NONCE_CORE))
    assert decoder_message_vers_poste(defi.model_dump_json()) == defi


def test_le_core_et_le_poste_prouvent_la_cle_sans_jamais_l_envoyer():
    # Chacun signe les deux nonces, avec son propre rôle : la preuve de l'un ne sert jamais
    # de preuve à l'autre, et aucune ne vaut sous une autre clé ou d'autres nonces.
    nonce = nouveau_nonce()
    assert len(nonce) == 32 and nonce != nouveau_nonce()
    du_core = preuve_du_core("cle", NONCE_POSTE, NONCE_CORE)
    du_poste = preuve_du_poste("cle", NONCE_POSTE, NONCE_CORE)
    assert len(du_core) == len(du_poste) == 64 and "cle" not in du_core + du_poste
    assert du_core != du_poste
    assert preuve_valide(du_core, preuve_du_core("cle", NONCE_POSTE, NONCE_CORE))
    assert not preuve_valide(du_core, preuve_du_core("autre", NONCE_POSTE, NONCE_CORE))
    assert not preuve_valide(du_core, preuve_du_core("cle", NONCE_CORE, NONCE_POSTE))
    session = cle_de_session("cle", NONCE_POSTE, NONCE_CORE)
    assert session not in (du_core, du_poste)


def test_une_action_et_un_resultat_ne_valent_que_signes_de_la_session():
    session = cle_de_session("cle", NONCE_POSTE, NONCE_CORE)
    action = signer(session, ActionPoste(id=3, geste=Taper(texte="bonjour")))
    recue = decoder_message_vers_poste(action.model_dump_json())
    assert est_signe(session, recue)
    assert not est_signe(session, ActionPoste(id=3, geste=Taper(texte="bonjour")))
    assert not est_signe(session, recue.model_copy(update={"id": 4}))
    assert not est_signe(session, recue.model_copy(update={"geste": Taper(texte="rm -rf")}))
    autre = cle_de_session("cle", NONCE_POSTE, "c" * 32)
    assert not est_signe(autre, recue)
    resultat = signer(session, ResultatPoste(id=3, ok=True, image="AAA"))
    assert est_signe(session, decoder_message_poste(resultat.model_dump_json()))
    assert not est_signe(session, resultat.model_copy(update={"image": "BBB"}))


@pytest.mark.parametrize(
    "geste",
    [
        Ouvrir(app="Safari"),
        Ouvrir(app="Visual Studio Code"),
        Ouvrir(app="Aperçu"),
        Ouvrir(app="Réglages Système"),
        Ouvrir(adresse="https://example.com/page?q=1"),
        Ouvrir(adresse="http://example.com"),
        Cliquer(x=0, y=0),
        Taper(texte="Bonjour à tous, ça va ?"),
        Touches(touches="cmd+maj+t"),
        Touches(touches="page bas"),
        Defiler(sens="bas", quantite=20),
    ],
)
def test_ces_gestes_sont_permis(geste):
    action = ActionPoste(id=1, geste=geste)
    assert decoder_message_vers_poste(action.model_dump_json()) == action


@pytest.mark.parametrize(
    "geste",
    [
        {"nom": "ouvrir"},
        {"nom": "ouvrir", "app": "Safari", "adresse": "https://example.com"},
        {"nom": "ouvrir", "app": "/Applications/Safari.app"},
        {"nom": "ouvrir", "app": "-a"},
        {"nom": "ouvrir", "app": "../Terminal"},
        {"nom": "ouvrir", "app": ".."},
        {"nom": "ouvrir", "app": "Utilities/Terminal"},
        {"nom": "ouvrir", "app": "a" * 81},
        {"nom": "ouvrir", "app": ""},
        {"nom": "ouvrir", "adresse": "file:///etc/passwd"},
        {"nom": "ouvrir", "adresse": "javascript:alert(1)"},
        {"nom": "ouvrir", "adresse": "https://example.com/a b"},
        {"nom": "ouvrir", "adresse": "https://example.com/" + "a" * TEXTE_MAX},
        {"nom": "cliquer", "x": -1, "y": 0},
        {"nom": "cliquer", "x": 1, "y": COORDONNEE_MAX + 1},
        {"nom": "cliquer", "x": 1, "y": 2, "bouton": "milieu"},
        {"nom": "taper", "texte": ""},
        {"nom": "taper", "texte": "x" * (TEXTE_MAX + 1)},
        {"nom": "touches", "touches": "cmd+q+w"},
        {"nom": "touches", "touches": "hyper+a"},
        {"nom": "touches", "touches": "f13"},
        {"nom": "touches", "touches": "cmd+é"},
        {"nom": "defiler", "sens": "gauche", "quantite": 1},
        {"nom": "defiler", "sens": "bas", "quantite": 0},
        {"nom": "defiler", "sens": "bas", "quantite": 21},
        {"nom": "executer", "commande": "rm -rf ~"},
    ],
)
def test_le_reste_est_refuse(geste):
    with pytest.raises(ValueError):
        decoder_message_vers_poste(json.dumps({"type": "action", "id": 1, "geste": geste}))


def test_les_touches_se_lisent_modificateurs_puis_touche():
    assert verifier_touches("cmd+l") == "cmd+l"
    assert verifier_touches(" Cmd + Maj + T ") == "cmd+maj+t"
    assert verifier_touches("entrée") == "entrée"
    for refusee in ("", "cmd+", "cmd+cmd+a", "maj", "a+b"):
        with pytest.raises(ValueError):
            verifier_touches(refusee)


def test_un_message_invalide_est_refuse_lisiblement():
    with pytest.raises(ValueError, match="Field required"):
        decoder_message_poste('{"type":"bonjour"}')
    with pytest.raises(ValueError):
        decoder_message_poste("pas du json")
    for invalide in (
        {"type": "bonjour", "cle": "la-cle-en-clair"},
        {"type": "bonjour", "nonce": "court"},
        {"type": "reponse", "preuve": "x" * 64},
    ):
        with pytest.raises(ValueError):
            decoder_message_poste(json.dumps(invalide))

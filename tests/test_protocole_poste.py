"""Les messages entre le poste et le Core : chaque geste est fermé, et vérifié ici."""

import json

import pytest

from atlas_core.protocole_poste import (
    COORDONNEE_MAX,
    TAILLE_MAX_CLE,
    TEXTE_MAX,
    ActionPoste,
    BonjourPoste,
    Capturer,
    Cliquer,
    Defiler,
    Ouvrir,
    PretPoste,
    ResultatPoste,
    Taper,
    Touches,
    decoder_message_poste,
    decoder_message_vers_poste,
    verifier_touches,
)


def test_le_poste_se_presente_puis_repond_aux_actions():
    assert decoder_message_poste('{"type":"bonjour","cle":"abc"}') == BonjourPoste(cle="abc")
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
    }


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
    with pytest.raises(ValueError, match="clé|cle|Field required|type"):
        decoder_message_poste('{"type":"bonjour"}')
    with pytest.raises(ValueError):
        decoder_message_poste("pas du json")
    with pytest.raises(ValueError):
        decoder_message_poste(json.dumps({"type": "bonjour", "cle": "x" * (TAILLE_MAX_CLE + 1)}))

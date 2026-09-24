import json

import pytest
from pydantic import ValidationError

from atlas_core.protocole import Etat
from atlas_core.protocole_web import (
    LONGUEUR_MAX_SAISIE,
    Authentification,
    Echange,
    Historique,
    Latences,
    Muet,
    Niveau,
    Saisie,
    decoder_message_page,
)


def test_les_trois_messages_de_page_se_decodent():
    assert decoder_message_page('{"type":"authentification","cle":"abc"}') == Authentification(
        cle="abc"
    )
    assert decoder_message_page('{"type":"saisie","texte":"Quelle heure ?"}') == Saisie(
        texte="Quelle heure ?"
    )
    assert decoder_message_page('{"type":"muet","actif":true}') == Muet(actif=True)


def test_une_saisie_perd_ses_espaces_de_bord():
    assert decoder_message_page('{"type":"saisie","texte":"  bonjour \\n"}').texte == "bonjour"


@pytest.mark.parametrize("texte", ["", "   ", "x" * (LONGUEUR_MAX_SAISIE + 1)])
def test_une_saisie_vide_ou_trop_longue_est_refusee_lisiblement(texte):
    with pytest.raises(ValueError, match="entre 1 et 1000 caractères") as e:
        decoder_message_page(json.dumps({"type": "saisie", "texte": texte}))
    assert "Value error" not in str(e.value)


def test_une_saisie_de_1000_caracteres_passe():
    assert (
        len(decoder_message_page(json.dumps({"type": "saisie", "texte": "x" * 1000})).texte) == 1000
    )


@pytest.mark.parametrize(
    "brut",
    [
        '{"type":"inconnu"}',
        "pas du json",
        '{"type":"authentification","cle":' + '"' + "k" * 300 + '"}',
    ],
)
def test_le_reste_est_refuse(brut):
    with pytest.raises(ValueError):
        decoder_message_page(brut)


def test_un_niveau_reste_entre_0_et_1():
    with pytest.raises(ValidationError):
        Niveau(valeur=1.5)


def test_l_historique_se_serialise_avec_ses_latences():
    h = Historique(
        echanges=[
            Echange(
                heure="14:31",
                source="clavier",
                question="Quelle heure ?",
                reponse="Il est quatorze heures trente et une.",
                latences=Latences(reflexion_ms=12),
            )
        ]
    )
    donnees = json.loads(h.model_dump_json())
    assert donnees["type"] == "historique"
    assert donnees["echanges"][0]["latences"]["reflexion_ms"] == 12
    assert donnees["echanges"][0]["erreur"] is None


def test_l_etat_du_protocole_audio_sert_aussi_aux_pages():
    assert json.loads(Etat(valeur="parole").model_dump_json()) == {
        "type": "etat",
        "valeur": "parole",
    }

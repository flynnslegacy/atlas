"""Gmail : préparer un brouillon et envoyer (spec de Gmail et de Google Agenda, §6.3), contre la
doublure de Google. Ce qui part compte autant que ce qu'Atlas dit : les adresses exactes, du
texte simple, jamais de copie cachée. Le 1er octobre 2026 est un jeudi."""

import datetime as dt
from zoneinfo import ZoneInfo

import pytest
from aides_connecteurs import appeler, charger
from doublure_gmail import Gmail, lu
from doublure_google import DoublureGoogle

from atlas_core import google
from atlas_core.connecteurs import Action, ErreurConnecteur, Fait

PARIS = ZoneInfo("Europe/Paris")


@pytest.fixture
def doublure():
    return DoublureGoogle()


@pytest.fixture
def boite(doublure):
    boite = Gmail(doublure)
    boite.mail(
        "a1",
        "Paul Martin <paul@exemple.fr>",
        "Jeudi soir",
        "Tu viens toujours jeudi ?",
        date=dt.datetime(2026, 10, 1, 9, 12, tzinfo=PARIS),
        entetes=(("References", "<a0@exemple.fr>"),),
        fil="fil-jeudi",
    )
    return boite


@pytest.fixture
def gmail(tmp_path, doublure, boite):
    module = charger("gmail", tmp_path, doublure.reglages())
    return module.Gmail(doublure.reglages(), http=doublure.http, fuseau=PARIS)


async def test_un_brouillon_neuf_dans_gmail(boite, gmail):
    fait = await appeler(
        gmail,
        "gmail_brouillon",
        a="paul@exemple.fr",
        copie="Marie <marie@exemple.fr>",
        objet="Jeudi",
        texte="Je serai là jeudi à 19 h.\nDavid",
    )

    assert fait == Fait(
        "Le brouillon b1 est dans Gmail : David peut le relire, ou te demander de l'envoyer.",
        "Brouillon prêt pour paul@exemple.fr : « Jeudi ».",
    )
    [message] = boite.brouillons.values()
    ecrit = lu(message)
    assert (ecrit["To"], ecrit["Cc"], ecrit["Subject"]) == (
        "paul@exemple.fr",
        "marie@exemple.fr",
        "Jeudi",
    )
    assert ecrit.get_content_type() == "text/plain" and ecrit.get_content_charset() == "utf-8"
    assert ecrit.get_content() == "Je serai là jeudi à 19 h.\nDavid\n"
    assert "Bcc" not in ecrit and "From" not in ecrit


async def test_une_reponse_garde_son_fil(boite, gmail):
    await appeler(gmail, "gmail_chercher")
    fait = await appeler(gmail, "gmail_brouillon", repondre="m1", texte="Oui, à jeudi !")

    assert fait.annonce == "Brouillon prêt pour Paul Martin : « Re: Jeudi soir »."
    [message] = boite.brouillons.values()
    ecrit = lu(message)
    assert message["threadId"] == "fil-jeudi"
    assert (ecrit["To"], ecrit["Subject"], ecrit["In-Reply-To"], ecrit["References"]) == (
        "paul@exemple.fr",
        "Re: Jeudi soir",
        "<a1@exemple.fr>",
        "<a0@exemple.fr> <a1@exemple.fr>",
    )


async def test_une_reponse_va_a_l_adresse_de_reponse_sans_doubler_re(boite, gmail):
    boite.mail(
        "l1",
        "Club <bureau@club.example>",
        "RE: Sortie",
        "Qui vient ?",
        date=dt.datetime(2026, 10, 1, 10, tzinfo=PARIS),
        entetes=(("Reply-To", "liste@club.example"),),
    )
    await appeler(gmail, "gmail_chercher")
    fait = await appeler(gmail, "gmail_brouillon", repondre="m1", texte="Moi !")

    assert fait.annonce == "Brouillon prêt pour liste@club.example : « RE: Sortie »."
    ecrit = lu(list(boite.brouillons.values())[0])
    assert (ecrit["To"], ecrit["Subject"]) == ("liste@club.example", "RE: Sortie")


async def test_une_virgule_dans_un_nom_entre_guillemets(boite, gmail):
    # « Nom, Prénom », comme l'écrit Outlook : la virgule n'est pas entre deux adresses.
    boite.mail(
        "o1",
        '"Martin, Paul" <paul@exemple.fr>',
        "Devis",
        "Le voici.",
        date=dt.datetime(2026, 10, 1, 10, tzinfo=PARIS),
    )
    await appeler(gmail, "gmail_chercher")
    fait = await appeler(
        gmail,
        "gmail_brouillon",
        repondre="m1",
        copie='"Durand, Marie" <marie@exemple.fr>',
        texte="Merci !",
    )

    assert fait.annonce == "Brouillon prêt pour Martin, Paul : « Re: Devis »."
    ecrit = lu(list(boite.brouillons.values())[0])
    assert (ecrit["To"], ecrit["Cc"]) == ("paul@exemple.fr", "marie@exemple.fr")


async def test_une_reponse_a_une_adresse_donnee_quand_l_expediteur_est_illisible(boite, gmail):
    boite.mail("r1", "Robot", "Alerte", "Rien.", date=dt.datetime(2026, 10, 1, 10, tzinfo=PARIS))
    await appeler(gmail, "gmail_chercher")
    fait = await appeler(
        gmail, "gmail_brouillon", repondre="m1", a="support@exemple.fr", texte="Bonjour."
    )

    assert fait.annonce == "Brouillon prêt pour support@exemple.fr : « Re: Alerte »."


async def test_une_reponse_a_un_mail_sans_identifiant(boite, gmail):
    boite.mail(
        "n1",
        "Marie <marie@exemple.fr>",
        "Samedi",
        "On se voit samedi ?",
        date=dt.datetime(2026, 10, 1, 11, tzinfo=PARIS),
        fil="fil-samedi",
        identifiant=False,
    )
    await appeler(gmail, "gmail_chercher")
    action = await appeler(gmail, "gmail_envoyer", repondre="m1", texte="Oui !")

    assert action.question == "Je réponds à marie@exemple.fr, objet « Re: Samedi » : « Oui ! » ?"
    action.executer()
    [envoye] = boite.envoyes
    ecrit = lu(envoye)
    assert envoye["threadId"] == "fil-samedi" and ecrit["Subject"] == "Re: Samedi"
    assert "In-Reply-To" not in ecrit and "References" not in ecrit


async def test_une_reponse_peut_changer_ses_destinataires_et_son_objet(boite, gmail):
    await appeler(gmail, "gmail_chercher")
    fait = await appeler(
        gmail,
        "gmail_brouillon",
        repondre="m1",
        a="marie@exemple.fr",
        copie="paul@exemple.fr",
        objet="Jeudi, finalement",
        texte="Paul ne vient pas.",
    )

    assert fait.annonce == "Brouillon prêt pour marie@exemple.fr : « Jeudi, finalement »."
    [message] = boite.brouillons.values()
    ecrit = lu(message)
    assert (ecrit["To"], ecrit["Cc"], ecrit["Subject"], message["threadId"]) == (
        "marie@exemple.fr",
        "paul@exemple.fr",
        "Jeudi, finalement",
        "fil-jeudi",
    )


async def test_envoyer_lit_les_adresses_et_attend_le_oui(boite, gmail):
    action = await appeler(
        gmail,
        "gmail_envoyer",
        a="paul@exemple.fr",
        copie="marie@exemple.fr",
        objet="Jeudi",
        texte="Je serai là\njeudi à 19 h.",
    )

    assert isinstance(action, Action)
    assert (action.nom, action.poursuivre) == ("Envoi", False)
    assert action.question == (
        "J'envoie à paul@exemple.fr, copie à marie@exemple.fr, objet « Jeudi » : « Je serai là "
        "jeudi à 19 h. » ?"
    )
    assert boite.envoyes == [], "rien avant le « oui »"
    action.executer()
    [envoye] = boite.envoyes
    ecrit = lu(envoye)
    assert (ecrit["To"], ecrit["Cc"], ecrit.get_content()) == (
        "paul@exemple.fr",
        "marie@exemple.fr",
        "Je serai là\njeudi à 19 h.\n",
    )
    assert "Bcc" not in ecrit
    assert action.faite == "C'est parti : mail envoyé à paul@exemple.fr."
    assert action.bilan == "le mail « Jeudi » est envoyé à paul@exemple.fr"
    assert (action.refusee, action.abandonnee, action.page_faite) == (
        "D'accord, je n'envoie rien.",
        "Je n'envoie rien.",
        "Mail envoyé : Jeudi.",
    )


async def test_un_long_texte_est_lu_en_partie_avec_son_nombre_de_mots(gmail):
    texte = " ".join(["mot"] * 120)
    action = await appeler(gmail, "gmail_envoyer", a="paul@exemple.fr", objet="Long", texte=texte)

    lu_a_voix_haute = texte[:300].rstrip()
    assert action.question == (
        f"J'envoie à paul@exemple.fr, objet « Long » : « {lu_a_voix_haute}… » (120 mots en tout) ?"
    )


async def test_une_reponse_ou_un_brouillon_pret_s_envoient(boite, gmail):
    await appeler(gmail, "gmail_chercher")
    reponse = await appeler(gmail, "gmail_envoyer", repondre="m1", texte="Oui !")
    assert reponse.question == (
        "Je réponds à paul@exemple.fr, objet « Re: Jeudi soir » : « Oui ! » ?"
    )
    reponse.executer()
    assert lu(boite.envoyes[0])["In-Reply-To"] == "<a1@exemple.fr>"

    await appeler(gmail, "gmail_brouillon", a="paul@exemple.fr", objet="Photos", texte="Les voici.")
    envoi = await appeler(gmail, "gmail_envoyer", brouillon="b1")
    assert envoi.question == "J'envoie à paul@exemple.fr, objet « Photos » : « Les voici. » ?"
    envoi.executer()
    envoi.apres()
    assert boite.brouillons == {} and lu(boite.envoyes[1])["Subject"] == "Photos"
    with pytest.raises(ErreurConnecteur) as refus:
        await appeler(gmail, "gmail_envoyer", brouillon="b1")
    assert str(refus.value) == "Je ne connais pas « b1 » : prépare d'abord le brouillon."


async def test_un_brouillon_retouche_dans_gmail_est_lu_tel_qu_il_partira(boite, gmail):
    await appeler(gmail, "gmail_brouillon", a="paul@exemple.fr", objet="Photos", texte="Les voici.")
    [id_] = boite.brouillons
    boite.retoucher(
        id_,
        texte="Les voici, avec celles de Marie.",
        entetes=(("Cc", "Marie <marie@exemple.fr>"),),
    )

    envoi = await appeler(gmail, "gmail_envoyer", brouillon="b1")
    assert envoi.question == (
        "J'envoie à paul@exemple.fr, copie à marie@exemple.fr, objet « Photos » : « Les voici, "
        "avec celles de Marie. » ?"
    )


@pytest.mark.parametrize(
    "retouche",
    [{"entetes": (("Bcc", "secret@exemple.fr"),)}, {"piece": ("devis.pdf", b"%PDF")}],
)
async def test_un_brouillon_a_copie_cachee_ou_piece_jointe_part_depuis_gmail(
    boite, gmail, retouche
):
    await appeler(gmail, "gmail_brouillon", a="paul@exemple.fr", objet="Photos", texte="Les voici.")
    [id_] = boite.brouillons
    boite.retoucher(id_, **retouche)

    with pytest.raises(ErreurConnecteur) as refus:
        await appeler(gmail, "gmail_envoyer", brouillon="b1")
    assert str(refus.value) == (
        "Ce brouillon a une copie cachée ou une pièce jointe : envoie-le depuis Gmail."
    )
    assert boite.envoyes == []


async def test_un_brouillon_supprime_dans_gmail_entre_temps(boite, gmail):
    await appeler(gmail, "gmail_brouillon", a="paul@exemple.fr", objet="Photos", texte="Les voici.")
    envoi = await appeler(gmail, "gmail_envoyer", brouillon="b1")
    boite.brouillons.clear()

    with pytest.raises(ErreurConnecteur):
        envoi.executer()
    assert envoi.ratee == "Ce brouillon n'est plus dans Gmail : prépare-le de nouveau."
    assert boite.envoyes == []


async def test_une_nouvelle_conversation_oublie_les_brouillons(gmail):
    await appeler(gmail, "gmail_brouillon", a="paul@exemple.fr", objet="Photos", texte="Les voici.")
    gmail.nouvelle_conversation()

    with pytest.raises(ErreurConnecteur) as refus:
        await appeler(gmail, "gmail_envoyer", brouillon="b1")
    assert str(refus.value) == "Je ne connais pas « b1 » : prépare d'abord le brouillon."


async def test_un_envoi_rate_dit_pourquoi(doublure, boite, gmail):
    action = await appeler(gmail, "gmail_envoyer", a="paul@exemple.fr", objet="Jeudi", texte="Oui.")
    doublure.refus = (503, "backendError")

    with pytest.raises(ErreurConnecteur):
        action.executer()
    assert action.ratee == google.MUET


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"a": "paul@exemple.fr", "objet": "Jeudi"}, "Écris le texte du mail (texte)."),
        ({"objet": "Jeudi", "texte": "Oui."}, "À qui ? Donne son adresse mail (a)."),
        ({"a": "paul@exemple.fr", "texte": "Oui."}, "Donne un objet au mail (objet)."),
        (
            {"a": "Paul", "objet": "Jeudi", "texte": "Oui."},
            "a : « Paul » n'est pas une adresse mail ; par exemple paul@exemple.fr.",
        ),
        (
            {"a": "paul@exemple.fr", "copie": "marie@", "objet": "Jeudi", "texte": "Oui."},
            "copie : « marie@ » n'est pas une adresse mail ; par exemple paul@exemple.fr.",
        ),
        ({"repondre": "m9", "texte": "Oui."}, "Je ne connais pas « m9 » : cherche d'abord."),
    ],
)
async def test_un_mail_mal_decrit_est_refuse_sans_rien_ecrire(boite, gmail, arguments, message):
    for outil in ("gmail_brouillon", "gmail_envoyer"):
        with pytest.raises(ErreurConnecteur) as refus:
            await appeler(gmail, outil, **arguments)
        assert str(refus.value) == message
    assert boite.brouillons == {} and boite.envoyes == []

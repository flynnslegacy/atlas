"""L'agenda iCloud : modifier et supprimer un rendez-vous après le « oui » de David (spec de
l'agenda et des contacts, §5.5, §7), contre un vrai serveur CalDAV (Radicale, voir
serveur_dav.py). Le 1er octobre 2026 est un jeudi.

Le Core pose la question de l'action rendue par l'outil, puis, après le « oui », appelle
`executer` (hors de sa boucle) et `apres` ; ces tests font de même."""

import sys
from zoneinfo import ZoneInfo

import pytest
from serveur_dav import appeler, charger, evenement, ics, jour, paris, reglages, serveur_dav

from atlas_core.connecteurs import Action, ErreurConnecteur

PARIS = ZoneInfo("Europe/Paris")
INVITES = (
    "Ce rendez-vous a des invités : Atlas ne le change pas, pour ne pas leur écrire en ton nom. "
    "Change-le dans Calendrier."
)


@pytest.fixture
def serveur(tmp_path):
    with serveur_dav(tmp_path) as serveur:
        serveur.domicile = serveur.creer_agenda("domicile", "Domicile")
        serveur.travail = serveur.creer_agenda("travail", "Travail")
        yield serveur


@pytest.fixture
def agenda(tmp_path, serveur):
    module = charger("agenda-icloud", tmp_path, reglages())
    return module.AgendaIcloud(reglages(), adresse=serveur.url, fuseau=PARIS)


@pytest.fixture
def diner(serveur):
    contenu = evenement(
        "diner",
        paris("20261001T190000"),
        paris("20261001T210000"),
        "Dîner chez Paul",
        "LOCATION:Chez Paul",
    )
    return serveur.deposer(serveur.domicile, "diner.ics", ics(contenu))  # son ETag


def change() -> type[Exception]:
    """L'exception du client quand un rendez-vous a changé depuis sa lecture."""
    return sys.modules["atlas_connecteurs.agenda_icloud.agenda"].Change


async def lire(connecteur, debut: str, fin: str | None = None) -> str:
    return await appeler(connecteur, "agenda_lire", debut=debut, fin=fin or debut)


async def test_deplacer_le_meme_jour_garde_la_duree(serveur, agenda, diner):
    await lire(agenda, "2026-10-01")
    action = await appeler(agenda, "agenda_modifier", evenement="e1", debut="2026-10-01T20:00")

    assert isinstance(action, Action)
    assert (action.nom, action.poursuivre) == ("Modification", False)
    assert action.question == "Je déplace « Dîner chez Paul », jeudi 1er octobre, de 19 h à 20 h ?"
    assert "20 h 00" not in await lire(agenda, "2026-10-01"), "rien avant le « oui »"
    action.executer()
    action.apres()
    methode, _, conditions, _ = serveur.ecrits[-1]
    assert (methode, conditions["If-Match"]) == ("PUT", diner), "seulement s'il n'a pas changé"
    assert action.faite == (
        "C'est fait : le rendez-vous « Dîner chez Paul » est déplacé au jeudi 1er octobre à 20 h."
    )
    assert (
        action.bilan == "le rendez-vous « Dîner chez Paul » est déplacé au jeudi 1er octobre à 20 h"
    )
    assert action.page_faite == "Rendez-vous changé : Dîner chez Paul."
    assert await lire(agenda, "2026-10-01") == (
        "jeudi 1er octobre 2026\n  e1 · 20 h 00 – 22 h 00 · Dîner chez Paul · Domicile · Chez Paul"
    )


async def test_une_etiquette_se_relit_apres_un_changement(serveur, agenda, diner):
    await lire(agenda, "2026-10-01")
    action = await appeler(agenda, "agenda_modifier", evenement="e1", debut="2026-10-01T20:00")
    action.executer()
    action.apres()

    with pytest.raises(ErreurConnecteur) as refus:
        await appeler(agenda, "agenda_supprimer", evenement="e1")
    assert str(refus.value) == "Je ne connais pas « e1 » : relis l'agenda d'abord."
    await lire(agenda, "2026-10-01")
    suppression = await appeler(agenda, "agenda_supprimer", evenement="e1")
    assert suppression.question == "Je supprime « Dîner chez Paul », jeudi 1er octobre à 20 h ?"


async def test_deplacer_a_un_autre_jour_ou_changer_le_reste(serveur, agenda, diner):
    await lire(agenda, "2026-10-01")

    autre_jour = await appeler(agenda, "agenda_modifier", evenement="e1", debut="2026-10-02T20:00")
    assert autre_jour.question == (
        "Je déplace « Dîner chez Paul » du jeudi 1er octobre, 19 h, au vendredi 2 octobre, 20 h ?"
    )
    reste = await appeler(
        agenda,
        "agenda_modifier",
        evenement="e1",
        titre="Dîner chez Marie",
        lieu="Chez Marie",
        notes="Apporter le dessert",
        debut="2026-10-02T20:00",
    )
    assert reste.question == (
        "Je change « Dîner chez Paul », jeudi 1er octobre à 19 h : le titre devient « Dîner chez "
        "Marie » ; il passe au vendredi 2 octobre à 20 h ; le lieu devient « Chez Marie » ; les "
        "notes changent ?"
    )
    reste.executer()
    assert reste.faite == (
        "C'est fait : le rendez-vous « Dîner chez Marie » est déplacé au vendredi 2 octobre à 20 h."
    )
    assert await lire(agenda, "2026-10-02") == (
        "vendredi 2 octobre 2026\n"
        "  e1 · 20 h 00 – 22 h 00 · Dîner chez Marie · Domicile · Chez Marie"
    )
    [garde] = serveur.contenus(serveur.domicile)
    assert "DESCRIPTION:Apporter le dessert" in garde and "SEQUENCE:1" in garde


async def test_une_fin_ou_une_duree_qui_change_se_dit_telle_quelle(serveur, agenda, diner):
    # La question est ce que David confirme : elle dit la nouvelle fin, pas un déplacement.
    salon = evenement("salon", jour("20261007"), jour("20261010"), "Salon")
    serveur.deposer(serveur.domicile, "salon.ics", ics(salon))
    await lire(agenda, "2026-10-01", "2026-10-07")

    for arguments, question in [
        ({"fin": "2026-10-01T23:00"}, "il finit à 23 h"),
        ({"fin": "2026-10-02T01:00"}, "il finit le vendredi 2 octobre à 1 h"),
        (
            {"debut": "2026-10-02T20:00", "fin": "2026-10-02T23:00"},
            "il passe au vendredi 2 octobre, de 20 h à 23 h",
        ),
        (
            {"debut": "2026-10-01T20:00", "fin": "2026-10-02T01:00"},
            "il passe du jeudi 1er octobre, 20 h, au vendredi 2 octobre, 1 h",
        ),
    ]:
        action = await appeler(agenda, "agenda_modifier", evenement="e1", **arguments)
        assert action.question == (
            f"Je change « Dîner chez Paul », jeudi 1er octobre à 19 h : {question} ?"
        )
    prolonge = await appeler(agenda, "agenda_modifier", evenement="e2", fin="2026-10-10")
    assert prolonge.question == (
        "Je change « Salon », du mercredi 7 octobre au vendredi 9 octobre : il passe du mercredi "
        "7 octobre au samedi 10 octobre ?"
    )

    plus_tard = await appeler(agenda, "agenda_modifier", evenement="e1", fin="2026-10-01T23:00")
    plus_tard.executer()
    assert (
        plus_tard.faite
        == "C'est fait : le rendez-vous « Dîner chez Paul » est changé : il finit à 23 h."
    )
    assert "19 h 00 – 23 h 00 · Dîner chez Paul" in await lire(agenda, "2026-10-01")


async def test_un_nouveau_lieu_remplace_aussi_le_lieu_de_la_carte(serveur, agenda):
    # L'iPhone garde, à côté du texte du lieu, un lieu structuré (la carte, le temps de
    # trajet) : un nouveau lieu doit le remplacer, sans quoi l'iPhone guiderait vers l'ancien.
    diner = evenement(
        "diner",
        paris("20261001T190000"),
        paris("20261001T210000"),
        "Dîner",
        "LOCATION:Chez Paul",
        "X-APPLE-STRUCTURED-LOCATION;VALUE=URI;X-TITLE=Chez Paul:geo:45.76,4.83",
    )
    serveur.deposer(serveur.domicile, "diner.ics", ics(diner))
    await lire(agenda, "2026-10-01")

    titre = await appeler(agenda, "agenda_modifier", evenement="e1", titre="Dîner du jeudi")
    titre.executer()
    assert "X-APPLE-STRUCTURED-LOCATION" in serveur.ecrits[-1][3], "le lieu n'a pas changé"
    await lire(agenda, "2026-10-01")
    lieu = await appeler(agenda, "agenda_modifier", evenement="e1", lieu="Chez Marie")
    lieu.executer()
    envoye = serveur.ecrits[-1][3]
    assert "LOCATION:Chez Marie" in envoye and "X-APPLE-STRUCTURED-LOCATION" not in envoye


async def test_une_journee_entiere_se_deplace_ou_prend_une_heure(serveur, agenda):
    conges = evenement("conges", jour("20261005"), jour("20261006"), "Congés")
    serveur.deposer(serveur.domicile, "conges.ics", ics(conges))
    await lire(agenda, "2026-10-05")

    lendemain = await appeler(agenda, "agenda_modifier", evenement="e1", debut="2026-10-06")
    assert lendemain.question == "Je déplace « Congés » du lundi 5 octobre au mardi 6 octobre ?"
    a_l_heure = await appeler(agenda, "agenda_modifier", evenement="e1", debut="2026-10-05T09:00")
    assert a_l_heure.question == (
        "Je change « Congés », lundi 5 octobre : il passe au lundi 5 octobre, de 9 h à 10 h ?"
    )
    a_l_heure.executer()
    assert "9 h 00 – 10 h 00 · Congés" in await lire(agenda, "2026-10-05")


async def test_un_rendez_vous_de_plusieurs_jours_se_deplace_en_entier(serveur, agenda):
    salon = evenement("salon", jour("20261007"), jour("20261010"), "Salon")
    serveur.deposer(serveur.domicile, "salon.ics", ics(salon))
    await lire(agenda, "2026-10-07")

    action = await appeler(
        agenda, "agenda_modifier", evenement="e1", titre="Salon du livre", debut="2026-10-12"
    )
    assert action.question == (
        "Je change « Salon », du mercredi 7 octobre au vendredi 9 octobre : le titre devient "
        "« Salon du livre » ; il passe du lundi 12 octobre au mercredi 14 octobre ?"
    )
    action.executer()
    assert action.faite == (
        "C'est fait : le rendez-vous « Salon du livre » est déplacé du lundi 12 octobre au "
        "mercredi 14 octobre."
    )
    assert "journée entière, jusqu'au mercredi 14 octobre · Salon du livre" in await lire(
        agenda, "2026-10-12"
    )


async def test_une_fois_d_un_evenement_repete_change_seule(serveur, agenda):
    serie = evenement(
        "equipe",
        paris("20260924T100000"),
        paris("20260924T110000"),
        "Réunion d'équipe",
        "RRULE:FREQ=WEEKLY",
    )
    serveur.deposer(serveur.travail, "equipe.ics", ics(serie))
    await lire(agenda, "2026-10-01", "2026-10-15")

    deplacee = await appeler(agenda, "agenda_modifier", evenement="e2", debut="2026-10-08T14:00")
    assert deplacee.question == (
        "Je déplace « Réunion d'équipe », jeudi 8 octobre, de 10 h à 14 h (cette fois seulement) ?"
    )
    deplacee.executer()
    await lire(agenda, "2026-10-01", "2026-10-15")
    encore = await appeler(agenda, "agenda_modifier", evenement="e2", debut="2026-10-08T15:00")
    encore.executer()
    await lire(agenda, "2026-10-01", "2026-10-15")
    supprimee = await appeler(agenda, "agenda_supprimer", evenement="e3")
    assert supprimee.question == (
        "Je supprime « Réunion d'équipe », jeudi 15 octobre à 10 h (cette fois seulement) ?"
    )
    supprimee.executer()
    assert supprimee.faite == (
        "C'est fait : le rendez-vous « Réunion d'équipe » est supprimé, cette fois seulement."
    )

    lues = await lire(agenda, "2026-10-01", "2026-10-22")
    assert [ligne.split(" · ")[1] for ligne in lues.splitlines() if ligne.startswith("  ")] == [
        "10 h 00 – 11 h 00",
        "15 h 00 – 16 h 00",
        "10 h 00 – 11 h 00",
    ]
    assert "jeudi 15 octobre" not in lues and "jeudi 22 octobre" in lues
    [garde] = serveur.contenus(serveur.travail)
    assert (
        garde.count("RECURRENCE-ID") == 1
        and garde.count("RRULE:FREQ=WEEKLY") == 1
        and "EXDATE" in garde
    )

    await lire(agenda, "2026-10-01", "2026-10-15")
    deja_deplacee = await appeler(agenda, "agenda_supprimer", evenement="e2")
    deja_deplacee.executer()
    assert "jeudi 8 octobre" not in await lire(agenda, "2026-10-01", "2026-10-22")
    [garde] = serveur.contenus(serveur.travail)
    assert "RECURRENCE-ID" not in garde and "20261008T100000" in garde, "exclue de la série"


async def test_supprimer_un_rendez_vous_seul(serveur, agenda, diner):
    await lire(agenda, "2026-10-01")
    action = await appeler(agenda, "agenda_supprimer", evenement="e1")

    assert isinstance(action, Action)
    assert (action.nom, action.question) == (
        "Suppression",
        "Je supprime « Dîner chez Paul », jeudi 1er octobre à 19 h ?",
    )
    assert (action.refusee, action.abandonnee, action.rien) == (
        "D'accord, je n'y touche pas.",
        "Je n'y touche pas.",
        "le rendez-vous n'est pas supprimé",
    )
    action.executer()
    methode, _, conditions, _ = serveur.ecrits[-1]
    assert (methode, conditions["If-Match"]) == ("DELETE", diner), "seulement s'il n'a pas changé"
    assert action.faite == "C'est fait : le rendez-vous « Dîner chez Paul » est supprimé."
    assert action.objet == "la suppression du rendez-vous « Dîner chez Paul »"
    assert serveur.contenus(serveur.domicile) == []


async def test_un_rendez_vous_avec_des_invites_est_refuse_avant_toute_question(serveur, agenda):
    invitation = evenement(
        "invit",
        paris("20261001T120000"),
        paris("20261001T130000"),
        "Déjeuner d'affaires",
        "ORGANIZER:mailto:marie@example.com",
        "ATTENDEE:mailto:david@example.com",
    )
    serveur.deposer(serveur.domicile, "invit.ics", ics(invitation))
    organisee = evenement(
        "orga",
        paris("20261001T170000"),
        paris("20261001T180000"),
        "Conférence",
        "ORGANIZER:mailto:marie@example.com",
    )
    serveur.deposer(serveur.domicile, "orga.ics", ics(organisee))

    lues = await lire(agenda, "2026-10-01")
    assert "Déjeuner d'affaires · Domicile · avec invités" in lues
    assert "Conférence · Domicile · avec invités" in lues
    for etiquette in ("e1", "e2"):
        for nom, arguments in [
            ("agenda_modifier", {"evenement": etiquette, "titre": "Annulé"}),
            ("agenda_supprimer", {"evenement": etiquette}),
        ]:
            with pytest.raises(ErreurConnecteur) as refus:
                await appeler(agenda, nom, **arguments)
            assert str(refus.value) == INVITES


async def test_un_rendez_vous_change_entre_temps_n_est_pas_ecrase(serveur, agenda, diner):
    await lire(agenda, "2026-10-01")
    modification = await appeler(agenda, "agenda_modifier", evenement="e1", titre="Dîner")
    suppression = await appeler(agenda, "agenda_supprimer", evenement="e1")
    sur_l_iphone = evenement(
        "diner", paris("20261001T193000"), paris("20261001T213000"), "Dîner chez Paul"
    )
    serveur.deposer(serveur.domicile, "diner.ics", ics(sur_l_iphone))

    for action in (modification, suppression):
        with pytest.raises(change()):
            action.executer()
        assert action.ratee == "« Dîner chez Paul » a changé entre-temps : je n'y ai pas touché."
    [garde] = serveur.contenus(serveur.domicile)
    assert "T193000" in garde and "SUMMARY:Dîner chez Paul" in garde


async def test_les_fois_d_une_serie_se_relisent_apres_un_changement(serveur, agenda):
    # Toutes les fois d'une série vivent dans le même événement : après en avoir changé une,
    # les autres doivent être relues, plutôt que d'échouer après le « oui » de David.
    yoga = evenement(
        "yoga", paris("20261001T180000"), paris("20261001T190000"), "Yoga", "RRULE:FREQ=WEEKLY"
    )
    serveur.deposer(serveur.domicile, "yoga.ics", ics(yoga))
    await lire(agenda, "2026-10-01", "2026-10-22")
    supprimee = await appeler(agenda, "agenda_supprimer", evenement="e2")
    supprimee.executer()
    supprimee.apres()

    with pytest.raises(ErreurConnecteur) as refus:
        await appeler(agenda, "agenda_supprimer", evenement="e3")
    assert str(refus.value) == "Je ne connais pas « e3 » : relis l'agenda d'abord."
    await lire(agenda, "2026-10-01", "2026-10-22")
    encore = await appeler(agenda, "agenda_supprimer", evenement="e3")
    encore.executer()
    assert "jeudi 15 octobre" not in await lire(agenda, "2026-10-01", "2026-10-22")


async def test_apres_un_changement_entre_temps_le_rendez_vous_se_relit(serveur, agenda, diner):
    await lire(agenda, "2026-10-01")
    modification = await appeler(agenda, "agenda_modifier", evenement="e1", titre="Dîner")
    sur_l_iphone = evenement(
        "diner", paris("20261001T193000"), paris("20261001T213000"), "Dîner chez Paul"
    )
    serveur.deposer(serveur.domicile, "diner.ics", ics(sur_l_iphone))
    with pytest.raises(change()):
        modification.executer()

    with pytest.raises(ErreurConnecteur) as refus:
        await appeler(agenda, "agenda_modifier", evenement="e1", titre="Dîner")
    assert str(refus.value) == "Je ne connais pas « e1 » : relis l'agenda d'abord."
    await lire(agenda, "2026-10-01")
    nouvelle = await appeler(agenda, "agenda_modifier", evenement="e1", titre="Dîner")
    assert nouvelle.question == (
        "Je change « Dîner chez Paul », jeudi 1er octobre à 19 h 30 : le titre devient « Dîner » ?"
    )


async def test_un_rendez_vous_supprime_entre_temps(serveur, agenda, diner):
    await lire(agenda, "2026-10-01")
    modification = await appeler(agenda, "agenda_modifier", evenement="e1", titre="Dîner")
    suppression = await appeler(agenda, "agenda_supprimer", evenement="e1")
    serveur.client.delete(serveur.domicile + "diner.ics")

    for action in (modification, suppression):
        with pytest.raises(change()):
            action.executer()
        assert action.ratee == "« Dîner chez Paul » a changé entre-temps : je n'y ai pas touché."


async def test_un_agenda_en_lecture_seule_dit_pourquoi(serveur, agenda):
    revue = evenement("revue", paris("20261001T100000"), paris("20261001T110000"), "Revue")
    serveur.deposer(serveur.travail, "revue.ics", ics(revue))
    await lire(agenda, "2026-10-01")
    serveur.interdire(serveur.travail)

    for nom, arguments in [
        ("agenda_modifier", {"evenement": "e1", "titre": "Revue annuelle"}),
        ("agenda_supprimer", {"evenement": "e1"}),
    ]:
        action = await appeler(agenda, nom, **arguments)
        with pytest.raises(ErreurConnecteur):
            action.executer()
        assert action.ratee == "L'agenda « Travail » ne se modifie pas d'ici."


async def test_une_etiquette_d_une_conversation_precedente_est_inconnue(serveur, agenda, diner):
    await lire(agenda, "2026-10-01")
    agenda.nouvelle_conversation()

    with pytest.raises(ErreurConnecteur) as refus:
        await appeler(agenda, "agenda_supprimer", evenement="e1")
    assert str(refus.value) == "Je ne connais pas « e1 » : relis l'agenda d'abord."


async def test_une_etiquette_inconnue_ou_rien_a_changer(serveur, agenda, diner):
    with pytest.raises(ErreurConnecteur) as refus:
        await appeler(agenda, "agenda_supprimer", evenement="e9")
    assert str(refus.value) == "Je ne connais pas « e9 » : relis l'agenda d'abord."

    await lire(agenda, "2026-10-01")
    for arguments in [
        {},
        {"titre": "Dîner chez Paul", "lieu": " Chez Paul "},
        {"debut": "2026-10-01T19:00"},
    ]:
        with pytest.raises(ErreurConnecteur) as refus:
            await appeler(agenda, "agenda_modifier", evenement="e1", **arguments)
        assert str(refus.value) == (
            "Dis ce qui change : le titre, le début, la fin, le lieu ou les notes."
        )

"""Les contacts iCloud : chercher une fiche (spec de l'agenda et des contacts, §6, §7), contre un
vrai serveur CardDAV (Radicale, voir serveur_dav.py)."""

import socket
import sys

import httpx
import pytest
from serveur_dav import MOT_DE_PASSE, appeler, charger, evenement, ics, paris, reglages, serveur_dav

from atlas_core.connecteurs import ErreurConnecteur, Niveau
from atlas_core.registre import OFFICIELS, Registre

REFUS = (
    "iCloud refuse l'identifiant ou le mot de passe d'app : vérifie-les dans Paramètres › "
    "Connecteurs › Réglages."
)
MUET = "iCloud ne répond pas : réessaie dans un moment."

PAUL = """BEGIN:VCARD
VERSION:3.0
N:Martin;Paul;;;
FN:Paul Martin
NICKNAME:Polo
ORG:Martin & Fils;
item1.TEL;type=pref:06 12 34 56 78
item1.X-ABLabel:_$!<Mobile>!$_
TEL;type=HOME;type=VOICE:04.78.00.00.00
item2.EMAIL;type=INTERNET:paul@exemple.fr
item2.X-ABLabel:Club
item3.ADR;type=HOME;type=pref:;;12 rue des Lilas;Lyon;;69003;France
BDAY;X-APPLE-OMIT-YEAR=1604:1604-05-12
NOTE:Le code de la porte : 1234
PHOTO;ENCODING=b;TYPE=JPEG:AAAA
UID:paul
END:VCARD
"""


def carte(uid: str, nom: str, *lignes: str) -> str:
    suite = "".join(f"{ligne}\n" for ligne in lignes)
    return f"BEGIN:VCARD\nVERSION:3.0\nUID:{uid}\nFN:{nom}\nN:{nom};;;;\n{suite}END:VCARD\n"


class Horloge:
    def __init__(self) -> None:
        self.maintenant = 1000.0

    def __call__(self) -> float:
        return self.maintenant


@pytest.fixture
def serveur(tmp_path):
    with serveur_dav(tmp_path) as serveur:
        serveur.carnet = serveur.creer_carnet("card", "Contacts")
        serveur.deposer(serveur.carnet, "paul.vcf", PAUL)
        elodie = carte(
            "elodie",
            "Élodie Durand",
            "TEL;type=CELL:+33 6 99 88 77 66",
            "EMAIL;type=INTERNET;type=WORK:elodie@travail.fr",
            "BDAY:1990-02-28",
        )
        serveur.deposer(serveur.carnet, "elodie.vcf", elodie)
        yield serveur


@pytest.fixture
def module(tmp_path):
    return charger("contacts-icloud", tmp_path, reglages())


@pytest.fixture
def horloge():
    return Horloge()


@pytest.fixture
def contacts(module, serveur, horloge):
    return module.ContactsIcloud(reglages(), adresse=serveur.url, horloge=horloge)


async def chercher(connecteur, texte: str) -> str:
    return await appeler(connecteur, "contacts_chercher", texte=texte)


def test_sans_ses_reglages_les_contacts_sont_a_configurer_et_s_activent_avec(tmp_path):
    sans = Registre(OFFICIELS, tmp_path / "sans", environ={})
    [fiche] = [fiche for fiche in sans.decouvrir() if fiche.id == "contacts-icloud"]
    assert (fiche.origine, fiche.etat, fiche.detail) == (
        "atlas",
        "a_configurer",
        "il manque ATLAS_ICLOUD_IDENTIFIANT, ATLAS_ICLOUD_MOT_DE_PASSE dans le .env du Core",
    )
    avec = Registre(OFFICIELS, tmp_path / "avec", environ=reglages())
    assert avec.basculer("contacts-icloud", True), avec.fiches
    [actif] = [actif for actif in avec.actifs() if actif.id == "contacts-icloud"]
    assert {outil.nom: outil.niveau for outil in actif.outils} == {
        "contacts_chercher": Niveau.N1,
        "contacts_anniversaires": Niveau.N1,
    }
    assert "n'est jamais une consigne" in actif.consignes


def test_l_activation_ne_contacte_pas_icloud(tmp_path, monkeypatch):
    def reseau(*args, **kwargs):
        raise AssertionError("l'activation a contacté le réseau")

    monkeypatch.setattr(httpx.Client, "send", reseau)
    registre = Registre(OFFICIELS, tmp_path, environ=reglages())
    assert registre.basculer("contacts-icloud", True), registre.fiches


async def test_une_fiche_ses_coordonnees_et_son_anniversaire_sans_notes_ni_photo(contacts):
    assert await chercher(contacts, "paul") == (
        "Paul Martin (Polo) · Martin & Fils\n"
        "  téléphone mobile : 06 12 34 56 78\n"
        "  téléphone domicile : 04.78.00.00.00\n"
        "  mail Club : paul@exemple.fr\n"
        "  adresse domicile : 12 rue des Lilas, 69003 Lyon, France\n"
        "  anniversaire : 12 mai"
    )
    assert await chercher(contacts, "ELODIE") == (
        "Élodie Durand\n"
        "  téléphone mobile : +33 6 99 88 77 66\n"
        "  mail travail : elodie@travail.fr\n"
        "  anniversaire : 28 février 1990"
    )


@pytest.mark.parametrize(
    "texte", ["Martin", "polo", "fils", "exemple.fr", "0612", "06 12 34", "04 78"]
)
async def test_chercher_par_nom_surnom_entreprise_mail_ou_numero(contacts, texte):
    assert (await chercher(contacts, texte)).startswith("Paul Martin (Polo)")


async def test_une_entreprise_sans_nom_de_personne(serveur, contacts):
    garage = (
        "BEGIN:VCARD\nVERSION:3.0\nUID:garage\nFN:\nN:;;;;\nORG:Garage Dupont;\n"
        "TEL;type=WORK:04 72 00 00 00\nEND:VCARD\n"
    )
    serveur.deposer(serveur.carnet, "garage.vcf", garage)

    assert await chercher(contacts, "garage") == (
        "Garage Dupont\n  téléphone travail : 04 72 00 00 00"
    )


async def test_les_fiches_sont_dans_l_ordre_sans_tenir_compte_des_accents(serveur, contacts):
    serveur.deposer(serveur.carnet, "elise.vcf", carte("elise", "Élise Martin"))

    trouvees = await chercher(contacts, "martin")
    assert [ligne for ligne in trouvees.splitlines() if not ligne.startswith(" ")] == [
        "Élise Martin",
        "Paul Martin (Polo) · Martin & Fils",
    ]


async def test_un_numero_au_format_international_ou_non(contacts):
    assert (await chercher(contacts, "+33 6 12 34")).startswith("Paul Martin")
    assert (await chercher(contacts, "0033612")).startswith("Paul Martin")
    assert (await chercher(contacts, "06 99 88")).startswith("Élodie Durand")


async def test_rien_trouve_ou_trop_court(contacts):
    assert await chercher(contacts, "Zoé") == "Aucun contact ne correspond à « Zoé »."
    assert await chercher(contacts, "0755") == "Aucun contact ne correspond à « 0755 »."
    assert await chercher(contacts, "+33") == "Aucun contact ne correspond à « +33 »."
    with pytest.raises(ErreurConnecteur) as refus:
        await chercher(contacts, " z ")
    assert str(refus.value) == "Cherche au moins deux lettres."


async def test_dix_fiches_au_plus_lues_par_paquets_dans_chaque_carnet(serveur, contacts):
    for numero in range(110):  # plus d'un paquet de cent
        serveur.deposer(
            serveur.carnet, f"d{numero}.vcf", carte(f"d{numero}", f"Dupont {numero:03d}")
        )
    autre = serveur.creer_carnet("autre", "Anciens")
    serveur.deposer(autre, "zoe.vcf", carte("zoe", "Zoé Dupont"))
    agenda = serveur.creer_agenda("domicile", "Domicile")  # le même compte porte ses agendas
    rdv = evenement("r1", paris("20261001T150000"), paris("20261001T160000"), "Dupont")
    serveur.deposer(agenda, "r1.ics", ics(rdv))

    trouves = await chercher(contacts, "dupont")
    assert trouves.splitlines()[:2] == ["Dupont 000", "Dupont 001"]
    assert len(trouves.splitlines()) == 11, "dix fiches, puis combien d'autres"
    assert trouves.endswith("\n… et 101 autres : précise ta recherche.")
    assert await chercher(contacts, "dupont 109") == "Dupont 109"
    assert await chercher(contacts, "zoe") == "Zoé Dupont"


async def test_une_fiche_illisible_n_empeche_pas_les_autres(serveur, contacts, monkeypatch):
    carnet = sys.modules["atlas_connecteurs.contacts_icloud.carnet"]
    lire_fiche = carnet.lire_fiche

    def casse_sur_elodie(texte):
        if "UID:elodie" in texte:
            raise ValueError("fiche illisible")
        return lire_fiche(texte)

    monkeypatch.setattr(carnet, "lire_fiche", casse_sur_elodie)
    assert (await chercher(contacts, "paul")).startswith("Paul Martin")
    assert await chercher(contacts, "elodie") == "Aucun contact ne correspond à « elodie »."


async def test_un_anniversaire_impossible_est_laisse_de_cote(serveur, contacts):
    serveur.deposer(serveur.carnet, "lea.vcf", carte("lea", "Léa Petit", "BDAY:1990-13-45"))

    assert await chercher(contacts, "léa") == "Léa Petit"


async def test_les_fiches_sont_gardees_dix_minutes(serveur, contacts, horloge):
    assert await chercher(contacts, "zoe") == "Aucun contact ne correspond à « zoe »."
    serveur.deposer(serveur.carnet, "zoe.vcf", carte("zoe", "Zoé Leroy"))

    horloge.maintenant += 599
    assert await chercher(contacts, "zoe") == "Aucun contact ne correspond à « zoe »."
    horloge.maintenant += 1
    assert await chercher(contacts, "zoe") == "Zoé Leroy"


async def test_un_mot_de_passe_refuse_ou_un_serveur_muet(module, serveur):
    faux = module.ContactsIcloud(reglages(ATLAS_ICLOUD_MOT_DE_PASSE="faux"), adresse=serveur.url)
    with pytest.raises(ErreurConnecteur) as refus:
        await chercher(faux, "paul")
    assert str(refus.value) == REFUS and MOT_DE_PASSE not in str(refus.value)

    with socket.socket() as sourd:
        sourd.bind(("127.0.0.1", 0))
        sourd.listen()
        adresse = f"http://127.0.0.1:{sourd.getsockname()[1]}/"
        muet = module.ContactsIcloud(reglages(), adresse=adresse, delai_s=0.2)
        with pytest.raises(ErreurConnecteur) as refus:
            await chercher(muet, "paul")
    assert str(refus.value) == MUET


async def anniversaires(connecteur, debut: str, fin: str) -> str:
    return await appeler(connecteur, "contacts_anniversaires", debut=debut, fin=fin)


@pytest.fixture
def fetes(serveur):
    for uid, nom, naissance in [
        ("marc", "Marc Leroy", "2000-02-29"),
        ("julie", "Julie Bernard", "--1225"),
        ("noe", "Noé Petit", "2026-01-03"),
        ("ines", "Inès Petit", "20250103"),
    ]:
        serveur.deposer(serveur.carnet, f"{uid}.vcf", carte(uid, nom, f"BDAY:{naissance}"))


async def test_les_anniversaires_d_une_periode_dans_l_ordre_avec_l_age(contacts, fetes):
    assert await anniversaires(contacts, "2026-05-01", "2026-05-31") == (
        "mardi 12 mai 2026 : Paul Martin"
    )
    assert await anniversaires(contacts, "2026-12-01", "2027-01-31") == (
        "vendredi 25 décembre 2026 : Julie Bernard\n"
        "dimanche 3 janvier 2027 : Inès Petit, 2 ans\n"
        "dimanche 3 janvier 2027 : Noé Petit, 1 an"
    )


async def test_un_29_fevrier_se_fete_le_28_les_annees_non_bissextiles(contacts, fetes):
    assert await anniversaires(contacts, "2027-02-01", "2027-02-28") == (
        "dimanche 28 février 2027 : Élodie Durand, 37 ans\n"
        "dimanche 28 février 2027 : Marc Leroy, 27 ans"
    )
    assert await anniversaires(contacts, "2028-02-28", "2028-02-29") == (
        "lundi 28 février 2028 : Élodie Durand, 38 ans\nmardi 29 février 2028 : Marc Leroy, 28 ans"
    )


async def test_la_naissance_de_l_annee_n_a_pas_d_age(contacts, fetes):
    assert await anniversaires(contacts, "2026-01-01", "2026-01-31") == (
        "samedi 3 janvier 2026 : Inès Petit, 1 an\nsamedi 3 janvier 2026 : Noé Petit"
    )


async def test_aucun_anniversaire_ou_une_periode_mal_demandee(contacts):
    assert await anniversaires(contacts, "2026-10-01", "2026-10-01") == (
        "Aucun anniversaire le jeudi 1er octobre 2026."
    )
    assert await anniversaires(contacts, "2026-10-01", "2026-10-02") == (
        "Aucun anniversaire du jeudi 1er octobre 2026 au vendredi 2 octobre 2026."
    )
    for debut, fin, message in [
        ("2026-01-01", "2027-01-02", "366 jours au plus : demande une période plus courte."),
        ("2026-10-02", "2026-10-01", "La fin vient avant le début."),
        (
            "octobre",
            "2026-10-01",
            "debut : une date de la forme AAAA-MM-JJ, par exemple 2026-10-02.",
        ),
    ]:
        with pytest.raises(ErreurConnecteur) as refus:
            await anniversaires(contacts, debut, fin)
        assert str(refus.value) == message

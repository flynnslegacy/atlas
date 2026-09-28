"""Le contrat d'un connecteur : son manifeste, lu sans exécuter de code, et ses outils,
enrobés par le serveur « atlas » comme ceux du socle, même quand le connecteur se trompe."""

from pathlib import Path

import pytest

from atlas_core.confirmation import Confirmations
from atlas_core.connecteurs import (
    Connecteur,
    ErreurConnecteur,
    Fait,
    Manifeste,
    Niveau,
    Outil,
    Reglage,
    distribution,
    lire_manifeste,
)
from atlas_core.outils import ECHEC, ServeurAtlas

COMPLET = """
nom = "Agenda iCloud"
description = "Lit et crée des événements dans ton agenda iCloud."
version = "1.0.0"
auteur = "Atlas"
api = 1
dependances = ["caldav>=1.4", "google-api-python-client[oauth]~=2.0"]
services = ["poste"]
consignes = "Consulte l'agenda quand David parle de ses rendez-vous."

[[reglages]]
variable = "ATLAS_ICLOUD_IDENTIFIANT"
description = "Ton identifiant Apple"

[[reglages]]
variable = "ATLAS_ICLOUD_MOT_DE_PASSE"
description = "Un mot de passe pour app"
secret = true
"""

MINIMAL = """
nom = "Bonjour"
description = "Dit bonjour."
version = "0.1"
auteur = "Quelqu'un"
api = 1
"""


def _dossier(tmp_path: Path, manifeste: str | None) -> Path:
    dossier = tmp_path / "connecteur"
    dossier.mkdir()
    if manifeste is not None:
        (dossier / "connecteur.toml").write_text(manifeste, encoding="utf-8")
    return dossier


def test_un_manifeste_complet_se_lit(tmp_path):
    manifeste = lire_manifeste(_dossier(tmp_path, COMPLET))
    assert (manifeste.nom, manifeste.version, manifeste.auteur, manifeste.api) == (
        "Agenda iCloud",
        "1.0.0",
        "Atlas",
        1,
    )
    assert manifeste.dependances == ("caldav>=1.4", "google-api-python-client[oauth]~=2.0")
    assert manifeste.services == ("poste",)
    assert manifeste.reglages == (
        Reglage(variable="ATLAS_ICLOUD_IDENTIFIANT", description="Ton identifiant Apple"),
        Reglage(
            variable="ATLAS_ICLOUD_MOT_DE_PASSE",
            description="Un mot de passe pour app",
            secret=True,
        ),
    )


def test_un_manifeste_minimal_n_a_ni_dependance_ni_reglage(tmp_path):
    manifeste = lire_manifeste(_dossier(tmp_path, MINIMAL))
    assert manifeste == Manifeste(
        nom="Bonjour", description="Dit bonjour.", version="0.1", auteur="Quelqu'un", api=1
    )
    assert (manifeste.dependances, manifeste.services, manifeste.reglages) == ((), (), ())
    assert manifeste.consignes == ""


@pytest.mark.parametrize(
    ("manifeste", "raison"),
    [
        (None, "connecteur.toml absent"),
        ("nom = ", "connecteur.toml illisible"),
        (MINIMAL.replace('nom = "Bonjour"', ""), "nom : Field required"),
        (MINIMAL + 'couleur = "bleu"\n', "couleur : Extra inputs are not permitted"),
        (MINIMAL.replace("api = 1", "api = 2"), "contrat inconnu : api 2 (Atlas connaît api 1)"),
        (MINIMAL + 'services = ["micro"]\n', "services.0"),
        (MINIMAL + 'dependances = ["--index-url=https://ailleurs"]\n', "dependances.0"),
        (MINIMAL + 'dependances = ["git+https://ailleurs/paquet"]\n', "dependances.0"),
        (MINIMAL + 'dependances = ["-e"]\n', "dependances.0"),  # une option de pip, jamais
        (MINIMAL.replace('nom = "Bonjour"', 'nom = ""'), "nom : String should have at least"),
        (
            MINIMAL + '[[reglages]]\nvariable = "ATLAS_X"\ndescription = "x"\nsecet = true\n',
            "reglages.0.secet : Extra inputs are not permitted",
        ),
        (MINIMAL + '[[reglages]]\nvariable = "HOME"\ndescription = "x"\n', "reglages.0.variable"),
    ],
)
def test_un_manifeste_qui_ne_convient_pas_dit_pourquoi(tmp_path, manifeste, raison):
    with pytest.raises(ValueError, match="^connecteur.toml") as erreur:
        lire_manifeste(_dossier(tmp_path, manifeste))
    assert raison in str(erreur.value)


def test_le_nom_de_distribution_d_une_exigence():
    assert distribution("caldav>=1.4") == "caldav"
    assert distribution("google-api-python-client[oauth]~=2.0") == "google-api-python-client"
    assert distribution("icalendar") == "icalendar"


def test_un_connecteur_ne_fait_rien_de_ses_reactions_par_defaut():
    connecteur = Connecteur()
    connecteur.fin_du_tour(arretee=True)
    connecteur.nouvelle_phrase()
    connecteur.nouvelle_conversation()
    with pytest.raises(NotImplementedError):
        connecteur.outils()


async def _appeler(serveur: ServeurAtlas, nom: str) -> tuple[str, bool]:
    outil = next(o for o in serveur.outils if o.name == nom)
    resultat = await outil.handler({})
    return resultat["content"][0]["text"], resultat.get("is_error", False)


async def test_le_refus_d_un_connecteur_revient_a_claude():
    async def refuser(arguments: dict) -> str:
        raise ErreurConnecteur("Le calendrier « Travail » n'existe pas.")

    serveur = ServeurAtlas([Outil("agenda_lire", "Lit.", {}, Niveau.N1, refuser)], Confirmations())
    assert await _appeler(serveur, "agenda_lire") == (
        "Le calendrier « Travail » n'existe pas.",
        True,
    )


@pytest.mark.parametrize(
    ("niveau", "resultat"),
    [(Niveau.N1, None), (Niveau.N1, 42), (Niveau.N2, "écrit"), (Niveau.N3, Fait("fait"))],
)
async def test_un_resultat_de_travers_est_un_echec_pas_une_panne(caplog, niveau, resultat):
    async def maladroit(arguments: dict) -> object:
        return resultat

    confirmations = Confirmations()
    serveur = ServeurAtlas([Outil("maladroit", "Rend.", {}, niveau, maladroit)], confirmations)
    assert await _appeler(serveur, "maladroit") == (ECHEC, True)
    assert "l'outil maladroit a échoué" in caplog.text
    assert f"maladroit (N{niveau.value}) doit rendre" in caplog.text  # le journal dit quoi
    assert serveur.prendre_les_annonces() == [] and not confirmations.en_attente


def test_un_manifeste_dans_un_autre_encodage_dit_qu_il_est_illisible(tmp_path):
    dossier = _dossier(tmp_path, None)
    (dossier / "connecteur.toml").write_bytes(MINIMAL.replace("Dit", "Écrit").encode("latin-1"))
    with pytest.raises(ValueError, match="^connecteur.toml illisible"):
        lire_manifeste(dossier)

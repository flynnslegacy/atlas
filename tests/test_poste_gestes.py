"""Les gestes du poste, sans toucher au Mac : de fausses commandes macOS (`open`,
`screencapture`, `sips`, `osascript`) et de faux événements Quartz."""

import base64
import subprocess
from pathlib import Path

import pytest

from atlas_core.protocole_poste import (
    TOUCHES_NOMMEES,
    ActionPoste,
    Capturer,
    Cliquer,
    Defiler,
    Ouvrir,
    Taper,
    Touches,
)
from atlas_poste.gestes import CODES_TOUCHES, Gestes, script_des_touches
from atlas_poste.quartz import morceaux


class FauxLanceur:
    """Les commandes macOS, jouées de mémoire."""

    def __init__(self) -> None:
        self.commandes: list[list[str]] = []
        self.introuvables: set[str] = set()
        self.capture_cassee = False
        self.osascript_refuse = False

    def __call__(self, commande: list[str]) -> subprocess.CompletedProcess:
        self.commandes.append(commande)
        code, sortie, erreur = 0, "", ""
        if commande[0] == "open" and commande[-1] in self.introuvables:
            code, erreur = 1, f"Unable to open '{commande[-1]}'"
        elif commande[0] == "screencapture":
            if self.capture_cassee:
                code = 1
            else:
                Path(commande[-1]).write_bytes(b"JPEG-PLEIN")
        elif commande[:2] == ["sips", "-Z"]:
            Path(commande[-1]).write_bytes(b"JPEG-REDUIT")
        elif commande[:2] == ["sips", "-g"]:
            sortie = f"{commande[-1]}\n  pixelWidth: 1280\n  pixelHeight: 800\n"
        elif commande[0] == "osascript" and self.osascript_refuse:
            code, erreur = (
                1,
                "System Events got an error: osascript is not allowed to send keystrokes.",
            )
        return subprocess.CompletedProcess(commande, code, sortie, erreur)


class FauxEvenements:
    def __init__(self) -> None:
        self.gestes: list[tuple] = []
        self.capture_permise = True
        self.action_permise = True

    def peut_capturer(self) -> bool:
        return self.capture_permise

    def peut_agir(self) -> bool:
        return self.action_permise

    def taille_ecran(self) -> tuple[float, float]:
        return 1440.0, 900.0  # en points : un écran Retina de 2880 × 1800 pixels

    def cliquer(self, x: float, y: float, bouton: str, double: bool) -> None:
        self.gestes.append(("cliquer", x, y, bouton, double))

    def taper(self, texte: str) -> None:
        self.gestes.append(("taper", texte))

    def defiler(self, sens: str, quantite: int) -> None:
        self.gestes.append(("defiler", sens, quantite))


@pytest.fixture
def lanceur() -> FauxLanceur:
    return FauxLanceur()


@pytest.fixture
def evenements() -> FauxEvenements:
    return FauxEvenements()


@pytest.fixture
def gestes(lanceur, evenements) -> Gestes:
    return Gestes(lancer=lanceur, evenements=evenements)


def faire(gestes: Gestes, geste, identifiant: int = 7):
    return gestes.executer(ActionPoste(id=identifiant, geste=geste))


# --- ouvrir ------------------------------------------------------------------------


def test_ouvrir_une_app_par_son_nom(gestes, lanceur):
    resultat = faire(gestes, Ouvrir(app="Safari"))
    assert (resultat.id, resultat.ok, resultat.erreur) == (7, True, None)
    assert lanceur.commandes == [["open", "-a", "Safari"]]


def test_une_app_introuvable_se_dit(gestes, lanceur):
    lanceur.introuvables.add("Spotifi")
    resultat = faire(gestes, Ouvrir(app="Spotifi"))
    assert (resultat.ok, resultat.erreur) == (False, "Je ne trouve pas l'app Spotifi.")


def test_ouvrir_une_page_web(gestes, lanceur):
    assert faire(gestes, Ouvrir(adresse="https://example.com/meteo")).ok
    assert lanceur.commandes == [["open", "https://example.com/meteo"]]
    lanceur.introuvables.add("https://example.com/panne")
    assert faire(gestes, Ouvrir(adresse="https://example.com/panne")).erreur == (
        "Je n'arrive pas à ouvrir https://example.com/panne."
    )


# --- capturer ----------------------------------------------------------------------


def test_une_capture_est_reduite_rendue_puis_effacee(gestes, lanceur):
    resultat = faire(gestes, Capturer())
    assert resultat.ok and (resultat.largeur, resultat.hauteur) == (1280, 800)
    assert base64.b64decode(resultat.image) == b"JPEG-REDUIT"
    capture, reduction, taille = lanceur.commandes
    assert capture[:4] == ["screencapture", "-x", "-t", "jpg"]
    assert reduction == ["sips", "-Z", "1280", capture[-1]]
    assert taille == ["sips", "-g", "pixelWidth", "-g", "pixelHeight", capture[-1]]
    assert not Path(capture[-1]).exists(), "aucune capture ne reste sur le disque"


def test_sans_autorisation_la_capture_le_dit_sans_rien_lancer(gestes, lanceur, evenements):
    evenements.capture_permise = False
    resultat = faire(gestes, Capturer())
    assert (resultat.ok, resultat.erreur) == (
        False,
        "Autorise l'enregistrement de l'écran pour le poste dans les Réglages.",
    )
    assert lanceur.commandes == []


def test_une_capture_ratee_se_dit(gestes, lanceur):
    lanceur.capture_cassee = True
    assert faire(gestes, Capturer()).erreur == "La capture de l'écran a échoué."


# --- cliquer, taper, défiler ---------------------------------------------------------


def test_un_clic_vise_la_derniere_capture_et_se_convertit_en_points(gestes, evenements):
    faire(gestes, Capturer())
    assert faire(gestes, Cliquer(x=640, y=400, bouton="droit", double=True)).ok
    assert evenements.gestes == [("cliquer", 720.0, 450.0, "droit", True)]


def test_un_clic_sans_capture_ou_hors_capture_est_refuse(gestes, evenements):
    assert faire(gestes, Cliquer(x=10, y=10)).erreur == (
        "Capture l'écran d'abord : un clic vise un point de la dernière capture."
    )
    faire(gestes, Capturer())
    assert faire(gestes, Cliquer(x=1280, y=10)).erreur == "Ce point sort de la dernière capture."
    assert faire(gestes, Cliquer(x=10, y=800)).erreur == "Ce point sort de la dernière capture."
    assert evenements.gestes == []


def test_taper_et_defiler(gestes, evenements):
    assert faire(gestes, Taper(texte="Bonjour à tous")).ok
    assert faire(gestes, Defiler(sens="bas", quantite=5)).ok
    assert evenements.gestes == [("taper", "Bonjour à tous"), ("defiler", "bas", 5)]


@pytest.mark.parametrize(
    "geste",
    [
        Cliquer(x=1, y=1),
        Taper(texte="x"),
        Touches(touches="cmd+l"),
        Defiler(sens="haut", quantite=1),
    ],
)
def test_sans_accessibilite_aucun_geste_ne_part(gestes, lanceur, evenements, geste):
    faire(gestes, Capturer())
    evenements.action_permise = False
    lanceur.commandes.clear()
    resultat = faire(gestes, geste)
    assert (resultat.ok, resultat.erreur) == (
        False,
        "Autorise l'accessibilité pour le poste dans les Réglages.",
    )
    assert evenements.gestes == [] and lanceur.commandes == []


# --- les touches -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("touches", "script"),
    [
        ("cmd+l", 'tell application "System Events" to keystroke "l" using {command down}'),
        (
            "cmd+maj+t",
            'tell application "System Events" to keystroke "t" using {command down, shift down}',
        ),
        ("a", 'tell application "System Events" to keystroke "a"'),
        ("entrée", 'tell application "System Events" to key code 36'),
        (
            "alt+ctrl+gauche",
            'tell application "System Events" to key code 123 using {option down, control down}',
        ),
        ("page bas", 'tell application "System Events" to key code 121'),
    ],
)
def test_les_touches_passent_par_system_events_qui_connait_le_clavier(touches, script):
    # Par des caractères, pas des codes de touches physiques : sur un clavier AZERTY, le
    # code de « a » en QWERTY tape « q », et cmd+a deviendrait cmd+q.
    assert script_des_touches(touches) == script


def test_chaque_touche_nommee_a_son_code_macos():
    # Les codes virtuels de macOS (HIToolbox, Events.h) : kVK_Return = 0x24, kVK_Tab = 0x30…
    # Une touche nommée sans code partirait en texte : « page haut » serait tapé en lettres.
    assert set(CODES_TOUCHES) == set(TOUCHES_NOMMEES)
    assert CODES_TOUCHES == {
        "entrée": 0x24,
        "tab": 0x30,
        "espace": 0x31,
        "effacer": 0x33,
        "échap": 0x35,
        "gauche": 0x7B,
        "droite": 0x7C,
        "bas": 0x7D,
        "haut": 0x7E,
        "début": 0x73,
        "fin": 0x77,
        "page haut": 0x74,
        "page bas": 0x79,
    }


def test_une_combinaison_passe_par_osascript(gestes, lanceur):
    assert faire(gestes, Touches(touches="cmd+l")).ok
    assert lanceur.commandes == [
        [
            "osascript",
            "-e",
            'tell application "System Events" to keystroke "l" using {command down}',
        ]
    ]


def test_sans_autorisation_d_automatisation_les_touches_le_disent(gestes, lanceur):
    lanceur.osascript_refuse = True
    assert faire(gestes, Touches(touches="entrée")).erreur == (
        "Autorise le poste à contrôler « System Events » dans les Réglages (Automatisation)."
    )


def test_une_panne_inattendue_ne_fait_jamais_tomber_le_poste(evenements):
    def lanceur_en_panne(commande):
        raise RuntimeError("disque plein")

    resultat = Gestes(lancer=lanceur_en_panne, evenements=evenements).executer(
        ActionPoste(id=3, geste=Ouvrir(app="Safari"))
    )
    assert (resultat.id, resultat.ok, resultat.erreur) == (
        3,
        False,
        "Le geste a échoué (RuntimeError).",
    )


def test_la_frappe_part_en_morceaux_de_20_unites_sans_couper_un_emoji():
    # macOS perd la fin d'un événement clavier de plus de 20 unités UTF-16 ; un emoji en
    # compte deux.
    texte = "Bravo " + "🎉" * 10 + " à tous, ça marche !"
    parties = morceaux(texte)
    assert "".join(parties) == texte
    assert all(len(partie.encode("utf-16-le")) // 2 <= 20 for partie in parties)
    assert parties[0] == "Bravo " + "🎉" * 7
    assert morceaux("a" * 45) == ["a" * 20, "a" * 20, "a" * 5]
    assert morceaux("") == []

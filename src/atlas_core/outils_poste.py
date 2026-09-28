"""Les outils du poste : ouvrir et regarder sur le Mac de David, et piloter ses apps dans une
mission qu'il confirme (spec du poste, §5).

`mac_ouvrir` et `mac_regarder` sont N2 : faits, puis annoncés. `mac_mission` est N3 : la
tâche entière attend le « oui » de David ; ce « oui » ouvre la mission et part à Claude, qui
pilote dans la réponse qui suit. Les gestes (`mac_capture`, `mac_cliquer`…) n'existent que
pendant une mission : hors mission, ils refusent. Une mission s'arrête quand Claude la
termine, au bout de sa durée, quand David parle, quand la réponse se termine, ou quand la
conversation se ferme.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlsplit

from pydantic import ValidationError

from .confirmation import Mission
from .outils import Capture, Fait, Niveau, Outil
from .poste import ABSENT, ErreurPoste, Poste
from .protocole_poste import Capturer, Cliquer, Defiler, Geste, Ouvrir, Taper, Touches

DUREE_S = 180.0
AUCUNE_MISSION = "Aucune mission en cours : demande d'abord à David avec mac_mission."
TEMPS_ECOULE = "Le temps de la mission est écoulé."
FAIT = "Fait."

OUVRIR = (
    "Ouvre une app du Mac de David (app), par le nom de son fichier, souvent en anglais même "
    "sur un Mac en français (Calendar, Preview, System Settings, Music, Reminders), ou une "
    "page web en http(s) (adresse), quand David te le demande. Atlas l'annonce : ne l'annonce "
    "pas toi-même."
)
REGARDER = (
    "Regarde l'écran du Mac de David, seulement quand il te demande quelque chose sur son "
    "écran. Atlas le lui dit : ne l'annonce pas toi-même."
)
MISSION = (
    "Pour tout ce qui demande de cliquer ou de taper sur le Mac de David : décris la tâche "
    "entière à l'infinitif, avec le détail exact (le texte à écrire, le destinataire). Atlas "
    "demande à David de confirmer : n'ajoute rien après l'appel. S'il dit oui, la mission "
    "commence dans ta réponse suivante : pilote avec mac_capture, mac_cliquer, mac_taper, "
    "mac_touches et mac_defiler, puis termine par mac_fin_de_mission."
)
CAPTURE = (
    "Pendant une mission : montre l'écran (1280 pixels de large). Capture avant de viser, et "
    "après pour vérifier."
)
CLIQUER = (
    "Pendant une mission : clique au point (x, y) de la dernière capture, en pixels depuis son "
    "coin haut gauche ; bouton gauche (par défaut) ou droit, double au besoin."
)
TAPER = (
    "Pendant une mission : tape un texte (2 000 caractères au plus). Jamais un mot de passe, "
    "un identifiant ni des coordonnées bancaires."
)
TOUCHES = (
    "Pendant une mission : une combinaison, par exemple cmd+l, cmd+maj+t, entrée, tab, échap, "
    "ou une flèche (haut, bas, gauche, droite)."
)
DEFILER = "Pendant une mission : fait défiler vers le haut ou le bas (quantite de 1 à 20)."
FIN = (
    "Termine la mission, une fois la tâche faite ou impossible ; puis dis à David son bilan en "
    "une ou deux phrases."
)
_SCHEMA_OUVRIR = {
    "type": "object",
    "properties": {"app": {"type": "string"}, "adresse": {"type": "string"}},
}
_SCHEMA_CLIQUER = {
    "type": "object",
    "properties": {
        "x": {"type": "integer"},
        "y": {"type": "integer"},
        "bouton": {"type": "string", "enum": ["gauche", "droit"]},
        "double": {"type": "boolean"},
    },
    "required": ["x", "y"],
}


class Missions:
    """La mission en cours : ouverte par le « oui » de David, fermée par sa fin, sa durée, une
    phrase de David, la fin de la réponse ou celle de la conversation. `sur_debut` et
    `sur_fin` préviennent les pages."""

    def __init__(
        self,
        duree_s: float = DUREE_S,
        attendre: Callable[[float], Awaitable[None]] = asyncio.sleep,
        sur_debut: Callable[[str], None] | None = None,
        sur_fin: Callable[[str], None] | None = None,
    ) -> None:
        self.duree_s = duree_s
        self._attendre = attendre
        self.sur_debut = sur_debut or (lambda texte: None)
        self.sur_fin = sur_fin or (lambda texte: None)
        self.en_cours: str | None = None
        self._expiree = False
        self._minuterie: asyncio.Task | None = None

    def ouvrir(self, description: str) -> None:
        self.fermer("Mission arrêtée.")
        self.en_cours, self._expiree = description, False
        self._minuterie = asyncio.create_task(self._expirer())
        self.sur_debut(f"Mission en cours : {description}")

    def fermer(self, fin: str) -> None:
        """Ferme la mission en cours, s'il y en a une, et le dit aux pages."""
        self._expiree = False
        if self.en_cours is None:
            return
        self._arreter_la_minuterie()
        self.en_cours = None
        self.sur_fin(fin)

    def verifier(self) -> None:
        """Un geste n'a lieu que pendant une mission ; sinon `ErreurPoste`, pour Claude."""
        if self.en_cours is None:
            raise ErreurPoste(TEMPS_ECOULE if self._expiree else AUCUNE_MISSION)

    async def _expirer(self) -> None:
        await self._attendre(self.duree_s)
        self._minuterie = None  # c'est elle qui sonne : rien à annuler
        if self.en_cours is not None:
            self.en_cours, self._expiree = None, True
            self.sur_fin("Temps de la mission écoulé.")

    def _arreter_la_minuterie(self) -> None:
        if self._minuterie is not None:
            self._minuterie.cancel()
            self._minuterie = None


def _domaine(adresse: str) -> str:
    hote = urlsplit(adresse).hostname or adresse
    return hote.removeprefix("www.")


def outils_du_poste(poste: Poste, missions: Missions) -> list[Outil]:
    async def faire(geste_de: Callable[[], Geste]) -> None:
        try:
            geste = geste_de()
        except ValidationError as e:
            premiere = e.errors()[0]
            raise ErreurPoste(str(premiere.get("msg", "geste invalide"))) from None
        await poste.demander(geste)

    async def capturer() -> Capture:
        resultat = await poste.demander(Capturer())
        return Capture(resultat.image or "", resultat.largeur or 0, resultat.hauteur or 0)

    async def ouvrir(arguments: dict[str, Any]) -> Fait:
        app = (arguments.get("app") or "").strip() or None
        adresse = (arguments.get("adresse") or "").strip() or None
        try:
            geste = Ouvrir(app=app, adresse=adresse)
        except ValidationError:
            raise ErreurPoste(
                "Donne une app par son nom, ou une adresse web en http(s), pas les deux."
            ) from None
        await poste.demander(geste)
        annonce = f"J'ouvre {app}." if app else f"J'ouvre la page {_domaine(adresse or '')}."
        return Fait("C'est ouvert.", annonce)

    async def regarder(arguments: dict[str, Any]) -> Fait:
        vue = await capturer()
        legende = f"Capture de l'écran, {vue.largeur} × {vue.hauteur}."
        return Fait(legende, "Je regarde ton écran.", image=vue)

    async def mission(arguments: dict[str, Any]) -> Mission:
        description = arguments.get("mission", "").strip().rstrip(".")
        if not description:
            raise ErreurPoste("Décris la mission à l'infinitif, avec le détail exact.")
        if not poste.connecte:
            raise ErreurPoste(ABSENT)

        def encore_connecte() -> None:
            if not poste.connecte:  # parti entre la question et le « oui »
                raise ErreurPoste(ABSENT)

        return Mission(
            description, executer=encore_connecte, apres=lambda: missions.ouvrir(description)
        )

    async def capture(arguments: dict[str, Any]) -> Capture:
        missions.verifier()
        return await capturer()

    async def cliquer(arguments: dict[str, Any]) -> str:
        missions.verifier()
        await faire(
            lambda: Cliquer(
                x=arguments["x"],
                y=arguments["y"],
                bouton=arguments.get("bouton") or "gauche",
                double=bool(arguments.get("double", False)),
            )
        )
        return FAIT

    async def taper(arguments: dict[str, Any]) -> str:
        missions.verifier()
        await faire(lambda: Taper(texte=arguments["texte"]))
        return FAIT

    async def touches(arguments: dict[str, Any]) -> str:
        missions.verifier()
        await faire(lambda: Touches(touches=arguments["touches"]))
        return FAIT

    async def defiler(arguments: dict[str, Any]) -> str:
        missions.verifier()
        await faire(lambda: Defiler(sens=arguments["sens"], quantite=arguments["quantite"]))
        return FAIT

    async def fin(arguments: dict[str, Any]) -> str:
        missions.verifier()
        missions.fermer("Mission terminée.")
        return "La mission est terminée : dis son bilan à David en une ou deux phrases."

    return [
        Outil("mac_ouvrir", OUVRIR, _SCHEMA_OUVRIR, Niveau.N2, ouvrir),
        Outil("mac_regarder", REGARDER, {}, Niveau.N2, regarder),
        Outil("mac_mission", MISSION, {"mission": str}, Niveau.N3, mission),
        # Les gestes : couverts par le « oui » de la mission, ils refusent hors mission.
        Outil("mac_capture", CAPTURE, {}, Niveau.N1, capture),
        Outil("mac_cliquer", CLIQUER, _SCHEMA_CLIQUER, Niveau.N1, cliquer),
        Outil("mac_taper", TAPER, {"texte": str}, Niveau.N1, taper),
        Outil("mac_touches", TOUCHES, {"touches": str}, Niveau.N1, touches),
        Outil("mac_defiler", DEFILER, {"sens": str, "quantite": int}, Niveau.N1, defiler),
        Outil("mac_fin_de_mission", FIN, {"bilan": str}, Niveau.N1, fin),
    ]

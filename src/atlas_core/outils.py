"""Les outils d'Atlas et leurs niveaux d'autorisation (spec parente §10, spec 2c §4).

Chaque outil déclare son niveau dans le code, et le Core applique la règle autour de lui :
Claude ne choisit jamais. N1 lit, sans rien dire ; N2 agit, puis le Core fait annoncer ce qui
a été fait ; N3 ne fait rien lui-même : il décrit son action, que le Core met en attente du
« oui » de David (confirmation.py). Tous les outils sont servis à Claude par un seul serveur
MCP, « atlas », qui tourne dans le Core (le SDK de Claude).
"""

from __future__ import annotations

import enum
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    SdkMcpTool,
    ToolUseBlock,
    create_sdk_mcp_server,
    tool,
)
from claude_agent_sdk.types import McpSdkServerConfig

from .cerveau import Confirmation, Note
from .confirmation import Confirmations
from .memoire import ErreurMemoire

_journal = logging.getLogger(__name__)

SERVEUR = "atlas"
PENDANT_LE_RESUME = "La conversation se résume : rien ne s'écrit maintenant."
ECHEC = "L'outil n'a pas pu faire ça : une erreur est notée dans le journal du Core."
EN_ATTENTE = (
    "En attente de la confirmation de David : Atlas lui pose la question. N'ajoute rien, et "
    "ne dis pas que c'est fait."
)
DEJA_EN_ATTENTE = "Une action attend déjà la réponse de David : attends-la avant une autre."

Gestionnaire = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class Niveau(enum.IntEnum):
    N1 = 1  # lecture, consultation : fait, sans rien dire
    N2 = 2  # modification réversible : fait, puis annoncé
    N3 = 3  # irréversible ou sortant : attend le « oui » de David


@dataclass(frozen=True)
class Fait:
    """Le résultat d'un outil N2 : le texte pour Claude, et l'annonce pour David — None si
    rien n'a changé."""

    texte: str
    annonce: str | None = None


@dataclass(frozen=True)
class Outil:
    """Un outil et son niveau. Son gestionnaire rend du texte (N1), un `Fait` (N2), ou
    l'action à confirmer (N3, une `Suppression`)."""

    nom: str
    description: str
    parametres: dict[str, type]
    niveau: Niveau
    gestionnaire: Callable[[dict[str, Any]], Awaitable[Any]]


def _texte(texte: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": texte}]}


def _refus(texte: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": texte}], "is_error": True}


class ServeurAtlas:
    """Le serveur « atlas » : ses outils, la règle de leur niveau, les annonces à faire, et
    l'action qui attend le « oui » de David."""

    def __init__(self, outils: list[Outil], confirmations: Confirmations) -> None:
        self.declarations = list(outils)
        self.confirmations = confirmations
        self.ecriture_permise = True  # False pendant le résumé d'une conversation
        # Le SDK exécute nos outils dès que le CLI le demande, avant que le cerveau ait lu le
        # texte qui précède l'appel : chaque annonce, et la question, attendent que le cerveau
        # ait lu l'appel de leur outil (les appels sont numérotés, ceux lus comptés).
        self._annonces: list[tuple[int, Note]] = []
        self._appels = 0
        self._vus = 0
        self._appel_de_la_question: int | None = None
        self.outils: list[SdkMcpTool] = [
            tool(o.nom, o.description, o.parametres)(self._regle(o)) for o in outils
        ]

    @property
    def noms(self) -> list[str]:
        """Les noms sous lesquels Claude voit ces outils."""
        return [f"mcp__{SERVEUR}__{outil.name}" for outil in self.outils]

    def serveur(self) -> McpSdkServerConfig:
        return create_sdk_mcp_server(SERVEUR, tools=self.outils)

    def prendre_les_annonces(self, toutes: bool = True) -> list[Note]:
        """Ce qui a été fait depuis le dernier appel, à annoncer dans l'ordre ; avec
        `toutes=False`, seulement ce dont le cerveau a déjà lu l'appel."""
        pretes = [note for appel, note in self._annonces if toutes or appel <= self._vus]
        self._annonces = [(a, n) for a, n in self._annonces if not (toutes or a <= self._vus)]
        return pretes

    def marquer_vus(self, message: object) -> None:
        """Le cerveau a lu ce message : ses appels à nos outils sont passés dans la réponse."""
        if isinstance(message, AssistantMessage) and message.parent_tool_use_id is None:
            prefixe = f"mcp__{SERVEUR}__"
            self._vus += sum(
                isinstance(bloc, ToolUseBlock) and bloc.name.startswith(prefixe)
                for bloc in message.content
            )

    def poser_la_question(self) -> Confirmation | None:
        """La question de l'action N3 en attente, une fois le cerveau arrivé à son appel."""
        appel = self._appel_de_la_question
        if appel is None or appel > self._vus:
            return None
        return self.confirmations.poser()

    def nouvelle_conversation(self) -> None:
        """La conversation se termine : l'action en attente est abandonnée, et les appels se
        recomptent ; ce qui attend d'être annoncé le sera au début de la réponse suivante."""
        self.confirmations.abandonner()
        self._appels = self._vus = 0
        self._appel_de_la_question = None
        self._annonces = [(0, note) for _, note in self._annonces]

    def _regle(self, outil: Outil) -> Gestionnaire:
        async def appliquer(arguments: dict[str, Any]) -> dict[str, Any]:
            self._appels += 1
            appel = self._appels
            if outil.niveau > Niveau.N1 and not self.ecriture_permise:
                return _refus(PENDANT_LE_RESUME)
            try:
                resultat = await outil.gestionnaire(arguments)
            except ErreurMemoire as e:
                return _refus(str(e))  # un refus : Claude le dit à David
            except Exception:
                _journal.exception("l'outil %s a échoué", outil.nom)
                return _refus(ECHEC)
            if outil.niveau == Niveau.N3:
                if not self.confirmations.mettre_en_attente(resultat):
                    return _refus(DEJA_EN_ATTENTE)
                self._appel_de_la_question = appel
                return _texte(EN_ATTENTE)
            if outil.niveau == Niveau.N2:
                if resultat.annonce is not None:
                    self._annonces.append((appel, Note(resultat.annonce)))
                return _texte(resultat.texte)
            return _texte(resultat)

        return appliquer

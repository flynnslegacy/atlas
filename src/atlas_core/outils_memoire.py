"""Le serveur d'outils d'Atlas : les quatre outils de la mémoire, que Claude appelle.

Il tourne dans le Core, par le SDK de Claude (`create_sdk_mcp_server`). Chaque écriture
passe par `Memoire`, qui la vérifie et la commite ; l'outil garde pour le cerveau la
phrase qui l'annoncera (`Note`). La phase 2c y ajoutera ses outils et ses niveaux
d'autorisation.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from claude_agent_sdk import SdkMcpTool, create_sdk_mcp_server, tool
from claude_agent_sdk.types import McpSdkServerConfig

from .cerveau import Note
from .memoire import ErreurMemoire, Memoire

_journal = logging.getLogger(__name__)

SERVEUR = "atlas"
ANNONCE_PROFIL = "Je le note dans ton profil."
ANNONCE_RETRAIT = "J'ai retiré ma dernière note."
PENDANT_LE_RESUME = "La conversation se résume : rien ne s'écrit maintenant."
ECHEC = "La mémoire n'a pas pu faire ça : une erreur est notée dans le journal du Core."

LIRE = (
    "Lit un fichier de ta mémoire : profil.md, une fiche (entreprise/, projets/ ou "
    "personnes/ suivi du nom) ou un jour du journal (journal/AAAA-MM-JJ.md). Lis une fiche "
    "avant de la modifier."
)
CHERCHER = (
    "Cherche un mot ou un nom dans tes fiches et ton journal, sans tenir compte des "
    "majuscules ni des accents. Rend au plus vingt lignes, chacune avec son fichier."
)
ECRIRE = (
    "Crée ou remplace une fiche entière de ta mémoire : profil.md, ou entreprise/<nom>.md, "
    "projets/<nom>.md, personnes/<nom>.md, le nom en minuscules, chiffres et tirets. Le "
    "contenu commence par « # Titre », une ligne vide, puis une phrase de résumé ; le reste "
    "est libre. Atlas annonce l'écriture à David : ne l'annonce pas toi-même."
)
ANNULER = (
    "Retire ta dernière note encore en place, quand David dit « annule », « oublie ça » ou "
    "« ne note pas ça ». Rappeler cet outil remonte d'une note. Atlas le dit à David."
)

Gestionnaire = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


def annonce_de(chemin: str, titre: str) -> str:
    return ANNONCE_PROFIL if chemin == "profil.md" else f"Je le note dans la fiche {titre}."


def _texte(texte: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": texte}]}


def _refus(texte: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": texte}], "is_error": True}


def _protege(gestionnaire: Gestionnaire) -> Gestionnaire:
    """Un refus de la mémoire revient à Claude, qui le dit à David ; une panne aussi,
    notée en plus dans le journal du Core."""

    async def enveloppe(arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            return await gestionnaire(arguments)
        except ErreurMemoire as e:
            return _refus(str(e))
        except Exception:
            _journal.exception("un outil de la mémoire a échoué")
            return _refus(ECHEC)

    return enveloppe


class OutilsMemoire:
    def __init__(self, memoire: Memoire) -> None:
        self.memoire = memoire
        self.ecriture_permise = True  # False pendant le résumé d'une conversation
        self._annonces: list[Note] = []
        self.outils: list[SdkMcpTool] = [
            tool("memoire_lire", LIRE, {"chemin": str})(_protege(self._lire)),
            tool("memoire_chercher", CHERCHER, {"texte": str})(_protege(self._chercher)),
            tool("memoire_ecrire", ECRIRE, {"chemin": str, "contenu": str})(_protege(self._ecrire)),
            tool("memoire_annuler", ANNULER, {})(_protege(self._annuler)),
        ]

    @property
    def noms(self) -> list[str]:
        """Les noms sous lesquels Claude voit ces outils."""
        return [f"mcp__{SERVEUR}__{outil.name}" for outil in self.outils]

    def serveur(self) -> McpSdkServerConfig:
        return create_sdk_mcp_server(SERVEUR, tools=self.outils)

    def prendre_les_annonces(self) -> list[Note]:
        """Les écritures faites depuis le dernier appel, à annoncer dans l'ordre."""
        annonces, self._annonces = self._annonces, []
        return annonces

    async def _lire(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return _texte(await asyncio.to_thread(self.memoire.lire, arguments["chemin"]))

    async def _chercher(self, arguments: dict[str, Any]) -> dict[str, Any]:
        lignes = await asyncio.to_thread(self.memoire.chercher, arguments["texte"])
        return _texte("\n".join(lignes) if lignes else "Rien trouvé.")

    async def _ecrire(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if not self.ecriture_permise:
            return _refus(PENDANT_LE_RESUME)
        chemin = arguments["chemin"]
        titre = await asyncio.to_thread(self.memoire.ecrire, chemin, arguments["contenu"])
        if titre is None:
            return _texte("La fiche était déjà ainsi : rien n'a changé.")
        self._annonces.append(Note(annonce_de(chemin, titre)))
        return _texte(f"C'est noté dans {chemin}.")

    async def _annuler(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if not self.ecriture_permise:
            return _refus(PENDANT_LE_RESUME)
        defait = await asyncio.to_thread(self.memoire.annuler)
        self._annonces.append(Note(ANNONCE_RETRAIT))
        return _texte(f"La note « {defait.titre} » est retirée.")

"""Les options de Claude pour Atlas : le SDK Agent enfermé dans son rôle, et l'environnement
qu'il reçoit du Core."""

from __future__ import annotations

import shutil
from collections.abc import MutableMapping
from pathlib import Path
from typing import TYPE_CHECKING

from claude_agent_sdk import ClaudeAgentOptions

from .consignes import consignes_pour
from .outils import SERVEUR

if TYPE_CHECKING:
    from .outils_memoire import OutilsMemoire

OUTIL_RECHERCHE = "WebSearch"  # le seul outil de Claude en 2a (pas de WebFetch : spec D3)


def options_cerveau(
    modele: str, dossier: Path, outils: OutilsMemoire | None = None
) -> ClaudeAgentOptions:
    """Claude enfermé dans son rôle : la recherche web, et ses outils s'il en a (mémoire,
    connecteurs) ; aucun réglage ni `CLAUDE.md` de la machine, aucun autre MCP, un dossier
    vide."""
    return ClaudeAgentOptions(
        tools=[OUTIL_RECHERCHE],
        allowed_tools=[OUTIL_RECHERCHE, *(outils.noms if outils else [])],
        system_prompt=consignes_pour(outils),
        setting_sources=[],
        mcp_servers={SERVEUR: outils.serveur()} if outils else {},
        strict_mcp_config=True,
        include_partial_messages=True,
        model=modele,
        cwd=dossier,
        # Le CLI installé et connecté à l'abonnement ; sans lui (PATH réduit d'un service
        # launchd), le SDK prend le CLI qu'il embarque, qui lit la même connexion.
        cli_path=shutil.which("claude"),
        # Aucune transcription de conversation écrite sur le disque par le CLI.
        env={"CLAUDE_CODE_SKIP_PROMPT_HISTORY": "1"},
    )


def purger_cles_api(environnement: MutableMapping[str, str]) -> list[str]:
    """Retire les variables `ANTHROPIC_*` : le SDK passe tout l'environnement du Core au
    CLI, et une clé d'API y ferait payer à l'usage au lieu de l'abonnement. Rend les
    noms retirés (jamais les valeurs). `CLAUDE_CODE_OAUTH_TOKEN`, lui, reste."""
    retirees = sorted(nom for nom in environnement if nom.startswith("ANTHROPIC_"))
    for nom in retirees:
        del environnement[nom]
    return retirees

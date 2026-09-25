"""Le cerveau de la phase 2 : Claude, piloté par le SDK Agent.

Un seul `CerveauClaude` pour tout le Core : la voix et le clavier nourrissent la même
conversation. Le client SDK — et derrière lui le CLI `claude`, connecté à l'abonnement
de David — ne démarre qu'à la première question : un Core sans Claude démarre quand
même, et l'erreur ne paraît qu'au moment de répondre.

Une question à la fois. Une réponse abandonnée en route (interruption, question tapée,
réveil) laisse un tour ouvert chez Claude : une tâche de ménage l'interrompt et en vide
les derniers messages, et la question suivante attend ce ménage avant de partir. La
session, elle, n'attend rien : sa voix se tait tout de suite.
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
import logging
import shutil
import time
from collections.abc import AsyncIterator, Callable, MutableMapping
from pathlib import Path
from typing import Any, Protocol

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKError,
    CLIConnectionError,
    CLINotFoundError,
    RateLimitEvent,
    ResultMessage,
    StreamEvent,
    TextBlock,
    ToolUseBlock,
)

from .cerveau import RECHERCHE, ErreurCerveau, Recherche
from .consignes import CONSIGNES, CONSIGNES_AVEC_MEMOIRE, ligne_de_date
from .outils_memoire import SERVEUR, OutilsMemoire

_journal = logging.getLogger(__name__)

OUTIL_RECHERCHE = "WebSearch"  # le seul outil de Claude en 2a (pas de WebFetch : spec D3)
DELAI_MENAGE_S = 15.0
PHRASE_FIL_PERDU = "Je reprends de zéro, j'ai perdu le fil."

ABSENT = "Claude Code n'est pas installé sur cette machine."
DECONNECTE = "Claude n'est plus connecté : il faut renouveler sa connexion."
LIMITE = "J'ai atteint la limite de l'abonnement Claude pour le moment."
INJOIGNABLE = "Je n'arrive pas à joindre Claude : vérifie le réseau."
ARRET = "Claude s'est arrêté en pleine réponse."

_ERREURS_ASSISTANT = {
    "authentication_failed": DECONNECTE,
    "rate_limit": LIMITE,
    "server_error": INJOIGNABLE,
}


def options_cerveau(
    modele: str, dossier: Path, outils: OutilsMemoire | None = None
) -> ClaudeAgentOptions:
    """Claude enfermé dans son rôle : la recherche web, et les outils de sa mémoire s'il en
    a une ; aucun réglage ni `CLAUDE.md` de la machine, aucun autre serveur MCP, un
    dossier de travail vide."""
    return ClaudeAgentOptions(
        tools=[OUTIL_RECHERCHE],
        allowed_tools=[OUTIL_RECHERCHE, *(outils.noms if outils else [])],
        system_prompt=CONSIGNES_AVEC_MEMOIRE if outils else CONSIGNES,
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


def _message_exception(e: BaseException) -> str:
    if isinstance(e, CLINotFoundError):
        return ABSENT
    if isinstance(e, CLIConnectionError):
        return INJOIGNABLE
    return str(e) or type(e).__name__


class ClientClaude(Protocol):
    """Ce que le cerveau utilise de `ClaudeSDKClient` (une doublure le remplace en test)."""

    async def connect(self) -> None: ...
    async def query(self, prompt: str) -> None: ...
    def receive_response(self) -> AsyncIterator[Any]: ...
    async def interrupt(self) -> None: ...
    async def disconnect(self) -> None: ...


class CerveauClaude:
    def __init__(
        self,
        fabrique: Callable[[], ClientClaude],
        oubli_s: float = 30 * 60,
        horloge: Callable[[], float] = time.monotonic,
        maintenant: Callable[[], dt.datetime] = dt.datetime.now,
    ) -> None:
        self._fabrique = fabrique
        self._oubli_s = oubli_s
        self._horloge = horloge
        self._maintenant = maintenant
        self._verrou = asyncio.Lock()
        self._client: ClientClaude | None = None
        self._dernier_echange: float | None = None
        self._tour_ouvert = False  # une question est partie, son message de fin pas encore lu
        self._interrompu = False  # le tour en cours a été coupé par une autre question
        self._fil_perdu = False  # la conversation a été perdue : la réponse suivante le dit
        self._menage: asyncio.Task | None = None

    async def repondre(self, texte: str) -> AsyncIterator[str | Recherche]:
        if self._verrou.locked():
            # Une question à la fois : celle-ci, d'où qu'elle vienne, coupe celle en cours.
            await self._interrompre_le_tour()
        async with self._verrou:
            await self._attendre_le_menage()
            self._interrompu = False
            question = f"{ligne_de_date(self._maintenant())}\n{texte}"
            try:
                client = await self._poser(question)
                if self._fil_perdu:
                    self._fil_perdu = False
                    yield PHRASE_FIL_PERDU + " "
                async with contextlib.aclosing(self._lire_le_tour(client)) as fragments:
                    async for fragment in fragments:
                        yield fragment
            finally:
                self._dernier_echange = self._horloge()
                if self._tour_ouvert and self._client is not None:
                    # Réponse lâchée en route (ou coupée par une erreur) : le tour doit
                    # finir chez Claude avant la question suivante, sans retenir la session.
                    self._menage = asyncio.create_task(self._vider_le_tour(self._client))

    async def fermer(self) -> None:
        menage, self._menage = self._menage, None
        if menage is not None:
            with contextlib.suppress(Exception):
                await menage
        await self._jeter_le_client()

    # --- le client SDK -------------------------------------------------------

    async def _poser(self, question: str) -> ClientClaude:
        """Envoie la question ; un processus mort depuis la dernière est relancé."""
        try:
            client = await self._client_pret()
            try:
                await self._envoyer(client, question)
            except (ClaudeSDKError, OSError) as e:
                _journal.warning("Claude ne répond plus (%s) : on le relance", type(e).__name__)
                await self._jeter_le_client()
                self._fil_perdu = True
                client = await self._client_pret()
                await self._envoyer(client, question)
        except (ClaudeSDKError, OSError) as e:
            raise ErreurCerveau(_message_exception(e)) from e
        return client

    async def _envoyer(self, client: ClientClaude, question: str) -> None:
        # Ouvert avant l'envoi : une question annulée pendant l'écriture laisse peut-être
        # un tour en route chez Claude, que le ménage doit alors refermer.
        self._tour_ouvert = True
        try:
            await client.query(question)
        except Exception:
            self._tour_ouvert = False
            raise

    async def _client_pret(self) -> ClientClaude:
        dernier = self._dernier_echange
        if dernier is not None and self._horloge() - dernier >= self._oubli_s:
            # L'oubli est voulu : la conversation repart de zéro sans rien en dire.
            _journal.info("longtemps sans échange : nouvelle conversation")
            self._fil_perdu = False
            await self._jeter_le_client()
        if self._client is None:
            client = self._fabrique()
            try:
                await client.connect()
            except BaseException:
                with contextlib.suppress(Exception):
                    await client.disconnect()
                raise
            self._client = client
        return self._client

    async def _jeter_le_client(self) -> None:
        client, self._client = self._client, None
        self._tour_ouvert = False
        if client is not None:
            with contextlib.suppress(Exception):
                await client.disconnect()

    # --- un tour de conversation ---------------------------------------------

    async def _lire_le_tour(self, client: ClientClaude) -> AsyncIterator[str | Recherche]:
        recherches: set[str] = set()
        texte_rendu = False
        separer = False
        try:
            async with contextlib.aclosing(client.receive_response()) as messages:
                async for message in messages:
                    # Une question arrivée d'ailleurs a coupé ce tour (`_interrompu`) : on
                    # continue à lire jusqu'au message de fin, pour vider le tampon du SDK
                    # tout de suite, mais on ne rend plus rien — la réponse s'arrête là.
                    if isinstance(message, StreamEvent):
                        if message.parent_tool_use_id is not None:
                            continue  # un sous-agent : pas la réponse d'Atlas
                        evenement = message.event
                        if evenement.get("type") == "content_block_start":
                            bloc = evenement.get("content_block") or {}
                            if bloc.get("type") == "text":
                                # Deux blocs de texte (avant et après une recherche) : sans
                                # espace, « …vérifier.D'après… » ne se couperait jamais.
                                separer = texte_rendu
                            elif self._est_une_recherche(bloc, recherches) and not self._interrompu:
                                yield RECHERCHE
                        elif evenement.get("type") == "content_block_delta":
                            delta = evenement.get("delta") or {}
                            morceau = delta.get("text") if delta.get("type") == "text_delta" else ""
                            if morceau:
                                if separer:
                                    morceau, separer = " " + morceau, False
                                texte_rendu = True
                                if not self._interrompu:
                                    yield morceau
                    elif isinstance(message, AssistantMessage):
                        if message.error is not None:
                            raise ErreurCerveau(self._message_assistant(message))
                        for bloc in message.content:
                            if not isinstance(bloc, ToolUseBlock):
                                continue
                            desc = {"type": "tool_use", "name": bloc.name, "id": bloc.id}
                            if self._est_une_recherche(desc, recherches) and not self._interrompu:
                                yield RECHERCHE
                    elif isinstance(message, RateLimitEvent):
                        if message.rate_limit_info.status == "rejected":
                            raise ErreurCerveau(LIMITE)
                    elif isinstance(message, ResultMessage):
                        self._tour_ouvert = False
                        if message.is_error and not self._interrompu:
                            raise ErreurCerveau(self._message_resultat(message))
        except ErreurCerveau:
            raise
        except Exception as e:  # noqa: BLE001 — le SDK ne sait plus où il en est
            await self._perdre_le_fil(type(e).__name__)
            raise ErreurCerveau(_message_exception(e)) from e
        if self._tour_ouvert:
            # Le flux s'est tari sans message de fin : le processus Claude s'est arrêté.
            await self._perdre_le_fil("fin du flux")
            raise ErreurCerveau(ARRET)

    @staticmethod
    def _est_une_recherche(bloc: dict, deja_vues: set[str]) -> bool:
        """Un appel à la recherche web, signalé une seule fois (l'événement partiel et le
        message complet décrivent le même appel)."""
        if bloc.get("type") != "tool_use" or bloc.get("name") != OUTIL_RECHERCHE:
            return False
        identifiant = bloc.get("id") or ""
        if identifiant in deja_vues:
            return False
        deja_vues.add(identifiant)
        return True

    @staticmethod
    def _message_assistant(message: AssistantMessage) -> str:
        if message.error in _ERREURS_ASSISTANT:
            return _ERREURS_ASSISTANT[message.error]
        texte = " ".join(b.text for b in message.content if isinstance(b, TextBlock)).strip()
        return texte or f"Claude a signalé une erreur ({message.error})."

    @staticmethod
    def _message_resultat(message: ResultMessage) -> str:
        statut = message.api_error_status
        if statut == 429:
            return LIMITE
        if statut in (401, 403):
            return DECONNECTE
        if statut is not None and statut >= 500:
            return INJOIGNABLE
        if message.errors:
            return " ; ".join(message.errors)
        return message.result or f"Claude n'a pas pu répondre ({message.subtype})."

    async def _perdre_le_fil(self, cause: str) -> None:
        """La conversation est perdue : Claude sera relancé à la question suivante, qui
        commencera par le dire."""
        _journal.warning("conversation avec Claude perdue (%s)", cause)
        await self._jeter_le_client()
        self._fil_perdu = True

    # --- l'interruption --------------------------------------------------------

    async def _interrompre_le_tour(self) -> None:
        """Une autre question arrive : la réponse en cours se termine, sans erreur."""
        client = self._client
        if client is None or not self._tour_ouvert:
            return
        self._interrompu = True
        try:
            await client.interrupt()
        except Exception as e:  # noqa: BLE001 — au pire, la nouvelle question attend la fin
            _journal.warning("interruption de Claude impossible (%s)", type(e).__name__)

    async def _vider_le_tour(self, client: ClientClaude) -> None:
        """Interrompt le tour abandonné et consomme ses derniers messages jusqu'au message
        de fin : la question suivante part d'un état propre. Si Claude ne finit pas le
        tour à temps, la conversation est perdue : on repartira de zéro."""
        try:
            async with asyncio.timeout(DELAI_MENAGE_S):
                # Le SDK ne garde que 100 messages en attente : lire pendant qu'on
                # interrompt, sinon la réponse à l'interruption reste coincée derrière
                # les événements déjà en file, et le ménage n'aboutit jamais.
                interruption = asyncio.create_task(client.interrupt())
                try:
                    async with contextlib.aclosing(client.receive_response()) as reste:
                        async for _message in reste:
                            pass
                finally:
                    # Toujours reprendre la main sur cette tâche : si le vidage s'arrête en
                    # cours de route (erreur, minuterie), l'interruption ne finira peut-être
                    # jamais toute seule (plus personne ne lit) ; on la coupe alors, pour ne
                    # laisser ni tâche oubliée ni exception jamais récupérée.
                    if not interruption.done():
                        interruption.cancel()
                    with contextlib.suppress(BaseException):
                        await interruption
            self._tour_ouvert = False
        except Exception as e:  # noqa: BLE001 — TimeoutError compris
            await self._perdre_le_fil(f"tour interrompu mal refermé : {type(e).__name__}")

    async def _attendre_le_menage(self) -> None:
        menage = self._menage
        if menage is None:
            return
        # Protégé : une question elle-même annulée ne doit pas annuler le ménage.
        await asyncio.shield(menage)
        if self._menage is menage:
            self._menage = None

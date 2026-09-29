"""L'entretien du Core depuis la page (spec des réglages et du Core, §5 et §6) : la version
qui tourne, le redémarrage, et la mise à jour (`git pull` en avance rapide, `make install`).

Le Core redémarre en s'arrêtant proprement, comme à un Ctrl-C, après avoir laissé la marque
`donnees/redemarrer` : `make run-core` le relance alors par un `make` neuf, qui relit le .env.
Aucun texte venu d'une page n'entre dans une commande : `git` et `make` sont lancés avec des
arguments fixes, dans le dépôt du Core, avec des délais fixes.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel

from .protocole_web import CoreEnCours, EtatCore, FinCore

_journal = logging.getLogger(__name__)

DEPOT = Path(__file__).resolve().parents[2]
BRANCHE = "main"
INSTALLER = ("make", "install")
DELAI_GIT_S = 120.0
DELAI_INSTALLATION_S = 600.0
DELAI_ARRET_S = 0.5  # le temps que « Redémarrage du Core… » parte vers les pages
NOUVEAUTES_MAX = 5
LIGNES_MAX = 10  # les dernières lignes d'une erreur, montrées dans la page
LIGNE_MAX = 200

REDEMARRAGE = "Redémarrage du Core…"
RECUPERATION = "Récupération de la dernière version…"
INSTALLATION = "Installation…"
DEJA_A_JOUR = "Atlas est déjà à jour."
OCCUPE = "Un redémarrage ou une mise à jour est déjà en cours."
ECHEC_RECUPERATION = "La récupération a échoué : rien n'a changé."
ECHEC_INSTALLATION = (
    "L'installation a échoué : relance make install au Terminal avant de redémarrer."
)
TROP_LONGUE = "Arrêtée : elle a dépassé son délai."
AU_TERMINAL = " : mets-le à jour au Terminal."


def marque(depot: Path) -> Path:
    """Laissée par un Core qui demande à `make run-core` de le relancer."""
    return depot / "donnees" / "redemarrer"


def arreter_le_core() -> None:
    """Comme un Ctrl-C : uvicorn s'arrête proprement (la conversation se clôt, avec son
    résumé au journal ; une mission s'arrête ; une confirmation est abandonnée)."""
    os.kill(os.getpid(), signal.SIGTERM)


@dataclass
class _Sortie:
    code: int  # -1 : arrêtée, trop longue
    lignes: list[str]


class Entretien:
    """`publier` envoie un message à toutes les pages ; `arreter`, par défaut
    `arreter_le_core`, arrête le Core une fois la marque laissée."""

    def __init__(
        self,
        publier: Callable[[BaseModel], None],
        depot: Path | None = None,
        *,
        installer: Sequence[str] = INSTALLER,
        delais: tuple[float, float] = (DELAI_GIT_S, DELAI_INSTALLATION_S),
        arreter: Callable[[], None] | None = None,
    ) -> None:
        self._publier = publier
        self.depot = DEPOT if depot is None else depot
        self._installer = list(installer)
        self._delai_git, self._delai_installation = delais
        self._arreter = arreter
        self.occupe = False
        self.tache: asyncio.Task[None] | None = None  # la mise à jour en cours

    def effacer_la_marque(self) -> None:
        """Au démarrage : une marque restée là (un Core tué juste après) ne relance rien."""
        try:
            marque(self.depot).unlink(missing_ok=True)
        except OSError as e:
            _journal.warning("marque de redémarrage non effacée : %s", e)

    async def etat(self) -> EtatCore:
        sortie = await self._lancer(["git", "log", "-1", "--format=%h %cs"], self._delai_git)
        version, _, date = (
            sortie.lignes[0] if sortie.code == 0 and sortie.lignes else ""
        ).partition(" ")
        raison = OCCUPE if self.occupe else await self._raison_du_depot()
        return EtatCore(
            version=version or "inconnue",
            date=date,
            occupe=self.occupe,
            mise_a_jour_possible=raison is None,
            raison=raison or "",
        )

    async def _raison_du_depot(self) -> str | None:
        """Pourquoi le dépôt ne se met pas à jour depuis la page ; None s'il le peut."""
        branche = await self._lancer(["git", "symbolic-ref", "--short", "HEAD"], self._delai_git)
        if branche.code != 0 or not branche.lignes:
            return "Le dépôt du Core n'est sur aucune branche" + AU_TERMINAL
        if branche.lignes[0] != BRANCHE:
            nom = branche.lignes[0]
            return f"Le dépôt du Core est sur la branche {nom}, pas sur {BRANCHE}" + AU_TERMINAL
        suivis = ["git", "status", "--porcelain", "--untracked-files=no"]
        modifies = await self._lancer(suivis, self._delai_git)
        if modifies.lignes:  # git écrit aussi ici son erreur, s'il n'a pas pu lire
            return "Le dépôt du Core a des modifications" + AU_TERMINAL
        return None

    # --- le redémarrage ----------------------------------------------------------------

    def demander_redemarrage(self) -> FinCore | None:
        """Le bouton « Redémarrer » : un refus pour la page qui l'a demandé, ou None."""
        if self.occupe:
            return FinCore(ok=False, texte=OCCUPE)
        self.occupe = True
        self._redemarrer([])
        return None

    def _redemarrer(self, nouveautes: list[str]) -> None:
        self._publier(CoreEnCours(etape="redemarrage", texte=REDEMARRAGE, nouveautes=nouveautes))
        try:
            marque(self.depot).parent.mkdir(parents=True, exist_ok=True)
            marque(self.depot).touch()
        except OSError as e:
            self.occupe = False
            texte = (
                f"Le Core ne peut pas redémarrer ({e.strerror or e}) : redémarre-le au Terminal."
            )
            self._publier(FinCore(ok=False, texte=texte))
            return
        _journal.info("redémarrage demandé depuis la page")
        arreter = self._arreter or arreter_le_core
        asyncio.get_running_loop().call_later(DELAI_ARRET_S, arreter)

    # --- la mise à jour ----------------------------------------------------------------

    async def demander_mise_a_jour(self) -> FinCore | None:
        """Le bouton « Mettre à jour et redémarrer » : un refus pour la page qui l'a demandé,
        ou None, la mise à jour partie en arrière-plan (Atlas continue de répondre)."""
        if self.occupe:
            return FinCore(ok=False, texte=OCCUPE)
        self.occupe = True
        raison = await self._raison_du_depot()
        if raison is not None:
            self.occupe = False
            return FinCore(ok=False, texte=raison)
        self.tache = asyncio.create_task(self._mettre_a_jour())
        return None

    async def _mettre_a_jour(self) -> None:
        redemarre = False
        try:
            self._publier(CoreEnCours(etape="recuperation", texte=RECUPERATION))
            avant = await self._tete()
            tire = await self._lancer(["git", "pull", "--ff-only"], self._delai_git)
            if tire.code != 0:
                self._publier(FinCore(ok=False, texte=ECHEC_RECUPERATION, details=_fin(tire)))
                return
            apres = await self._tete()
            if apres == avant:
                self._publier(FinCore(ok=True, texte=DEJA_A_JOUR))
                return
            titres = await self._lancer(
                ["git", "log", "--format=%s", f"{avant}..{apres}"], self._delai_git
            )
            nouveautes = _resumer(titres.lignes)
            self._publier(
                CoreEnCours(etape="installation", texte=INSTALLATION, nouveautes=nouveautes)
            )
            installe = await self._lancer(self._installer, self._delai_installation)
            if installe.code != 0:
                details = _fin(installe)
                self._publier(FinCore(ok=False, texte=ECHEC_INSTALLATION, details=details))
                return
            redemarre = True
            self._redemarrer(nouveautes)
        finally:
            if not redemarre:
                self.occupe = False

    async def _tete(self) -> str:
        sortie = await self._lancer(["git", "rev-parse", "HEAD"], self._delai_git)
        return sortie.lignes[0] if sortie.code == 0 and sortie.lignes else ""

    async def _lancer(self, commande: list[str], delai: float) -> _Sortie:
        """Lance une commande dans le dépôt, dans son propre groupe de processus : trop
        longue, ou le Core qui s'arrête, et tout le groupe est tué (make et ce qu'il lance)."""
        environ = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}  # jamais une question
        try:
            processus = await asyncio.create_subprocess_exec(
                *commande,
                cwd=self.depot,
                env=environ,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                start_new_session=True,
            )
        except OSError as e:
            return _Sortie(127, [f"{commande[0]} : {e.strerror or e}"])
        try:
            sortie, _ = await asyncio.wait_for(processus.communicate(), delai)
        except TimeoutError:
            await _tuer(processus)
            return _Sortie(-1, [TROP_LONGUE])
        except asyncio.CancelledError:
            await _tuer(processus)
            raise
        lignes = sortie.decode(errors="replace").splitlines()
        for ligne in lignes:
            _journal.info("%s : %s", commande[0], ligne)
        return _Sortie(processus.returncode or 0, lignes)

    async def fermer(self) -> None:
        """L'arrêt du Core : une mise à jour en cours s'arrête, sa commande comprise."""
        if self.tache is not None:
            self.tache.cancel()
            await asyncio.wait([self.tache])  # sans avaler l'annulation de l'arrêt lui-même


async def _tuer(processus: asyncio.subprocess.Process) -> None:
    try:
        os.killpg(processus.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    await processus.wait()


def _resumer(titres: list[str]) -> list[str]:
    """Les titres des nouveaux commits, les plus récents d'abord, cinq au plus."""
    if len(titres) <= NOUVEAUTES_MAX:
        return titres
    return [*titres[:NOUVEAUTES_MAX], f"et {len(titres) - NOUVEAUTES_MAX} autres"]


def _fin(sortie: _Sortie) -> list[str]:
    return [ligne[:LIGNE_MAX] for ligne in sortie.lignes[-LIGNES_MAX:]]

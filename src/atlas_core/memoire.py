"""La mémoire d'Atlas : un dépôt git local de fichiers Markdown.

Des fiches — le profil de David, l'entreprise, les projets, les personnes — qu'Atlas tient
de lui-même, et un journal que le Core écrit seul. Tout passe par ici : chaque écriture est
vérifiée (chemin, format, secrets), puis commitée sous l'auteur « Atlas ». Le dépôt n'a
aucun distant et n'est jamais poussé : rien ne quitte la machine.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import threading
from collections.abc import Iterable
from pathlib import Path

_journal = logging.getLogger(__name__)

GIT = "git"
AUTEUR_NOM = "Atlas"
AUTEUR_COURRIEL = "atlas@atlas.local"

DOSSIERS_FICHES = ("entreprise", "projets", "personnes")
_NOM = r"[a-z0-9]+(?:-[a-z0-9]+)*"
_FICHE = re.compile(rf"(?:profil|(?:{'|'.join(DOSSIERS_FICHES)})/(?P<nom>{_NOM}))\.md")
_JOURNAL = re.compile(r"journal/\d{4}-\d{2}-\d{2}\.md")
NOM_MAX = 60
TITRE_MAX = 100
RESUME_MAX = 200
FICHE_MAX = 20_000
# Ce qui ressemble à un secret n'entre jamais dans la mémoire (spec parente §13).
_SECRETS = [
    re.compile(motif)
    for motif in (
        r"\bsk-(?:ant-)?[A-Za-z0-9_-]{16,}",
        r"\bgh[pousr]_[A-Za-z0-9]{20,}",
        r"\bgithub_pat_[A-Za-z0-9_]{20,}",
        r"\bAKIA[0-9A-Z]{16}\b",
        r"\bxox[abprs]-[A-Za-z0-9-]{10,}",
        r"\bAIza[0-9A-Za-z_-]{35}",
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
        r"(?i)\b(?:mot de passe|mdp|password|passwd)\b\s*(?::|=|est\b)\s*\S+",
    )
]
SECRET_MIN = 8  # une clé du Core plus courte ne se cherche pas : trop de faux refus


class ErreurMemoire(Exception):
    """L'écriture ou la lecture est refusée. Le message, en français, va à Claude."""


def _git(racine: Path, *arguments: str) -> str:
    """Lance git dans le dépôt, sans dépendre de la configuration git de la machine."""
    commande = [
        GIT,
        "-C",
        str(racine),
        "-c",
        "commit.gpgsign=false",
        # Les crochets git de la machine (vérifications, messages imposés) ne concernent pas
        # la mémoire d'Atlas : ils pourraient bloquer chacune de ses notes.
        "-c",
        "core.hooksPath=/dev/null",
        *arguments,
    ]
    # L'auteur par l'environnement, qui passe avant toute configuration : une identité
    # imposée à la machine ferait sinon signer les notes par un autre, et « annule » ne
    # les retrouverait plus.
    identite = {
        "GIT_AUTHOR_NAME": AUTEUR_NOM,
        "GIT_AUTHOR_EMAIL": AUTEUR_COURRIEL,
        "GIT_COMMITTER_NAME": AUTEUR_NOM,
        "GIT_COMMITTER_EMAIL": AUTEUR_COURRIEL,
    }
    environnement = {**os.environ, **identite}
    return subprocess.run(
        commande, capture_output=True, text=True, check=True, env=environnement
    ).stdout


def _lire_texte(fichier: Path) -> str:
    """Un fichier retouché à la main dans un autre encodage se lit quand même : ses octets
    illisibles deviennent « � » au lieu de tout faire échouer."""
    return fichier.read_text(encoding="utf-8", errors="replace")


def verifier_fiche(contenu: str) -> str:
    """Une fiche : « # Titre », une ligne vide, une phrase de résumé, puis le reste.
    Rend le titre."""
    if len(contenu) > FICHE_MAX:
        raise ErreurMemoire(f"Une fiche fait au plus {FICHE_MAX} caractères.")
    lignes = contenu.split("\n")
    forme = (
        len(lignes) >= 3
        and lignes[0].startswith("# ")
        and not lignes[1].strip()
        and lignes[2].strip()
        and not lignes[2].startswith("#")
    )
    if not forme:
        raise ErreurMemoire(
            "Une fiche commence par « # Titre », une ligne vide, puis une phrase de résumé."
        )
    titre = lignes[0][2:].strip()
    if not titre or len(titre) > TITRE_MAX:
        raise ErreurMemoire(f"Le titre d'une fiche fait de 1 à {TITRE_MAX} caractères.")
    if len(lignes[2].strip()) > RESUME_MAX:
        raise ErreurMemoire(f"La phrase de résumé fait au plus {RESUME_MAX} caractères.")
    return titre


class Memoire:
    def __init__(self, racine: Path, secrets: Iterable[str] = ()) -> None:
        self.racine = racine
        self._secrets = [s for s in secrets if len(s) >= SECRET_MIN]
        self._verrou = threading.Lock()  # une écriture à la fois

    @classmethod
    def ouvrir(cls, racine: Path, secrets: Iterable[str] = ()) -> Memoire | None:
        """Crée le dossier et son dépôt au besoin. None si c'est impossible (git absent,
        dossier interdit) : Atlas marche alors sans mémoire, comme en phase 2a."""
        try:
            racine.mkdir(parents=True, exist_ok=True)
            if not (racine / ".git").exists():
                _git(racine, "init", "-q")
            verrou_git = racine / ".git" / "index.lock"
            if verrou_git.exists():
                # Laissé par un Core tué en plein commit : sans ce ménage, plus aucune note
                # ne s'écrirait jamais.
                _journal.warning("verrou git laissé par un arrêt brutal : retiré")
                verrou_git.unlink()
        except (OSError, subprocess.CalledProcessError) as e:
            _journal.warning("mémoire indisponible (%s) : Atlas marche sans elle", e)
            return None
        return cls(racine, secrets)

    def _cible(self, chemin: str, ecriture: bool) -> Path:
        """Le fichier désigné, s'il est permis ; sinon `ErreurMemoire`."""
        fiche = _FICHE.fullmatch(chemin)
        if not (fiche or (not ecriture and _JOURNAL.fullmatch(chemin))):
            raise ErreurMemoire(
                f"« {chemin} » n'est pas une fiche : profil.md, ou entreprise/, projets/ ou "
                "personnes/ suivi d'un nom en minuscules, chiffres et tirets, en .md."
            )
        if fiche and fiche["nom"] and len(fiche["nom"]) > NOM_MAX:
            raise ErreurMemoire(f"Un nom de fiche fait au plus {NOM_MAX} caractères.")
        cible = (self.racine / chemin).resolve()
        if not cible.is_relative_to(self.racine.resolve()):
            raise ErreurMemoire(f"« {chemin} » sort de la mémoire.")
        return cible

    def _assurer_le_depot(self) -> None:
        """Le dossier a pu être supprimé pendant que le Core tournait : il renaît vide."""
        if not (self.racine / ".git").exists():
            _journal.warning("dépôt de la mémoire disparu : recréé")
            self.racine.mkdir(parents=True, exist_ok=True)
            _git(self.racine, "init", "-q")

    def verifier_secrets(self, texte: str) -> None:
        if any(motif.search(texte) for motif in _SECRETS) or any(
            secret in texte for secret in self._secrets
        ):
            raise ErreurMemoire(
                "Refusé : le texte contient ce qui ressemble à un mot de passe ou à une clé "
                "secrète. Rien n'a été écrit."
            )

    def lire(self, chemin: str) -> str:
        cible = self._cible(chemin, ecriture=False)
        if not cible.is_file():
            raise ErreurMemoire(f"{chemin} n'existe pas.")
        return _lire_texte(cible)

    def ecrire(self, chemin: str, contenu: str) -> str | None:
        """Crée ou remplace une fiche entière, puis la commite. Rend son titre, ou None si
        elle était déjà ainsi (rien à commiter, rien à annoncer)."""
        cible = self._cible(chemin, ecriture=True)
        contenu = contenu.strip("\n") + "\n"
        titre = verifier_fiche(contenu)
        self.verifier_secrets(contenu)
        with self._verrou:
            self._assurer_le_depot()
            if cible.is_file() and _lire_texte(cible) == contenu:
                return None
            cible.parent.mkdir(parents=True, exist_ok=True)
            cible.write_text(contenu, encoding="utf-8")
            # Le seul fichier écrit : les retouches de David ailleurs restent les siennes.
            _git(self.racine, "add", "--", chemin)
            _git(self.racine, "commit", "-q", "-m", f"Atlas : {titre}", "--", chemin)
        return titre

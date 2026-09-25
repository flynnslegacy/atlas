"""La mémoire d'Atlas : un dépôt git local de fichiers Markdown.

Des fiches — le profil de David, l'entreprise, les projets, les personnes — qu'Atlas tient
de lui-même, et un journal que le Core écrit seul. Tout passe par ici : chaque écriture est
vérifiée (chemin, format, secrets), puis commitée sous l'auteur « Atlas ». Le dépôt n'a
aucun distant et n'est jamais poussé : rien ne quitte la machine.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import logging
import os
import re
import subprocess
import threading
import unicodedata
from collections.abc import Iterable
from pathlib import Path

from .consignes import date_en_lettres, heure_en_chiffres

_journal = logging.getLogger(__name__)

GIT = "git"
AUTEUR_NOM = "Atlas"
AUTEUR_COURRIEL = "atlas@atlas.local"
# Les variables par lesquelles git désigne un autre dépôt, un autre index ou d'autres
# réglages (`git rev-parse --local-env-vars`) : héritées de l'environnement (le Core lancé
# depuis un crochet git, par exemple), elles détourneraient les notes ailleurs.
_VARIABLES_LOCALES_GIT = frozenset(
    {
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_CONFIG",
        "GIT_CONFIG_PARAMETERS",
        "GIT_CONFIG_COUNT",
        "GIT_OBJECT_DIRECTORY",
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_IMPLICIT_WORK_TREE",
        "GIT_GRAFT_FILE",
        "GIT_INDEX_FILE",
        "GIT_NO_REPLACE_OBJECTS",
        "GIT_REPLACE_REF_BASE",
        "GIT_PREFIX",
        "GIT_SHALLOW_FILE",
        "GIT_COMMON_DIR",
    }
)

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
        # « Mot de passe Gmail : … », « le mot de passe du wifi est … », « code PIN = … » :
        # un court qualificatif peut séparer le mot-clé de sa valeur.
        r"(?i)\b(?:mot de passe|mdp|password|passwd|code (?:pin|wi-?fi|secret))\b"
        r"[^\n:=.]{0,30}?(?::|=|\best\b)\s*\S+",
    )
]
SECRET_MIN = 8  # une clé du Core plus courte ne se cherche pas : trop de faux refus
RESULTATS_MAX = 20
PREFIXE_NOTE = "Atlas : "
PREFIXE_ANNULE = "Annulé : "
PREFIXE_JOURNAL = "Journal : "
# L'amorçage d'une conversation reste court, même quand la mémoire grossit.
PROFIL_MAX = 4_000
SOMMAIRE_MAX = 150
JOURNAL_MAX = 6_000
JOURS_DE_JOURNAL = 7


class ErreurMemoire(Exception):
    """L'écriture ou la lecture est refusée. Le message, en français, va à Claude."""


def _git(racine: Path, *arguments: str, entree: str | None = None) -> str:
    """Lance git dans le dépôt, sans dépendre de la configuration git de la machine ;
    `entree` est passée sur son entrée standard."""
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
    heritees = {k: v for k, v in os.environ.items() if k not in _VARIABLES_LOCALES_GIT}
    environnement = {**heritees, **identite}
    return subprocess.run(
        commande, input=entree, capture_output=True, text=True, check=True, env=environnement
    ).stdout


def _lire_texte(fichier: Path) -> str:
    """Un fichier retouché à la main dans un autre encodage se lit quand même : ses octets
    illisibles deviennent « � » au lieu de tout faire échouer."""
    return fichier.read_text(encoding="utf-8", errors="replace")


def _plier(texte: str) -> str:
    """Sans majuscules ni accents : « Élise » se trouve en cherchant « elise »."""
    decompose = unicodedata.normalize("NFD", texte.casefold())
    return "".join(c for c in decompose if not unicodedata.combining(c))


def _tronquer(texte: str, taille: int) -> str:
    return texte if len(texte) <= taille else texte[:taille].rstrip() + " […]"


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
            _git(self.racine, "commit", "-q", "-m", f"{PREFIXE_NOTE}{titre}", "--", chemin)
        return titre

    def _fichiers(self, avec_journal: bool) -> list[str]:
        """Les fiches (le profil, puis chaque dossier par ordre alphabétique), puis le
        journal du plus récent au plus ancien ; seulement ce qui est permis."""
        candidats = ["profil.md"]
        for dossier in DOSSIERS_FICHES:
            noms = (p.name for p in (self.racine / dossier).glob("*.md"))
            candidats += sorted(f"{dossier}/{nom}" for nom in noms)
        if avec_journal:
            noms = (p.name for p in (self.racine / "journal").glob("*.md"))
            candidats += sorted((f"journal/{nom}" for nom in noms), reverse=True)
        permis = []
        for chemin in candidats:
            with contextlib.suppress(ErreurMemoire):
                if self._cible(chemin, ecriture=False).is_file():
                    permis.append(chemin)
        return permis

    def chercher(self, texte: str) -> list[str]:
        """Les lignes qui contiennent le texte, chacune précédée de son fichier : les fiches
        d'abord, puis le journal du plus récent au plus ancien. Vingt au plus."""
        cle = _plier(texte.strip())
        if not cle:
            raise ErreurMemoire("Rien à chercher.")
        trouvees: list[str] = []
        for chemin in self._fichiers(avec_journal=True):
            for ligne in _lire_texte(self.racine / chemin).splitlines():
                if cle in _plier(ligne):
                    trouvees.append(f"{chemin} : {ligne.strip()}")
                    if len(trouvees) == RESULTATS_MAX:
                        return trouvees
        return trouvees

    def annuler(self) -> str:
        """Défait la dernière écriture d'Atlas encore en place (`git revert`) ; rend son
        titre. Ni le journal, ni les commits de David ne s'annulent."""
        with self._verrou:
            try:
                historique = _git(self.racine, "log", "--format=%H%x1f%ae%x1f%s%x1f%b%x1e")
            except subprocess.CalledProcessError:
                historique = ""  # aucun commit encore
            annulees: set[str] = set()
            for entree in historique.split("\x1e"):
                if not entree.strip():
                    continue
                sha, courriel, sujet, corps = entree.strip("\n").split("\x1f", 3)
                if courriel != AUTEUR_COURRIEL:
                    continue
                if sujet.startswith(PREFIXE_ANNULE):
                    annulees.update(re.findall(r"Annule ([0-9a-f]{40})", corps))
                elif sujet.startswith(PREFIXE_NOTE) and sha not in annulees:
                    return self._defaire(sha, sujet.removeprefix(PREFIXE_NOTE))
        raise ErreurMemoire("Il n'y a plus de note à retirer.")

    def _defaire(self, sha: str, titre: str) -> str:
        """Applique l'inverse de la note, tout ou rien, sur ses seuls fichiers : le travail
        de David, préparé ou non, n'est jamais touché."""
        chemins = _git(self.racine, "show", "--name-only", "--format=", sha).split()
        refus = ErreurMemoire("Je ne peux pas retirer cette note : la fiche a été modifiée depuis.")
        if _git(self.racine, "status", "--porcelain", "--", *chemins).strip():
            raise refus  # une retouche de David sur la fiche, même pas encore commitée
        inverse = _git(self.racine, "show", "--format=", "--patch", "-R", sha, "--", *chemins)
        try:
            _git(self.racine, "apply", "--check", "--index", entree=inverse)
        except subprocess.CalledProcessError:
            raise refus from None  # la fiche a changé depuis la note : rien n'est touché
        _git(self.racine, "apply", "--index", entree=inverse)
        message = f"{PREFIXE_ANNULE}{titre}\n\nAnnule {sha}"
        _git(self.racine, "commit", "-q", "-m", message, "--", *chemins)
        return titre

    # --- l'amorçage et le journal -----------------------------------------------------

    def sommaire(self) -> list[str]:
        """Une ligne par fiche hors profil : son chemin et sa phrase de résumé (son titre,
        si la fiche a été retouchée à la main hors du format)."""
        lignes = []
        for chemin in self._fichiers(avec_journal=False):
            if chemin == "profil.md":
                continue
            debut = _lire_texte(self.racine / chemin).split("\n", 3)
            au_format = len(debut) > 2 and not debut[1].strip() and debut[2].strip()
            if au_format and not debut[2].startswith("#"):
                resume = debut[2].strip()
            else:
                resume = debut[0].lstrip("#").strip()
            lignes.append(f"- {chemin} : {resume}")
        return lignes

    def amorcage(self, aujourd_hui: dt.date) -> str:
        """Le bloc qui précède la première question d'une conversation : le profil, le
        sommaire des fiches et le journal des derniers jours, chacun plafonné."""
        profil = ""
        with contextlib.suppress(ErreurMemoire):
            profil = self.lire("profil.md").strip()
        fiches = self.sommaire()
        journal = self._journal_recent(aujourd_hui)
        if not (profil or fiches or journal):
            corps = "La mémoire est vide."
        else:
            if len(fiches) > SOMMAIRE_MAX:
                reste = len(fiches) - SOMMAIRE_MAX
                fiches = [*fiches[:SOMMAIRE_MAX], f"- … et {reste} autres fiches."]
            corps = "\n\n".join(
                [
                    "Profil :\n" + (_tronquer(profil, PROFIL_MAX) or "pas encore de profil."),
                    "Fiches :\n" + ("\n".join(fiches) or "aucune."),
                    "Journal des sept derniers jours :\n" + (journal or "rien."),
                ]
            )
        return f"[Mémoire d'Atlas]\n{corps}\n[Fin de la mémoire]"

    def _journal_recent(self, aujourd_hui: dt.date) -> str:
        """Les derniers jours du journal, du plus ancien au plus récent ; les plus récents
        sont gardés en priorité quand le plafond est atteint."""
        jours = []
        for ecart in range(JOURS_DE_JOURNAL):
            chemin = f"journal/{aujourd_hui - dt.timedelta(days=ecart):%Y-%m-%d}.md"
            with contextlib.suppress(ErreurMemoire):
                jours.append(self.lire(chemin).strip())
        gardes: list[str] = []
        taille = 0
        for texte in jours:  # du plus récent au plus ancien
            if taille + len(texte) > JOURNAL_MAX:
                if not gardes:
                    gardes.append("[…] " + texte[-JOURNAL_MAX:])
                break
            gardes.append(texte)
            taille += len(texte)
        return "\n\n".join(reversed(gardes))

    def ajouter_au_journal(self, debut: dt.datetime, fin: dt.datetime, resume: str) -> None:
        """Ajoute le résumé d'une conversation au journal du jour où elle s'est terminée,
        puis le commite, en silence. Un résumé qui contient un secret est refusé."""
        self.verifier_secrets(resume)
        chemin = f"journal/{fin:%Y-%m-%d}.md"
        cible = self._cible(chemin, ecriture=False)
        with self._verrou:
            self._assurer_le_depot()
            cible.parent.mkdir(parents=True, exist_ok=True)
            entete = "" if cible.exists() else f"# Journal du {date_en_lettres(fin)}\n"
            heures = f"{heure_en_chiffres(debut)} – {heure_en_chiffres(fin)}"
            with cible.open("a", encoding="utf-8") as fichier:
                fichier.write(f"{entete}\n## {heures}\n\n{resume.strip()}\n")
            _git(self.racine, "add", "--", chemin)
            message = f"{PREFIXE_JOURNAL}{date_en_lettres(fin)}, {heure_en_chiffres(fin)}"
            _git(self.racine, "commit", "-q", "-m", message, "--", chemin)

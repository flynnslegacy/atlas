"""Les réglages des connecteurs, écrits dans le .env du Core depuis la page (spec des réglages
et du Core, §4).

Le .env est lu par `make` (`-include .env`, puis `export`) : une valeur y est écrite pour que
`make` la relise à l'identique. Seules s'y écrivent les variables déclarées par le connecteur,
jamais une clé d'Atlas, quoi que dise son manifeste ; le reste du fichier ne bouge pas.
"""

from __future__ import annotations

import os
import re
import unicodedata
from collections.abc import Iterable, Mapping
from pathlib import Path

from .connecteurs import Manifeste

DEPOT = Path(__file__).resolve().parents[2]
FICHIER_ENV = DEPOT / ".env"  # celui que lit `make run-core` ; les tests le remplacent
VALEUR_MAX = 4096

# Les variables qu'Atlas lit lui-même (le Core, le client audio, le poste), et le jeton de
# Claude : jamais écrites depuis la page. Un test la compare au code.
CLES_D_ATLAS = frozenset(
    {
        "CLAUDE_CODE_OAUTH_TOKEN",
        "ATLAS_AEC_BINAIRE",
        "ATLAS_AUDIO_CLE",
        "ATLAS_AUDIO_PERIPHERIQUE",
        "ATLAS_BARGEIN_DBFS",
        "ATLAS_BARGEIN_MS",
        "ATLAS_CERVEAU",
        "ATLAS_CERVEAU_MODELE",
        "ATLAS_CERVEAU_OUBLI_MIN",
        "ATLAS_CONNECTEURS_DOSSIER",
        "ATLAS_CORE_PORT",
        "ATLAS_CORE_URL",
        "ATLAS_MEMOIRE_DOSSIER",
        "ATLAS_MISSION_MIN",
        "ATLAS_MOT_REVEIL",
        "ATLAS_POSTE_CLE",
        "ATLAS_POSTE_URL",
        "ATLAS_RELANCE_S",
        "ATLAS_REVEILLEUR",
        "ATLAS_REVEIL_SEUIL",
        "ATLAS_SILENCE_MS",
        "ATLAS_STT_URL",
        "ATLAS_TTS_URL",
        "ATLAS_TTS_VOIX",
        "ATLAS_VAD_MODELE",
        "ATLAS_VOIX_BARGEIN_DBFS",
        "ATLAS_VOIX_MARGE_S",
        "ATLAS_WEB_CLE",
    }
)
# Une affectation de la variable, telle que `make` la lit (`=`, `:=`, `::=`, `?=`, `+=`).
_AFFECTATION = r"^\s*(?:export\s+)?{}\s*(?::{{1,2}}|\?|\+)?="


class ReglageRefuse(ValueError):
    """Un réglage que le Core n'écrit pas : la raison se lit telle quelle dans la page."""


def secretes(manifestes: Iterable[Manifeste | None]) -> set[str]:
    """Les variables qu'au moins un manifeste déclare secrètes : secrètes pour tous les
    connecteurs qui les déclarent (deux connecteurs iCloud qui partagent un mot de passe)."""
    return {r.variable for m in manifestes if m is not None for r in m.reglages if r.secret}


def modifiable(variable: str) -> bool:
    """Faux pour une clé d'Atlas : elle se change au Terminal."""
    return variable not in CLES_D_ATLAS


def changements_permis(
    manifeste: Manifeste, valeurs: Mapping[str, str], effacer: Iterable[str]
) -> dict[str, str | None]:
    """Ce que la page demande pour ce connecteur, vérifié : variable → valeur à écrire, ou
    None pour la retirer. `ReglageRefuse` au moindre écart : rien ne s'écrit alors."""
    effacer = list(effacer)
    declarees = {r.variable for r in manifeste.reglages}
    for variable in [*valeurs, *effacer]:
        if variable not in declarees:
            raise ReglageRefuse(f"{variable} n'est pas un réglage de ce connecteur.")
        if not modifiable(variable):
            raise ReglageRefuse(f"{variable} est une clé d'Atlas : elle se change au Terminal.")
    changements: dict[str, str | None] = {}
    for variable, valeur in valeurs.items():
        _verifier(variable, valeur)
        changements[variable] = valeur
    for variable in effacer:
        if variable in changements:
            raise ReglageRefuse(f"{variable} : à la fois écrit et effacé.")
        changements[variable] = None
    return changements


def _verifier(variable: str, valeur: str) -> None:
    if not valeur:
        raise ReglageRefuse(f"{variable} : une valeur vide ; « Effacer » le retire.")
    if len(valeur) > VALEUR_MAX:
        raise ReglageRefuse(f"{variable} : {VALEUR_MAX} caractères au plus.")
    # Un caractère de contrôle (C0, C1) ou un séparateur de ligne Unicode : à la relecture, le
    # .env pourrait se couper en deux lignes, et la seconde devenir une variable.
    if any(unicodedata.category(c) in ("Cc", "Zl", "Zp") for c in valeur):
        raise ReglageRefuse(f"{variable} : une seule ligne, sans caractère de contrôle.")
    if valeur != valeur.strip():
        raise ReglageRefuse(f"{variable} : pas d'espace au début ni à la fin.")
    if valeur.endswith("\\"):
        # `make` y verrait une ligne qui continue sur la suivante.
        raise ReglageRefuse(f"{variable} : ne peut pas finir par une barre oblique inverse.")


def pour_make(valeur: str) -> str:
    """La valeur telle que `make` la relira à l'identique : `$` doublé, `#` protégé, et les
    barres obliques inverses qui le précèdent doublées."""
    valeur = valeur.replace("$", "$$")
    return re.sub(r"(\\*)#", lambda m: m.group(1) * 2 + "\\#", valeur)


def ecrire_env(fichier: Path, changements: Mapping[str, str | None]) -> None:
    """Remplace la ligne de chaque variable (retire ses doublons), l'ajoute à la fin, ou la
    retire (None), sans toucher au reste. L'écriture est atomique, et le fichier finit
    lisible par David seul. `ReglageRefuse` si elle échoue : rien n'a changé. Un .env en
    lien symbolique garde son lien : c'est sa cible qui s'écrit."""
    fichier = fichier.resolve()
    try:
        texte = fichier.read_text(encoding="utf-8") if fichier.exists() else ""
    except (OSError, UnicodeDecodeError) as e:
        raise ReglageRefuse(f"Le .env ne se lit pas : {type(e).__name__}.") from e
    lignes = texte.split("\n")  # « \n » seul, comme make : jamais un séparateur Unicode
    if lignes[-1] == "":
        lignes.pop()
    for variable, valeur in changements.items():
        motif = re.compile(_AFFECTATION.format(re.escape(variable)))
        nouvelle = None if valeur is None else f"{variable}={pour_make(valeur)}"
        suite: list[str] = []
        for ligne in lignes:
            if not motif.match(ligne):
                suite.append(ligne)
            elif nouvelle is not None:
                suite.append(nouvelle)  # à la place de la première ; les doublons partent
                nouvelle = None
        if nouvelle is not None:
            suite.append(nouvelle)
        lignes = suite
    temporaire = fichier.with_name(fichier.name + ".tmp")
    try:
        descripteur = os.open(temporaire, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descripteur, "w", encoding="utf-8") as sortie:
            sortie.write("".join(f"{ligne}\n" for ligne in lignes))
        os.chmod(temporaire, 0o600)
        os.replace(temporaire, fichier)
    except OSError as e:
        try:
            temporaire.unlink(missing_ok=True)
        except OSError:
            pass
        raise ReglageRefuse(f"Le .env n'a pas pu s'écrire : {e.strerror or e}.") from e

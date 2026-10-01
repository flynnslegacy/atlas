"""`make google` (spec de Gmail et de Google Agenda, §4.2) : obtient le jeton durable de Google,
une fois, dans le navigateur de ce Mac, et l'écrit dans le .env d'Atlas.

L'identifiant et le secret du client viennent du .env (make les exporte), où la page les a
écrits. `AFFICHER=1` montre aussi le jeton, à coller dans « Réglages… » d'un Core qui tourne
ailleurs (le néo). Ce script vit hors de `src/` : les réglages Google appartiennent aux
connecteurs Gmail et Google Agenda, que la page peut réécrire ; le Core ne les lit jamais lui-même.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from pathlib import Path

from atlas_core import reglages
from atlas_core.connecteurs import ErreurConnecteur
from atlas_core.google import ErreurConnexion, connecter

MANQUE = (
    "Il manque ATLAS_GOOGLE_ID_CLIENT ou ATLAS_GOOGLE_SECRET_CLIENT : saisis-les dans "
    "Paramètres › Connecteurs › Gmail › Réglages…, puis relance make google."
)
NAVIGATEUR = (
    "Google s'ouvre dans ton navigateur. Il dit que l'application n'est pas vérifiée : c'est la "
    "tienne ; clique sur « Paramètres avancés », puis sur « Accéder à Atlas », et accepte."
)
AUTORISE = (
    "Atlas est autorisé : le jeton est dans le .env. Redémarre le Core depuis la page "
    "(Paramètres › Le Core › Redémarrer…)."
)
A_COLLER = "Le jeton, à coller dans « Réglages… » d'un Core qui tourne ailleurs :"


def main(
    environ: Mapping[str, str] = os.environ,
    *,
    fichier_env: Path | None = None,
    obtenir: Callable[[str, str], str] = connecter,
    dire: Callable[[str], object] = print,
) -> int:
    id_client = environ.get("ATLAS_GOOGLE_ID_CLIENT", "").strip()
    secret_client = environ.get("ATLAS_GOOGLE_SECRET_CLIENT", "").strip()
    if not id_client or not secret_client:
        dire(MANQUE)
        return 1
    dire(NAVIGATEUR)
    try:
        jeton = obtenir(id_client, secret_client)
    except (ErreurConnexion, ErreurConnecteur) as e:
        dire(str(e))
        return 1
    reglages.ecrire_env(fichier_env or reglages.FICHIER_ENV, {"ATLAS_GOOGLE_JETON": jeton})
    dire(AUTORISE)
    if environ.get("AFFICHER") == "1":
        dire(A_COLLER)
        dire(jeton)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

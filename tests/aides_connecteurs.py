"""Des aides pour tester un connecteur officiel sans lancer Atlas : l'activer par le vrai
registre, et appeler ses outils comme le Core le ferait."""

from __future__ import annotations

import sys
import types
from pathlib import Path

from atlas_core.registre import OFFICIELS, Registre


def charger(id_: str, dossier: Path, environ: dict[str, str]) -> types.ModuleType:
    """Active le connecteur officiel `id_` par le vrai registre (ses interrupteurs rangés dans
    `dossier`), et rend son module `connecteur`."""
    registre = Registre(OFFICIELS, dossier / "perso", environ=environ)
    assert registre.basculer(id_, True), [(f.id, f.etat, f.detail) for f in registre.fiches]
    return sys.modules[f"atlas_connecteurs.{id_.replace('-', '_')}.connecteur"]


async def appeler(connecteur, nom: str, **arguments: object) -> object:
    """Appelle l'outil `nom` du connecteur, comme le Core le ferait."""
    [outil] = [outil for outil in connecteur.outils() if outil.nom == nom]
    return await outil.gestionnaire(arguments)

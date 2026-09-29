"""Réglages communs aux tests.

La mémoire d'Atlas est un dépôt git sur la machine du Core, et ses connecteurs vivent à côté :
les tests, qui démarrent le Core, ne doivent jamais toucher les vrais. Les dossiers sont forcés
avant tout import du Core (`make test` exporte le .env de la machine, qui pourrait en nommer
d'autres). Les réglages écrits depuis la page vont dans un .env de test, jamais dans celui du
dépôt ; et aucun test ne redémarre le Core ni ne met à jour le dépôt de David.
"""

import os
import tempfile

import pytest

_TEMPORAIRE = tempfile.mkdtemp(prefix="atlas-tests-")
os.environ["ATLAS_MEMOIRE_DOSSIER"] = os.path.join(_TEMPORAIRE, "memoire")
os.environ["ATLAS_CONNECTEURS_DOSSIER"] = os.path.join(_TEMPORAIRE, "connecteurs")


@pytest.fixture(autouse=True)
def _jamais_le_env_du_depot(monkeypatch, tmp_path_factory):
    from atlas_core import entretien, reglages

    monkeypatch.setattr(reglages, "FICHIER_ENV", tmp_path_factory.mktemp("env") / ".env")
    monkeypatch.setattr(entretien, "DEPOT", tmp_path_factory.mktemp("depot"))
    monkeypatch.setattr(entretien, "arreter_le_core", lambda: None)

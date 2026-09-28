"""Réglages communs aux tests.

La mémoire d'Atlas est un dépôt git sur la machine du Core, et ses connecteurs vivent à côté :
les tests, qui démarrent le Core, ne doivent jamais toucher les vrais. Les dossiers sont forcés
avant tout import du Core (`make test` exporte le .env de la machine, qui pourrait en nommer
d'autres).
"""

import os
import tempfile

_TEMPORAIRE = tempfile.mkdtemp(prefix="atlas-tests-")
os.environ["ATLAS_MEMOIRE_DOSSIER"] = os.path.join(_TEMPORAIRE, "memoire")
os.environ["ATLAS_CONNECTEURS_DOSSIER"] = os.path.join(_TEMPORAIRE, "connecteurs")

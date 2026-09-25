"""Réglages communs aux tests.

La mémoire d'Atlas est un dépôt git sur la machine du Core : les tests, qui démarrent le
Core, ne doivent jamais toucher la vraie. Le dossier est forcé avant tout import du Core
(`make test` exporte le .env de la machine, qui pourrait en nommer un autre).
"""

import os
import tempfile

os.environ["ATLAS_MEMOIRE_DOSSIER"] = os.path.join(
    tempfile.mkdtemp(prefix="atlas-tests-"), "memoire"
)

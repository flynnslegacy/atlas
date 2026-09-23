"""Répartition entraînement / test, identique sur le Mac et sur l'Unraid.

Le Mac (evaluer.py) et l'Unraid (preparer.py) doivent réserver exactement les
mêmes enregistrements au test sans s'échanger de liste : on décide par
l'empreinte du nom de fichier.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable


def est_test(nom: str, une_sur: int) -> bool:
    """Vrai pour environ un nom sur `une_sur`, toujours le même d'une machine à l'autre."""
    empreinte = int(hashlib.sha1(nom.encode("utf-8")).hexdigest()[:8], 16)
    return empreinte % une_sur == 0


def repartir(noms: Iterable[str], une_sur: int) -> tuple[list[str], list[str]]:
    noms = list(noms)
    entrainement = sorted(n for n in noms if not est_test(n, une_sur))
    test = sorted(n for n in noms if est_test(n, une_sur))
    return entrainement, test


def noms_copies(nom: str, fois: int) -> list[str]:
    """Noms des `fois` copies d'un extrait : train.py ne sait pas pondérer autrement.

    Son option `augmentation_rounds` n'a pas d'effet au commit 368c037.
    """
    base = nom[:-4] if nom.endswith(".wav") else nom
    return [f"{base}__c{i:02d}.wav" for i in range(fois)]

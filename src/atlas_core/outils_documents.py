"""L'outil des documents : ce que la réflexion de David devient, à sa demande (spec 2c §5).

Un document s'écrit en entier dans `documents/<nom>.md`, comme une fiche mais plus long, et
dans un Markdown structuré que la page met en forme. L'écriture est N2 : faite, puis
annoncée ; les pages sont prévenues pour mettre leur liste à jour.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from .memoire import Memoire
from .outils import Fait, Niveau, Outil

ECRIRE_DOCUMENT = (
    "Crée ou remplace un document entier, documents/<nom>.md, le nom en minuscules, chiffres "
    "et tirets : seulement quand David te demande un document. Le contenu commence par "
    "« # Titre », une ligne vide, puis une phrase de résumé ; ensuite un Markdown structuré : "
    "sous-titres (## et ###), paragraphes, listes à puces ou numérotées, gras, italique, "
    "citations (>), code, tableaux simples, liens https. Pour une retouche, relis le document "
    "avec memoire_lire, puis réécris-le en entier. Atlas annonce l'écriture à David : ne "
    "l'annonce pas toi-même."
)


def outils_des_documents(memoire: Memoire, sur_documents: Callable[[], None]) -> list[Outil]:
    async def ecrire(arguments: dict[str, Any]) -> Fait:
        nom = arguments["nom"]
        ecrit = await asyncio.to_thread(memoire.ecrire_document, nom, arguments["contenu"])
        if ecrit is None:
            return Fait("Le document était déjà ainsi : rien n'a changé.")
        titre, cree = ecrit
        sur_documents()
        if cree:
            annonce = f"J'ai écrit le document {titre}, il est dans la page."
        else:
            annonce = f"J'ai mis à jour le document {titre}."
        return Fait(f"C'est écrit dans documents/{nom}.md.", annonce)

    return [
        Outil("document_ecrire", ECRIRE_DOCUMENT, {"nom": str, "contenu": str}, Niveau.N2, ecrire)
    ]

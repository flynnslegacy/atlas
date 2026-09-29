"""Ce que le Core répond à une page qui le lui demande : la liste des documents, un
document (spec 2c, §7), et la liste des connecteurs (spec des connecteurs, §6)."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping

from .consignes import date_en_lettres, heure_en_chiffres
from .memoire import ErreurMemoire
from .outils_memoire import OutilsMemoire
from .protocole_web import (
    Document,
    FicheConnecteur,
    ListeConnecteurs,
    ListeDocuments,
    ReglageConnecteur,
    ResumeDocument,
)
from .registre import Fiche
from .reglages import modifiable

MEMOIRE_ABSENTE = "La mémoire n'est pas disponible."


async def liste_documents(outils: OutilsMemoire | None) -> ListeDocuments:
    if outils is None:
        return ListeDocuments(disponible=False)
    infos = await asyncio.to_thread(outils.memoire.documents)
    return ListeDocuments(
        documents=[
            ResumeDocument(
                chemin=info.chemin,
                titre=info.titre,
                resume=info.resume,
                modifie=f"{date_en_lettres(info.modifie)}, {heure_en_chiffres(info.modifie)}",
            )
            for info in infos
        ]
    )


async def lire_document(outils: OutilsMemoire | None, chemin: str) -> Document:
    if outils is None:
        return Document(chemin=chemin, erreur=MEMOIRE_ABSENTE)
    try:
        contenu = await asyncio.to_thread(outils.memoire.lire, chemin)
    except (ErreurMemoire, OSError) as e:
        return Document(chemin=chemin, erreur=str(e))
    titre = contenu.split("\n", 1)[0].lstrip("#").strip()
    return Document(chemin=chemin, titre=titre, contenu=contenu)


def liste_connecteurs(outils: OutilsMemoire | None) -> ListeConnecteurs:
    """Les connecteurs trouvés, relus à l'instant (manifestes seuls) ; sans mémoire, aucun."""
    if outils is None or outils.registre is None:
        return ListeConnecteurs(disponible=False)
    environ = outils.registre.environ
    fiches = outils.registre.decouvrir()
    return ListeConnecteurs(connecteurs=[_pour_la_page(f, environ) for f in fiches])


def _pour_la_page(fiche: Fiche, environ: Mapping[str, str]) -> FicheConnecteur:
    manifeste = fiche.manifeste
    reglages = [
        ReglageConnecteur(
            variable=r.variable,
            description=r.description,
            secret=r.secret,
            defini=bool(environ.get(r.variable, "").strip()),
            modifiable=modifiable(r.variable),
            # Jamais la valeur d'un secret, ni celle d'une clé d'Atlas, même déclarée
            # « ordinaire » par un manifeste.
            valeur=environ.get(r.variable, "") if not r.secret and modifiable(r.variable) else "",
        )
        for r in (manifeste.reglages if manifeste else ())
    ]
    return FicheConnecteur(
        id=fiche.id,
        nom=manifeste.nom if manifeste else fiche.id,
        description=manifeste.description if manifeste else "",
        version=manifeste.version if manifeste else "",
        auteur=manifeste.auteur if manifeste else "",
        origine=fiche.origine,
        etat=fiche.etat,
        detail=fiche.detail,
        en_attente=fiche.en_attente,
        reglages=reglages,
    )

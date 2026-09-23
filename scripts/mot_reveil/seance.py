"""Le déroulé de la séance d'enregistrement de David (environ 30 minutes)."""

from __future__ import annotations

from dataclasses import dataclass

TONS = (
    "normalement",
    "vite, comme pressé",
    "fatigué, un peu mou",
    "fort",
    "doucement",
    "en souriant",
)
DISTANCES = (
    ("bureau", "assis à ton bureau, face au Mac"),
    ("m150", "debout à 1,5 m du Mac"),
    ("m300", "à 3 m du Mac"),
)
PHRASES_ATLAS_SEUL = (
    "Atlas.",
    "Le projet Atlas avance bien.",
    "Atlas, c'est mon assistant.",
    "J'ai parlé d'Atlas à mon associé.",
    "Atlas, ça reste entre nous.",
    "On lance Atlas lundi.",
    "Atlas tourne sur mon Mac.",
    "Tu connais Atlas ?",
    "Atlas et moi, on travaille ensemble.",
    "La version d'Atlas est prête.",
)
SUJETS_PAROLE = (
    "ta journée d'hier",
    "un projet en cours",
    "ton dernier repas",
    "tes prochaines vacances",
    "un film que tu as aimé",
    "ton métier",
    "ta ville",
    "un livre ou une série",
    "tes outils de travail",
    "ce que tu veux",
)


@dataclass(frozen=True)
class Prise:
    dossier: str  # sous-dossier de donnees/mot_reveil/david
    nom: str  # nom du fichier, sans extension
    consigne: str
    duree_s: float


def plan_seance(par_ton: int = 6) -> list[Prise]:
    prises = []
    for prefixe, lieu in DISTANCES:
        for i in range(par_ton * len(TONS)):
            ton = TONS[i % len(TONS)]
            consigne = f"{lieu} : dis « Hey Atlas » {ton}."
            prises.append(Prise("positifs", f"{prefixe}_{i + 1:03d}", consigne, 3.0))
    for i, phrase in enumerate(PHRASES_ATLAS_SEUL, 1):
        prises.append(Prise("atlas_seul", f"atlas_{i:02d}", f"Dis simplement : « {phrase} »", 4.0))
    for i, sujet in enumerate(SUJETS_PAROLE, 1):
        consigne = f"Parle une minute de {sujet}, sans jamais dire « Hey Atlas »."
        prises.append(Prise("parole", f"parole_{i:02d}", consigne, 60.0))
    for i in range(1, 13):
        consigne = (
            "Ne parle pas : tape au clavier, bouge la souris, la chaise… "
            "ou laisse simplement tourner."
        )
        prises.append(Prise("bureau", f"bureau_{i:02d}", consigne, 60.0))
    return prises

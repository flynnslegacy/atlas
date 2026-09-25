"""Le ménage d'une réponse abandonnée : la question suivante qui l'attend puis est
elle-même annulée, et le tampon plein du SDK. Déplacé de `test_cerveau_claude.py` (qui
dépassait 500 lignes) : les doublures et les aides viennent de là, sans être dupliquées."""

import asyncio
import contextlib
import time

from test_cerveau_claude import (
    BLOQUE,
    FauxClientClaude,
    _cerveau,
    _tout,
    debut_texte,
    delta,
    fin,
    reponse,
)

from atlas_core import cerveau_claude


async def test_une_question_annulee_en_attendant_le_menage_ne_l_annule_pas(monkeypatch):
    monkeypatch.setattr(cerveau_claude, "DELAI_MENAGE_S", 0.05)
    client = FauxClientClaude([debut_texte(), delta("Long "), BLOQUE], reponse("Oui."))
    client.interruption_sans_effet = True
    cerveau = _cerveau(client)
    flux = cerveau.repondre("Raconte.")
    await anext(flux)
    await flux.aclose()
    menage = cerveau._menage

    tache = asyncio.create_task(_tout(cerveau, "Et alors ?"))
    await asyncio.sleep(0.01)
    tache.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await tache
    assert menage is not None and not menage.cancelled()
    # Attend proprement le ménage (délai court : `interruption_sans_effet` le fait finir
    # par le délai de garde) plutôt que de l'annuler sans jamais l'attendre, ce qui
    # laissait une tâche encore en route à la fermeture de la boucle.
    await cerveau.fermer()


# --- le tampon plein du SDK ---------------------------------------------------------

# Le vrai SDK ne garde que 100 messages en attente : quand la session prend du retard
# sur Claude (elle synthétise chaque phrase le temps qu'elle parle), le tampon se
# remplit. Le ménage doit alors lire pendant qu'il interrompt, sinon la réponse à
# l'interruption reste coincée derrière les événements déjà en file.


async def test_un_gros_reliquat_ne_bloque_pas_le_menage(monkeypatch):
    monkeypatch.setattr(cerveau_claude, "DELAI_MENAGE_S", 0.05)
    tour = [debut_texte(), *(delta(f"m{i} ") for i in range(150)), fin()]
    client = FauxClientClaude(tour, reponse("Suite."))
    cerveau = _cerveau(client)

    flux = cerveau.repondre("Raconte.")
    await anext(flux)
    await flux.aclose()  # laisse un gros reliquat non lu (149 deltas + la fin)

    assert await _tout(cerveau, "Attends.") == ["Suite."], "pas de fil perdu : le ménage a fini"
    assert client.interruptions == 1


async def test_une_interruption_croisee_n_attend_pas_tout_le_reliquat_de_l_autre():
    tour_a = [debut_texte(), *(delta(f"m{i} ") for i in range(150)), fin()]
    client = FauxClientClaude(tour_a, reponse("Seconde."))
    cerveau = _cerveau(client)
    premiere: list = []

    async def lire_la_premiere() -> None:
        async for f in cerveau.repondre("une"):
            premiere.append(f)
            await asyncio.sleep(0.02)  # la session « parle » chaque fragment reçu

    tache = asyncio.create_task(lire_la_premiere())
    while not premiere:
        await asyncio.sleep(0)

    debut = time.monotonic()
    assert await _tout(cerveau, "deux") == ["Seconde."]
    duree = time.monotonic() - debut
    await tache  # finie sans erreur : l'interruption n'est pas un échec

    assert duree < 0.5, "la deuxième question a attendu tout le reliquat de la première"
    assert len(premiere) < 150, "la première a continué de parler après avoir été coupée"
    assert client.interruptions == 1

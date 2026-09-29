# Écrire un connecteur pour Atlas

Un connecteur relie Atlas à l'extérieur : un agenda, une boîte mail, la maison, le Mac. C'est
un dossier, que l'on dépose, et qu'on active d'un interrupteur dans la page d'Atlas
(Paramètres › Connecteurs). Ce guide suffit pour en écrire un.

## Où le déposer

- `connecteurs/` dans le dépôt d'Atlas : les connecteurs officiels (badge « Atlas »).
- `~/.atlas/connecteurs/` sur la machine du Core : les tiens et ceux de la communauté (badge
  « Communauté »). Le réglage `ATLAS_CONNECTEURS_DOSSIER` le déplace.

Le nom du dossier est l'identifiant du connecteur : minuscules, chiffres et tirets
(`agenda-icloud`), 40 caractères au plus. Un connecteur déposé commence coupé ; son code ne
tourne qu'une fois activé dans la page. Un connecteur de la communauté demande une
confirmation à l'activation.

## Le manifeste : `connecteur.toml`

Atlas le lit sans exécuter aucun code, pour lister le connecteur dans la page.

| Clé | Obligatoire | Rôle |
|---|---|---|
| `nom` | oui | Le nom affiché, 60 caractères au plus |
| `description` | oui | Une phrase, 300 caractères au plus |
| `version`, `auteur` | oui | Affichés dans la page |
| `api` | oui | La version du contrat : `1` |
| `dependances` | non | Des exigences pip (`"caldav>=1.4"`), installées par `make install` sans jamais changer une version dont Atlas dépend |
| `services` | non | Les services du Core dont il a besoin : `"poste"` (le lien avec le Mac et les missions) |
| `consignes` | non | Ce que Claude doit savoir pour se servir de ses outils, ajouté à ses consignes quand le connecteur est actif |
| `[[reglages]]` | non | Chacun : `variable` (`ATLAS_…`, dans le `.env` du Core), `description`, `secret` (vrai ou faux) |

Tant qu'un réglage manque dans le `.env`, le connecteur est « à configurer » ; tant qu'une
dépendance manque, « à installer ». David saisit les réglages dans la page (Paramètres ›
Connecteurs › Réglages) ou dans le `.env` ; ils prennent effet aussitôt, sans redémarrer. La
page ne reçoit jamais la valeur d'un réglage `secret`, qui n'est jamais écrit non plus dans la
mémoire d'Atlas. Une variable qu'Atlas lit lui-même (`ATLAS_WEB_CLE`, `ATLAS_POSTE_CLE`…) ne
s'écrit jamais depuis la page, même déclarée par un connecteur : elle se change au Terminal.

## Le code : `connecteur.py`

Il définit `creer(contexte)`, qui rend un `Connecteur`. Le `contexte` donne les réglages du
manifeste (`contexte.reglages`, et eux seuls) et les services demandés (`contexte.poste`,
`contexte.missions`). Tout ce dont un connecteur a besoin s'importe de `atlas_core.connecteurs`.
`creer` et `outils()` rendent la main vite, sans réseau ni attente : Atlas les appelle à
l'activation. Ce qui prend du temps va dans les gestionnaires, qui sont `async` ; une
bibliothèque qui bloque s'appelle par `asyncio.to_thread`.

Chaque outil est un `Outil(nom, description, parametres, niveau, gestionnaire)` :

- `nom` : minuscules, chiffres et `_`, 52 caractères au plus, unique parmi tous les outils
  d'Atlas ; préfixe-le du nom de ton connecteur (`agenda_lire`).
- `description` : ce que Claude lit pour décider de s'en servir.
- `parametres` : les types des arguments (`{"jour": str}`), ou un schéma JSON quand certains
  sont facultatifs.
- `niveau` : ce qu'Atlas fait autour de l'outil, que Claude ne choisit jamais.
- `gestionnaire` : une fonction `async`, qui reçoit les arguments et rend le résultat :

| Niveau | Pour | Le gestionnaire rend | Atlas |
|---|---|---|---|
| `Niveau.N1` | Lire, consulter | Un texte, ou une `Capture` | Rend le résultat à Claude, sans rien dire |
| `Niveau.N2` | Une modification réversible | Un `Fait(texte, annonce)` | Rend le texte à Claude, et dit l'annonce à David |
| `Niveau.N3` | Irréversible ou sortant (envoyer, supprimer) | Une action à confirmer (voir `Action`) | Pose la question à David, et n'agit qu'après son « oui » |

Pour refuser (un argument qui ne va pas, un service injoignable), lève
`ErreurConnecteur("…")` : le message va à Claude, qui le dit à David. Toute autre exception
est notée dans le journal du Core, et Claude apprend que l'outil a échoué ; Atlas continue.

Un `Connecteur` peut aussi réagir au fil de la conversation, s'il en a besoin :
`fin_du_tour(arretee)`, `nouvelle_phrase()`, `nouvelle_conversation()`.

## Un connecteur minimal

`bonjour/connecteur.toml` :

```toml
nom = "Bonjour"
description = "Atlas te salue par ton nom."
version = "1.0.0"
auteur = "Toi"
api = 1
consignes = "Quand David te demande de le saluer, appelle bonjour_dire."

[[reglages]]
variable = "ATLAS_BONJOUR_NOM"
description = "Le nom à saluer"
```

`bonjour/connecteur.py` :

```python
from atlas_core.connecteurs import Connecteur, Contexte, Niveau, Outil


class Bonjour(Connecteur):
    def __init__(self, contexte: Contexte) -> None:
        self.nom = contexte.reglages["ATLAS_BONJOUR_NOM"]

    def outils(self) -> list[Outil]:
        async def dire(arguments: dict) -> str:
            return f"Bonjour {self.nom} !"

        return [Outil("bonjour_dire", "Salue David par son nom.", {}, Niveau.N1, dire)]


def creer(contexte: Contexte) -> Bonjour:
    return Bonjour(contexte)
```

Dans la page, ouvre les réglages de « Bonjour », saisis `David` pour `ATLAS_BONJOUR_NOM` (ou
mets `ATLAS_BONJOUR_NOM=David` dans le `.env` du Core, puis redémarre-le), active « Bonjour »,
puis demande à Atlas de te saluer.

## Tester son connecteur

Sans lancer Atlas, avec pytest : le registre charge le connecteur comme la page le ferait.
Place ce test à côté du dossier `bonjour/`, puis, depuis le dossier d'Atlas :
`uv run pytest ~/.atlas/connecteurs/test_bonjour.py` (ou son chemin chez toi).

`test_bonjour.py` :

```python
from pathlib import Path

import pytest

from atlas_core.registre import Registre

ICI = Path(__file__).resolve().parent  # le dossier qui contient bonjour/


@pytest.mark.asyncio
async def test_bonjour_salue_par_le_nom_regle(tmp_path):
    registre = Registre(ICI, tmp_path / "rien", environ={"ATLAS_BONJOUR_NOM": "David"})
    assert registre.basculer("bonjour", True), registre.fiches
    [actif] = registre.actifs()
    assert await actif.outils[0].gestionnaire({}) == "Bonjour David !"
```

Si l'activation échoue, `registre.fiches` dit pourquoi, comme la page.

## Un exemple complet

`connecteurs/poste/` : le poste du Mac. Des outils N1, N2 et N3, une image rendue à Claude,
une mission confirmée, des refus, et le service `poste`.

## La confiance

Un connecteur n'est pas enfermé : son code tourne dans Atlas, et pourrait tout lire. Ne dépose
que ce en quoi tu as confiance, et relis-le. Atlas garantit seulement qu'aucun code ne tourne
avant l'activation, qu'un connecteur ne reçoit que ses propres réglages, qu'il ne prend le nom
d'aucun autre outil, et que les annonces et les confirmations suivent les niveaux déclarés.

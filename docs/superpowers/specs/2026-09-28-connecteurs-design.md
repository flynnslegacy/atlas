# Les connecteurs : des interconnexions activables — design

**Date :** 28 septembre 2026
**Statut :** design validé par David, section par section
**Spec parente :** `2026-09-22-atlas-design.md` (§9 les outils, §10 les permissions, §15 le phasage) ; s'appuie sur
`2026-09-25-phase-2c-outils-design.md` (le serveur d'outils « atlas », les niveaux, la confirmation) et
`2026-09-26-poste-mac-design.md` (le poste, qui devient le premier connecteur)
**Approche retenue :** un connecteur est un dossier (un manifeste lisible et du code Python) déposé dans l'un de deux
répertoires ; le Core le liste sans l'exécuter, le charge quand David l'active dans la page, et l'applique à la
question suivante, dans une conversation neuve

## 1. Objectif et critères de réussite

David veut que toutes les interconnexions d'Atlas soient **activables et désactivables depuis les Paramètres de la
page**, et que chacune vive dans **son propre dossier**, pour qu'une communauté puisse écrire ses connecteurs : on
dépose le dossier, il apparaît dans les Paramètres, un interrupteur l'active.

Ce document est la première partie de l'étape 2 de la feuille de route (l'agenda iCloud et Gmail) : le cadre des
connecteurs, éprouvé en y faisant passer le poste du Mac. L'agenda iCloud, puis Gmail, viendront chacun avec leur
spec, comme connecteurs officiels.

| Critère | Objectif, vérifié par David sur le M5 |
|---|---|
| Lister | Après la mise à jour, la rubrique « Connecteurs » montre le poste, badge « Atlas », coupé |
| Activer | David active le poste ; à la question suivante, « Ouvre Notes » marche |
| Couper | David coupe le poste ; « Ouvre Notes » : Atlas dit qu'il ne peut pas |
| Déposer | Le connecteur minimal du guide, copié dans `~/.atlas/connecteurs/`, apparaît « Communauté », coupé ; l'activer demande confirmation ; ensuite il marche |
| À configurer | Un connecteur dont une variable du `.env` manque affiche « à configurer » et la nomme |
| En erreur | Un connecteur au code cassé affiche « en erreur », et Atlas continue |
| Non-régression | `make test` au vert |

## 2. Décisions

- **D1. Les connecteurs sont les liens vers l'extérieur** : le poste du Mac, l'agenda, le mail, Home Assistant, les
  appels, les réseaux sociaux. La mémoire, les documents et la recherche web restent le socle d'Atlas, toujours actifs.
- **D2. Les secrets restent dans le `.env` du Core.** Chaque connecteur déclare ses variables ; la page dit seulement
  lesquelles manquent. Aucun secret ne passe jamais par la page.
- **D3. Un connecteur est un dossier** : un manifeste `connecteur.toml`, lisible et lu sans exécuter aucun code, et
  le code Python de ses outils (`connecteur.py`, et d'autres fichiers au besoin).
- **D4. Deux répertoires** : les connecteurs officiels dans le dépôt (`connecteurs/`), mis à jour par `git pull` ;
  ceux de David et de la communauté dans `~/.atlas/connecteurs/`, sur la machine du Core, que git ne touche jamais.
- **D5. Un connecteur déposé commence coupé** ; son code ne tourne qu'une fois activé. Activer un connecteur qui ne
  vient pas du dépôt d'Atlas demande une confirmation dans la page.
- **D6. Une bascule prend effet à la question suivante, dans une conversation neuve** : la conversation en cours se
  clôt comme à l'oubli (son résumé va au journal), et la suivante porte les outils et les consignes des connecteurs
  actifs. La bascule en pleine conversation (`toggle_mcp_server` du SDK) est écartée : les consignes, fixées au début
  d'une conversation, ne suivraient pas, et un connecteur neuf demanderait de toute façon une conversation neuve.

## 3. Architecture

```
connecteurs/ (dépôt)              ~/.atlas/connecteurs/ (machine du Core)
  poste/                            exemple/
    connecteur.toml                   connecteur.toml
    connecteur.py                     connecteur.py
        │   manifestes lus sans code       │
        └──────────────┬───────────────────┘
                       ▼
        Core : le registre des connecteurs ── ~/.atlas/connecteurs.json (les interrupteurs)
          découverte, états, chargement à l'activation
                       │ outils et consignes des connecteurs actifs
                       ▼
        serveur d'outils « atlas » (socle + connecteurs actifs) ─► Claude, conversation neuve
                       ▲
        Pages ── « Connecteurs » dans les Paramètres : liste, états, interrupteurs
```

| Fichier | Rôle |
|---|---|
| `src/atlas_core/connecteurs.py` (nouveau) | Le contrat d'un connecteur (`Connecteur`, `Contexte`) et le manifeste : ce qu'importe un connecteur |
| `src/atlas_core/registre.py` (nouveau) | La découverte, les états, les interrupteurs, le chargement à l'activation, les dépendances |
| `connecteurs/poste/` (nouveau) | Le poste en connecteur officiel : son manifeste, ses outils `mac_…` et ses consignes (tirés de `outils_poste.py` et de `consignes.py`) |
| `connecteurs/LISEZMOI.md` (nouveau) | Le guide pour écrire un connecteur |
| `src/atlas_core/outils_memoire.py`, `outils_poste.py` | Le serveur « atlas » construit avec les outils des connecteurs actifs ; les missions restent un service du Core |
| `src/atlas_core/consignes.py`, `cerveau_claude.py` | Les consignes des connecteurs actifs ; la conversation close à une bascule |
| `src/atlas_core/protocole_web.py`, `hub.py` | Les messages `connecteurs`, `activer_connecteur`, `liste_connecteurs` |
| `src/atlas_web/connecteurs.js` (nouveau), `app.js`, `index.html`, `documents.css` | La rubrique « Connecteurs » |
| `Makefile` | `make install` installe aussi les dépendances des connecteurs |

La voix, la régie, les clients audio, le poste du M5 (`src/atlas_poste/`), la route `/ws/poste` et la mémoire ne
changent pas.

## 4. Le connecteur

- **Son dossier** porte son identifiant : minuscules, chiffres et tirets (`agenda-icloud`), 40 caractères au plus.
- **Le manifeste `connecteur.toml`** :

| Clé | Obligatoire | Rôle |
|---|---|---|
| `nom` | oui | Le nom affiché (« Agenda iCloud ») |
| `description` | oui | Une phrase, affichée sous le nom |
| `version`, `auteur` | oui | Affichés dans la page |
| `api` | oui | La version du contrat ; `1` pour ce document. Une autre version : « en erreur (contrat inconnu) » |
| `dependances` | non | Des exigences pip (`"caldav>=1.4"`) |
| `services` | non | Les services du Core qu'il utilise ; en version 1 : `"poste"` (le lien avec le Mac et les missions) |
| `consignes` | non | Le texte ajouté aux consignes de Claude quand le connecteur est actif |
| `[[reglages]]` | non | Chacun : `variable` (un nom de variable du `.env`, `ATLAS_…`), `description`, `secret` (vrai ou faux) |

- **Le code** : `connecteur.py` définit `creer(contexte: Contexte) -> Connecteur`. Le dossier est chargé comme un
  paquet Python, si bien qu'il peut contenir d'autres fichiers et les importer.
- **Le `Contexte`** donne au connecteur ses réglages (les seules variables déclarées dans son manifeste, lues dans
  l'environnement du Core) et les services demandés : `poste` et `missions` pour le service `poste`.
- **Le `Connecteur`** rend ses outils (`outils()`, une liste d'`Outil` : nom, description, paramètres, niveau N1, N2 ou
  N3, gestionnaire), avec les mêmes résultats qu'aujourd'hui : un texte ou une image (N1), un `Fait` avec son annonce
  et son image éventuelle (N2), une action à confirmer (N3), ou un refus (`ErreurConnecteur`, dont le message va à
  Claude). Il peut aussi réagir à `fin_du_tour`, `nouvelle_phrase` et `nouvelle_conversation`, s'il en a besoin.
- **Les noms d'outils** : minuscules, chiffres et `_`, 64 caractères au plus, uniques parmi le socle et tous les
  connecteurs actifs.
- **Le Core enrobe ces outils comme ceux du socle** : les annonces, la confirmation N3, le refus pendant le résumé, et
  une exception inattendue rendue à Claude comme un échec, sans jamais faire tomber Atlas.
- **Le poste devient `connecteurs/poste/`** : manifeste (réglage `ATLAS_POSTE_CLE`, secret ; service `poste` ;
  consignes : celles du poste aujourd'hui), outils `mac_…` inchangés. `Missions` et le lien avec le Mac restent des
  services du Core.

## 5. Le Core

- **La découverte** : au démarrage, puis à chaque demande de la liste par une page, le Core relit les deux répertoires
  et ne lit que les manifestes. Un dossier sans manifeste valide apparaît « en erreur », avec la raison. Un même
  identifiant aux deux endroits : l'officiel l'emporte, le doublon apparaît « en erreur (déjà fourni par Atlas) ».
- **Les états** :

| État | Quand | L'interrupteur |
|---|---|---|
| `actif` | Activé, chargé, ses outils sont à Claude | Allumé |
| `coupe` | Configuré et installé, pas activé | Éteint, activable |
| `a_configurer` | Une variable déclarée est absente ou vide dans le `.env` ; le détail la nomme | Grisé |
| `a_installer` | Une dépendance n'est pas installée ; le détail dit « lance make install » | Grisé |
| `en_erreur` | Manifeste invalide, contrat inconnu, doublon, code qui ne se charge pas, nom d'outil déjà pris | Grisé |

- **Les interrupteurs** sont rangés dans `~/.atlas/connecteurs.json` (droits 600) : la liste des connecteurs activés,
  chacun lié à son origine (`atlas:poste`, `communaute:meteo`). Tout connecteur qui n'y est pas est coupé, les
  officiels compris : après la mise à jour, David active le poste une fois. Un dossier retiré emporte son interrupteur
  (un répertoire momentanément illisible garde les siens) : un autre code déposé sous le même nom repart coupé.
- **L'activation** : le Core charge alors le code du connecteur (jamais avant), appelle `creer`, et vérifie ses
  outils. Un échec le laisse coupé, « en erreur », avec le message. Au démarrage, les connecteurs activés sont chargés
  de même ; un échec ne bloque pas les autres, et coupe le sien.
- **La conversation neuve** : dès qu'une bascule change l'ensemble des connecteurs actifs, le Core clôt la
  conversation en cours comme à l'oubli (résumé au journal ; une réponse en cours se finit d'abord), et le serveur
  « atlas » est reconstruit avec le socle et les connecteurs actifs. La question suivante ouvre la conversation neuve,
  avec la mémoire, les outils et les consignes des connecteurs actifs.
- **Les dépendances** : `make install` installe, après Atlas, les dépendances de tous les connecteurs trouvés aux deux
  endroits (`uv pip install`), bornées par le verrou d'Atlas (`uv export` de `uv.lock`) : une dépendance qui
  changerait une version dont Atlas dépend ne s'installe pas. Les officiels s'installent ensemble, puis chaque
  connecteur de la communauté à part ; un échec de ceux-là le laisse `a_installer` sans faire échouer `make install`.
  L'état `a_installer` vérifie la présence de chaque paquet par son nom de distribution.
- **Les secrets** : les réglages `secret` de tous les connecteurs trouvés rejoignent les clés que la mémoire refuse
  d'écrire.
- **Sans mémoire, pas de connecteurs** : ils s'appuient sur le serveur d'outils et la confirmation qu'elle porte ; la
  liste le dit (`disponible` faux).

## 6. La page

- **Une rubrique « Connecteurs »** en tête des Paramètres. Une ligne par connecteur : son nom, un badge « Atlas » ou
  « Communauté », sa description, sa version et son auteur, son état et son détail, et un interrupteur, grisé s'il
  n'est pas activable. Les connecteurs sont triés par nom, les officiels d'abord.
- **Un connecteur « Communauté »** : l'activer fait d'abord apparaître, sous sa ligne, « Ce connecteur ne vient pas
  d'Atlas : son code tournera dans Atlas, avec accès à tes réglages et à ta mémoire. », avec « Activer quand même » et
  « Annuler ». Un officiel s'active d'un toucher ; couper ne demande jamais rien.
- **Après une bascule**, la ligne dit « Prend effet à ta prochaine question. », jusqu'à la question suivante.
- **Les messages** (`/ws/web`, protégés par la clé) :

| Sens | Message | Contenu |
|---|---|---|
| page → Core | `connecteurs` | La demande de la liste (à l'ouverture des Paramètres) |
| page → Core | `activer_connecteur` | `id`, `actif` |
| Core → page | `liste_connecteurs` | `disponible`, et pour chacun : `id`, `nom`, `description`, `version`, `auteur`, `origine` (`atlas` ou `communaute`), `etat`, `detail`, `en_attente` (vrai jusqu'à la question suivante) ; envoyée à la page qui la demande, et à toutes les pages après une bascule |

- **Les textes d'un manifeste** viennent d'un tiers : la page les affiche toujours comme du texte, jamais comme du
  HTML.
- **Sans mémoire**, la rubrique dit « La mémoire n'est pas disponible : pas de connecteurs. ».

## 7. Sécurité et erreurs

- **Un connecteur n'est pas enfermé** : son code Python tourne dans le Core et pourrait tout lire. La confiance se
  donne en déposant le dossier, puis en l'activant ; la page le rappelle pour un connecteur de la communauté.
- **Ce que le cadre garantit** : aucun code ne tourne avant l'activation ; un connecteur ne reçoit que ses propres
  réglages et les services qu'il déclare ; il ne peut pas prendre le nom d'un outil existant ; le Core fait lui-même
  les annonces et les confirmations, selon les niveaux déclarés. Un connecteur malveillant pourrait mentir sur ses
  niveaux : c'est ce que l'avertissement « Communauté » couvre.
- **Les erreurs** : un manifeste illisible, un code qui plante au chargement, une exception dans un outil ne font
  jamais tomber Atlas ; le connecteur passe « en erreur » ou l'outil rend un échec à Claude, et le journal du Core le
  note.
- **Un identifiant ou un nom d'outil hors motif** est refusé ; un chemin n'est jamais construit à partir d'un texte
  venu de la page sans passer par la liste des connecteurs découverts.

## 8. Fichiers et réglages

| Chemin | Rôle |
|---|---|
| `connecteurs/` | Les connecteurs officiels, dans le dépôt |
| `~/.atlas/connecteurs/` | Ceux de David et de la communauté (réglage `ATLAS_CONNECTEURS_DOSSIER`, vide par défaut) |
| `~/.atlas/connecteurs.json` | Les connecteurs activés |

Les réglages de chaque connecteur sont les variables de son manifeste, dans le `.env` du Core.

## 9. Le guide des connecteurs

`connecteurs/LISEZMOI.md` : le manifeste complet, un connecteur minimal d'une vingtaine de lignes (un outil N1, un
réglage), les niveaux et ce que le Core fait de chacun, les services, comment tester son connecteur avec pytest sans
lancer Atlas ; le poste sert d'exemple complet.

## 10. Les tests

- **Le registre**, avec de faux connecteurs dans des dossiers temporaires : un manifeste invalide, un contrat
  inconnu, une dépendance absente, un réglage manquant, un code qui plante à l'import ou dans `creer`, un nom d'outil
  déjà pris, un doublon aux deux endroits, un identifiant hors motif ; les interrupteurs rangés et relus ; aucun code
  exécuté avant l'activation.
- **Le serveur « atlas »** reconstruit avec les connecteurs actifs, et la conversation neuve qui suit une bascule (le
  résumé, puis les nouveaux outils et les nouvelles consignes).
- **Les messages et la rubrique** de la page, l'avertissement « Communauté », « Prend effet à ta prochaine question. ».
- **Le poste**, dont tous les tests passent désormais par son connecteur ; et le connecteur minimal du guide.
- **Jamais** le vrai Claude ni un vrai `make install` dans `make test`.
- **À la main, par David**, sur le M5 : les critères du §1.

## 11. Hors périmètre

- L'enfermement du code d'un connecteur ; installer un connecteur depuis la page ou depuis Internet.
- Des connecteurs dans d'autres langages (serveurs MCP) ; des tâches de fond propres à un connecteur (il en faudra pour
  le point du matin).
- Des réglages saisis dans la page ; une bascule sans conversation neuve.
- L'agenda iCloud et Gmail : leurs specs suivent celle-ci.

## 12. Changements dans la spec parente

- **§9 :** les outils d'Atlas se répartissent entre le socle (mémoire, documents, recherche web) et des connecteurs,
  un dossier chacun, découverts automatiquement et activés depuis la page ; c'est ainsi que se réalise « un fichier par
  outil, découverte automatique ».
- **§15 :** l'étape 2 de la feuille de route commence par le cadre des connecteurs.

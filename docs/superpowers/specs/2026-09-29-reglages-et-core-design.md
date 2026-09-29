# Les réglages des connecteurs et le Core, depuis la page — design

**Date :** 29 septembre 2026
**Statut :** design validé par David, section par section
**Spec parente :** `2026-09-28-connecteurs-design.md` (le registre, les réglages déclarés par un manifeste, la bascule
qui prend effet à la question suivante) ; s'appuie sur `2026-09-22-atlas-design.md` (§12 la page, §13 le néo)
**Approche retenue :** la page modifie les réglages déclarés par les connecteurs, que le Core écrit dans son `.env` et
applique aussitôt ; deux boutons redémarrent le Core, avec ou sans mise à jour, en le faisant sortir proprement et
relancer par `make run-core`, qui relit le `.env`

## 1. Objectif et critères de réussite

Après l'essai des connecteurs, David demande deux choses :

- **redémarrer le Core depuis la page**, parce que le redémarrer depuis le Terminal n'est pas facile, surtout quand
  le Core tourne sur une autre machine (le néo) ;
- **modifier le `.env` depuis la page**, pour régler un connecteur sans ouvrir de Terminal.

Sa troisième demande, l'interrupteur des connecteurs habillé comme « Hey Atlas », est faite à part (PR #15).

| Critère | Objectif, vérifié par David sur le M5 |
|---|---|
| Régler | Le connecteur « bonjour » du guide, « à configurer » : David saisit `ATLAS_BONJOUR_NOM` dans la page ; il devient activable aussitôt, sans redémarrage ; activé, « Salue-moi. » répond avec ce nom |
| Changer | David change le nom : « Prend effet à ta prochaine question. » ; la question suivante salue le nouveau nom |
| Secret | Un réglage secret s'affiche « défini », jamais sa valeur ; David le remplace, puis l'efface |
| Clé d'Atlas | La clé du poste s'affiche « se change au Terminal », sans champ |
| Redémarrer | Le bouton, confirmé, redémarre le Core ; la page dit « Redémarrage du Core… », puis revient en ligne seule |
| Mettre à jour, refus | Le dépôt sur une autre branche que `main` : la page dit pourquoi, rien ne change |
| Mettre à jour | Sur `main` : « Atlas est déjà à jour. », ou les nouveautés, l'installation, puis le redémarrage |
| Non-régression | `make test` au vert |

## 2. Décisions

- **D1. Seuls les réglages des connecteurs se modifient dans la page.** Chaque connecteur montre ses réglages dans sa
  ligne. Les clés d'Atlas (le jeton Claude, les clés de la page, du client audio et du poste, et tout ce que lit la
  configuration du Core) restent au Terminal.
- **D2. Un secret va de la page au Core, jamais dans l'autre sens.** La page sait seulement s'il est défini ; elle
  peut le remplacer ou l'effacer.
- **D3. Un réglage prend effet tout de suite**, comme une bascule : un connecteur « à configurer » devient
  activable aussitôt ; un connecteur actif se recharge à la question suivante, dans une conversation neuve.
- **D4. Deux boutons :** « Redémarrer » et « Mettre à jour et redémarrer ».
- **D5. Le Core redémarre en sortant proprement**, avec une marque « redémarre-moi », et `make run-core` le relance
  par un `make` neuf, qui relit le `.env`. Le même chemin sert dans un Terminal sur le M5 et sous launchd sur le néo.
- **D6. La mise à jour est faite par le Core** : `git pull` en avance rapide seulement, puis `make install`, puis le
  redémarrage ; seulement sur `main`, sans fichier suivi modifié ; un échec n'entraîne aucun redémarrage.

## 3. Architecture

```
Page ── Paramètres › Connecteurs : « Réglages » dans la ligne de chaque connecteur
     ── Paramètres › Le Core : version, « Redémarrer », « Mettre à jour et redémarrer »
          │  /ws/web (authentifiée comme aujourd'hui)
Core ── routage des messages de la page (module à part)
     ── reglages.py : vérifier et écrire le .env ; appliquer tout de suite (registre, mémoire)
     ── entretien.py : redémarrer ; mettre à jour (git, make install), étapes publiées aux pages
          │  sortie propre + marque donnees/redemarrer
make run-core ── boucle : relance le Core par un make neuf tant qu'il laisse la marque
```

| Fichier | Rôle |
|---|---|
| `src/atlas_core/reglages.py` (nouveau) | Les clés d'Atlas, la vérification d'un réglage, la lecture et l'écriture du `.env` |
| `src/atlas_core/entretien.py` (nouveau) | La version qui tourne, les garde-fous, la mise à jour, la demande de redémarrage |
| `src/atlas_core/routage_pages.py` (nouveau) | Le traitement des messages d'une page, sorti de `hub.py` (qui approche 500 lignes) |
| `src/atlas_core/registre.py` | Les réglages de chaque fiche ; recharger un connecteur actif |
| `src/atlas_core/memoire.py` | Ajouter un secret à ceux qu'elle refuse d'écrire |
| `src/atlas_core/protocole_web.py`, `pages.py` | Les messages nouveaux ; les réglages dans `liste_connecteurs` |
| `src/atlas_web/reglages.js`, `core.js` (nouveaux) | Le formulaire des réglages ; la rubrique « Le Core » |
| `Makefile` | `run-core` devient la boucle de relance |

## 4. Les réglages

**Dans la page.** Un connecteur qui déclare des réglages a un bouton « Réglages » dans sa ligne. Il ouvre un champ par
réglage, avec la description du manifeste et le nom de la variable en petit, et un bouton « Enregistrer ».

- Un **réglage ordinaire** montre sa valeur, modifiable ; le vider le retire du `.env`.
- Un **secret** montre « défini » ou « à définir », jamais sa valeur ; un champ masqué le remplace, « Effacer » le
  retire ; un champ laissé vide ne change rien.
- Une **clé d'Atlas** déclarée par un manifeste (la clé du poste) montre « défini » ou « à définir » et « se change
  au Terminal », sans champ.

**Ce que le Core accepte.** Il vérifie tout ; la page ne décide rien.

- Le connecteur est découvert et a un manifeste lisible, quel que soit son état.
- Chaque variable est déclarée par **ce** connecteur.
- Aucune variable n'est une **clé d'Atlas** : toute variable que lit la configuration du Core (`config.py`), tenue dans
  une liste que les tests comparent au code. Un manifeste ne peut déclarer que des `ATLAS_…` : le jeton Claude est
  donc hors d'atteinte par construction.
- Une valeur est un texte d'une ligne, sans caractère de contrôle, sans espace au début ni à la fin, 4 096
  caractères au plus.
- Un refus ne change rien ; la page qui a demandé reçoit le message.

**L'écriture du `.env`.** Le fichier est celui que `make` lit : `.env` à la racine du dépôt.

- Le Core relit le fichier juste avant d'écrire (David peut l'avoir modifié à la main), remplace la ligne
  `VARIABLE=…` de la variable, ou l'ajoute à la fin, et laisse tout le reste tel quel : commentaires, ordre, autres
  variables, lignes qu'il ne comprend pas.
- L'écriture est atomique (un fichier voisin, puis un renommage), et le fichier finit en 600, lisible par David seul.
- La valeur est écrite pour que `make` la relise à l'identique : un `$` ou un `#` y est protégé. Une valeur que
  `make` ne saurait pas relire à l'identique est refusée. Les tests le vérifient avec le vrai `make`.
- Un secret n'est jamais journalisé, ni renvoyé à une page, pas même sa longueur.

**L'effet, tout de suite.**

- Le Core met la nouvelle valeur dans son environnement et relit les connecteurs ; toutes les pages reçoivent la
  liste à jour.
- Un connecteur actif est rechargé avec ses nouveaux réglages ; son interrupteur ne change pas ; la conversation se
  renouvelle comme pour une bascule, et la page dit « Prend effet à ta prochaine question. ». S'il ne se recharge
  pas, il passe « en erreur », comme à une activation.
- Un nouveau secret rejoint aussitôt ceux que la mémoire refuse d'écrire.
- Un réglage n'est jamais une clé d'Atlas : la configuration du Core, lue au démarrage, ne change pas.

## 5. Le redémarrage

**Dans la page.** Une rubrique « Le Core », en bas des Paramètres : la version qui tourne (commit court et date),
« Redémarrer » et « Mettre à jour et redémarrer ». « Redémarrer » demande : « Redémarrer le Core ? La conversation en
cours se clôt, avec son résumé au journal. Atlas revient dans une dizaine de secondes. »

**Le Core.**

- Il publie à toutes les pages « Redémarrage du Core… ». Pendant un redémarrage ou une mise à jour, une nouvelle
  demande est refusée.
- Il écrit la marque `donnees/redemarrer`, puis s'arrête comme à un Ctrl-C : la conversation se clôt avec son résumé
  au journal, une mission en cours s'arrête, une confirmation en attente est abandonnée.
- Au démarrage, il efface une marque restée là.

**Le lanceur.** `make run-core` devient une petite boucle :

- elle efface la marque, puis lance le Core par un `make` neuf, qui relit le `.env` ;
- quand le Core s'arrête, elle le relance s'il a laissé la marque, et s'arrête sinon (Ctrl-C, ou le Core qui tombe :
  sur le néo, launchd le relance comme aujourd'hui) ;
- une variable retirée du `.env` ne survit pas à la relance : la boucle ne transmet pas au `make` neuf les variables
  que le `.env` avait données au premier ;
- la commande ne change pas pour David, ni le service du néo.

**La page.** La barre du haut dit « Redémarrage du Core… », puis la page se reconnecte d'elle-même, comme
aujourd'hui, et redemande la version. Si le Core n'est pas revenu au bout d'une minute, elle le dit : « Le Core ne
revient pas : regarde son journal (`donnees/logs/core.log` sur le néo). » Le client audio et le poste se reconnectent
déjà seuls.

## 6. La mise à jour

« Mettre à jour et redémarrer » demande : « Mettre Atlas à jour ? Le Core récupère la dernière version, installe ce
qui manque, puis redémarre. La conversation en cours se clôt. »

**Les garde-fous**, vérifiés avant de rien toucher, et encore au moment du clic. Si l'un manque, le Core refuse, la
page qui a demandé dit pourquoi et renvoie au Terminal, et rien ne change.

- Le dépôt du Core est sur `main`.
- Aucun fichier suivi par git n'est modifié ; les fichiers non suivis et le `.env` ne comptent pas.
- Aucun redémarrage ni aucune mise à jour n'est en cours.

La page le sait d'avance : `etat_core` dit si la mise à jour est possible, et pourquoi sinon ; le bouton est alors
grisé, avec la raison.

**Les étapes**, publiées à toutes les pages :

1. « Récupération… » : `git pull --ff-only`. Rien n'est jamais fusionné, écrasé ni poussé. S'il n'y a rien de neuf :
   « Atlas est déjà à jour. », sans redémarrage. Sinon, les nouveautés : les titres des nouveaux commits, cinq au
   plus, puis « et N autres ».
2. « Installation… » : `make install` (les dépendances d'Atlas, puis celles des connecteurs).
3. Le redémarrage, comme au §5.

Pendant ce temps, Atlas continue de répondre. La sortie des commandes va aussi dans le journal du Core.

**Les échecs.** Aucun ne redémarre le Core ; la page montre les dernières lignes de l'erreur.

- `git pull` échoue (réseau, historique divergent) : rien n'a changé.
- `make install` échoue : le code est à jour, mais le Core continue avec l'ancienne version. « L'installation a
  échoué : relance `make install` au Terminal avant de redémarrer. »
- Un connecteur de la communauté qui ne s'installe pas ne fait pas échouer `make install` : il reste « à installer ».
- Délais : 2 minutes pour `git pull`, 10 minutes pour `make install`. Au-delà, la commande est arrêtée : c'est un
  échec.

## 7. Les messages

| Message | Sens | Contenu |
|---|---|---|
| `regler_connecteur` | page → Core | `id`, `valeurs` (variable → valeur), `effacer` (variables) |
| `resultat_reglage` | Core → la page qui a demandé | `id`, `ok`, `message` |
| `liste_connecteurs` | Core → pages | gagne, par connecteur, `reglages` : `variable`, `description`, `secret`, `defini`, `modifiable`, et `valeur` pour un réglage ordinaire seulement |
| `demande_core` | page → Core | — |
| `etat_core` | Core → la page qui a demandé | `version`, `date`, `occupe`, `mise_a_jour_possible`, `raison` |
| `redemarrer_core`, `mettre_a_jour_core` | page → Core | — |
| `core_en_cours` | Core → pages | `etape` (`redemarrage`, `recuperation`, `installation`), `texte`, `nouveautes` |
| `fin_core` | Core → pages (un refus : la page qui a demandé) | `ok`, `texte`, `details` (les dernières lignes d'une erreur) |

Les textes des manifestes et des commits sont toujours affichés comme du texte.

## 8. Sécurité et erreurs

- Tout passe derrière l'authentification actuelle de la page ; les confirmations sont celles de la page, comme pour
  un connecteur « Communauté ».
- Les variables permises : celles que déclare le connecteur, jamais une clé d'Atlas ; chaque valeur est vérifiée.
- Un secret ne sort jamais du Core : ni vers une page, ni dans le journal.
- Aucun texte venu de la page n'entre dans une commande : `git` et `make` sont lancés avec des arguments fixes, dans
  le dépôt du Core, avec des délais fixes.
- Un seul redémarrage ou une seule mise à jour à la fois.
- Une écriture du `.env` qui échoue (disque plein, droits) est un refus : le `.env` et l'environnement du Core ne
  changent pas.

## 9. Les tests

- **Réglages** : des valeurs avec `$`, `#`, des guillemets, des accents, des barres obliques inverses, relues par le
  vrai `make` à l'identique ; refusés : un manifeste de la communauté qui déclare `ATLAS_WEB_CLE`, une variable non
  déclarée, un retour à la ligne, une valeur trop longue ; le reste du `.env` intact (commentaires, ordre, lignes
  inconnues) ; le fichier en 600 ; une écriture qui échoue ne change rien ; la liste des clés d'Atlas comparée aux
  variables que lit `config.py`.
- **Effet immédiat** : « à configurer » devient « coupé » ; un connecteur actif rechargé avec ses nouveaux réglages,
  en attente jusqu'à la question suivante, la conversation renouvelée ; la mémoire refuse le nouveau secret ; un
  secret n'apparaît dans aucun message ni dans le journal.
- **Mise à jour**, sur un vrai dépôt git temporaire (un dépôt d'origine local, sans réseau) : chaque garde-fou ;
  « déjà à jour » ; les nouveautés listées ; un historique divergent ; `make install` qui échoue ; un délai dépassé ;
  une deuxième demande pendant la première.
- **Redémarrage** : la marque écrite, puis l'arrêt demandé ; une marque restée là effacée au démarrage.
- **Boucle de relance** : le vrai `make` lance un faux Core qui laisse la marque une fois ; il est relancé une seule
  fois ; une variable retirée du `.env` entre les deux a disparu ; sans marque, la boucle s'arrête.
- **Page** : un secret jamais pré-rempli ; un champ secret vide n'envoie rien ; « Effacer » ; une clé d'Atlas sans
  champ ; les confirmations ; les étapes et les nouveautés affichées ; le bouton de mise à jour grisé avec sa raison ;
  « ne revient pas » au bout d'une minute ; les textes affichés comme du texte.
- **Jamais** dans `make test` : un vrai `git pull` sur le dépôt de David, un vrai `make install`, ni un redémarrage de
  son Core.

## 10. Hors périmètre

- Modifier les clés d'Atlas depuis la page.
- Mettre à jour depuis une autre branche que `main`, ou revenir en arrière après une mise à jour.
- Lire le journal du Core dans la page.
- Les mises à jour automatiques.
- Redémarrer le client audio ou le poste depuis la page : ils se reconnectent seuls.

## 11. Changements dans les autres documents

- **Spec des connecteurs** : D2 et §7 disent désormais qu'un secret peut aller de la page au Core, jamais dans
  l'autre sens, et que les réglages se modifient dans la page (ce document, §4).
- **Guide des connecteurs** (`connecteurs/LISEZMOI.md`) : les réglages se saisissent aussi dans la page ; une clé
  d'Atlas déclarée comme réglage reste au Terminal.
- **Guide du néo** (`scripts/neo/LISEZMOI.md`) : redémarrer et mettre à jour depuis la page ; le Terminal reste
  possible.

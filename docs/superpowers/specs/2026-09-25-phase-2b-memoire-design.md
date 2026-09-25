# Phase 2b : la mémoire — design

**Date :** 25 septembre 2026
**Statut :** design validé par David, section par section
**Spec parente :** `2026-09-22-atlas-design.md` (§6.2 le Brain et sa rotation de contexte, §8 la mémoire, §9 les outils,
§13 la sécurité, §15 le phasage) ; s'appuie sur `2026-09-24-phase-2a-cerveau-design.md` (le cerveau)
**Approche retenue :** des outils mémoire servis par le Core lui-même (approche A) — chaque écriture passe par le Core,
qui vérifie, commite et annonce

## 1. Objectif et critères de réussite

Aujourd'hui, la conversation avec Atlas repart de zéro après trente minutes sans échange : il ne se souvient de rien
d'un jour à l'autre. La phase 2b lui donne une mémoire à deux étages : **le fil entre les jours** (un résumé de chaque
conversation, relu au début des suivantes) et **les faits à retenir** (des fiches : le profil de David, l'entreprise,
les projets, les personnes), qu'Atlas tient de lui-même en l'annonçant.

| Critère | Objectif, vérifié par David sur le M5 |
|---|---|
| Se présenter | « Appelle-moi Dieu » : annoncé, noté dans le profil, appliqué tout de suite et aux conversations suivantes |
| Un fait qui dure | « J'ai deux enfants, de 18 mois et 4 ans et demi » : noté avec des dates de naissance approximatives ; à la conversation suivante, « quel âge ont mes enfants ? » reçoit une réponse juste |
| Une fiche | « Note que mon rendez-vous avec Paul Durand est jeudi » : la fiche `personnes/paul-durand.md`, avec la date écrite en entier, et l'annonce |
| Annuler | « Annule » défait la dernière note d'Atlas, et le dit |
| Un secret | « Note mon mot de passe : … » : refusé, et Atlas le dit |
| Le fil entre les jours | Passé le délai d'oubli, le résumé est dans le journal ; la conversation suivante s'en sert (« de quoi on a parlé tout à l'heure ? ») |
| Rien ne sort | La mémoire n'est dans aucun dépôt poussé |
| Non-régression | `make test` au vert |

## 2. Décisions

- **D1. Les deux étages.** Le journal (automatique) et les fiches (tenues par Atlas).
- **D2. Atlas écrit les fiches de lui-même, et l'annonce** en une phrase (niveau N2 de la spec parente). David peut
  dire « annule ».
- **D3. Un dépôt git local** sur la machine du Core, jamais poussé : rien ne quitte la maison. La sauvegarde est celle
  de la machine.
- **D4. Pas d'index vectoriel en 2b.** La mémoire tient d'abord en quelques dizaines de fiches : Atlas en voit le
  sommaire et cherche dans le texte. L'index viendra quand elle aura grossi.
- **D5. Le journal s'écrit tout seul, sans annonce** : c'est le compte-rendu de ce qui s'est dit, pas un fait nouveau.
  C'est la seule exception à la règle « Atlas n'écrit jamais en silence » de la spec parente.
- **D6. Des outils servis par le Core (approche A).** Un serveur d'outils MCP tourne dans le Core, par le SDK de
  Claude. Chaque écriture passe par le Core : chemin vérifié, secret refusé, commit, annonce garantie. C'est le serveur
  que la phase 2c complétera avec ses autres outils et ses niveaux d'autorisation.
- **D7. Les faits s'écrivent sous une forme qui reste vraie** : une date de naissance approximative plutôt qu'un âge,
  une date plutôt que « jeudi ».
- **D8. Tout sur le M5 pour l'instant** ; la mémoire suivra le Core sur le néo au déploiement.

## 3. Architecture

```
Question ─► CerveauClaude ──── amorçage (profil, sommaire, journal) ─┐
                 │                                                   ▼
                 │                                        Claude (SDK, abonnement)
                 │                                                   │ outils
                 │                                                   ▼
                 │                               serveur « atlas » (dans le Core)
                 │                               memoire_lire / chercher / ecrire / annuler
                 │                                                   │
                 │   Note (ce qui a été écrit) ◄─────────────────────┤
                 ▼                                                   ▼
             Session : « Je le note dans la fiche Paul Durand. »   Memoire : ~/.atlas/memoire (git)
```

| Fichier | Rôle |
|---|---|
| `src/atlas_core/memoire.py` (nouveau) | Le dépôt de la mémoire : lire, chercher, écrire, annuler, le sommaire, l'amorçage, le journal ; les vérifications (chemin, format, secrets) et les commits git |
| `src/atlas_core/outils_memoire.py` (nouveau) | Le serveur d'outils « atlas » et ses quatre outils ; il signale au cerveau chaque écriture à annoncer |
| `src/atlas_core/cerveau.py` | Le marqueur `Note`, comme `Recherche` |
| `src/atlas_core/cerveau_claude.py` | Les outils mémoire dans les options de Claude ; l'amorçage de chaque nouvelle conversation ; le résumé à l'échéance et à l'arrêt |
| `src/atlas_core/consignes.py` | Les consignes de la mémoire, le bloc d'amorçage, la demande de résumé |
| `src/atlas_core/session.py` | L'annonce d'une note |
| `src/atlas_core/config.py` | `memoire_dossier` |
| `src/atlas_core/hub.py` | La mémoire ouverte au démarrage et confiée au cerveau |

La voix, les pages, la régie et les clients audio ne changent pas. Le dépôt public d'Atlas ne contient que le code :
jamais une ligne de la mémoire de David.

## 4. Le contenu de la mémoire

Le dossier `~/.atlas/memoire` (réglage `ATLAS_MEMOIRE_DOSSIER`), selon la spec parente :

```
profil.md                 qui est David, comment il travaille, ses préférences
entreprise/<nom>.md       la vision, les offres, decisions.md (les arbitrages, avec leur raison)
projets/<nom>.md          l'état, les bloqueurs, la prochaine action
personnes/<nom>.md        contacts, prospects, historique des échanges
journal/AAAA-MM-JJ.md     les résumés des conversations du jour, écrits par le Core seul
documents/                réservé à la phase 2c
```

- **Claude n'écrit que les fiches** : `profil.md`, et `<nom>.md` dans `entreprise/`, `projets/` et `personnes/`. Un nom
  est en minuscules, chiffres et tirets, 60 caractères au plus (`personnes/paul-durand.md`).
- **Une fiche** commence par son titre (`# Paul Durand`, 100 caractères au plus), une ligne vide, puis une phrase de
  résumé (200 caractères au plus) ; le reste est libre, 20 000 caractères au plus en tout. Le Core refuse une fiche qui
  ne suit pas ce format, et dit pourquoi à Claude, qui corrige. Le titre sert à l'annonce, la phrase de résumé au
  sommaire.
- **Au premier démarrage**, le dossier est créé et `git init` y est lancé ; la mémoire est vide. Atlas remplit le profil
  et les fiches au fil des conversations.
- **David reste libre** de lire et de corriger les fichiers à la main : Atlas voit tout de suite ce qui est sur le
  disque. Le Core ne commite que les fichiers qu'il écrit ; les retouches de David, David les commite s'il le veut.

## 5. Les outils et l'écriture

Le serveur d'outils s'appelle `atlas` ; Claude voit ses outils sous les noms `mcp__atlas__memoire_…`.

| Outil | Ce qu'il fait |
|---|---|
| `memoire_lire(chemin)` | Rend le contenu d'un fichier de la mémoire (fiche ou journal), ou dit qu'il n'existe pas |
| `memoire_chercher(texte)` | Cherche dans les fiches et le journal, sans tenir compte des majuscules ni des accents ; rend au plus vingt lignes trouvées, chacune avec son fichier |
| `memoire_ecrire(chemin, contenu)` | Crée ou remplace une fiche entière, après les vérifications ; puis la commite et la fait annoncer |
| `memoire_annuler()` | Défait la dernière écriture d'Atlas encore en place (`git revert`), et la fait annoncer |

- **Les vérifications d'une écriture**, dans l'ordre : le chemin (§8), le format (§4), l'absence de secret (§8). Un refus
  rend à Claude sa raison en une phrase, qu'il dit à David ; rien n'est écrit.
- **Le commit** : le fichier seul, sous l'auteur « Atlas », avec le message « Atlas : <titre> ». Une seule écriture à la
  fois (un verrou).
- **L'annonce** : l'outil signale au cerveau ce qui a été écrit, et le cerveau le passe à la session par un marqueur
  `Note`, à sa place dans la réponse, comme `Recherche`. La session dit une phrase, affichée aussi en sous-titre :
  - « Je le note dans ton profil. » pour `profil.md` ;
  - « Je le note dans la fiche <titre>. » pour une autre fiche ;
  - « J'ai retiré ma dernière note. » après `memoire_annuler`.

  Deux écritures dans une même réponse font deux annonces. En mode muet, ou sur une session sans voix, l'annonce ne
  s'affiche qu'en texte.
- **Annuler** : redire « annule » remonte d'une note. Seuls les commits d'Atlas sur les fiches s'annulent : ni le
  journal, ni les commits de David. Si la fiche a été modifiée depuis et que le `git revert` échoue, rien ne change et
  Claude le dit.
- **Les consignes** données à Claude (`consignes.py`) :
  - noter les décisions, les faits durables sur David, un projet ou une personne, et ses préférences ; pas les
    banalités ;
  - des fiches courtes, des faits datés, sous une forme qui reste vraie (D7) ;
  - relire une fiche avant de la modifier, puisque l'écriture la remplace en entier ;
  - ne pas annoncer lui-même qu'il note : Atlas le dit pour lui ;
  - « annule », « oublie ça » ou « ne note pas ça » juste après une note : appeler `memoire_annuler` ;
  - appeler David comme son profil l'indique, et « David » tant que le profil ne dit rien d'autre ;
  - il peut désormais réfléchir, chercher sur le web et tenir sa mémoire, et rien d'autre.

## 6. L'amorçage d'une conversation

La première question de chaque conversation neuve part précédée d'un bloc de mémoire, avant la ligne de date :

- **le profil** en entier, 4 000 caractères au plus ;
- **le sommaire** : une ligne par fiche, son chemin et sa phrase de résumé, 150 lignes au plus ;
- **le journal des sept derniers jours** : les résumés, 6 000 caractères au plus, les plus récents gardés en priorité.

Une mémoire vide donne « La mémoire est vide. ». Le bloc est délimité (« [Mémoire d'Atlas] … [Fin de la mémoire] »)
et les consignes l'expliquent : c'est ce qu'Atlas sait déjà, et il peut lire une fiche en entier avec `memoire_lire`.

## 7. Le journal et la fin d'une conversation

- **À l'échéance** (`ATLAS_CERVEAU_OUBLI_MIN` minutes, trente par défaut, après la fin du dernier échange), une tâche de
  fond, sans attendre la question suivante :
  1. demande à Claude, dans la même conversation et sans rien dire à voix haute, un résumé : ce qui s'est dit, ce qui a
     été décidé, ce qui reste à faire, en quelques phrases, sans rien inventer ; « RIEN » s'il n'y a rien à garder ;
  2. l'ajoute à `journal/AAAA-MM-JJ.md` (le jour de la fin de la conversation), sous l'heure de début et de fin
     (« ## 14 h 05 – 14 h 32 ») ; un fichier neuf commence par « # Journal du 25 septembre 2026 » ;
  3. le commite en silence (« Journal : 25 septembre 2026, 14 h 32 ») ;
  4. ferme la conversation. La question suivante en ouvre une neuve, déjà amorcée.
- **Pendant le résumé, Claude ne peut rien écrire** : les outils d'écriture refusent, quoi que Claude tente. Le résumé
  ne va ni à la session ni aux pages.
- **Une question qui arrive pendant le résumé** attend qu'il finisse : une question à la fois, comme aujourd'hui.
- **Le résumé a un délai** : 60 secondes à l'échéance, 20 à l'arrêt du Core. Passé ce délai, ou si Claude est
  injoignable ou à la limite de l'abonnement, rien n'est écrit, la conversation est fermée quand même, et le journal
  technique du Core le note.
- **Une conversation sans question** ne se résume pas. Une conversation perdue (« Je reprends de zéro, j'ai perdu le
  fil ») ne peut plus rien résumer ; la suivante est amorcée comme les autres.
- **Le contexte qui se remplit** pendant une longue conversation reste confié au compactage automatique de Claude Code.
  La rotation de la spec parente se fait donc à l'échéance : un résumé au journal, puis une conversation neuve amorcée.
- **Le coût** : un appel à Claude de plus par conversation.

## 8. Sécurité et erreurs

- **Les chemins** : un chemin est résolu, puis doit rester sous le dossier de la mémoire (aucun `..`, aucun lien
  symbolique qui en sorte), en `.md`, dans un dossier autorisé (§4). La lecture accepte aussi `journal/`.
- **Les secrets**, refusés avant tout commit (spec parente §13) :
  - des clés et jetons reconnaissables : `sk-…`, `sk-ant-…`, `ghp_…`, `github_pat_…`, `AKIA…`, `xox…-`, `AIza…`, les
    en-têtes `-----BEGIN … PRIVATE KEY-----` ;
  - « mot de passe », « mdp », « password » ou « passwd » suivi d'une valeur (« : », « = », « est ») ;
  - les valeurs des clés du Core lui-même (`ATLAS_WEB_CLE`, `ATLAS_AUDIO_CLE`, `CLAUDE_CODE_OAUTH_TOKEN`), si elles
    sont définies.
- **Claude reste enfermé** : la recherche web et les quatre outils mémoire, rien d'autre ; toujours aucun réglage ni
  `CLAUDE.md` de la machine, et aucun fichier hors de la mémoire.
- **La mémoire n'est jamais poussée** : aucun dépôt distant n'est configuré, et le Core ne lance jamais `git push`.
- **Sans mémoire** : si `git` manque ou si le dossier ne peut pas être créé, Atlas marche comme en 2a (ni outils, ni
  amorçage, ni journal). Le journal technique du Core le dit une fois, au démarrage.
- **Les commandes git** tournent hors de la boucle du Core (`asyncio.to_thread`) et ne dépendent pas de la
  configuration git de la machine (auteur et adresse passés à chaque commit).

## 9. Réglages

| Variable | Défaut | Rôle |
|---|---|---|
| `ATLAS_MEMOIRE_DOSSIER` | `~/.atlas/memoire` | Le dépôt de la mémoire |
| `ATLAS_CERVEAU_OUBLI_MIN` | 30 | Existant : le délai après lequel la conversation se résume et se ferme |

## 10. Les tests

- **La mémoire** (dépôts git temporaires) : écrire, lire, chercher (accents, majuscules, plafond), annuler (et remonter,
  sans toucher au journal ni aux commits de David, et le refus après une retouche), les secrets, les chemins interdits
  (`..`, lien symbolique, extension, dossier), le format d'une fiche, le sommaire, l'amorçage et ses plafonds, le
  journal (fichier neuf, ajout, « RIEN »), la mémoire indisponible.
- **Les outils** : appelés directement ; l'annonce signalée ; le refus pendant le résumé.
- **Le cerveau**, avec la doublure du SDK de la phase 2a : l'amorçage de la première question d'une conversation (et
  pas des suivantes) ; le résumé à l'échéance, puis la conversation fermée ; la question qui arrive pendant le résumé ;
  le résumé à l'arrêt, ses délais et ses échecs. Jamais le vrai Claude dans `make test`.
- **La session** : l'annonce d'une note, à sa place dans la réponse, et en texte seulement en mode muet.
- **À la main, par David**, sur le M5, avec `ATLAS_CERVEAU_OUBLI_MIN=2` pour ne pas attendre : les critères du §1.

## 11. Hors périmètre

- L'index vectoriel (D4).
- Les documents, et la réflexion transformée en document (phase 2c).
- Les autres outils, et les niveaux d'autorisation N1 à N3 (phase 2c).
- La mémoire sur le néo (au déploiement) ; un dépôt distant pour la mémoire.

## 12. Changements dans la spec parente

- **§8 :** en 2b, pas d'index vectoriel (D4) ; le dépôt est local, jamais poussé (D3) ; le journal s'écrit sans
  annonce (D5).
- **§6.2 :** la rotation de contexte se fait à l'échéance de l'oubli, par un résumé au journal ; le compactage de
  Claude Code gère une conversation qui dure.
- **§9 :** le serveur MCP d'Atlas tourne dans le Core, par le SDK de Claude, et non en stdio.
- **§15 :** la phase 2b est décrite par cette spec.

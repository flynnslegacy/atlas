# Phase 2c : les outils et les permissions — design

**Date :** 25 septembre 2026
**Statut :** design validé par David, section par section
**Spec parente :** `2026-09-22-atlas-design.md` (§8 la mémoire, §9 les outils, §10 les permissions, §15 le phasage) ;
s'appuie sur `2026-09-25-phase-2b-memoire-design.md` (la mémoire et le serveur d'outils « atlas »)
**Approche retenue :** l'action en attente, tenue par le Core (approche A) — une action N3 n'est jamais exécutée par
l'outil que Claude appelle : le Core la met de côté, formule lui-même la question, et tranche sur la réponse suivante
de David

## 1. Objectif et critères de réussite

Atlas se souvient, mais il ne produit rien qui se garde en dehors de ses fiches, et tous ses outils agissent de la même
façon. La phase 2c lui donne **la réflexion transformée en document** — David réfléchit à voix haute, puis demande un
document structuré, qu'il lit dans la page — et **les niveaux d'autorisation** de la spec parente : chaque outil
déclare le sien, et le Core applique la règle ; une action N3 attend le « oui » de David.

| Critère | Objectif, vérifié par David sur le M5 |
|---|---|
| Réflexion vers document | Après quelques minutes de réflexion à voix haute, « fais-en un document » : annoncé, visible dans le panneau « Documents », et il se relit sans retouche (critère de la phase 2, spec parente §15) |
| Retouche | « Ajoute une partie sur les prix » : le document est réécrit, l'écriture annoncée ; « annule » le ramène à sa version précédente |
| Suppression confirmée | « Supprime ce document » : « Je supprime le document <titre>. Tu confirmes ? » ; « oui » : supprimé, et annoncé ; « annule » juste après le remet |
| Pas de oui, pas d'action | « Non », trente secondes de silence, ou une autre phrase : rien n'est supprimé |
| Le bouton | La confirmation par le bouton « Confirmer » de la page, depuis l'iPhone |
| Les niveaux | Lire ou chercher dans la mémoire ne s'annonce pas ; écrire s'annonce |
| Non-régression | `make test` au vert |

## 2. Décisions

- **D1. Les deux.** Les documents comme premier vrai usage, et les niveaux N1, N2 et N3 avec la confirmation, prêts
  pour les outils de la phase 3 (n8n).
- **D2. Les documents se lisent dans la page d'Atlas** : un panneau « Documents », sur l'iPhone comme sur le Mac. Ils
  restent dans la mémoire locale : rien ne quitte la maison.
- **D3. Un document naît à la demande de David.** Il réfléchit, puis dit « fais-en un document » ; Atlas l'écrit en
  entier et l'annonce (N2). David le retouche à la voix ; chaque version est gardée, « annule » revient à la
  précédente. Atlas peut suggérer d'en faire un, jamais l'écrire de lui-même.
- **D4. En N3 dès la 2c : supprimer une fiche ou un document.** Les écritures restent N2 : faites, puis annoncées.
- **D5. Confirmer à la voix, au clavier ou d'un bouton.** Atlas reformule l'action exacte ; sans réponse claire dans les
  trente secondes, c'est non.
- **D6. L'action en attente, tenue par le Core (approche A).** Seul David peut confirmer : ni Claude, ni un outil, ni
  une page web lue par Claude.
- **D7. Une liste explicite d'outils par famille**, chacun avec son niveau déclaré ; pas encore de découverte
  automatique « un fichier par outil » (écart avec la spec parente §9, §12).
- **D8. Tout sur le M5 pour l'instant** ; le déploiement sur le néo viendra après.

## 3. Architecture

```
Phrase de David ─► CerveauClaude : une action attend-elle un « oui » ?
                        │ oui, et la réponse est oui / non ─► le Core exécute ou abandonne, et le dit
                        │ sinon ─────────────────────────────► Claude, comme aujourd'hui
                        ▼
                  Claude ─► serveur « atlas » (dans le Core)
                              N1  memoire_lire, memoire_chercher            → fait, rien d'annoncé
                              N2  memoire_ecrire, document_ecrire,          → fait, puis annoncé (Note)
                                  memoire_annuler
                              N3  memoire_supprimer                         → mis en attente ; le Core fait
                                                                              dire la question (Confirmation)
Pages ◄── documents, confirmation en cours ── Core ◄── « Confirmer » / « Annuler », lecture des documents
```

| Fichier | Rôle |
|---|---|
| `src/atlas_core/outils.py` (nouveau) | La déclaration d'un outil et de son niveau ; la règle de chaque niveau, appliquée par le Core autour de l'outil ; le serveur « atlas » assemblé à partir des familles |
| `src/atlas_core/confirmation.py` (nouveau) | L'action en attente : une seule à la fois, son délai, la lecture de la réponse de David, l'exécution et les phrases |
| `src/atlas_core/outils_memoire.py` | Ses outils déclarés avec leur niveau ; `memoire_supprimer` (N3) |
| `src/atlas_core/outils_documents.py` (nouveau) | `document_ecrire` (N2) |
| `src/atlas_core/memoire.py` | Les documents, la suppression et son annulation, les documents dans le sommaire et la recherche ; s'il approche des 500 lignes, les documents prennent leur propre module |
| `src/atlas_core/cerveau.py` | Le marqueur `Confirmation`, comme `Note` |
| `src/atlas_core/cerveau_claude.py` | La réponse de David lue avant Claude ; la ligne qui dit le résultat à Claude ; l'abandon d'une action à la coupure et à la fin d'une conversation |
| `src/atlas_core/consignes.py` | Les consignes des documents, de la suppression et des lignes de résultat |
| `src/atlas_core/session.py` | La question de confirmation dite à sa place, comme une note |
| `src/atlas_core/protocole_web.py`, `hub.py` | Les messages des documents et de la confirmation ; le bouton traité comme une réponse tapée |
| `src/atlas_web/documents.js`, `markdown.js` (nouveaux) ; `app.js`, `index.html`, `style.css` | Le panneau « Documents », la mise en forme, les boutons « Confirmer » et « Annuler » |

La voix, la régie, les clients audio et `/ws/voix` ne changent pas.

## 4. Les niveaux d'autorisation

Chaque outil est déclaré avec son nom, sa description pour Claude, ses paramètres et son niveau. Le niveau est dans le
code : **Claude ne choisit jamais son niveau**, et le Core applique la règle autour de l'outil.

| Niveau | Règle appliquée par le Core |
|---|---|
| **N1** | L'outil s'exécute ; son résultat revient à Claude ; rien n'est annoncé |
| **N2** | L'outil s'exécute ; si quelque chose a changé, le Core fait annoncer ce qui a été fait (`Note`, comme en 2b) |
| **N3** | L'outil ne fait rien lui-même : il vérifie l'action et la décrit ; le Core la met en attente (§6), fait dire la question à David (`Confirmation`), et rend à Claude « En attente de la confirmation de David. N'ajoute rien, et ne dis pas que c'est fait. » |

| Outil | Niveau | Ce qu'il fait |
|---|---|---|
| `memoire_lire(chemin)` | N1 | Rend une fiche, un document ou un jour du journal |
| `memoire_chercher(texte)` | N1 | Cherche dans les fiches, les documents et le journal (comme en 2b, au plus vingt lignes) |
| `memoire_ecrire(chemin, contenu)` | N2 | Crée ou remplace une fiche (inchangé) |
| `document_ecrire(nom, contenu)` | N2 | Crée ou remplace `documents/<nom>.md` (§5) |
| `memoire_annuler()` | N2 | Défait la dernière écriture ou suppression d'Atlas encore en place |
| `memoire_supprimer(chemin)` | N3 | Supprime une fiche (profil compris) ou un document, après le « oui » de David |

- **Pendant le résumé de fin de conversation**, les outils N2 et N3 refusent, comme les écritures en 2b.
- **Les familles** (mémoire, documents) sont des listes explicites, assemblées en un seul serveur « atlas ». Un test
  vérifie que chaque outil a un niveau, et qu'un outil N3 ne change jamais rien sans confirmation.

## 5. Les documents

- **Le fichier** : `documents/<nom>.md`, le nom en minuscules, chiffres et tirets, 60 caractères au plus, comme les
  fiches. Il commence par « # Titre » (100 caractères au plus), une ligne vide, puis une phrase de résumé (200
  caractères au plus) ; le reste est un Markdown structuré. **50 000 caractères au plus** (une fiche : 20 000). Les
  vérifications de la 2b s'appliquent : chemin, format, secrets.
- **La syntaxe permise**, la même pour les consignes de Claude et pour la page : titres (`#`, `##`, `###`),
  paragraphes, listes à puces et numérotées, **gras**, *italique*, citations (`>`), `code`, tableaux simples (`|`), et
  liens `[texte](https://…)`.
- **L'écriture** : `document_ecrire(nom, contenu)` remplace le document entier, le commite sous l'auteur « Atlas »
  (« Atlas : <titre> ») et le fait annoncer :
  - « J'ai écrit le document <titre>, il est dans la page. » à la création ;
  - « J'ai mis à jour le document <titre>. » à une retouche.
- **Annuler** revient à la version précédente, comme pour une fiche. L'annonce dit ce qui a été défait :
  - « J'ai retiré le document <titre>. » pour une création ;
  - « Le document <titre> revient à sa version précédente. » pour une retouche ;
  - « J'ai retiré ma dernière note. » pour une fiche (inchangé) ;
  - « J'ai remis le document <titre>. », « J'ai remis la fiche <titre>. » ou « J'ai remis ton profil. » pour une
    suppression.
- **Ce qu'Atlas en sait** : le sommaire de l'amorçage liste aussi les documents, une ligne chacun (chemin et phrase de
  résumé), dans le même plafond de 150 lignes ; la recherche les couvre.
- **Les consignes** données à Claude :
  - un document seulement quand David le demande ; il peut le suggérer, jamais l'écrire de lui-même ;
  - un texte qui se relit sans retouche : un plan clair, des phrases complètes, rien d'inventé, la syntaxe permise
    seulement ;
  - après l'écriture, dire en deux ou trois phrases ce que contient le document, sans le lire à voix haute ;
  - pour une retouche, relire le document, puis le réécrire en entier ;
  - ne pas annoncer lui-même l'écriture : Atlas le dit pour lui.

## 6. La confirmation (N3)

- **La demande.** Claude appelle `memoire_supprimer(chemin)`. Le Core vérifie que le fichier existe et qu'il peut être
  supprimé (une fiche ou un document : ni le journal, ni un autre fichier), lit son titre, et prépare l'action. Un
  refus (fichier absent, chemin interdit) revient tout de suite à Claude : rien n'est mis en attente.
- **Une seule action à la fois.** Si une action attend déjà, l'outil refuse : « Une action attend déjà la réponse de
  David. »
- **La question**, formulée par le Core à partir de l'action résolue, jamais par Claude, et dite à sa place dans la
  réponse (marqueur `Confirmation`) :
  - « Je supprime le document <titre>. Tu confirmes ? »
  - « Je supprime la fiche <titre>. Tu confirmes ? »
  - « Je supprime ton profil. Tu confirmes ? »

  La relance (`ATLAS_RELANCE_S`, dix secondes) permet de répondre sans « Hey Atlas ». En mode muet, ou sur une
  session sans voix, la question ne s'affiche qu'en texte.
- **La réponse de David**, quelle qu'en soit la source (la voix de n'importe quel appareil, le clavier d'une page, un
  bouton), est lue par le Core avant Claude, comme toute question : elle coupe d'abord la réponse en cours. Le texte
  est comparé sans majuscules, accents ni ponctuation, un « Atlas » au début ou à la fin ignoré :
  - **oui** — exactement l'une de ces phrases : « oui », « ouais », « oui oui », « vas-y », « oui vas-y », « je
    confirme », « oui je confirme », « confirme », « d'accord », « oui d'accord », « ok », « oui ok », « c'est bon »,
    « oui c'est bon », « supprime », « oui supprime », « supprime-le », « supprime-la », « exactement », « tout à
    fait » : le Core exécute (un commit « Atlas : suppression de <titre> ») et répond « C'est fait : le document
    <titre> est supprimé. » (« la fiche <titre> est supprimée », « ton profil est supprimé ») ; la réponse ne passe
    pas par Claude ;
  - **non** — exactement l'une de ces phrases : « non », « non non », « non merci », « annule », « non annule »,
    « laisse tomber », « non laisse tomber », « stop », « arrête », « surtout pas », « pas du tout », « ne supprime
    pas », « ne supprime rien » : « D'accord, je ne supprime rien. » ; pendant l'attente, « annule » veut dire non, et
    ne défait pas la note précédente ;
  - **autre chose**, même « oui, mais lis-le-moi d'abord » : l'action est abandonnée, Atlas dit « Je ne supprime
    rien. », puis la phrase part à Claude, dans la même réponse. Dans le doute, c'est non.
- **Trente secondes sans réponse**, comptées depuis la mise en attente : l'action est abandonnée sans un mot (Atlas ne
  parle jamais de lui-même) ; les pages affichent « Suppression abandonnée : pas de réponse. »
- **Ce que Claude apprend** : une ligne au début de la question suivante qui lui est envoyée, avant la ligne de date :
  - « [Confirmé par David : le document « <titre> » est supprimé.] »
  - « [Refusé par David : rien n'a été supprimé.] »
  - « [Sans réponse de David : la suppression du document « <titre> » est abandonnée.] »
  - « [David a répondu autre chose : la suppression du document « <titre> » est abandonnée.] »
  - « [La suppression du document « <titre> » a échoué.] »
  - « [David a parlé avant la question : la suppression du document « <titre> » est abandonnée.] »
- **Un échec après le oui** (le fichier a changé ou disparu entre-temps) : « Je n'ai pas pu supprimer le document
  <titre>. » ; l'erreur est notée dans les logs du Core.
- **Le filet** : une suppression est un commit d'Atlas ; « annule » juste après remet le fichier (§5).
- **Les cas limites** :
  - une réponse coupée ou abandonnée avant que la question ne soit passée à la session : l'action est abandonnée,
    David ne l'a pas entendue (au contraire d'une `Note`, une `Confirmation` ne se reporte pas à la réponse suivante) ;
  - la fin d'une conversation (résumé à l'échéance, arrêt du Core, conversation perdue) abandonne l'action en attente ;
  - une confirmation ne vient que d'une phrase de David ou d'un bouton de la page : jamais d'un texte de Claude, d'un
    résultat d'outil ni d'une page web.

## 7. La page

- **Le panneau « Documents »**, ouvert par une icône à côté de l'historique :
  - la liste, du plus récent au plus ancien : titre, phrase de résumé, date de la dernière modification ;
  - un toucher ouvre le document, mis en forme par `markdown.js` : la syntaxe permise (§5) seulement ; **tout le texte
    est échappé**, aucun HTML du document n'est jamais interprété ; les liens ne sont permis qu'en `http(s)` et
    s'ouvrent dans un nouvel onglet ;
  - la liste se met à jour d'elle-même quand un document est écrit, supprimé ou remis ;
  - sans mémoire, le panneau dit « La mémoire n'est pas disponible. »
- **La confirmation** : pendant une attente, toutes les pages ouvertes affichent la question avec deux boutons,
  « Confirmer » et « Annuler ». Toucher un bouton revient à taper « oui » ou « non » depuis cette page. Un bouton
  touché quand plus rien n'attend ne fait rien. La fin de l'attente retire les boutons et l'indique en une ligne :
  « Supprimé : le document <titre>. » (ou la fiche, ou le profil), « Rien n'a été supprimé. » (non, autre chose, question
  coupée, fin de conversation), « Suppression abandonnée : pas de réponse. », « La suppression a échoué. »
- **Les messages** (`/ws/web`, protégés par la clé de la page comme le reste) :

| Sens | Message | Contenu |
|---|---|---|
| page → Core | `documents` | demande la liste |
| page → Core | `lire_document` | `chemin` |
| page → Core | `confirmer` | `oui` (booléen) |
| Core → page | `liste_documents` | `documents` : `chemin`, `titre`, `resume`, `modifie` |
| Core → page | `document` | `chemin`, `titre`, `contenu` |
| Core → pages | `documents_changes` | `{}` : la liste est à redemander |
| Core → pages | `confirmation` | `texte` : la question ; une page qui s'ouvre pendant une attente la reçoit aussi |
| Core → pages | `confirmation_finie` | `texte` : la ligne qui dit comment l'attente s'est finie |

## 8. Sécurité et erreurs

- **Les niveaux sont dans le code** ; un outil N3 ne change rien avant le « oui ». Un test le vérifie pour chaque outil.
- **Les documents** passent par les vérifications de la 2b : chemin enfermé dans `documents/`, format, secrets refusés,
  commit sous l'auteur « Atlas », jamais de `git push`.
- **La suppression** n'accepte qu'une fiche ou un document : ni le journal, ni un chemin hors de la mémoire.
- **La page** : le texte d'un document est toujours échappé ; les liens hors `http(s)` restent du texte ; un document
  ne sort que par `/ws/web`, avec la clé de la page.
- **La confirmation** ne vient que de David (§6) : Claude ne peut ni la donner, ni la simuler.
- **Claude reste enfermé** : la recherche web et les outils d'« atlas », rien d'autre ; toujours pas de `WebFetch`.
- **Les erreurs** : un refus revient à Claude avec sa raison, sans annonce (comme en 2b) ; une panne du dépôt revient
  à Claude et se note dans les logs du Core ; sans mémoire (git absent), ni outils, ni documents, ni confirmation, et
  le panneau le dit.

## 9. Réglages

Aucun réglage nouveau. Le délai de confirmation (trente secondes) est une constante du code ; `ATLAS_RELANCE_S`
(existant) règle la fenêtre où répondre sans « Hey Atlas ».

## 10. Les tests

- **Les niveaux** : chaque outil déclaré a un niveau ; N1 n'annonce rien ; N2 annonce ce qui a changé ; N3 n'exécute
  rien, met en attente et fait dire la question ; N2 et N3 refusés pendant le résumé.
- **Les documents** (dépôts git temporaires) : écrire, remplacer, la taille, le format, les secrets, le nom ; le
  sommaire et la recherche ; annuler une création, une retouche, une suppression, avec la bonne annonce.
- **La confirmation**, avec une horloge factice : la table des réponses (oui, non, autre, avec majuscules, accents,
  ponctuation, « Atlas ») ; l'exécution sur oui ; l'abandon sur non, sur autre chose, au délai ; une seule action à la
  fois ; l'échec après le oui ; les lignes pour Claude.
- **Le cerveau**, avec la doublure du SDK : la réponse lue avant Claude ; « oui » et « non » sans appel à Claude ;
  « autre chose » envoyé à Claude avec sa ligne ; la ligne de résultat à la question suivante ; l'abandon à la coupure,
  au résumé et à l'arrêt.
- **La session** : la question dite à sa place ; en texte seulement en mode muet.
- **Le hub et le protocole** : les messages des documents ; le bouton traité comme une réponse tapée ; le bouton sans
  attente ignoré ; une page ouverte pendant une attente reçoit la question.
- **La page** (tests JavaScript) : `markdown.js` (chaque élément de la syntaxe, l'échappement, les liens refusés), le
  panneau, les boutons.
- **Jamais** le vrai Claude dans `make test`, et jamais la vraie mémoire de David.
- **À la main, par David**, sur le M5 : les critères du §1.

## 11. Hors périmètre

- n8n, la veille, le routeur d'intention et Ollama (phase 3).
- `WebFetch`, et tout autre outil sortant.
- Modifier, exporter ou envoyer un document depuis la page.
- Une confirmation pour la réécriture d'un document ; plusieurs actions en attente à la fois.
- La découverte automatique des outils (D7) ; l'index vectoriel.
- Le déploiement sur le néo ; le résumé perdu au Ctrl-C sur le M5 (décision de David après l'essai de la 2b).

## 12. Changements dans la spec parente

- **§8 :** le dossier `documents/` reçoit les documents produits par la réflexion vocale ; ils se lisent dans la page.
- **§9 :** en 2c, une liste explicite d'outils par famille, chacun avec son niveau déclaré ; la découverte automatique
  « un fichier par outil » attendra que les outils soient plus nombreux.
- **§10 :** la question N3 est formulée par le Core à partir de l'action résolue ; la réponse vient de la voix, du
  clavier ou d'un bouton de la page ; trente secondes sans réponse valent non ; la première action N3 est la
  suppression d'une fiche ou d'un document.
- **§15 :** la phase 2c est décrite par cette spec.

# Les Paramètres : un menu à gauche, la rubrique à droite — design

**Date :** 29 septembre 2026
**Statut :** maquette validée par David (canevas de design « Paramètres d'Atlas », Mac et iPad, iPhone)
**Spec parente :** `2026-09-22-atlas-design.md` (§12 la page) ; s'appuie sur `2026-09-28-connecteurs-design.md` (§6) et
`2026-09-29-reglages-et-core-design.md` (§4, §5)
**Approche retenue :** comme les Réglages Système du Mac, une colonne de rubriques (une icône et un mot) et, à droite,
la rubrique choisie ; sur un écran étroit, la liste des rubriques puis la rubrique, avec un retour

## 1. Objectif et critères de réussite

Avec les connecteurs, leurs réglages et la rubrique « Le Core », les Paramètres sont devenus une longue page où l'on
cherche. David veut un menu à base d'icônes et d'un mot à gauche, et les fonctions de la rubrique choisie à droite, comme
les Réglages Système du Mac. La page sert aussi sur iPhone et iPad.

| Critère | Objectif, vérifié par David |
|---|---|
| Menu | Sur le Mac, les Paramètres s'ouvrent en fenêtre : à gauche Connecteurs, Voix, Orbe, Fond, Le Core, chacun avec son icône ; un clic affiche sa rubrique à droite |
| Mémoire | Rouverts, les Paramètres montrent la dernière rubrique choisie sur cet appareil |
| iPad | En portrait comme en paysage, les deux colonnes |
| iPhone | La liste des rubriques, chacune avec sa valeur ; un toucher ouvre la rubrique ; « ‹ Paramètres » revient à la liste |
| Rien de perdu | Tout ce que les Paramètres font aujourd'hui marche comme avant : interrupteurs et réglages des connecteurs, confirmation « Communauté », « Hey Atlas », orbes, fonds, redémarrer, mettre à jour |
| Non-régression | `make test` au vert |

## 2. Décisions

- **D1. Cinq rubriques, dans cet ordre :** Connecteurs, Voix, Orbe, Fond, Le Core. Chacune a une icône (un trait blanc
  sur un carré arrondi de couleur, dessiné en SVG dans la page, jamais un emoji ni une image venue d'ailleurs) et un mot.
- **D2. Un écran large** (720 px et plus : Mac, iPad) : une fenêtre centrée par-dessus l'orbe, la colonne des rubriques à
  gauche, la rubrique choisie à droite, avec son titre et le bouton de fermeture.
- **D3. Un écran étroit** (moins de 720 px : iPhone) : les Paramètres couvrent l'écran ; d'abord la liste des rubriques,
  chacune avec sa valeur à droite (« 1 actif », le nom de l'orbe, le nom du fond, la version du Core…) ; un toucher
  ouvre la rubrique, « ‹ Paramètres » revient à la liste.
- **D4. La dernière rubrique est retenue** sur l'appareil (comme l'orbe et le fond) ; la première fois, Connecteurs. Sur
  un écran étroit, les Paramètres s'ouvrent toujours sur la liste.
- **D5. « Muet » reste dans la barre du haut**, où il sert souvent.
- **D6. Rien ne change côté Core** : les mêmes messages, les mêmes réponses ; seule la page change.

## 3. La page

**La fenêtre (écran large).** Centrée, 920 × 640 px au plus (moins sur un petit écran), coins arrondis, le verre fort
d'aujourd'hui ; l'orbe reste visible autour, assombrie.

- **La colonne des rubriques** : « Paramètres » en titre, puis une ligne de 44 px par rubrique (l'icône de 28 px, le
  mot) ; la rubrique choisie est surlignée d'ambre. Ce sont de vrais boutons ; la rubrique choisie porte
  `aria-current="page"`.
- **La rubrique** : son titre, une phrase qui dit à quoi elle sert, puis son contenu en cartes groupées (un fond à peine
  plus clair, un bord fin, des séparateurs entre les lignes), comme les Réglages Système.

**L'écran étroit.** Les Paramètres prennent tout l'écran (marges de sécurité comprises). La liste : « Paramètres » en
grand titre, le bouton de fermeture, puis les rubriques en une carte, une ligne de 52 px chacune (icône, mot, valeur,
chevron). Une rubrique : « ‹ Paramètres » en haut à gauche, la fermeture à droite, le titre en grand, puis le même
contenu que sur un écran large, sur une colonne. Les interrupteurs y sont plus grands, pour le doigt.

**Les rubriques**, avec leur phrase :

- **Connecteurs** — « Les liens d'Atlas vers l'extérieur. Un connecteur de la communauté demande confirmation avant de
  s'activer. » Une carte par connecteur : son nom et son badge, sa description, son état ; à droite « Réglages… » (s'il
  en a) et son interrupteur ; ses réglages s'ouvrent sous une ligne de séparation. L'avertissement « Communauté » et
  « Prend effet à ta prochaine question. » restent, dans la carte.
- **Voix** — « Le micro de la page, et le mot qui réveille Atlas. » Une carte : « Hey Atlas », « Écouter « Hey Atlas »
  quand le micro est allumé. » et son interrupteur.
- **Orbe** — « L'orbe au centre de la page. Un clic l'applique tout de suite. » La galerie actuelle, en quatre colonnes
  (trois sur un écran étroit).
- **Fond** — « Le fond derrière l'orbe. » La galerie actuelle, en trois colonnes (deux sur un écran étroit).
- **Le Core** — « Le Core d'Atlas, sur cette machine ou sur le néo. » Une carte : la version ; « Redémarrer », sa phrase
  et le bouton « Redémarrer… » ; « Mettre à jour et redémarrer », sa phrase et « Mettre à jour… » (grisé avec sa raison
  dessous quand ce n'est pas possible). Sous la carte : la confirmation, les étapes, les nouveautés, la fin, comme
  aujourd'hui.

**Le comportement.**

- Ouvrir les Paramètres redemande toujours les connecteurs et l'état du Core, comme aujourd'hui, quelle que soit la
  rubrique.
- Les galeries n'animent leurs aperçus que tant que leur rubrique est affichée.
- Échap ferme les Paramètres, comme aujourd'hui ; changer de rubrique ramène la rubrique en haut.
- Les messages du Core (liste des connecteurs, étapes du Core…) mettent à jour leur rubrique même quand elle n'est pas
  affichée : on la retrouve à jour.

## 4. Organisation du code

- `index.html` : les Paramètres gardent leurs identifiants (`liste-connecteurs`, `hey-atlas`, `galerie-orbes`,
  `galerie-fonds`, `rubrique-core`), rangés chacun dans sa rubrique, plus la colonne des rubriques.
- Un module neuf pour la navigation (les rubriques, leur choix retenu, la liste et le retour sur un écran étroit) et
  leurs icônes ; `app.js` le branche et n'ouvre une galerie que quand sa rubrique est affichée. La largeur (720 px)
  est une règle CSS ; la page dit seulement « la liste » ou « la rubrique », et l'écran large montre les deux.
- Les styles des Paramètres (la fenêtre, les rubriques, les cartes, les connecteurs, les réglages, « Le Core ») vont
  dans une feuille à eux, pour que `style.css` et `documents.css` restent sous 500 lignes.
- `connecteurs.js` et `core.js` dessinent leurs cartes ; leurs messages et leurs envois ne changent pas.

## 5. Les tests

- **La navigation** : cinq rubriques dans l'ordre, chacune avec son icône et son mot ; un clic affiche la sienne et la
  marque `aria-current="page"` ; le choix est retenu, et relu à l'ouverture (Connecteurs la première fois, ou si le
  choix retenu n'existe pas) ; un stockage interdit ne casse rien ; la liste et le retour.
- **Les valeurs de la liste** (écran étroit) : le nombre de connecteurs actifs, l'orbe, le fond, la version du Core, à
  jour quand ils changent.
- **Les galeries** : leurs aperçus ne tournent que dans leur rubrique.
- **Rien de perdu** : les tests actuels des connecteurs, des réglages, de « Le Core » et de la page passent, adaptés à
  la nouvelle disposition ; chaque identifiant que cherche `app.js` existe dans `index.html`.
- Un essai à l'œil dans un navigateur, en large et en étroit, avant la PR.

## 6. Hors périmètre

- Un champ de recherche dans les Paramètres.
- Une icône propre à chaque connecteur, ou une page par connecteur.
- De nouveaux réglages ; déplacer « Muet ».
- Tout changement côté Core.

# Interface graphique : l'orbe et la conversation — design

**Date :** 24 septembre 2026
**Statut :** design validé par David, section par section
**Spec parente :** `2026-09-22-atlas-design.md`, §6.5 (`atlas-web`) et phase 4, dont cette partie est avancée
**Approche retenue :** une page simple servie par le Core, en HTML, CSS et JavaScript standard, sans étape de compilation

## 1. Objectif et critères de réussite

David voit Atlas vivre : une orbe animée réagit à l'état d'Atlas et au volume de la voix, et la conversation s'affiche
en sous-titres. Il peut aussi taper une question quand parler n'est pas possible, en visio par exemple, et rendre Atlas
muet. La même page sert du téléphone au grand écran : un iPad posé sur le bureau, un second écran, un onglet du Mac.

| Critère | Objectif |
|---|---|
| Réaction de l'orbe | L'état affiché change dès que le Core change d'état, et le volume suit la voix entendue, sans avance visible sur la lecture |
| Question tapée | Traitée comme une question dite : réponse à voix haute sur le Mac et par écrit, ou par écrit seulement en mode muet ou sans client audio |
| Choix de l'orbe | 12 styles au choix dans les paramètres, mémorisés par écran ; l'aurore boréale par défaut |
| Accès | Impossible sans la clé, et impossible depuis un autre site ouvert dans le navigateur |
| Légèreté | Une page ouverte toute la journée sur un iPad reste fluide : une seule orbe animée hors de la galerie, et une pause quand l'onglet est caché |

## 2. Décisions

- **D1. Orbe et conversation d'abord.** L'icône de barre de menu et le reste du tableau de bord (n8n, mémoire, documents)
  viendront plus tard.
- **D2. Une page adaptative.** Pas d'écran privilégié : la même page, du téléphone au grand écran.
- **D3. Disposition « cinéma ».** L'orbe au centre, le dernier échange en sous-titres qui s'effacent, l'historique dans
  un panneau qu'on fait glisser. Choisie parmi trois maquettes (cinéma, tableau de bord, fil unique).
- **D4. Une zone de saisie.** Une question tapée est un nouveau chemin d'entrée dans le Core.
- **D5. Un interrupteur « muet ».** Actif, il rend Atlas silencieux, pour les questions tapées comme pour les questions
  dites. C'est un réglage du Core : il vaut pour toutes les pages, et redevient inactif au redémarrage du Core.
- **D6. Une clé d'accès.** `ATLAS_WEB_CLE`, dans le `.env` du Core, avec une vérification de l'origine. Le tout reste sur
  le réseau local.
- **D7. Douze orbes interchangeables, dès la première version.** Le style se choisit dans les paramètres et se mémorise
  par écran, dans le navigateur. L'aurore boréale est le style par défaut.
- **D8. Dessin 2D natif, sans Three.js.** La spec parente prévoyait Three.js. Les 12 maquettes validées tournent en
  Canvas 2D sans aucune bibliothèque : on garde ce choix.
- **D9. Aucune étape de compilation, aucune dépendance.** Des modules JavaScript standard, testés avec `node --test`
  (Node 26, déjà installé sur le Mac).

## 3. Architecture

### 3.1 Côté Core (`src/atlas_core/`)

- **Un diffuseur.** Les sessions y publient ce qui se passe : état, niveau, question, réponse, erreur, délais, muet.
  Chaque page connectée est abonnée. Le diffuseur garde les 50 derniers échanges en mémoire ; ils s'effacent au
  redémarrage (la mémoire durable arrivera en phase 2).
- **Une présence.** Le Core retient la session du client audio connecté (le plus récent s'il y en a plusieurs), pour y
  faire passer les questions tapées.
- **Une connexion `/ws/web`,** réservée aux pages et protégée par la clé (§4).
- **Le service de la page** à la racine du Core, avec sa politique de sécurité (§4.3). `/sante` et `/ws/audio` restent
  inchangés.
- **Le réglage muet,** unique pour tout le Core.

### 3.2 Côté page (`src/atlas_web/`)

| Fichier | Rôle |
|---|---|
| `index.html`, `style.css` | La disposition « cinéma » : barre du haut, orbe, sous-titres, saisie, panneaux d'historique, de paramètres et de clé |
| `app.js` | Le démarrage : relie la connexion, l'état, l'orbe et les panneaux |
| `connexion.js` | La connexion `/ws/web`, l'authentification, la reconnexion avec des tentatives espacées |
| `etat.js` | L'état courant, construit à partir des messages : état, volume lissé, couleur, attaques de syllabes, sous-titres, historique, muet |
| `orbes/index.js` | Le registre des 12 orbes et le choix mémorisé (aurore par défaut) |
| `orbes/*.js` | Une orbe par fichier (§6) |
| `parametres.js` | La galerie des 12 orbes |
| `historique.js`, `sous_titres.js` | Les deux affichages de la conversation |

## 4. Connexion et sécurité

### 4.1 La clé

- **Sans `ATLAS_WEB_CLE`,** `/ws/web` refuse toute connexion, avec un code de fermeture dédié, et la page explique
  comment configurer la clé. Par défaut, rien n'est ouvert.
- **La clé part dans le premier message** (`authentification`), jamais dans l'adresse de la page, qui finit dans les
  historiques et les journaux.
- **Le Core la compare en temps constant** (`hmac.compare_digest`). Sans clé valide dans les 5 secondes, il ferme la
  connexion.
- **La page demande la clé au premier affichage** sur un appareil, puis la mémorise dans ce navigateur. Si le Core la
  refuse, elle la redemande.

### 4.2 L'origine

Le Core n'accepte que les connexions ouvertes par sa propre page : l'en-tête `Origin` doit correspondre à l'hôte de la
requête. Un autre site ouvert dans le navigateur ne peut donc pas piloter Atlas.

### 4.3 La page

- **Aucun script extérieur.** Tout est servi par le Core, avec l'en-tête
  `Content-Security-Policy: default-src 'self'; connect-src 'self'`.
- **Tout le texte affiché est inséré comme du texte brut** (`textContent`, jamais `innerHTML`) : une transcription ou une
  réponse ne peut pas injecter de code.

### 4.4 Les messages

Du Core vers la page :

| Message | Contenu |
|---|---|
| `etat` | `repos`, `ecoute`, `reflexion` ou `parole` |
| `niveau` | le volume, de 0 à 1, au plus 15 fois par seconde, pendant l'écoute et la parole seulement |
| `question` | le texte et sa source (`voix` ou `clavier`) |
| `reponse` | le texte, phrase par phrase |
| `erreur` | un code et un message en français |
| `latences` | transcription, réflexion et première voix, en millisecondes |
| `muet` | actif ou non |
| `historique` | les 50 derniers échanges, envoyés juste après l'authentification |

De la page vers le Core :

| Message | Contenu |
|---|---|
| `authentification` | la clé |
| `saisie` | le texte tapé, de 1 à 1 000 caractères, vérifié par le Core |
| `muet` | activer ou désactiver |

**Reconnexion.** Si le Core redémarre ou si le réseau coupe, la page affiche « hors ligne », puis se reconnecte seule,
en espaçant ses tentatives jusqu'à 30 secondes.

## 5. Le comportement du Core

### 5.1 La question tapée

- Elle est traitée comme une question dite, sans passer par la transcription. L'échange est marqué `clavier`.
- **Si Atlas est occupé** (écoute, réflexion ou parole), elle l'interrompt, comme une coupure à la voix. Le client
  audio arrête de jouer (`StopAudio`), et la question tapée passe en priorité.
- **Sans client audio connecté,** une session sans voix répond. La page voit les mêmes états : réflexion, parole le temps
  d'afficher la réponse, puis repos.

### 5.2 Le mode muet

- Actif, le Core n'appelle plus la synthèse vocale, mais envoie toujours le texte des réponses aux pages.
- Il vaut aussi pour les questions dites.
- L'activer pendant qu'Atlas parle coupe la phrase en cours.
- Toutes les pages voient l'interrupteur changer en même temps.
- Il redevient inactif au redémarrage du Core.

### 5.3 Les niveaux pour l'orbe

- **En écoute,** le niveau vient de la voix de David, que le Core reçoit déjà, calculé sur les trames reçues.
- **En parole,** il vient de la voix d'Atlas. La synthèse va environ deux fois plus vite que la lecture : le Core cale
  donc chaque niveau sur le moment où son morceau sera joué, d'après la durée des morceaux déjà envoyés.
- **Une interruption** annule les niveaux qui restaient à envoyer.
- **Au repos,** aucun niveau : le Mac n'envoie pas d'audio avant le réveil, et l'orbe respire seule.

### 5.4 Les délais et l'historique

- Trois délais par tour : **transcription** (durée de l'appel à Whisper), **réflexion** (jusqu'au premier fragment du
  cerveau), **première voix** (de la fin de la phrase de David au premier morceau d'audio envoyé).
- L'historique garde les 50 derniers échanges : heure, source, question, réponse, erreur éventuelle, délais.

## 6. Les orbes

### 6.1 L'interface commune

Chaque orbe est un module qui exporte son identifiant, son nom, une phrase de présentation et une fonction
`creer(canvas)`. Celle-ci rend un objet dont la méthode `dessiner(t, scene)` est appelée à chaque image, avec
`scene = { etat, volume, couleur, syllabe }` :

- `volume` : le niveau lissé, de 0 à 1 ;
- `couleur` : la couleur de l'état, qui passe en douceur d'un état à l'autre ;
- `syllabe` : vrai à l'image où une attaque de voix est détectée dans le vrai volume.

Une orbe ne touche ni au réseau ni au reste de la page. On peut donc en ajouter une sans rien changer ailleurs.

### 6.2 Les douze styles

| N° | Identifiant | Style |
|---|---|---|
| 1 | `particules` | Sphère de particules en 3D, qui se gonfle avec la voix |
| 2 | `liquide` | Orbe liquide aux contours mouvants |
| 3 | `anneaux` | Anneaux « réacteur » en segments autour d'un cœur |
| 4 | `armillaire` | Sphère armillaire en laiton : Atlas porte la voûte céleste |
| 5 | `relief` | Globe en lignes de relief : un atlas, ce sont des cartes |
| 6 | `cymatique` | Sable qui dessine les figures de Chladni au rythme de la voix |
| 7 | `oscilloscope` | Courbes de Lissajous en phosphore vert, dont la figure change avec l'état |
| 8 | `plasma` | Boule plasma dont les filaments convergent quand Atlas parle |
| 9 | `constellations` | Étoiles reliées, où des éclairs courent pendant la réflexion |
| 10 | `aurore` | Aurore boréale dans un hublot (**par défaut**) |
| 11 | `galaxie` | Galaxie spirale, dont la voix lance des ondes le long des bras |
| 12 | `mandala` | Kaléidoscope à 12 branches qui respire avec la voix |

Les couleurs par état : ardoise au repos, cyan à l'écoute, violet en réflexion, or en parole. Les maquettes validées
sont le point de départ du code.

## 7. La page

- **La barre du haut :** un point de couleur et l'état en toutes lettres, l'interrupteur « muet », la roue ⚙.
- **L'orbe** au centre, sur environ 60 % de la hauteur.
- **Les sous-titres :** la question en petit et en gris, la réponse en grand, qui s'écrit phrase par phrase. Ils
  s'effacent après 10 secondes de repos. Une erreur s'affiche en rouge, au même endroit.
- **La saisie en bas :** Entrée pour envoyer, puis le champ se vide.
- **L'historique :** un panneau par-dessus l'orbe, ouvert en glissant vers le haut ou par un bouton discret, fermé par
  Échap ou un glissement vers le bas. Pour chaque échange : l'heure, 🎙 ou ⌨, la question, la réponse et les délais.
- **Les paramètres :** la galerie des 12 orbes animées. Un clic applique le style tout de suite, et le navigateur s'en
  souvient. Les aperçus ne tournent que pendant que la galerie est ouverte.
- **La pause :** l'animation s'arrête quand l'onglet est caché.
- **La clé :** un petit écran au premier affichage, et de nouveau si le Core la refuse.
- **Hors ligne :** l'orbe devient grise et immobile, avec « Hors ligne — nouvelle tentative… ».
- **« Réduire les animations »** (`prefers-reduced-motion`) : les orbes s'animent plus lentement et plus doucement.

## 8. Erreurs

- **Une saisie invalide** (vide ou trop longue) : le Core la refuse avec un message clair, et la page l'affiche.
- **Une page qui se ferme** en plein tour : le Core continue, puisque la page ne faisait qu'observer.
- **Le client audio qui se déconnecte** pendant une réponse à une question tapée : la réponse se termine par écrit.
- **Une page trop lente :** le Core laisse tomber ses messages `niveau` plutôt que de ralentir Atlas. Les états, les
  textes et les erreurs ne sont jamais perdus.

## 9. Les tests

Écrits avant le code.

- **En Python, pour le Core :**
  - la clé : absente, fausse, trop tardive, comparée en temps constant ;
  - l'origine refusée ;
  - la diffusion vers plusieurs pages ;
  - une question tapée, avec et sans client audio, et pendant qu'Atlas parle ;
  - le mode muet, qui n'appelle jamais la synthèse ;
  - le calage des niveaux sur la lecture, et leur annulation à l'interruption ;
  - les trois délais, et l'historique limité à 50 ;
  - la page servie avec sa politique de sécurité.
- **En JavaScript, avec `node --test` :**
  - l'état reconstruit à partir des messages ;
  - la détection des syllabes ;
  - le passage d'une couleur à l'autre ;
  - la reconnexion ;
  - le choix d'orbe mémorisé, avec l'aurore par défaut ;
  - **un test de contrat pour les 12 orbes :** chacune est animée sur un faux canevas, dans les quatre états, pendant
    plusieurs centaines d'images. Elle ne doit pas planter, et doit dessiner quelque chose.
- **`make test`** lance les deux séries.
- **À la fin, un essai sur le vrai matériel avec David :** la page sur le Mac et l'iPad, à la voix et au clavier.

## 10. Hors périmètre

- Le reste du tableau de bord : n8n, mémoire, documents.
- L'icône dans la barre de menu du Mac.
- Un bouton « Stop » dans la page.
- La clé pour le client audio (`/ws/audio`), déjà prévue avant la phase 2.
- Un historique qui survit au redémarrage : il viendra avec la mémoire de la phase 2.

## 11. Changements dans la spec parente

- **§6.5 :** l'orbe se dessine en Canvas 2D, sans Three.js ; 12 styles au choix.
- **§6.6 :** le protocole gagne la connexion `/ws/web` et ses messages (§4.4 ci-dessus).
- **Phases :** l'orbe et la conversation, prévues en phase 4, sont avancées. Le reste du tableau de bord reste en phase 4.

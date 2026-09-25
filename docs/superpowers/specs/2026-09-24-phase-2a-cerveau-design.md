# Phase 2a : le cerveau branché — design

**Date :** 24 septembre 2026
**Statut :** design validé par David, section par section
**Spec parente :** `2026-09-22-atlas-design.md`, §6.2 (le Brain), §13 (sécurité) et phase 2, que ce document ouvre
**Approche retenue :** le SDK Agent de Claude en Python (`claude-agent-sdk`), qui pilote le CLI Claude Code installé et
connecté à l'abonnement de David

## 1. Objectif et critères de réussite

Atlas cesse d'être un bouchon : c'est Claude qui répond, à la voix comme au clavier, dans une conversation qui se
souvient de ce qui vient d'être dit. Les réponses deviennent longues et arrivent au fil des mots : la boucle vocale doit
les dire phrase par phrase, se laisser couper à tout moment, et ne jamais prendre trop d'avance. Le Core quitte le Mac
de développement pour le MacBook néo de la baie.

La phase 2 est découpée en trois étapes, chacune avec sa spec, son plan et sa fusion : **2a, le cerveau branché** (ce
document) ; **2b, la mémoire** (fichiers Markdown, journal, index, rotation de contexte avec résumé) ; **2c, outils et
permissions** (serveur MCP, niveaux N1/N2/N3, la réflexion transformée en document).

| Critère | Objectif, mesuré sur le vrai matériel |
|---|---|
| Conversation | Une question, puis une suite qui s'appuie sur la réponse précédente |
| Premier mot | 3 s au plus après la fin de la question, sans recherche web (délai « réflexion » de l'historique) |
| Recherche web | « Je regarde ça », l'orbe en réflexion pendant la recherche, puis la réponse |
| Interruption | Une réponse d'environ une minute, coupée en pleine phrase, puis dans un blanc entre deux phrases |
| Clavier | Une question tapée depuis l'iPhone reçoit sa réponse à voix haute |
| Déploiement | Le Core tourne sur le néo ; après un redémarrage, le client audio se reconnecte seul ; la page marche à l'adresse du néo |
| Non-régression | `make test` au vert |

## 2. Décisions

- **D1. Trois étapes pour la phase 2.** 2a le cerveau, 2b la mémoire, 2c outils et permissions.
- **D2. Développement sur le M5, puis déploiement sur le néo** en fin d'étape.
- **D3. Conversation, plus la recherche web.** Claude n'a qu'un outil, `WebSearch`. Pas de `WebFetch` : une page piégée
  pourrait sinon lui faire envoyer des morceaux de la conversation vers une adresse extérieure. Les autres outils
  arrivent en 2c, avec les permissions.
- **D4. Sonnet 5.** Le modèle est un réglage (`ATLAS_CERVEAU_MODELE`, `claude-sonnet-5` par défaut).
- **D5. Bref et direct.** 2 à 4 phrases, la conclusion d'abord, puis Atlas propose d'aller plus loin. Il tutoie David,
  sans aucune mise en forme : tout est dit à voix haute.
- **D6. Le SDK Agent de Claude** (`claude-agent-sdk`), plutôt que le CLI brut piloté à la main ou un `claude -p` neuf
  à chaque question : un processus qui reste allumé, `interrupt()` documenté, des options typées.
- **D7. Un seul cerveau, une seule conversation**, partagés par la voix et le clavier.
- **D8. Pendant une recherche web, l'orbe repasse en réflexion** après la phrase d'attente (demande de David).
- **D9. `/ws/audio` protégé par une clé** (`ATLAS_AUDIO_CLE`), sur le même modèle que `/ws/web`.
- **D10. Le bouchon reste disponible** (`ATLAS_CERVEAU=bouchon`), pour les tests et pour faire tourner Atlas sans Claude.

## 3. Architecture

### 3.1 Côté Core (`src/atlas_core/`)

| Fichier | Rôle |
|---|---|
| `cerveau_claude.py` (nouveau) | `CerveauClaude` : le `ClaudeSDKClient` gardé allumé, les questions une à une, l'interruption, l'oubli, la relance après plantage |
| `consignes.py` (nouveau) | Les consignes d'Atlas (l'invite système) et la ligne de date placée devant chaque question |
| `mise_en_voix.py` (nouveau) | Le filtre qui rend un texte prononçable, et la liste des hallucinations connues de Whisper |
| `cerveau.py` | L'interface `Cerveau` gagne l'annonce d'une recherche (§4.3) ; le bouchon reste |
| `phrases.py` | Le découpeur de phrases, revu pour un texte qui arrive mot par mot (§5.1) |
| `session.py` | La phrase d'attente, le retour en réflexion pendant une recherche, le filtre des hallucinations |
| `etat.py` | La transition « parole → réflexion » |
| `config.py` | `cerveau`, `cerveau_modele`, `cerveau_oubli_min`, `audio_cle` |
| `hub.py` | Un seul cerveau pour tout le Core, créé au démarrage ; la clé de `/ws/audio` |
| `protocole.py` | `Bonjour` porte la clé du client audio |

### 3.2 Côté client audio (`src/atlas_audio/`)

| Fichier | Rôle |
|---|---|
| `client.py` | Le barge-in armé tant que le Core annonce « parole » ; la tâche de lecture qui ne prend jamais trop d'avance ; la reconnexion ; la clé dans `Bonjour` |

### 3.3 Déploiement (`scripts/neo/`, nouveau)

Un guide pas à pas (`LISEZMOI.md`) et le modèle du service launchd qui lance le Core au démarrage du néo.

### 3.4 Dépendance

`claude-agent-sdk` (≥ 0.2.140, pour `ResultError`) rejoint les dépendances `core` (Python ≥ 3.10, le projet est en
3.12). Il lance le CLI `claude` installé, qui doit être connecté à l'abonnement de David.

## 4. Le cerveau

### 4.1 Cycle de vie

- Le Core crée **un seul** `CerveauClaude` au démarrage et le partage entre toutes les sessions : la voix et le clavier
  alimentent la même conversation. Le client SDK démarre à la première question, pas au lancement du Core : un Core
  sans Claude connecté démarre quand même, et l'erreur n'apparaît qu'à la première question.
- `repondre(texte)` rend la réponse au fil des mots : les deltas de texte des événements partiels du SDK.
- **Une question à la fois.** Une nouvelle question, d'où qu'elle vienne, interrompt celle qui est en cours avant de
  partir.
- **L'oubli.** Au-delà de `ATLAS_CERVEAU_OUBLI_MIN` minutes sans échange (30 par défaut), la question suivante ouvre une
  conversation neuve. Pendant une conversation, le compactage automatique de Claude Code gère un contexte qui se remplit.
  La rotation avec résumé écrit dans le journal viendra en 2b.
- **Le plantage.** Si le processus Claude meurt, la question suivante le relance, dans une conversation neuve. Atlas le
  dit en une phrase (« Je reprends de zéro, j'ai perdu le fil. »).

### 4.2 L'interruption

Quand la session abandonne une réponse (barge-in, question tapée, réveil), elle ferme le flux du cerveau. Le cerveau
appelle alors `interrupt()`, puis vide les messages restés en route jusqu'au message de fin du tour : la question
suivante part d'un état propre. Le muet n'interrompt pas Claude : la réponse se termine, en texte seulement.

### 4.3 La recherche web

Quand Claude commence un appel `WebSearch`, le cerveau le signale à la session (un événement « recherche » dans le flux,
distinct du texte). La session :

1. dit la phrase d'attente « Je regarde ça. », une seule fois par question ;
2. dès que cette phrase a fini de jouer (calendrier de lecture), repasse en « réflexion » (machine, client et pages) :
   les pages montrent le violet et l'animation de réflexion propres à chaque orbe ;
3. repasse en « parole » à la première phrase de la réponse.

Pendant la recherche, comme avant toute réponse, on interrompt Atlas par « Hey Atlas » ou par une question tapée : le
barge-in, lui, ne vaut que pendant la parole (§5).

## 5. La boucle vocale, prête pour les longues réponses

1. **Le découpeur de phrases.** Il n'arrête plus une phrase sur une ponctuation qui termine le texte reçu : il attend le
   caractère suivant. Il ne coupe jamais entre deux chiffres (« 3.5 », « 3,5 »). Une phrase qui dépasse 250 caractères
   est coupée sur la dernière virgule, le dernier point-virgule ou le dernier espace avant la limite : le premier son
   arrive plus vite, et la synthèse (1 000 caractères au plus) n'est jamais débordée.
2. **La mise en voix.** Avant d'être dite et affichée, chaque phrase perd sa mise en forme (astérisques, dièses, puces,
   accents graves), et toute adresse web devient « un lien ». Les consignes l'interdisent déjà ; le filtre est un filet.
3. **Le barge-in entre deux phrases.** Le client reste à l'affût d'une interruption tant que le Core annonce « parole »,
   et plus seulement pendant qu'un son joue : un « attends » dans le blanc entre deux phrases coupe Atlas.
4. **La cadence.** Le client joue l'audio depuis sa propre tâche, avec une file bornée : il n'envoie jamais plus de
   quelques secondes d'avance au programme Swift. Le flux WebSocket reste donc libre, un `StopAudio` est traité aussitôt,
   et le client envoie `Interruption` au Core avant de vider son son. Une trame reçue est revérifiée après chaque attente
   de lecture.
5. **La reconnexion.** Si le Core disparaît, le client se reconnecte seul (1, 2, 4, 8, 16 puis 30 s entre les
   tentatives) et remet à zéro ses repères d'énoncé.

**Limite acceptée :** une phrase déjà en cours de synthèse chez Qwen finit d'être calculée après une interruption ; avec
des phrases de 250 caractères au plus, l'attente reste courte.

## 6. Le comportement d'Atlas

### 6.1 Les consignes

Atlas est l'assistant vocal de David. Il parle français et le tutoie. Il répond en 2 à 4 phrases, la conclusion
d'abord, puis propose d'aller plus loin. Tout ce qu'il écrit est dit à voix haute : ni listes, ni mise en forme, ni
émojis, ni adresse web. Il ne prétend jamais avoir fait une action qu'il ne peut pas faire : en 2a, il réfléchit et
cherche sur le web, rien d'autre. S'il ne sait pas, il le dit. S'il s'appuie sur une page, il cite le site par son nom.

### 6.2 L'heure et la date

Chaque question part précédée d'une ligne de contexte, par exemple `[jeudi 24 septembre 2026, 21 h 50]`. Claude
connaît ainsi l'heure et la date.

### 6.3 Les hallucinations de Whisper

Sur un bruit bref, Whisper produit parfois une phrase fantôme (« Merci. », « Sous-titres réalisés par… »). Une liste de
ces phrases connues, comparée au texte normalisé, fait traiter la transcription comme « rien entendu » : Claude n'est
pas appelé.

### 6.4 Les erreurs

Dites à voix haute et affichées en rouge, en clair :

| Cause | Signal du SDK | Message |
|---|---|---|
| CLI absent | `CLINotFoundError` | « Claude Code n'est pas installé sur cette machine. » |
| CLI déconnecté | erreur `authentication_failed` | « Claude n'est plus connecté : il faut renouveler sa connexion. » |
| Limite de l'abonnement | erreur `rate_limit`, ou `RateLimitEvent` « rejected » | « J'ai atteint la limite de l'abonnement Claude pour le moment. » |
| Réseau ou serveur | erreur `server_error`, `CLIConnectionError` | « Je n'arrive pas à joindre Claude : vérifie le réseau. » |
| Autre | `ResultError`, `ProcessError` | le message d'erreur du SDK, comme aujourd'hui |

### 6.5 Les délais

Le délai « réflexion » (jusqu'au premier fragment du cerveau) est déjà mesuré et affiché dans l'historique. L'objectif
est un premier mot en 3 s au plus sans recherche.

## 7. Sécurité

- **Claude enfermé dans son rôle :** `tools=["WebSearch"]`, `allowed_tools=["WebSearch"]`, `setting_sources=[]` (aucun
  réglage, aucun `CLAUDE.md` de la machine), aucun serveur MCP (`strict_mcp_config`), un dossier de travail vide qui lui
  est réservé.
- **L'abonnement, jamais une clé d'API :** les variables `ANTHROPIC_*` sont retirées de l'environnement passé au CLI.
  Un test le vérifie. `CLAUDE_CODE_OAUTH_TOKEN` (§8), lui, est transmis.
- **Rien d'écrit sur le disque par le CLI :** `CLAUDE_CODE_SKIP_PROMPT_HISTORY=1` empêche l'écriture des transcriptions
  de conversation. La mémoire d'Atlas, qui viendra en 2b, sera la seule trace voulue.
- **`/ws/audio` protégé :** le premier message du client audio, `Bonjour`, porte `ATLAS_AUDIO_CLE`. Comparaison en temps
  constant, 5 s pour s'authentifier, fermeture 4401 sinon ; sans clé configurée, `/ws/audio` refuse tout (fermeture
  4000). Les navigateurs restent refusés avant même l'acceptation (en-tête `Origin`).
- Le Core reste sur le réseau local.

## 8. Le déploiement sur le néo

Guide pas à pas (`scripts/neo/LISEZMOI.md`), exécuté par David :

1. installer `uv`, cloner le dépôt, `make install` ;
2. connecter le CLI Claude à l'abonnement de David : `claude setup-token` ouvre la connexion dans un navigateur (par
   SSH, un code à coller dans le terminal) et affiche un jeton valable un an, à placer dans `CLAUDE_CODE_OAUTH_TOKEN`.
   Ce jeton est un secret : il ne va que dans le `.env` du néo, jamais dans le dépôt, et il faudra le renouveler avant
   son échéance ;
3. écrire le `.env` du néo (adresses de l'Unraid, `ATLAS_WEB_CLE`, `ATLAS_AUDIO_CLE`, `CLAUDE_CODE_OAUTH_TOKEN`,
   réglages du cerveau) ;
4. installer le service launchd, qui lance le Core au démarrage et le relance s'il tombe ;
5. sur le M5 : `ATLAS_CORE_URL` pointe vers le néo, et `ATLAS_AUDIO_CLE` est la même que sur le néo ;
6. ouvrir la page à l'adresse du néo.

## 9. Les tests

Écrits avant le code, sans appeler Claude : une doublure du client SDK rejoue des événements réalistes (deltas de texte,
début d'un appel `WebSearch`, message de fin, erreurs).

- **Le cerveau :** texte au fil des mots ; interruption puis vidage ; une question à la fois ; oubli après
  `ATLAS_CERVEAU_OUBLI_MIN` ; relance après plantage ; ligne de date ; événement « recherche » ; erreurs traduites.
- **La sécurité :** options passées au SDK (WebSearch seul, aucun réglage, aucun MCP, le modèle, le dossier) ; purge
  des `ANTHROPIC_*` ; clé de `/ws/audio`.
- **La boucle vocale :** découpeur nourri mot par mot (« 3. » puis « 5 euros », « M. Dupont », décimales, plafond de
  250 caractères) ; mise en voix ; hallucinations ; phrase d'attente et retour en réflexion ; barge-in entre deux
  phrases ; tâche de lecture bornée ; reconnexion.
- **Un essai réel, hors de `make test`,** avec le vrai `claude` et les options exactes (une question, une recherche, une
  interruption), lancé à la main avec l'accord de David, puisqu'il consomme un peu de l'abonnement.

## 10. Hors périmètre

- La mémoire, le journal et la rotation de contexte avec résumé (2b).
- Les outils MCP, les permissions N1/N2/N3 et la réflexion transformée en document (2c).
- Le routeur d'intention et l'étage réflexe Ollama (phase 3).
- `WebFetch` et tout autre outil.
- Le streaming audio de Qwen3, qui rend chaque phrase entière.

## 11. Changements dans la spec parente

- **Phasage :** la phase 2 est découpée en 2a, 2b et 2c.
- **§6.2 :** le Brain passe par le SDK Agent de Claude (le CLI reste le moteur, connecté à l'abonnement) ; la rotation
  de contexte avec résumé est en 2b.
- **§6.6 :** `hello` (`Bonjour`) porte la clé du client audio.
- **§13 :** `/ws/audio` est protégé par une clé.

# Helios — Assistant vocal personnel

**Date :** 2026-09-22
**Statut :** design validé, prêt pour le plan d'implémentation
**Auteur :** David, avec Claude

---

## 1. Objectif

Helios est un assistant vocal personnel, francophone, qui tourne sur l'infrastructure
de David. Il doit tenir trois rôles :

1. **Copilote de développement vocal** — brainstormer à l'oral, produire des documents
   structurés, lancer et suivre du travail Claude Code.
2. **Structuration de la nouvelle entreprise** — réflexion vers document, suivi des
   projets et des chantiers, clients et prospection, veille.
3. **Supervision des agents n8n existants** — alerter, résumer, diagnostiquer,
   déclencher. Superviseur, jamais décideur.

La domotique Home Assistant et la productivité personnelle (agenda, mail) sont des
objectifs de phase ultérieure, prévus dans l'architecture mais hors v1.

### Inspirations

Le design emprunte aux deux projets de référence, en prenant le meilleur de chacun :

- **ethanplusai/jarvis** — le modèle du cerveau : un process `claude -p` persistant sur
  abonnement plutôt qu'une requête par tour ; la mémoire en Markdown ; les outils via MCP ;
  la présence visuelle (orbe) et le tableau de bord.
- **sosoj92/jarvis-assistant-vocal** — la chaîne audio : wake word openWakeWord, STT
  faster-whisper local ; le registre d'outils auto-découvert par décorateur ; les niveaux
  de permission gradués.

Ce qui est explicitement **écarté** de ces références : le Web Speech API du navigateur
(ethanplusai), incompatible avec l'interruption en pleine phrase ; et la dépendance dure
à ElevenLabs (sosoj92), remplacée par un TTS local.

---

## 2. Périmètre

### Dans la v1

- Boucle vocale complète en français : wake word, transcription, réponse vocale,
  interruption en pleine phrase.
- Cerveau Claude Code persistant, avec rotation de contexte.
- Mémoire Markdown versionnée + index vectoriel.
- Registre d'outils avec permissions graduées.
- Supervision n8n : alerte, point quotidien, déclenchement vocal, diagnostic.
- Interface web : orbe de présence + tableau de bord.
- Accès distant par Hermes (Telegram / WhatsApp).

### Hors v1, prévu par l'architecture

- Home Assistant (domotique).
- Agenda et mail.
- Satellites audio multi-pièces.
- Sortie audio sur le HomePod.

### Hors périmètre, décidé

- Toute action financière ou transactionnelle.
- Toute saisie de mot de passe ou d'identifiant par Helios.
- Correction automatique de workflows n8n sans validation humaine.

---

## 3. Infrastructure disponible

| Machine | Rôle | Caractéristiques |
|---|---|---|
| MacBook Pro M5 | Poste de travail principal de David | Apple M5, 17 Go unifiés. Porte le client audio. |
| MacBook « néo » | Serveur headless en baie de brassage | Pas de micro, pas d'écran. Porte le Core et le cerveau. |
| Unraid `unraid.local` | Serveur 24/7 | RTX 4070 Ti 12 Go, remplacée par une RTX 3090 24 Go sous un mois. Héberge déjà ComfyUI (`:8188`), n8n, Home Assistant, un reverse proxy et Hermes Agent (`:PORT`, exposé en `hermes.example.com`). |
| HomePod, iPhone | Périphériques d'appoint | Sorties et entrées secondaires, phases ultérieures. |

Services tiers déjà en place et réutilisés : n8n, Home Assistant, Supabase, ComfyUI,
reverse proxy avec nom de domaine.

---

## 4. Décisions structurantes

Chaque décision est notée avec sa raison, pour qu'on puisse la rouvrir plus tard en
connaissance de cause.

| # | Décision | Raison |
|---|---|---|
| D1 | Le cerveau est un process `claude -p` persistant, sur abonnement | Pas de coût à la requête ; accès natif aux fichiers, aux MCP et aux sous-agents. C'est ce qui rend le copilote de dev possible. |
| D2 | Le cerveau tourne donc sur un Mac — le néo | Le CLI Claude Code exige une session authentifiée macOS. Contrainte, pas préférence. |
| D3 | Architecture en trois étages (M5 audio / néo cerveau / Unraid GPU) | Seule combinaison qui donne à la fois le 24/7 et un cerveau ayant accès aux fichiers de travail. |
| D4 | Client audio natif sur le M5, pas le navigateur | L'interruption en pleine phrase impose un micro ouvert pendant la lecture et une annulation d'écho. Le Web Speech API ne le permet pas. |
| D5 | STT local (faster-whisper) sur le GPU Unraid | Le français est bon, la latence maîtrisée, rien ne sort du réseau. |
| D6 | TTS local Qwen3-TTS, repli Piper/Kokoro | Choix de David. Le repli est nécessaire car le support français et la latence restent à valider (voir §12). |
| D7 | Wake word « Hey Helios » entraîné sur mesure | openWakeWord permet l'entraînement d'un modèle custom sur le GPU. Le nom du projet prime sur la facilité. |
| D8 | Mémoire en fichiers Markdown versionnés, index vectoriel par-dessus | Relisible, corrigeable et versionnable à la main. Claude Code lit nativement les fichiers. La mémoire ne devient jamais une boîte noire. |
| D9 | Permissions graduées N1/N2/N3, portées par le code | Un modèle de langage ne s'auto-autorise jamais. Le niveau est une propriété de l'outil, pas une décision du LLM. |
| D10 | Étage réflexe local : Ollama sur le GPU Unraid | Les commandes mécaniques répondent en ~300 ms au lieu de 2 s, et le travail de fond tourne la nuit sans coût. En cas de doute, l'étage réflexe passe la main à Claude. |
| D11 | Hermes Agent cantonné au rôle de porte d'entrée distante | Hermes est un gateway multi-modèles doté de sa propre mémoire et de ses propres skills. Deux agents entretenant chacun un modèle de David produiraient deux mémoires divergentes dont aucune ne ferait autorité. Sa mémoire reste donc hors-jeu. |
| D12 | Une seule source de vérité mémoire : les Markdown d'Helios | Corollaire de D8 et D11. |

---

## 5. Architecture

```
   M5 (poste de travail)         néo headless (baie)           Unraid unraid.local
 ┌────────────────────┐        ┌───────────────────────┐     ┌──────────────────────┐
 │ helios-audio       │        │ helios-core :8080     │     │ helios-stt    :9010  │
 │  capture 16 kHz    │        │  hub WebSocket        │────▶│ helios-tts    :9011  │
 │  AEC (écho)        │◀─ WSS ▶│  routeur d'intention  │────▶│ ollama       :11434  │
 │  wake « Helios »   │        │  Brain : claude -p    │     ├──────────────────────┤
 │  VAD + barge-in    │        │  mémoire MD + vecteurs│────▶│ n8n                  │
 │  lecture audio     │        │  outils + permissions │     │ Home Assistant (après) │
 └────────────────────┘        │  serveur MCP local    │     │ Hermes Agent  :PORT  │
                               │  front web (orbe)     │     │ reverse proxy        │
                               └───────────────────────┘     └──────────────────────┘
```

### Flux d'un tour de parole

1. Le micro du M5 tourne en permanence. L'annulation d'écho retire du signal ce qu'Helios
   est en train de dire.
2. `openWakeWord` repère « Hey Helios ». Le client passe en capture.
3. Le VAD détecte la fin de phrase après ~400 ms de silence.
4. L'audio capturé part au Core en WebSocket.
5. Le Core le fait transcrire par `helios-stt`.
6. Le **routeur d'intention** classe la demande : mécanique → étage réflexe (Ollama) ;
   sinon → Claude.
7. La réponse revient en streaming et est **découpée phrase par phrase**.
8. Chaque phrase part à `helios-tts` et revient en audio pendant que la suivante s'écrit.
9. Le client joue l'audio, en gardant le VAD actif.

### Interruption en pleine phrase

Le VAD ne s'arrête jamais, même pendant la lecture. Dès qu'il détecte de la voix pendant
plus de 300 ms alors qu'Helios parle, le client coupe la lecture net, vide sa file audio et
envoie `barge_in` au Core, qui interrompt la génération en cours et jette les phrases non
encore prononcées. C'est la raison d'être de D4.

### Budget de latence

Du silence de David au premier son de la réponse :

| Étape | Budget |
|---|---|
| Détection de fin de phrase (VAD) | ~400 ms |
| Transcription (faster-whisper, GPU) | 300–600 ms |
| Premier jeton — étage réflexe (Ollama) | ~150 ms |
| Premier jeton — Claude | 800–1500 ms |
| Premier morceau audio (TTS) | ~300 ms |
| **Total, commande mécanique** | **~1,0 s** |
| **Total, réponse de Claude** | **1,8 – 2,8 s** |

Ces chiffres sont des objectifs mesurés par `make bench` (§13), pas des estimations à
vérifier une fois pour toutes.

---

## 6. Composants

### 6.1 `helios-audio` (M5)

Le seul composant qui touche au matériel, et le seul qui ne contient aucune intelligence :
il ne sait que transporter du son. Il ne bougera donc presque jamais une fois réglé.

Responsabilités : capture micro 16 kHz mono, annulation d'écho, détection du wake word,
VAD, lecture audio, détection du barge-in, indicateur d'état en barre de menu.

**Annulation d'écho** — le point le plus délicat du projet. Python n'a pas accès au bon
moteur sur macOS. Décision : un petit binaire Swift utilisant le *Voice Processing*
d'Apple (le moteur de FaceTime), piloté par le daemon Python. Repli si le spike échoue :
casque, qui rend l'AEC inutile.

Le client est volontairement passif : il n'a aucune connaissance des outils, de la mémoire
ou des permissions. Il se reconnecte seul si le Core redémarre.

### 6.2 `helios-core` (néo)

Le chef d'orchestre. Un process FastAPI qui tient :

- **le hub WebSocket** vers les clients audio et le front web ;
- **le routeur d'intention** (§7) ;
- **le Brain** : le process `claude -p` persistant, sa rotation de contexte, la reprise
  après plantage ;
- **la segmentation en phrases** du flux de réponse, avec rejet d'écho ;
- **la mémoire** (§8) ;
- **le registre d'outils** et le serveur MCP local (§9) ;
- **les permissions** (§10) ;
- **la supervision n8n** (§11) ;
- le service du front web.

**Le Brain en détail.** Le process est lancé avec `--output-format stream-json`,
`--input-format stream-json` et `--strict-mcp-config`, pointé sur un `connections.json`
généré listant le seul serveur MCP d'Helios. Les variables d'environnement `ANTHROPIC_*`
sont purgées avant le lancement, afin de garantir que le CLI utilise bien la session
d'abonnement et non une clé API — emprunté à ethanplusai, et vérifié par un test.

**Rotation de contexte.** Quand le contexte approche de sa limite, le Core fait produire
au Brain un résumé de la session, l'écrit dans `journal/AAAA-MM-JJ.md`, tue le process et
en relance un neuf amorcé avec ce résumé et le profil. La conversation continue sans que
David ait à le savoir.

### 6.3 `helios-stt` (Unraid, Docker)

faster-whisper, modèle français, sur GPU. Une seule route :

```
POST /transcribe    body: audio/wav (16 kHz mono)
                    → {"text": str, "language": str, "duration_ms": int}
```

Chargement du modèle à la demande avec déchargement après inactivité, tant que les 12 Go
sont partagés avec ComfyUI. Le comportement redevient « toujours chargé » avec la 3090.

### 6.4 `helios-tts` (Unraid, Docker)

Qwen3-TTS, avec Piper FR ou Kokoro en repli configurable.

```
POST /synthesize    body: {"text": str, "voice": str}
                    → audio/wav en streaming par morceaux
```

Le streaming par morceaux est une exigence, pas un confort : c'est ce qui permet de
commencer à parler avant que la phrase entière soit synthétisée.

### 6.5 `helios-web` (servi par le Core)

L'orbe Three.js qui réagit à la voix — amplitude d'entrée, état d'écoute, de réflexion, de
parole — et le tableau de bord : état des workflows n8n, contenu de la mémoire, documents
produits, historique de conversation, erreurs, latences mesurées.

### 6.6 Protocole entre le client audio et le Core

WebSocket `wss://<core>/ws/audio`, messages JSON entrelacés avec des trames binaires
(PCM 16 kHz mono s16le, blocs de 20 ms).

Client vers Core :

| Message | Contenu |
|---|---|
| `hello` | `{client, sample_rate, caps: ["aec","vad","wakeword"]}` |
| `wake` | `{confidence, ts}` |
| *(binaire)* | trames PCM pendant la capture |
| `utterance_end` | `{duration_ms}` |
| `barge_in` | `{ts}` — David a repris la parole pendant la lecture |
| `confirm_response` | `{request_id, accepted: bool}` |

Core vers client :

| Message | Contenu |
|---|---|
| `state` | `idle` \| `listening` \| `thinking` \| `speaking` |
| `transcript` | `{text, final}` |
| `say` | `{utterance_id, seq, text}` suivi des trames audio |
| `stop_audio` | `{utterance_id}` — vidage immédiat de la file |
| `confirm` | `{request_id, action_fr, level, timeout_s}` |
| `error` | `{code, message_fr}` |

---

## 7. Routeur d'intention et étages d'intelligence

Deux étages, avec une règle unique et non négociable : **en cas de doute, l'étage réflexe
passe la main à Claude, jamais l'inverse.**

**Étage 1 — réflexe (Ollama sur le GPU Unraid, ~150 ms).** Un petit modèle de la classe
Qwen3 4B, chargé à la demande. Il traite ce qui est mécanique et sans ambiguïté :
déclenchement d'un workflow n8n nommé, commandes d'état, « répète », « stop »,
« quelle heure ». Il produit aussi le travail de fond non interactif : point quotidien,
digest n8n, réindexation de la mémoire — y compris la nuit, sans coût.

**Étage 2 — Claude (`claude -p`, 0,8–1,5 s au premier jeton).** Tout le reste :
raisonnement, écriture, code, conversation, diagnostic.

Le routeur classe sur trois critères : l'intention correspond-elle à un outil de niveau 1
au nom sans ambiguïté ; la demande tient-elle en une action unique ; le score de confiance
dépasse-t-il le seuil. Un seul « non » envoie vers Claude. Le seuil est un réglage exposé,
mesuré par `make bench`, pas une constante enfouie dans le code.

---

## 8. Mémoire

Un dépôt git sur le néo, en Markdown lisible :

```
memory/
  profil.md                  qui est David, comment il travaille, ses préférences
  entreprise/
    vision.md                le cap, les décisions structurantes
    offres.md
    decisions.md             journal des arbitrages, avec leur raison
  projets/<nom>.md           état, bloqueurs, prochaine action
  personnes/<nom>.md         contacts, prospects, historique des échanges
  journal/AAAA-MM-JJ.md      ce qui s'est dit, ce qui a été décidé
  documents/                 les documents produits par la réflexion vocale
```

Par-dessus, un index vectoriel local (embeddings multilingues sur le GPU Unraid, stockage
SQLite) dont le seul rôle est de **choisir quels fichiers charger dans le contexte**.
Claude lit ensuite les vrais fichiers : l'index ne remplace jamais le contenu, il ne fait
que le trouver. L'index se reconstruit sur modification de fichier ; il est jetable et
reconstructible à tout moment.

**Règle d'écriture :** Helios n'écrit jamais en silence. Toute écriture mémoire est
annoncée à voix haute (« je note ça dans projets/x.md »). Les écritures mémoire sont de
niveau N2 : il fait, et il annonce.

---

## 9. Outils

Le pattern retenu est celui de sosoj92, qui est le bon : un fichier par outil dans
`tools/`, un décorateur, découverte automatique, zéro câblage manuel.

```python
@outil(
    nom="n8n_lancer_workflow",
    description="Déclenche un workflow n8n par son nom",
    niveau=2,
)
def lancer_workflow(nom: str) -> str:
    ...
```

Le Core expose ces outils au process Claude par **un serveur MCP local en stdio** — natif
pour Claude Code, donc on ne réimplémente pas le tool-calling, et les mêmes outils restent
utilisables depuis d'autres clients MCP.

Familles d'outils en v1 : n8n, mémoire et documents, veille. Home Assistant et agenda/mail
viennent après la v1.

---

## 10. Permissions

Le niveau est une propriété déclarée de l'outil, lue par le Core. **Le modèle ne choisit
jamais son propre niveau d'autorisation.**

| Niveau | Nature | Comportement |
|---|---|---|
| **N1** | Lecture, consultation, état | Exécution directe, sans annonce. |
| **N2** | Modification réversible : écriture mémoire, déclenchement d'un workflow, création de document | Exécution, puis annonce de ce qui a été fait. |
| **N3** | Irréversible ou sortant : envoi de mail, suppression, modification d'un workflow, action sur un serveur | **Reformulation à voix haute de l'action exacte**, puis attente d'un oui explicite, avec expiration. Pas de réponse vaut non. |

La reformulation N3 porte sur l'action résolue, pas sur la demande : « envoyer un mail à
Paul Durand, objet Proposition commerciale » et non « envoyer le mail dont on parlait ».
C'est ce qui permet à David d'attraper une erreur de compréhension avant qu'elle ne coûte.

---

## 11. Supervision n8n

Helios est **superviseur, pas décideur** — c'est un choix explicite de David.

- **Sondage** régulier des exécutions n8n : détection des échecs et des workflows en
  retard par rapport à leur cadence habituelle.
- **Alerte vocale** uniquement si David est présent, c'est-à-dire si un client audio est
  connecté et actif. Sinon l'alerte part en notification et attend son retour ; elle n'est
  pas perdue, et elle n'est pas répétée en boucle.
- **Point quotidien** à heure fixe : ce qui a tourné, ce qui a produit, ce qui dérive.
  Produit par l'étage réflexe, donc gratuit.
- **Diagnostic** : à l'échec, Helios lit l'exécution et l'erreur, et donne la cause en une
  phrase. Il **propose** un correctif ; il ne l'applique jamais seul. Toute modification de
  workflow est N3.
- **Déclenchement vocal** des workflows, en N2.

---

## 12. Hermes Agent — porte d'entrée distante

Hermes (`nousresearch/hermes-agent`, exposé en `hermes.example.com`) est un gateway
multi-modèles doté de ses propres intégrations de messagerie — Telegram, Discord, Slack,
WhatsApp, Signal, Email — **avec transcription vocale incluse**.

Son rôle dans Helios est strictement celui-là : **un transport**. Un skill Hermes relaie
les messages entrants vers un endpoint d'Helios et rend la réponse dans la messagerie.
David peut ainsi parler à Helios depuis n'importe où, sans qu'on ait à écrire une
application iPhone.

**Ce qui est délibérément laissé hors-jeu :** la mémoire d'Hermes, son modèle de
l'utilisateur (Honcho) et ses skills auto-créés. Hermes n'a pas à se construire un modèle
de David en parallèle de celui d'Helios : deux mémoires divergentes dont aucune ne fait
autorité est un piège connu, et le jour où elles se contredisent, il n'y a plus rien à
corriger de façon fiable. La source de vérité reste les fichiers Markdown d'Helios (D12).

---

## 13. Réseau, sécurité et secrets

- Communication entre machines en **WSS et HTTPS**, derrière le reverse proxy Unraid
  existant, sous le domaine déjà en place.
- **Vérification de l'origine** sur toutes les routes qui modifient un état.
- Les services GPU (`helios-stt`, `helios-tts`, Ollama) ne sont **pas exposés à
  l'extérieur** : ils ne sont joignables que depuis le LAN.
- Secrets en variables d'environnement, jamais dans le dépôt. Un `.env.example` documente
  les clés attendues ; `.env` est dans `.gitignore`.
- Le dépôt mémoire est versionné, donc **aucun secret ne doit y être écrit**. Un test
  vérifie l'absence de motifs de secrets à chaque commit mémoire.
- Helios ne saisit jamais d'identifiant ni de mot de passe, et n'exécute aucune action
  financière. Ces deux interdits ne sont pas configurables.

---

## 14. Risques et spikes préalables

Trois inconnues peuvent invalider une partie du design. Elles sont levées en **phase 0**,
avant toute ligne de code structurant, et chacune a un repli déjà identifié.

| # | Question | Repli si la réponse est non |
|---|---|---|
| S1 | Qwen3-TTS tient-il en français sur le 4070 Ti ? Qualité de voix, latence du premier morceau, VRAM en cohabitation avec ComfyUI. | Piper FR ou Kokoro. L'interface `/synthesize` est identique, donc le repli ne coûte qu'un changement de conteneur. |
| S2 | L'AEC d'Apple (Voice Processing, via un binaire Swift) supprime-t-il assez d'écho pour que le barge-in soit utilisable sur enceintes ? | Casque : l'AEC devient inutile, le barge-in reste fonctionnel, le confort baisse. |
| S3 | Un skill Hermes peut-il appeler un endpoint HTTP externe et rendre la réponse dans Telegram ? | Application web installée sur l'écran d'accueil de l'iPhone, comme envisagé initialement. |

Risques résiduels connus et acceptés :

- **VRAM partagée** — 12 Go pour Whisper, le TTS, Ollama et ComfyUI impose un chargement à
  la demande, donc une latence supérieure sur la première requête après inactivité. Le
  problème disparaît avec la 3090.
- **Le néo est un point de défaillance unique** — s'il tombe, Helios est muet. Acceptable
  pour un usage personnel ; à revoir si Helios devient critique.
- **Faux déclenchements du wake word** — inhérents à un wake word entraîné sur mesure. Le
  réglage de sensibilité est piloté par la mesure (§16), pas par l'impression.

---

## 15. Phasage

Chaque phase est utilisable seule. Si le projet s'arrête à la phase 2, il reste un
assistant qui vaut le coup.

**Phase 0 — Spikes.** S1, S2, S3. Sortie : trois réponses et les replis éventuellement
activés.

**Phase 1 — La boucle vocale, et rien d'autre.** `helios-audio`, `helios-core` réduit au
hub, `helios-stt`, `helios-tts`. Pas d'outils, pas de mémoire, pas de front.
*Critère de réussite :* « Hey Helios, quelle heure est-il » donne une réponse vocale, et
David peut le couper en pleine phrase. Push-to-talk d'abord, wake word entraîné ensuite
dans la même phase.

**Phase 2 — Le cerveau et la mémoire.** Brain persistant, rotation de contexte, mémoire
Markdown et index, serveur MCP local, permissions.
*Critère de réussite :* la conversation « réflexion vers document » tient de bout en bout,
et le document produit se relit sans retouche.

**Phase 3 — Les outils.** Registre d'outils, routeur d'intention, Ollama, supervision n8n,
point quotidien, déclenchement vocal, diagnostic.
*Critère de réussite :* un workflow n8n qui échoue déclenche une alerte vocale exacte, et
un workflow se déclenche à la voix.

**Phase 4 — Présence et accès.** Orbe et tableau de bord, Hermes en porte mobile.
*Critère de réussite :* David parle à Helios depuis Telegram hors de chez lui, et le
tableau de bord montre l'état réel du système.

**La v1 est l'ensemble des phases 0 à 4.** Au-delà, et déjà prévus par l'architecture :
Home Assistant, agenda et mail, satellites audio multi-pièces, sortie sur le HomePod.

---

## 16. Stratégie de test

Ce projet a une particularité qu'il faut assumer : la moitié ne se teste pas en unitaire.

**Le cœur logique se teste classiquement, en TDD.** Segmentation des phrases, routeur
d'intention, permissions, mémoire, registre d'outils, rotation de contexte — avec le
process Claude mocké derrière une interface. C'est là que vivront les vrais bugs, et c'est
là que va l'effort de test.

**La chaîne audio se mesure au lieu de se tester.** On constitue un jeu d'enregistrements
de référence — David, en français, dans ses conditions réelles : bureau, musique de fond,
à trois mètres du micro — et une commande `make bench` produit les chiffres qui comptent :

- taux de détection du wake word ;
- faux positifs sur une heure de parole normale ;
- taux d'erreur de transcription ;
- latence de bout en bout, par étage.

Sans cette mesure, la sensibilité se règle au jugé et chaque correction en casse une autre.
Les objectifs du §5 sont les seuils de ce banc.

**Un test compte plus que les autres :** une action de niveau N3 qui s'exécuterait sans
confirmation doit faire échouer la suite bruyamment. Un mail parti tout seul à un prospect
ne se rattrape pas. Ce test est écrit en premier, avant l'implémentation des permissions.

**Pas d'appel à la vraie API Claude en intégration continue.** Le Brain est derrière une
interface, et le process est mocké.

---

## 17. Structure du dépôt

```
Helios/
  src/
    helios_audio/      client M5 : Python + binaire Swift pour l'AEC
    helios_core/       Core : hub, Brain, routeur, mémoire, permissions, MCP
    helios_web/        front : orbe Three.js + tableau de bord
  tools/               un fichier par outil, découverte automatique
  services/
    stt/               Dockerfile + service faster-whisper
    tts/               Dockerfile + service Qwen3-TTS (et repli)
  memory/              dépôt mémoire Markdown (versionné)
  tests/
  bench/               jeu d'enregistrements de référence et banc de mesure
  config/
  scripts/
  docs/
```

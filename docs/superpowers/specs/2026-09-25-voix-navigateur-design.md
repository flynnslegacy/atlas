# La voix dans le navigateur — design

**Date :** 25 septembre 2026
**Statut :** design validé par David, section par section ; ajusté par le spike S4 (§8) et par le plan (§12)
**Spec parente :** `2026-09-22-atlas-design.md` (§6.5 la page, §13 réseau et sécurité, §15 phasage) ; s'appuie sur
`2026-09-24-interface-orbe-design.md` (la page) et `2026-09-24-phase-2a-cerveau-design.md` (le cerveau, la boucle
vocale, la clé de `/ws/audio`)
**Approche retenue :** le Core écoute pour la page — la page n'est qu'un terminal audio, et le Core fait tourner pour
elle le même code que le client audio du Mac

## 1. Objectif et critères de réussite

Aujourd'hui, seul le MacBook où tourne `make run-audio` entend « Hey Atlas » : parler à Atlas oblige à être devant
l'ordinateur. La page d'Atlas, déjà ouverte sur l'iPhone et l'iPad, doit pouvoir écouter et répondre à voix haute,
elle aussi.

Deux contraintes d'iOS bornent ce qu'une page peut faire :

- **pas de micro sans HTTPS** : Safari n'ouvre le micro que pour une page servie de façon sûre ; la page d'Atlas est
  aujourd'hui servie en HTTP sur le réseau local ;
- **pas de micro en arrière-plan** : iOS coupe le micro d'une page dès que l'écran se verrouille ou que Safari passe
  en arrière-plan. Une page écoute tant qu'elle est ouverte, écran allumé — un iPad sur un support, un iPhone posé sur
  le bureau —, jamais dans la poche.

| Critère | Objectif, mesuré sur les vrais appareils |
|---|---|
| iPad sur un support | « Hey Atlas » dit à l'iPad : la réponse sort de l'iPad |
| iPhone, bouton | Toucher l'orbe sur l'iPhone, poser la question : la réponse sort de l'iPhone |
| Coupure de parole | À l'iPad, « attends » pendant qu'Atlas parle le coupe (si le spike S4 la valide, §8) |
| Clavier | Une question tapée sur l'iPhone, micro allumé, reçoit sa réponse à voix haute sur l'iPhone |
| Écran verrouillé | Verrouiller l'iPhone ferme proprement le micro ; au retour, un toucher le rouvre |
| Le Mac | Le client audio du Mac marche toujours, en même temps que les pages |
| Non-régression | `make test` au vert |

## 2. Décisions

- **D1. Deux usages, page ouverte.** « Hey Atlas » écouté par la page (iPad sur un support, iPhone posé), et l'orbe
  à toucher pour parler. Siri avec le téléphone verrouillé, l'écoute en arrière-plan et une app native restent hors
  périmètre.
- **D2. Le HTTPS par Nginx Proxy Manager**, le reverse proxy de l'Unraid, sous un sous-domaine du domaine de David,
  avec un vrai certificat, l'accès limité au réseau local et au VPN (spec parente §13).
- **D3. Chacun le sien.** Chaque appareil qui écoute répond pour lui-même ; aucun arbitrage entre appareils. Tous
  partagent le cerveau : si deux appareils se réveillent ensemble, la seconde question coupe la première, comme
  aujourd'hui entre la voix et le clavier.
- **D4. Le Core écoute pour la page.** La page capte le micro, l'envoie au Core et joue le son qu'il renvoie. Le mot
  de réveil, la détection de voix, la fin de phrase, la coupure de parole et la relance tournent sur le Core, dans le
  `ClientAudio` déjà écrit et réglé pour le Mac, une instance par page. Aucun modèle d'IA dans le navigateur.
- **D5. Une connexion `/ws/voix` par page qui utilise le micro**, distincte de `/ws/web` et protégée comme elle.
- **D6. Le client audio du Mac reste**, avec son annulation d'écho Swift éprouvée.
- **D7. Le spike S4 d'abord** : l'annulation d'écho du navigateur doit effacer la voix d'Atlas du micro. Repli s'il
  échoue sur un appareil : pas de coupure à la voix sur celui-là (§8).

## 3. Architecture

```
Page (iPhone, iPad, Mac)                         Core
 micro ─► AudioWorklet ─► blocs 16 kHz ─────►  /ws/voix ─► PeripheriqueNavigateur
 haut-parleur ◄── lecture ◄── trames ◄──────               │ lire_bloc / jouer / vider
                                                          ▼
                                         ClientAudio (le code du client du Mac)
                                                          │ en mémoire, sans réseau
                                                          ▼
                                         Session ─► cerveau partagé, STT, TTS
```

Le `ClientAudio` ne change pas de rôle : son « périphérique » n'est plus le binaire Swift mais la page, et son
« transport » appelle directement la `Session` dans le même processus, comme le fait déjà le test d'intégration
(`tests/test_integration_boucle.py`). La session, elle, envoie au `ClientAudio` ce qu'elle envoyait au client du Mac.

### 3.1 Côté Core

| Fichier | Rôle |
|---|---|
| `src/atlas_core/voix.py` (nouveau) | `PeripheriqueNavigateur`, `ReveilleurPage`, et le montage d'une page : `ClientAudio` + `Session` |
| `src/atlas_core/protocole_voix.py` (nouveau) | Les messages de `/ws/voix` (§6) |
| `src/atlas_core/hub.py` | La route `/ws/voix` ; `Authentification` de `/ws/web` porte l'identifiant de la page |
| `src/atlas_core/protocole_web.py` | `Authentification` gagne `page` (facultatif) |
| `src/atlas_core/regie.py` | Plusieurs sessions audio ; une question tapée va à la session de sa page ; le muet les fait toutes taire |
| `src/atlas_core/config.py` | `voix_marge_s`, `voix_bargein_dbfs` |
| `src/atlas_audio/client.py` | La marge de sortie (`MARGE_SORTIE_S`) devient un paramètre du `ClientAudio` ; l'amorçage de l'annuleur d'écho ; l'orbe touchée (`demander_la_parole`) |

Le Core importe désormais `atlas_audio` (le client, Silero, openWakeWord) : la machine du Core a besoin des
dépendances `audio` et des modèles (§7.3).

### 3.2 Côté page

| Fichier | Rôle |
|---|---|
| `src/atlas_web/voix.js` (nouveau) | La connexion `/ws/voix`, le micro, le verrou d'écran, les boutons |
| `src/atlas_web/voix_worklet.js` (nouveau) | Les deux processeurs AudioWorklet, capture et lecture, et leurs calculs purs, testés avec `node --test` : rééchantillonnage, découpage en blocs de 20 ms, tampon de lecture |
| `src/atlas_web/app.js`, `index.html`, `style.css` | Le bouton « Micro », l'interrupteur « Hey Atlas », l'orbe à toucher |

### 3.3 Documentation

| Fichier | Rôle |
|---|---|
| `scripts/neo/LISEZMOI.md` | Nginx Proxy Manager, le DNS, le certificat, les modèles sur la machine du Core |
| `docs/superpowers/spikes/2026-09-25-s4-voix-navigateur.md` (nouveau) | Le protocole et le verdict du spike S4 |

## 4. La page

- **Un bouton « Micro » par appareil**, à côté de « muet ». Il faut le toucher après chaque ouverture de la page :
  iOS exige un geste pour ouvrir le micro et le son (`getUserMedia`, `AudioContext.resume`). Safari demande
  l'autorisation la première fois. Micro allumé, la page envoie le son en continu au Core (iOS affiche son point
  orange) ; éteint, plus rien ne part et `/ws/voix` se ferme.
- **Un interrupteur « Hey Atlas »**, retenu par l'appareil (`localStorage`, comme le choix de l'orbe) : allumé, le
  Core écoute le mot de réveil pour cette page ; éteint, il ne se réveille jamais seul.
- **Toucher l'orbe**, micro allumé : au repos, Atlas t'écoute, comme après « Hey Atlas » ; pendant qu'il parle, c'est
  une coupure de parole. Dans les deux modes. La relance après une réponse fonctionne comme sur le Mac.
- **Le son.** Le micro est capté avec les réglages par défaut du navigateur : annulation d'écho, réduction de bruit,
  gain automatique (spike S4). L'annulation d'écho n'est jamais coupée : sans elle, iOS baisse la voix d'Atlas. Le processeur de capture ramène le son à 16 kHz mono en blocs de 20 ms (640 octets,
  s16le) ; le processeur de lecture joue les trames reçues, rééchantillonnées à la fréquence du contexte, dans un
  tampon que le Core peut vider d'un coup.
- **Écran allumé.** Tant que « Hey Atlas » écoute, la page demande à l'écran de rester allumé (API Wake Lock,
  iOS 16.4 et plus), et le redemande quand elle redevient visible.
- **Quand iOS coupe le son** (écran verrouillé, app en arrière-plan, appel), la page garde `/ws/voix` ouverte (et la
  rouvre si iOS l'a fermée entre-temps). Au retour, le son repart seul (spike S4) ; la page n'affiche « Touche pour
  réactiver le micro » que s'il ne reprend pas, et signale la reprise au Core (`reprise`).
- Aucune dépendance, aucune ressource extérieure ; la politique de sécurité ne change pas (`default-src 'self'`
  couvre le module de l'AudioWorklet ; `connect-src` accepte déjà `wss://` sur l'hôte de la page).

## 5. Le Core

- **La route `/ws/voix`**, sur le modèle de `/ws/web` : origine vérifiée avant d'accepter (`1008`) ; premier message
  `authentification` avec la clé des pages (`ATLAS_WEB_CLE`) sous 5 s, comparée en temps constant ; fermeture `4401`
  sinon, `4000` sans clé configurée.
- **Par page, le Core monte** :
  - un `PeripheriqueNavigateur` : `lire_bloc` attend le prochain bloc reçu de la page ; `jouer` lui envoie une trame ;
    `vider` lui envoie `vider` ;
  - un `ReveilleurPage` : il se déclenche sur « Hey Atlas » (openWakeWord, `hey_atlas.onnx`) si l'interrupteur est
    allumé ;
  - `parler` va directement au `ClientAudio` (`demander_la_parole`), qui le traite au bloc suivant : au repos, il
    ouvre l'écoute comme un réveil ; pendant qu'Atlas parle, il déclenche la même coupure qu'un barge-in —
    `Interruption` au Core, son vidé, capture ouverte ;
  - un détecteur de voix Silero, le `ClientAudio` et sa `Session`, rattachée à la régie sous l'identifiant de la page.
    Les modèles (Silero, « Hey Atlas ») gardent un état : chaque page a les siens, chargés hors de la boucle du Core.
    S'ils manquent sur la machine du Core, la page reçoit `erreur` (`modeles_absents`) et la connexion se ferme
    (`4000`).
  - Quand la page part, la session est fermée et détachée, comme pour `/ws/audio`.
- **Les réglages** sont ceux du client du Mac, lus par le Core (`ATLAS_REVEIL_SEUIL`, `ATLAS_SILENCE_MS`,
  `ATLAS_BARGEIN_MS`, `ATLAS_RELANCE_S`), plus deux réglages du navigateur :
  - `ATLAS_VOIX_MARGE_S` : la latence de sortie du navigateur, là où le client du Mac prend 0,15 s ;
  - `ATLAS_VOIX_BARGEIN_DBFS` : la porte d'énergie du barge-in, l'écho résiduel n'étant pas celui du binaire Swift.
  Valeurs par défaut, d'après le spike S4 : 0,2 s et −40 dBFS.
- **Le démarrage de l'annuleur** (spike S4) : pendant les dix premières secondes de voix d'Atlas jouée après
  l'ouverture de `/ws/voix` ou un message `reprise`, la coupure à la voix est ignorée (toucher l'orbe coupe
  toujours). L'annuleur laisse passer l'écho le temps de s'installer, une seule fois : 0,7 s sur iOS, 7 à 10 s dans
  Chrome sur macOS.
- **La régie** garde toutes les sessions audio (et non plus seulement la dernière). Une question tapée va à la session
  de sa page si elle en a une, sinon à la session audio la plus récente, sinon à la session écrite. Le muet fait taire
  toutes les sessions audio.
- **Le calcul** (openWakeWord et Silero, quelques millisecondes toutes les 80 ms par page à l'écoute) tourne sur la
  boucle du Core ; c'est acceptable pour quelques appareils, et le spike S4 le mesure.

## 6. Le protocole de `/ws/voix`

Page vers Core :

| Message | Contenu |
|---|---|
| `authentification` | `{cle, page, hey_atlas}` — premier message, sous 5 s |
| *(binaire)* | un bloc de micro : 640 octets s16le à 16 kHz (20 ms), bruts — sur `/ws/voix`, tout ce qui est binaire est de l'audio |
| `parler` | `{}` — l'orbe a été touchée |
| `hey_atlas` | `{actif}` — l'interrupteur a changé |
| `reprise` | `{}` — le son reprend après une interruption d'iOS |

Core vers page :

| Message | Contenu |
|---|---|
| `pret` | `{}` — la clé est acceptée : la page peut envoyer son micro |
| *(binaire)* | une trame à jouer : 640 octets bruts ; le client que le Core fait tourner pour la page a déjà écarté celles d'un énoncé coupé |
| `vider` | `{}` — le son en cours s'arrête net |
| `erreur` | `{code, message}` — `cle_absente`, `modeles_absents`, `message_invalide`, `trame_invalide` |

Fermetures : `1008` (origine), `4401` (clé refusée ou absente du premier message), `4000` (clé ou modèles non
configurés sur le Core), `1011` (la voix de la page s'est arrêtée sur une panne : la page se rebranche).

`/ws/web` : `authentification` gagne `page` (facultatif), le même identifiant tiré au hasard par la page à son
ouverture, pour qu'une question tapée trouve la session de sa page.

## 7. HTTPS et déploiement

### 7.1 Nginx Proxy Manager

Un « Proxy Host » dans Nginx Proxy Manager, sur l'Unraid :

- le sous-domaine (dans le dépôt : `atlas.example.com`) → `http://<machine du Core>:8080` ;
- « Websockets Support » coché ; l'en-tête `Host` transmis tel quel (le comportement par défaut), pour que le
  contrôle d'origine du Core reconnaisse la page ;
- une « Access List » qui n'autorise que le réseau local et le VPN ;
- « Force SSL », avec un certificat Let's Encrypt. Le sous-domaine n'étant pas joignable depuis Internet, le
  certificat s'obtient par le défi DNS (ou par un certificat générique du domaine, s'il en existe déjà un) ;
- des délais longs pour les WebSockets (onglet « Advanced » : `proxy_read_timeout 3600s;` et
  `proxy_send_timeout 3600s;`) : sinon nginx ferme au bout de 60 s une connexion `/ws/web` restée silencieuse.

### 7.2 Le DNS

Le sous-domaine pointe vers l'adresse de l'Unraid sur le réseau local (enregistrement DNS local, ou enregistrement
public vers une adresse privée).

### 7.3 Les modèles sur la machine du Core

La machine du Core doit avoir les dépendances `audio` (`make install` les installe déjà) et les modèles :
`models/hey_atlas.onnx`, `models/silero_vad.onnx` et les modèles d'openWakeWord. Le guide du néo dit de les copier
depuis le M5.

### 7.4 Le client du Mac

Il continue de parler directement au Core (`ATLAS_CORE_URL`, sur le réseau local), sans passer par le proxy.

## 8. Le spike S4

Avant d'écrire le plan, lancé par David sur l'iPhone et l'iPad, à travers le proxy : le HTTPS (§7.1, §7.2) est donc
installé d'abord. Une page jetable, hors du dépôt (`spikes/s4-voix-navigateur/`), servie le temps du spike par un
petit serveur sur le M5 vers lequel pointe le « Proxy Host », mesure :

- **l'écho résiduel** pendant qu'Atlas parle, comme le spike S2 : niveau du micro avec et sans la voix d'Atlas, et
  atténuation obtenue par l'annulation d'écho du navigateur ;
- la fréquence réelle du micro et du contexte audio, et le fonctionnement de l'AudioWorklet ;
- le verrou d'écran, et ce qui arrive au micro quand l'écran se verrouille puis se déverrouille ;
- la latence de sortie (le délai entre l'envoi d'un son et son écoute), pour `ATLAS_VOIX_MARGE_S` ;
- le coût du mot de réveil et de Silero sur la boucle du Core, par page (par un script sur le M5, qui les fait
  tourner sur des blocs enregistrés).

**Sorties :** le verdict dans `docs/superpowers/spikes/2026-09-25-s4-voix-navigateur.md`, les valeurs par défaut de
`ATLAS_VOIX_MARGE_S` et `ATLAS_VOIX_BARGEIN_DBFS`, et les contraintes de capture retenues (`noiseSuppression`,
`autoGainControl`).

**Repli** si l'écho passe malgré tout sur un appareil : pas de coupure à la voix sur celui-là. Le micro se tait
pendant qu'Atlas parle, et on touche l'orbe pour le couper ; l'annulation d'écho, elle, reste active.

**Verdict (25 septembre 2026) :** approche validée sur l'iPhone et sur le Mac (Chrome) ; valeurs et ajustements
reportés aux §4, §5 et §6.
L'iPad reste à vérifier à l'essai sur le matériel. Voir `docs/superpowers/spikes/2026-09-25-s4-voix-navigateur.md`.

## 9. Les tests

- **Python** : `PeripheriqueNavigateur` et `ReveilleurPage` ; l'authentification de `/ws/voix` (clé, délai, origine,
  clé absente) ; la régie (plusieurs sessions, question tapée routée par page, muet pour toutes) ; un test
  d'intégration page → Core → page avec une fausse WebSocket, sur le modèle de `tests/test_integration_boucle.py`.
- **JavaScript** (`node --test`) : rééchantillonnage, découpage en blocs, tampon de lecture et vidage, protocole de
  `voix.js` avec une fausse WebSocket et un faux contexte audio.
- **À la main, par David** : l'essai sur les vrais appareils, contre les critères du §1.

## 10. Hors périmètre

- Siri avec le téléphone verrouillé ou la montre ; l'écoute en arrière-plan ; une app native.
- L'arbitrage entre appareils (qui répond quand plusieurs entendent).
- La sortie sur le HomePod.
- Le mot de réveil dans le navigateur (approches B et C, écartées).

## 11. Changements dans la spec parente

- **§6.5 :** la page capte aussi la voix (micro, « Hey Atlas », l'orbe à toucher), le Core écoutant pour elle.
- **§13 :** la page passe en HTTPS derrière Nginx Proxy Manager ; `/ws/voix` rejoint les routes protégées.
- **§15 :** une étape « la voix dans le navigateur » s'insère entre la phase 2a et la phase 2b.

## 12. Ajustements du plan (25 septembre 2026)

En écrivant et en vérifiant le code du plan (`docs/superpowers/plans/2026-09-25-voix-navigateur.md`) :

- **L'audio de `/ws/voix` passe brut**, 640 octets dans les deux sens (§6) : la connexion ne transporte que de l'audio
  en binaire, et les trames d'un énoncé coupé sont déjà écartées côté Core.
- **Le Core confirme l'entrée d'une page** par `pret` (§6) : la page n'envoie son micro qu'une fois acceptée.
- **Toucher l'orbe va directement au client audio** (§5), au repos comme pendant qu'Atlas parle ; le réveilleur de la
  page n'écoute que « Hey Atlas ».
- **Les calculs purs de l'audio vivent dans `voix_worklet.js`** (§3.2) : le module de l'AudioWorklet reste d'un seul
  tenant, sans import, et ses classes se testent quand même avec `node --test`.

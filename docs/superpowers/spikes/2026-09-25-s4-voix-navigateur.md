# Spike S4 — Verdict : la voix dans le navigateur

**Date :** 25 septembre 2026
**Statut :** mesuré sur l'iPhone le 25 septembre 2026 ; approche validée, avec trois ajustements de la spec. L'iPad, absent ce jour-là, reste à vérifier à l'essai sur le matériel
**Spec :** `docs/superpowers/specs/2026-09-25-voix-navigateur-design.md` (§8)
**Code du spike (jetable, non versionné) :** dossier local `spikes/s4-voix-navigateur/` (`index.html`, `essai.js`,
`processeurs.js`, `serveur.py`, `analyse_s4.py`, `cout_cpu.py`)

## Les questions

1. L'annulation d'écho du navigateur efface-t-elle assez la voix d'Atlas du micro, sur l'iPhone et sur l'iPad, pour
   qu'on puisse couper Atlas à la voix sans qu'il se coupe tout seul ? Avec quelle porte d'énergie
   (`ATLAS_VOIX_BARGEIN_DBFS`) ?
2. « Hey Atlas » est-il encore reconnu à travers le traitement du navigateur (annulation d'écho, réduction de bruit,
   gain automatique) ? Le modèle a été entraîné sur le micro brut du Mac.
3. Quelle latence entre le son envoyé à la page et son arrivée au micro (`ATLAS_VOIX_MARGE_S`) ?
4. Le verrou d'écran garde-t-il l'iPad allumé ? Que devient le micro quand l'écran se verrouille, ou quand Safari
   passe en arrière-plan, puis au retour ?
5. Combien coûte au Core une page à l'écoute ?

## Déjà mesuré : le coût sur le Core

`cout_cpu.py` fait tourner openWakeWord et Silero, avec les classes du client, sur 60 s de voix d'Atlas en blocs de
20 ms, sur le MacBook Pro M5 :

| Traitement | Calcul par seconde d'audio | Pire bloc |
|---|---|---|
| openWakeWord (`hey_atlas.onnx`) | 18,4 ms (1,8 % d'un cœur) | 2,2 ms |
| Silero | 1,9 ms (0,2 % d'un cœur) | 0,2 ms |
| **Par page à l'écoute** | **20,3 ms (2,0 % d'un cœur)** | — |

C'est négligeable pour la boucle du Core, même avec plusieurs appareils : le calcul peut rester sur la boucle, comme
la spec le prévoyait. À revérifier sur le néo s'il est nettement moins rapide que le M5.

## Ce que teste la page

La page utilise les deux processeurs AudioWorklet que la vraie page reprendra :
- la capture ramène le micro à 16 kHz mono en blocs de 20 ms, avec un passe-bas à 7,2 kHz. Vérifiée à 48 et à
  44,1 kHz sur des sinus synthétiques : fréquence et amplitude conservées, un 9 kHz atténué de 59 à 64 dB ;
- la lecture joue des blocs 16 kHz à la fréquence du contexte, et se vide d'un coup.

La voix d'Atlas jouée est celle du spike S2 (Qwen3). Chaque capture est ce que le Core recevrait : les blocs 16 kHz
produits par la page. Tout part au serveur du spike, sur le M5, pour l'analyse.

## Prérequis : le HTTPS

1. **DNS :** un sous-domaine (ici `atlas.example.com`) pointe vers l'adresse de l'Unraid sur le réseau local.
2. **Nginx Proxy Manager :**
   - **certificat :** « SSL Certificates » → « Add SSL Certificate » → Let's Encrypt, pour le sous-domaine, avec
     « Use a DNS Challenge » (le sous-domaine n'est pas joignable depuis Internet). Ou le certificat générique du
     domaine, s'il existe déjà ;
   - **liste d'accès :** « Access Lists » → une liste qui n'autorise que le réseau local et le VPN, et refuse le reste ;
   - **hôte :** « Proxy Hosts » → « Add Proxy Host » : le sous-domaine, schéma `http`, l'adresse du M5 sur le
     réseau local (`ipconfig getifaddr en0` sur le M5), port `8090` ; « Websockets Support » coché ; la liste d'accès
     ci-dessus ; onglet « SSL » : le certificat, « Force SSL » ; onglet « Advanced » :
     `proxy_read_timeout 3600s;` et `proxy_send_timeout 3600s;`.
3. **Le serveur du spike sur le M5 :** `uv run python spikes/s4-voix-navigateur/serveur.py` (autoriser les connexions
   entrantes si macOS le demande).

Après le spike, le même « Proxy Host » pointera vers le Core (port `8080`).

## Le protocole, sur chaque appareil (iPhone, puis iPad)

L'appareil à sa place habituelle (l'iPad sur son support, l'iPhone posé sur le bureau), volume à 50 %, la page ouverte
en HTTPS sur le sous-domaine :

1. **Environnement** : contexte sûr, AudioWorklet, Wake Lock, contexte audio à 16 kHz possible ou non.
2. **Essai d'écho et de réveil** (3 min, consignes à l'écran) :
   - `bruit` (8 s) : silence ;
   - `echo` (60 s) : Atlas parle, David se tait ;
   - `parole` (12 s) : David lit une phrase à sa distance habituelle ;
   - `reveil` (16 s) : « Hey Atlas » à chacun des trois « Parle ! » ;
   - `double` (24 s) : Atlas parle ; à chacun des trois « Parle ! », David dit « Attends, attends, stop » ;
   - `echo_repris` (18 s) : Atlas rejoue son début, l'annuleur ayant appris la pièce ;
   - `sans_aec` (22 s) : annulation d'écho coupée ; cinq clics (pour la latence), puis le même début de voix.
3. **Garder l'écran allumé** : attendre plus longtemps que le verrouillage automatique de l'appareil ; l'écran
   doit rester allumé.
4. **Verrouillage de l'écran** : écoute continue ; verrouiller 10 s puis revenir ; passer 10 s dans une autre app puis
   revenir ; ne rien toucher 10 s (le micro revient-il seul ?) ; puis « Reprendre » ; puis « Envoyer le journal ».

## L'analyse

`analyse_s4.py` rejoue sur les captures le jugement exact du client, comme au spike S2 : Silero à 0,5, porte
d'énergie sur 300 ms, 300 ms de voix pour couper ; et le mot de réveil au seuil 0,5. Il mesure :

- le bruit de fond, l'écho résiduel (médiane, 95e centile, maximum, début et fin de la minute d'écho) ;
- l'atténuation de l'écho : même voix, avec et sans annulation, au démarrage et une fois l'annuleur installé ;
- les faux barge-in sur `echo` et `echo_repris`, pour chaque porte d'énergie de −55 à −30 dBFS ;
- les vraies coupures sur `double` (délai après chaque « Parle ! », et coupures hors des répliques) ;
- le niveau de la voix de David, et le nombre de « Hey Atlas » reconnus sur trois ;
- la latence aller-retour d'après les cinq clics.

La chaîne page → serveur → analyse a été vérifiée sur un faux essai synthétique : latence, atténuation et comptes de
coupures retrouvés tels qu'injectés.

## Ce qui décidera

- **La coupure à la voix est retenue sur un appareil** s'il existe une porte d'énergie qui donne à la fois zéro faux
  barge-in sur `echo_repris`, au plus un sur la minute d'`echo` (le démarrage de l'annuleur, comme au spike S2), et les
  trois vraies coupures de `double` en moins de 1,5 s. Sinon, le repli de la spec : le micro se tait pendant
  qu'Atlas parle sur cet appareil, et on touche l'orbe pour le couper.
- **« Hey Atlas » tel quel** si au moins deux « Hey Atlas » sur trois sont reconnus. Sinon, essayer sans réduction de
  bruit ni gain automatique ; en dernier recours, réentraîner avec des prises passées par le navigateur.
- **`ATLAS_VOIX_MARGE_S`** : la moitié de la latence aller-retour mesurée, plus une marge pour le réseau.
- **L'iPad sur son support** n'est possible que si le verrou d'écran tient.

## Résultats

### L'iPhone

iOS 27, Chrome pour iOS (le moteur de Safari, imposé sur iOS), volume à 50 %, posé sur le bureau. Micro demandé avec
`echoCancellation`, `noiseSuppression` et `autoGainControl` (les valeurs par défaut du navigateur) ; contexte audio à
48 kHz.

| Mesure | Résultat | Exigé |
|---|---|---|
| Écho résiduel pendant qu'Atlas parle, sur 300 ms | −94,4 dBFS en médiane, −68,5 au 95e centile | — |
| Même voix, l'annuleur installé (`echo_repris`) | −95,0 dBFS en médiane, −77,6 au maximum | — |
| Voix de David à sa distance habituelle | −20,7 dBFS en médiane | — |
| Faux barge-in sur la minute d'écho | **1**, à toute porte d'énergie : le démarrage de l'annuleur (ci-dessous) | au plus 1 |
| Faux barge-in, l'annuleur installé | **0**, à toute porte d'énergie | 0 |
| Vraies coupures (« Attends, attends, stop ») | **3 sur 3**, en 1,29 ; 1,10 ; 1,06 s, réaction de David comprise, de −55 à −30 dBFS | 3 sur 3, < 1,5 s |
| « Hey Atlas » à travers le traitement du navigateur | **3 sur 3** | au moins 2 sur 3 |
| Latence aller-retour (cinq clics) | 71 à 72 ms | — |
| Écran gardé allumé | tenu (constaté par David) | — |
| Écran verrouillé, ou autre app devant | contexte « interrupted », plus aucun bloc ; la piste reste « live » | — |
| Retour sur la page | le son repart seul, 50 blocs/s, **sans toucher l'écran** | — |

**Le démarrage de l'annuleur.** Pendant les 0,7 premières secondes de la toute première voix d'Atlas après l'ouverture
du micro, l'écho passe entier (−19 dBFS, autant que la voix jouée), puis tombe sous −84 dBFS. C'est l'unique faux
barge-in. Les voix suivantes (`double`, `echo_repris`) démarrent déjà sous −85 dBFS : l'annuleur ne démarre qu'une
fois.

**Sans annulation d'écho, iOS baisse la voix d'Atlas.** David l'a entendue « très faible » dans la phase `sans_aec`,
normale partout ailleurs. L'atténuation calculée par le script (25 dB) compare donc deux sons joués différents : elle
ne vaut rien. La marge utile est celle, mesurée dans le même réglage, entre la voix de David et l'écho résiduel :
plus de 45 dB.

### Le Mac (Chrome)

Un premier passage est invalide : le micro n'a livré que des zéros, du début à la fin (Chrome avait l'autorisation du
site, mais macOS lui envoyait du silence). David a corrigé le réglage et refait l'essai, Chrome 153 sur macOS,
volume à 50 % :

| Mesure | Résultat |
|---|---|
| Bruit de fond | −59 dBFS |
| Écho résiduel, par tranches de 5 s (médiane) | −25, −39, puis −66 dBFS et stable |
| Même voix, l'annuleur installé | −73,9 dBFS en médiane, −59,8 au maximum |
| Atténuation, même voix avec et sans annulation | 34 dB au démarrage, 43 dB l'annuleur installé |
| Voix de David | −19,8 dBFS |
| Faux barge-in pendant l'installation de l'annuleur | **un épisode**, de 2,1 à 6,9 s (l'analyse le compte 17 fois : elle redéclenche toutes les 0,3 s tant qu'il dure) |
| Faux barge-in, l'annuleur installé | **0** |
| Vraies coupures | **3 sur 3**, en 0,92 à 1,04 s |
| « Hey Atlas » | **3 sur 3** |
| Latence aller-retour | 77 à 107 ms |
| Onglet caché | Chrome continue de capter (50 blocs/s) |

**L'annuleur de Chrome sur macOS met 7 à 10 s à s'installer**, contre 0,7 s pour celui d'iOS ; une seule fois lui
aussi. Sans annulation, la voix d'Atlas n'a pas baissé sur le Mac : l'atténuation mesurée y est valable.

### L'iPad

Pas mesuré (absent ce jour-là). Même moteur et même traitement vocal d'Apple que l'iPhone : on s'attend aux mêmes
résultats, à confirmer à l'essai sur le matériel, verrou d'écran compris.

### Le Core

2 % d'un cœur par page à l'écoute (voir plus haut).

## Décision

**L'approche de la spec est validée**, avec ces réglages et trois ajustements :

- **`ATLAS_VOIX_BARGEIN_DBFS` = −40 dBFS**, comme pour le Mac : toutes les portes de −55 à −30 donnent le même
  résultat, et −40 laisse une vingtaine de dB de marge sous la voix de David et plus de quarante au-dessus de l'écho
  résiduel.
- **`ATLAS_VOIX_MARGE_S` = 0,2 s** : la marge du Mac (0,15 s) plus 50 ms pour le Wi-Fi ; la latence aller-retour
  mesurée est de 72 ms.
- **Contraintes de capture** : les valeurs par défaut du navigateur (annulation d'écho, réduction de bruit, gain
  automatique), avec lesquelles « Hey Atlas » passe trois fois sur trois.

Les ajustements de la spec :

1. **Le démarrage de l'annuleur** : pendant les dix premières secondes de voix d'Atlas jouée après l'ouverture du
   micro (ou sa reprise après une interruption), la coupure à la voix est ignorée ; toucher l'orbe coupe toujours.
   Dix secondes couvrent l'annuleur de Chrome sur macOS (7 à 10 s) comme celui d'iOS (0,7 s) : un seul réglage
   partout, choisi par David plutôt qu'un réglage par appareil.
2. **L'annulation d'écho reste toujours active.** Le repli, si l'écho passait sur un appareil, supprime la coupure à
   la voix, jamais l'annulation d'écho : sans elle, iOS baisse la voix d'Atlas.
3. **Au retour sur la page, le son repart seul** : la page garde `/ws/voix` ouverte pendant une interruption, la
   rouvre si iOS l'a fermée, et n'affiche « Touche pour réactiver le micro » que si le son ne reprend pas.

## Leçon de méthode

- **Rejouer le jugement du client sur les captures** a encore payé : le faux barge-in se lit dans les niveaux bloc à
  bloc, et se révèle être un démarrage unique, pas un défaut de fond.
- **Demander à David ce qu'il entendait** a évité une fausse conclusion : sans son « très faible », le chiffre
  d'atténuation aurait été pris au sérieux.
- **Vérifier les captures brutes avant de conclure** : le premier passage du Mac « réussissait » (zéro faux
  barge-in) parce que son micro était muet.
- **Mesurer plus d'un navigateur** : l'iPhone seul aurait fixé l'amorçage à 1,5 s, trop court pour Chrome sur macOS.


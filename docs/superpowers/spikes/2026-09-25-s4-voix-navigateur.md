# Spike S4 — La voix dans le navigateur : protocole

**Date :** 25 septembre 2026
**Statut :** protocole prêt ; mesures sur l'iPhone et l'iPad à faire par David ; le verdict viendra compléter ce document
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

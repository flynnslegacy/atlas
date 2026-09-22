# Le banc de mesure

Ce banc produit les quatre chiffres qui décident des réglages d'Helios : le
taux de détection du mot de réveil, le nombre de faux réveils par heure, le
taux d'erreur de transcription et la latence. Sans lui, ces réglages se font
à l'oreille, et chaque correction en casse une autre sans qu'on s'en aperçoive.

Le banc ne vaut que par les enregistrements qu'on lui donne. Personne d'autre
que toi ne peut les fournir : ils doivent être ta voix, dans ta pièce, dans
tes conditions réelles. Ce document explique quoi enregistrer, comment, et ce
que fait `make bench` une fois que c'est en place.

## Ce qu'il faut enregistrer

Tout doit être au format suivant : **WAV, 16 kHz, mono, 16 bits**. Si un
enregistrement est dans un autre format (par exemple issu du micro du
téléphone ou d'une appli d'enregistrement), convertis-le avec :

```bash
ffmpeg -i source.m4a -ar 16000 -ac 1 -sample_fmt s16 phrase01.wav
```

(`ffmpeg -i source.wav ...` fonctionne pareil si la source est déjà un WAV
mais dans un mauvais format.)

Trois dossiers, à créer sous `bench/enregistrements/` — **ils ne doivent
jamais être commités** (voir plus bas) :

### 1. `bench/enregistrements/positifs/` — 30 prises de « Hey Helios »

Le mot de réveil prononcé, et rien d'autre par fichier. Varie les conditions
pour que la mesure reflète l'usage réel, par exemple une répartition possible
sur les 30 prises :

- au micro (tout près, comme en le testant)
- à un mètre
- à trois mètres
- avec de la musique de fond
- en parlant vite
- en parlant bas

Un fichier WAV par prise, nommé comme tu veux (`positif01.wav`, `positif02.wav`,
...).

### 2. `bench/enregistrements/negatifs/` — une heure de parole normale

Aucun fichier ne doit contenir le mot de réveil. L'idée est de mesurer les
faux réveils sur de la parole française ordinaire, dans la pièce où Helios
vivra : une réunion enregistrée, un appel, une vidéo qui tourne en fond,
toi qui parles tout seul... Ce qui compte, c'est que ce soit du français,
dans les mêmes conditions acoustiques que l'usage réel, et qu'au total ça
fasse environ une heure (répartis sur autant de fichiers que tu veux).

### 3. `bench/enregistrements/phrases/` — 20 énoncés représentatifs

Vingt phrases qui ressemblent à ce que tu diras vraiment à Helios une fois
en service (des questions, des commandes, des notes). Un fichier WAV par
phrase, et sa transcription exacte — mot pour mot, telle que tu l'as
prononcée — dans `bench/attendus.json`.

Exemple d'idées de phrases (à remplacer par les tiennes, adaptées à ton
usage réel) : « quelle heure est-il », « lance la veille concurrence »,
« note ça dans le projet Helios », « rappelle-moi d'appeler le plombier »,
« quel temps fait-il demain », etc.

## Format de `bench/attendus.json`

Le fichier associe chaque nom de fichier WAV de `phrases/` à sa transcription
exacte attendue. Exemple :

```json
{
  "phrase01.wav": "quelle heure est-il",
  "phrase02.wav": "lance la veille concurrence",
  "phrase03.wav": "note ça dans le projet Helios"
}
```

Le fichier livré dans le dépôt est `{}` (vide) : tant qu'il n'y a pas de
`phrases/*.wav`, il n'y a rien à transcrire. Ajoute une entrée par phrase au
fur et à mesure que tu enregistres.

## Prérequis : le modèle Silero

Le banc a besoin du modèle de détection de voix Silero, qui n'est pas dans le
dépôt (`models/` est ignoré par Git). Sans lui, `make bench` s'arrête tout de
suite avec un message qui donne cette même commande. Depuis la racine du
dépôt :

```bash
mkdir -p models && curl -L -o models/silero_vad.onnx https://raw.githubusercontent.com/snakers4/silero-vad/master/src/silero_vad/data/silero_vad.onnx
```

## Lancer le banc

```bash
make bench
```

Ça imprime un JSON avec trois sections :

- `reveil` — pour trois seuils (0.3, 0.5, 0.7), le taux de détection sur
  `positifs/` et le nombre de faux réveils par heure sur `negatifs/`.
- `endpointage` — pour trois durées de silence (300, 400, 600 ms), le retard
  médian (en ms) de la détection de fin de phrase et le nombre de coupures
  prématurées sur `phrases/` (voir plus bas).
- `transcription` — le taux d'erreur de mots moyen et la latence médiane (en
  ms) du service de transcription, mesurés sur `phrases/` + `attendus.json`.

Une fois le modèle Silero en place, tant que `enregistrements/` est vide (ou
absent) et que `attendus.json` vaut `{}`, tout tourne sans planter et affiche
des zéros partout — c'est l'état actuel du dépôt. Aucune connexion réseau
n'est ouverte vers le service de transcription tant que `attendus.json` ne
contient aucune entrée.

### Ce que mesure `endpointage`

Chaque fichier de `phrases/` contient **une seule phrase**. Pour chacun, le
banc fait passer l'enregistrement dans un détecteur de voix neuf, puis dans
l'endpointeur réglé sur la durée de silence testée.

- `retard_median_ms` — le temps entre le **dernier bloc de parole** et la
  **première fin de phrase décidée** : l'attente réelle entre le moment où tu
  te tais et celui où Helios le sait. La durée de la phrase elle-même n'y
  entre pas.
- `coupures_prematurees` — le nombre de fichiers où l'endpointeur a décidé
  **plus d'une fin**. Puisqu'il n'y a qu'une phrase par fichier, une deuxième
  fin veut dire que le réglage t'a coupé la parole au milieu, sur une simple
  pause. **Toute valeur non nulle disqualifie le réglage**, quel que soit son
  retard : un réglage court a un petit retard justement parce qu'il coupe
  trop tôt.

**Ne crois jamais `retard_median_ms` sans regarder à côté (ruling R29).**
Chaque entrée d'`endpointage` porte aussi `fichiers_mesures` et
`fichiers_total`. Si la fin de phrase n'est jamais détectée sur un
enregistrement (silence de fin trop bref, ou fichier sans réelle fin de
parole), ce fichier ne contribue rien à `retard_median_ms` —
`fichiers_mesures` compte uniquement les phrases où une fin a été trouvée,
`fichiers_total` compte tout ce qu'il y avait dans `phrases/`. Le piège :
ce sont justement les phrases les plus difficiles — celles qui auraient
donné le plus grand retard — qui risquent de ne jamais atteindre la fin ;
les exclure tire la médiane vers le bas et fait paraître un réglage
meilleur qu'il ne l'est. **Compare toujours `fichiers_mesures` à
`fichiers_total` avant de retenir un `retard_median_ms` : s'ils diffèrent,
le chiffre est optimiste et il faut comprendre pourquoi (écouter les
fichiers manquants) avant de figer un réglage dessus.** `transcription`
porte les deux mêmes champs par cohérence, même si elle n'exclut rien
aujourd'hui — vérifie quand même qu'ils sont égaux.

## Résultats et réglages retenus

**Pas encore mesuré.** Cette section sera complétée une fois les
enregistrements en place et `make bench` exécuté sur de vraies données.

Critères d'acceptation (à appliquer sur les résultats une fois obtenus) :

- **Seuil de réveil** : retenir la plus petite valeur parmi celles testées
  qui donne **plus de 95 % de détection** sur `positifs/` avec **moins d'un
  faux réveil par heure** sur `negatifs/`.
- **Durée de silence de fin de phrase** : retenir une valeur avec
  **`coupures_prematurees` à 0** et dont le **retard médian reste sous
  400 ms** sur `phrases/`.

Le client audio (`src/helios_audio/client.py`) lit ces trois réglages dans
l'environnement au démarrage (`lire_reglages()`), avec pour défauts les
valeurs actuelles — rien ne change tant que tu ne touches à rien. Une fois
les valeurs choisies grâce au banc, édite `.env.example` (et ton `.env`) :

**Les réglages de `.env` ne prennent effet qu'à travers les cibles `make`**
(`make run-audio`, `make run-core`, `make bench`…) : c'est le `Makefile` qui
charge `.env` et le passe aux commandes. Lancer `python -m helios_audio.client`
à la main ne lit pas `.env`. Crée ton `.env` en copiant `.env.example`, et sur
le MacBook vérifie en particulier `HELIOS_CORE_URL` : elle doit pointer vers
la machine où tourne le Core, pas vers `127.0.0.1` (le défaut du code).

- `HELIOS_REVEIL_SEUIL` (défaut `0.5`) — le seuil du mot de réveil. Prends la
  plus petite valeur testée par `make bench` qui donne, dans `reveil`, une
  `detection` > 0.95 avec un `faux_par_heure` < 1.
- `HELIOS_SILENCE_MS` (défaut `400`) — la durée de silence qui marque la fin
  d'une phrase dite à Helios. Prends la valeur testée par `make bench` dont
  les `coupures_prematurees` d'`endpointage` valent 0 et dont le
  `retard_median_ms` reste sous 400 ms (une fois vérifié que
  `fichiers_mesures == fichiers_total`, voir plus haut).
- `HELIOS_BARGEIN_MS` (défaut `300`) — la durée de parole minimale pour
  couper Helios quand il parle (barge-in). Le banc ne le mesure pas
  directement ; laisse la valeur par défaut sauf si l'usage réel montre
  qu'elle coupe trop vite ou trop lentement.

Reporte aussi la date et les chiffres obtenus ici, par exemple :

```
Date : AAAA-MM-JJ
Seuil de réveil retenu : ...   (détection : ... %, faux réveils/h : ...)
Silence de fin retenu : ... ms (retard médian : ... ms)
```

Ces valeurs serviront de référence pour comparer les versions suivantes du
modèle de wake word ou du VAD.

## Ce qui ne doit jamais entrer dans le dépôt

`bench/enregistrements/` est dans `.gitignore` : ta voix et tes
enregistrements audio n'ont rien à faire dans l'historique Git. Ne force
jamais leur ajout (`git add -f`).

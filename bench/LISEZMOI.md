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
`phrases/*.wav`, il n'y a rien à transcrire, et le banc tourne quand même en
rapportant des zéros. Ajoute une entrée par phrase au fur et à mesure que tu
enregistres.

## Lancer le banc

```bash
make bench
```

Ça imprime un JSON avec trois sections :

- `reveil` — pour trois seuils (0.3, 0.5, 0.7), le taux de détection sur
  `positifs/` et le nombre de faux réveils par heure sur `negatifs/`.
- `endpointage` — pour trois durées de silence (300, 400, 600 ms), le retard
  médian (en ms) avant que la fin de phrase soit détectée sur `phrases/`.
- `transcription` — le taux d'erreur de mots moyen et la latence médiane (en
  ms) du service de transcription, mesurés sur `phrases/` + `attendus.json`.

Tant que `enregistrements/` est vide (ou absent) et que `attendus.json` vaut
`{}`, tout tourne sans planter et affiche des zéros partout — c'est l'état
actuel du dépôt. Aucune connexion réseau n'est ouverte vers le service de
transcription tant que `attendus.json` ne contient aucune entrée.

**Un détail à connaître sur `endpointage` :** si la fin de phrase n'est
jamais détectée sur un enregistrement (silence de fin trop bref, ou fichier
sans réelle fin de parole), ce fichier est silencieusement absent de la
médiane — `retard_median_ms` ne compte que les phrases où une fin a été
trouvée. Si `retard_median_ms` semble bon mais que le nombre de phrases
utilisées est en réalité plus petit que 20, regarde le code (`mesurer_endpointage`
dans `bench/bench.py`) pour vérifier combien de fichiers ont réellement
produit une fin — le JSON actuel ne reporte pas ce compte séparément.

## Résultats et réglages retenus

**Pas encore mesuré.** Cette section sera complétée une fois les
enregistrements en place et `make bench` exécuté sur de vraies données.

Critères d'acceptation (à appliquer sur les résultats une fois obtenus) :

- **Seuil de réveil** : retenir la plus petite valeur parmi celles testées
  qui donne **plus de 95 % de détection** sur `positifs/` avec **moins d'un
  faux réveil par heure** sur `negatifs/`.
- **Durée de silence de fin de phrase** : retenir une valeur dont le
  **retard médian reste sous 400 ms** sur `phrases/`.

Une fois ces valeurs choisies, elles devront être reportées :

- dans `.env.example`, sous forme de nouvelles variables (aucune n'existe
  encore pour ces deux réglages : à ce jour, `ReveilleurMotCle` prend
  `seuil=0.5` par défaut et `src/helios_audio/client.py` construit
  l'`Endpointeur` avec `silence_ms=400` codé en dur — voir l'appel à
  `ReveilleurMotCle(PredicteurOpenWakeWord())` et à
  `Endpointeur(silence_ms=400, parole_min_ms=300)` dans ce fichier),
- ici, avec la date de la mesure et les chiffres obtenus, par exemple :

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

# Mot de réveil « Hey Atlas » — design

**Date :** 23 septembre 2026
**Statut :** design validé par David, section par section
**Spec parente :** `2026-09-22-atlas-design.md`, décision D7 (« Hey Atlas » entraîné sur mesure avec openWakeWord)
**Approche retenue :** A, c'est-à-dire openWakeWord avec nos propres données françaises. microWakeWord est le repli, avec les mêmes données.

## 1. Objectif et critères de réussite

David réveille Atlas en disant « Hey Atlas », prononcé à la française (« eille atlasse »), sans toucher le clavier. Ses proches doivent pouvoir le faire aussi.

Les critères sont mesurés sur le Mac, par le chemin exact du client :

| Critère | Objectif |
|---|---|
| « Hey Atlas » de David détectés, sur des enregistrements jamais vus à l'entraînement | au moins 90 %, avec le détail par distance (bureau, 1,5 m, 3 m) |
| Réveils sur « Atlas » dit seul | zéro, sur les phrases de test |
| Faux réveils en conditions réelles | au plus un par journée de travail |

Le lieu d'usage est un bureau calme : clavier, souris, chaise, ventilation, et des appels en visio.

## 2. Contraintes

- **Côté client, rien ne change.** `PredicteurOpenWakeWord` charge le modèle avec `openwakeword.Model(wakeword_models=[chemin], inference_framework="onnx")` (openwakeword 0.6.0), et le nourrit de blocs de 20 ms à 16 kHz. Le modèle produit doit être un classifieur openWakeWord standard, d'entrée (1, 16, 96). C'est le cas de ce que produit `train.py` : fenêtre de 2 s, extracteur de traits v0.5.1, identique à celui que télécharge `download_models()`.
- **Dépôt public.** Les enregistrements de David, les voix clonées, les données téléchargées et le modèle entraîné ne sont jamais commités. Aucune adresse réelle n'apparaît : les chemins de l'Unraid s'écrivent `<dossier-travail-unraid>`.
- **Licence.** Les traits négatifs précalculés d'openWakeWord (ACAV100M) sont sous licence CC-BY-NC-SA-4.0. C'est acceptable pour l'assistant personnel de David. Un modèle destiné à des clients devrait être réentraîné sans ces données.
- **GPU partagé.** La RTX 4070 Ti a 12 Go, déjà utilisés par les services STT et TTS et par ComfyUI. Les étapes lourdes passent l'une après l'autre, jamais en même temps.

## 3. Décisions

- **Orthographe pour Piper : « Eille Atlasse ».** Le phonétiseur français de Piper (espeak-ng) lit « Hey Atlas » /ɛ atla/, sans le « y » et sans le « s » final. « Eille Atlasse » donne /ɛj atlas/.
- **Orthographe pour Qwen3 : « Hey Atlas ».** Qwen ne passe pas par espeak, et « Eille Atlasse » le fait trébucher : sur la voix d'Atlas, Whisper y entend « Un atlas » 3 fois sur 3, contre « Hey Atlas » 4 fois sur 6 pour l'orthographe usuelle (24 septembre 2026). Qwen reçoit donc les mêmes phrases, écrites normalement.
- **« Atlas » seul ne réveille pas.** David parlera souvent de son projet Atlas en visio. Le mot seul, et « Atlas » dans une phrase, sont des exemples négatifs.
- **Pas de génération de phrases par openWakeWord.** Son générateur et ses phrases proches ne connaissent que l'anglais. Nous fournissons nous-mêmes tous les extraits, positifs comme négatifs, et nous sautons `--generate_clips`.
- **Voix variées, celle de David en priorité** : hommes, femmes, enfants, âges et timbres variés, plus des enregistrements réels de David.

## 4. Les données

### 4.1 Positifs : environ 18 000 extraits d'une à deux secondes

| Source | Volume visé | Détail |
|---|---|---|
| Voix Piper françaises | environ 6 000 | `siwis`, `tom` et `gilles`, les seules qui disent « Hey Atlas » juste à l'écoute (essais du 24 septembre 2026). Écartées : `mls` (125 locuteurs) et `mls_1840`, qui produisent 2 à 9 s de charabia pour deux mots (4,5 s en médiane pour `mls`), et `upmc`, qui prononce faux. Débits variés (`length_scale` de 0,8 à 1,3). Générées directement avec piper-tts 1.3.0 (`PiperVoice.synthesize` avec `speaker_id` et `length_scale`, API vérifiée), dans un environnement Python séparé de celui de l'entraînement, puis ramenées de leur fréquence native à 16 kHz. |
| Voix Qwen3 conçues | environ 12 000 | La source principale, qui remplace la diversité perdue avec `mls` : une quarantaine de voix de référence créées une fois par description avec le modèle VoiceDesign (hommes, femmes, enfants, âges, accents régionaux et francophones, timbres), puis clonées par le modèle Base, avec plusieurs tirages par voix. Chaque voix dit une fois « Hey Atlas » dans un essai que David écoute ; une voix ratée est écartée en retirant sa référence. |
| Enregistrements de David | environ 100 | Voir 4.3. Les deux tiers vont à l'entraînement, **dupliqués 20 à 50 fois** : l'option `augmentation_rounds` de `train.py` n'a pas d'effet, et la duplication est le seul moyen de leur donner du poids. Le dernier tiers est réservé au test. |

**Contrôle qualité :** les positifs synthétisés sont jugés à l'oreille, voix par voix, sur les essais, puis à leur durée (0,4 à 2 s), qui écarte le charabia. Whisper ne les juge pas : sur deux mots isolés, il ne reconnaît « Hey Atlas » que dans 29 % des prises de David, et transcrit « Un atlas » ou « Et à tout à l'heure » des extraits Piper justes à l'oreille (24 septembre 2026). Il garde son rôle pour les négatifs (4.2) : on écarte ceux où il entend « atlas » précédé d'une interjection (« hey », « eh », « eille »…) ou de « et », car « Hé » et « Et » se prononcent pareil.

### 4.2 Négatifs

| Source | Détail |
|---|---|
| Phrases proches | « Atlas » et « Atlasse » seuls ; « le projet Atlas », « Atlas, c'est prêt ? » ; « hélas », « et là », « c'est là », « est-ce là », « halte-là », « à las », « eh t'as vu » ; « eille Nicolas », « eille Thomas », « eille Lucas », « eille Alex » ; « au Texas », « Dallasse », « palace », « l'atlas routier », « atlantique ». Dites par les mêmes voix Piper et Qwen que les positifs, puis passées à Whisper, qui écarte celles qui sonnent comme « Hey Atlas ». |
| Parole normale de David | Environ 10 minutes où il parle sans dire le mot, découpées en fenêtres de 2 s, puis converties en traits openWakeWord : un fichier `.npy` supplémentaire, ajouté à `feature_data_files` et `batch_n_per_class`. |
| Bruits du bureau de David | 10 à 15 minutes : clavier, souris, chaise, ventilation. Ils servent de négatifs, et de fond sonore pour l'enrichissement des extraits (`background_paths`). |
| Traits ACAV100M | Environ 2 000 heures multilingues, précalculées par openWakeWord (17,3 Go). |
| Faux réveils réels | À partir de la deuxième itération : les extraits capturés par `veiller.py` (§7). |

### 4.3 Enregistrements de David : environ 30 minutes, dont une douzaine où il suffit de laisser tourner le micro

Ils sont captés par le vrai chemin du micro, le binaire Swift avec annulation d'écho, à 16 kHz mono, exactement ce qu'Atlas entendra :
- environ 100 « Hey Atlas » : ton normal, pressé, fatigué, fort, bas ; à trois distances (bureau, 1,5 m, 3 m), avec un délai après Entrée pour se placer (0, 3 et 5 s) ;
- une dizaine de phrases avec « Atlas » seul ;
- environ 10 minutes de parole normale sans le mot ;
- 10 à 15 minutes de bureau sans voix.

Ils sont rangés dans `donnees/mot_reveil/` sur le Mac, un dossier ignoré par git, puis copiés une fois dans `<dossier-travail-unraid>`.

## 5. Le pipeline

```
Mac                                   Unraid
───                                   ──────
enregistrer.py ──► donnees/mot_reveil ──(copie)──► <dossier-travail-unraid>/david
                                                  │
                        generer_piper.py (CPU) ───┤──► clips/piper
          generer_qwen.py (image atlas-tts, GPU) ─┤──► clips/qwen
                  filtrer.py (via atlas-stt, GPU) ┤──► clips retenus
                                    preparer.py ──┤──► entrainement/hey_atlas/{positive,negative}_{train,test}
                                                  │    + traits négatifs .npy + hey_atlas.yml
              entrainer.sh (conteneur d'entraînement, GPU)
                                                  └──► hey_atlas.onnx
evaluer.py ◄── models/hey_atlas.onnx ◄──(copie)──┘
veiller.py ──► donnees/mot_reveil/veille (faux réveils) ──► itération suivante
```

### 5.1 Composants, dans `scripts/mot_reveil/`

| Composant | Où il tourne | Rôle |
|---|---|---|
| `enregistrer.py` | Mac | Guide David, phrase par phrase, et enregistre chaque extrait par le binaire Swift. |
| `generer_piper.py` | Unraid, conteneur d'entraînement | Positifs et négatifs Piper. |
| `generer_qwen.py` | Unraid, conteneur ponctuel lancé depuis l'image `atlas-tts` | Conçoit les voix de référence (VoiceDesign), puis clone les phrases (Base). Le service `atlas-tts` est arrêté pendant ce temps, pour libérer la mémoire vidéo : les deux modèles occupent environ 9 Go. |
| `ecouter.py` | Mac | Fait écouter à David les essais Piper et Qwen rapatriés, voix par voix, avec la description de chaque voix Qwen. |
| `filtrer.py` | Unraid, conteneur d'entraînement | Contrôle qualité : durée des positifs ; Whisper (`atlas-stt`) pour les négatifs. Ignore les dossiers `essai/`. |
| `preparer.py` | Unraid, conteneur d'entraînement | Rééchantillonnage à 16 kHz mono int16 ; coupe des silences en gardant environ 100 ms ; séparation entraînement et test ; duplication des extraits de David ; traits des négatifs français ; écriture de `hey_atlas.yml`. |
| `hey_atlas.yml` (généré) | — | Configuration de `train.py`. |
| `Dockerfile`, `telecharger_donnees.sh` et `entrainer.sh` | Unraid | L'environnement d'entraînement figé, le téléchargement des données, et le lancement de `--augment_clips` puis `--train_model`. |
| `evaluer.py` | Mac | Mesures de la §7.1, par le chemin exact du client. |
| `veiller.py` | Mac | Écoute d'une journée ; garde 3 s autour de chaque faux réveil (§7.2). |

Les fonctions logiques sont séparées des entrées-sorties, et testées : découpe, séparation, duplication, génération de la configuration, calcul des métriques.

### 5.2 Ordre sur le GPU

1. **Piper :** processeur seulement.
2. **Qwen :** conteneur ponctuel, service `atlas-tts` arrêté.
3. **Whisper :** le service `atlas-tts` peut être relancé ; ensemble, Whisper et la voix d'Atlas tiennent dans les 12 Go.
4. **Préparation et entraînement :** moins de 2 Go de mémoire vidéo, services relancés au besoin. ComfyUI reste arrêté pendant toutes ces étapes : même inactif, il garde ses modèles en mémoire vidéo, et `atlas-stt` échoue alors (erreur 500, 0,1 Go libre sur 11,6, constaté le 24 septembre 2026).

## 6. L'environnement d'entraînement

Ces faits ont été vérifiés dans le code d'openWakeWord le 23 septembre 2026. Le relevé complet est dans le journal de recherche.

- **Pile figée**, qui marche d'après l'issue openWakeWord #317 :
  - Python 3.10 : `.[full]` ne s'installe pas en 3.11 ;
  - `torch==1.13.1+cu117`, dont les binaires sm_86 tournent sur Ada (réussite rapportée sur une RTX 4090) ;
  - `pyarrow<15`, `fsspec<2024.1.0` ;
  - openWakeWord au commit `368c037` ;
  - `tensorflow-cpu==2.8.1`, que `.[full]` installe de toute façon, figé comme dans la pile éprouvée ; nous ne produisons pas de `.tflite` ;
  - `numpy<2` : torch 1.13 est bâti contre NumPy 1, et `torch.from_numpy` échoue sous NumPy 2 (relevé par la revue finale).
  - Le conteneur se lance avec `--shm-size=32g`.
- **`piper_sample_generator_path`** doit pointer vers un dossier contenant un `generate_samples.py` importable, même quand on ne génère rien. Un checkout de piper-sample-generator v2.0.0, ou un fichier bouchon d'une ligne, suffit. La génération Piper, elle, utilise piper-tts 1.3.0, installé dans un environnement Python séparé du même conteneur.
- **Arborescence attendue :** `<output_dir>/hey_atlas/{positive,negative}_{train,test}/*.wav`, en 16 000 Hz exactement, mono int16. `positive_test/` ne doit pas être vide : la fenêtre se calcule sur la médiane de ses extraits, plus 750 ms.
- **`rir_paths` et `background_paths`** doivent exister. On utilise les réponses impulsionnelles MIT (270 fichiers, 8,4 Mo) et les bruits de bureau de David, plus un fond générique : ESC-50, 2 000 sons d'environnement de 5 s, sous licence non commerciale comme ACAV100M. L'ancien lien AudioSet du notebook ne répond plus.
- **Faux positifs par heure affichés par `train.py` :** ils sont calculés sur un jeu de validation anglais (185 Mo, environ 11 h), avec une durée codée en dur. Ce chiffre ne sert que d'indication ; seules comptent les mesures de la §7.
- **Disque :** environ 50 Go. **Mémoire :** 16 Go ou plus. David a confirmé avoir de la marge sur les deux.
- **Durée :** mesurée le 24 septembre 2026 sur la RTX 4070 Ti, 50 000 pas prennent 6 min 30, plus quelques minutes d'enrichissement sur le processeur. Une itération tient donc en moins d'une demi-heure.
- **Poids des négatifs : 600, et non les 1 500 d'openWakeWord.** À 1 500, le modèle répond « non » à tout (rappel nul, même sur les positifs d'entraînement) : nos négatifs proches, dits par les mêmes voix que les positifs, pèsent trop. Pourtant, un petit réseau entraîné à part sépare ces mêmes traits à 99 % : les données ne sont pas en cause. Mesuré à 50 000 pas sur les prises de David mises de côté : les poids 100 et 300 reconnaissent 87 à 91 % au seuil 0,5, mais se réveillent sur ses bruits de bureau (scores 0,94 et 0,83). Le poids 600 reconnaît 87 % (82 % à 3 m), sans aucun faux réveil ni réveil sur « Atlas » seul, avec un score maximal de 0,012 sur ses bruits et sa parole.

Avant la vraie journée de calcul, le conteneur fait un **essai à blanc** : quelques centaines d'extraits et quelques centaines de pas d'entraînement, pour vérifier que toute la chaîne produit un `.onnx` chargeable par openwakeword 0.6.

## 7. L'évaluation

### 7.1 `evaluer.py`, hors ligne, sur le Mac

Le script rejoue des fichiers audio par blocs de 20 ms à travers `PredicteurOpenWakeWord` et `ReveilleurMotCle` : même modèle, même seuil, même pause de 2 s après un réveil. Il mesure, pour chaque seuil de 0,1 à 0,9 :
- la **détection** sur le tiers réservé des « Hey Atlas » de David, par distance ;
- les **réveils sur « Atlas » seul** ;
- les **faux réveils par heure** sur la part réservée de sa parole normale et des bruits de bureau.

Le seuil retenu va dans `ATLAS_REVEIL_SEUIL`.

### 7.2 `veiller.py`, une journée réelle

Le modèle écoute pendant une journée de travail normale, sans rien déclencher. Pour chaque score au-dessus d'un seuil de journalisation, plus bas que le seuil réel, il garde les 3 s d'audio autour, avec l'heure et le score. **Rien d'autre n'est enregistré.** Le script donne le nombre de faux réveils de la journée au seuil retenu.

### 7.3 La boucle d'itération

Les extraits de `veiller.py` deviennent des négatifs, puis on relance `preparer.py` et `entrainer.sh`, soit 1 à 3 heures. C'est le levier le plus puissant d'après les retours publiés : un projet est passé de 91 à 1 faux réveil sur 140 cas pièges.

**Repli :** si la détection reste sous 85 à 90 % après deux ou trois itérations, on passe à microWakeWord (runtime `pymicro-wakeword`, qui a un paquet macOS), avec les mêmes extraits. Il faudra alors un nouveau `Predicteur` dans le client.

**Les proches :** ce n'est pas encore outillé. `evaluer.py` ne lit que les prises de David, par distance ; des « Hey Atlas » de proches demanderont un jeu de test dédié.

## 8. L'intégration

- `hey_atlas.onnx` va dans `models/`, qui est ignoré par git. Les modèles de traits se téléchargent une fois avec `openwakeword.utils.download_models()`, comme le client l'indique déjà.
- On active le mot de réveil dans `.env` avec `ATLAS_REVEILLEUR=motcle` et `ATLAS_REVEIL_SEUIL=<seuil retenu>`. Dans le code, la touche Entrée reste le défaut, pour qu'un clone neuf démarre sans modèle.
- `scripts/entrainer_mot_reveil.md`, dont plusieurs commandes n'existent pas, est remplacé par la vraie procédure : `scripts/mot_reveil/LISEZMOI.md`.
- `.gitignore` gagne `donnees/`.

## 9. Risques et inconnues

| Risque | Parade |
|---|---|
| Aucun résultat français publié pour openWakeWord ; d'autres langues plafonnent à 45-60 % sur de la parole réelle avec de la synthèse seule | Les enregistrements de David, les faux réveils réinjectés, et le repli microWakeWord |
| La voix `fr_FR-mls-medium` peut mal dire une phrase courte | Confirmé par l'essai du 24 septembre 2026, et pire que prévu : `mls`, `mls_1840` et `upmc` sont écartées, et les voix gardées sont écrites en dur. Qwen compense la perte de locuteurs |
| La prononciation de « Hey Atlas » par Qwen3 varie d'une voix à l'autre | Un « Hey Atlas » par voix, écouté avant le clonage complet ; les voix ratées sont écartées. « Eille Atlasse », essayé sur la voix d'Atlas, était mal prononcé : Qwen lit l'orthographe usuelle |
| `torch 1.13` sur une carte Ada | Confirmé par l'essai à blanc du 24 septembre 2026 sur la RTX 4070 Ti : le cuFFT de CUDA 11.7 plante (`CUFFT_INTERNAL_ERROR`) dans le décalage de hauteur de l'enrichissement. L'enrichissement tourne donc sur le processeur ; l'entraînement, sans FFT, reste sur le GPU. Le même essai a révélé un bug de `train.py` : ses options booléennes valent `default="False"` (une chaîne, donc vraie), si bien que la conversion tflite se déclenchait toujours et plantait (conflit protobuf) après l'export ONNX ; le `Dockerfile` corrige ces valeurs |
| Le modèle colle trop à la voix de David au détriment des proches | Voix de synthèse variées, et proches au jeu de test si possible |
| Les faux positifs par heure affichés par `train.py` ne représentent pas un foyer français | On ne décide que sur les mesures de la §7 |

## 10. Hors périmètre

- Garder la touche Entrée **en plus** du mot de réveil. David pourra le demander plus tard.
- Un second étage de vérification par Whisper après le réveil.
- Le vérificateur de locuteur d'openWakeWord (`custom_verifier`), qui rendrait Atlas sourd aux proches.
- Un modèle `.tflite`.

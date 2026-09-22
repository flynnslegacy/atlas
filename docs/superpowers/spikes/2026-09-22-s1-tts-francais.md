# Spike S1 — Verdict : la voix d'Atlas

**Date :** 22 septembre 2026
**Statut :** tranché par David
**Code du spike (jetable) :** branche `spike-s1-tts`, dossier `spikes/s1-tts/`

## La question

Qwen3-TTS tient-il en français sur la RTX 4070 Ti, avec une voix masculine et fluide ? Il faut juger la qualité de la voix, le délai avant le premier son et la place prise en mémoire GPU à côté de Whisper et de ComfyUI.

## Tour 1 — écoute à l'aveugle

Trois candidats, cinq phrases pièges (chiffres, guillemets, chemin de fichier, nom propre, question), soit quinze extraits dans un ordre mélangé. Tout a été ramené à 16 kHz, la fréquence qu'Atlas diffuse, et à un volume identique, pour que ni la qualité du fichier ni le volume ne trahissent le moteur.

| Moyenne sur 5 phrases, notée par David sur 5 | masculine | fluide | chiffres | nom propre | sonne français | **note** |
|---|---|---|---|---|---|---|
| **Qwen3 « voix décrite »** (VoiceDesign 1.7B) | **4,8** | **4,0** | **5,0** | **5,0** | **4,2** | **4,0** |
| Qwen3 « Uncle_Fu » (voix prédéfinie, CustomVoice 1.7B) | 4,2 | 3,8 | 4,4 | 4,0 | 3,2 | 3,4 |
| Piper `fr_FR-tom-medium` | 3,2 | 2,8 | 4,2 | 4,4 | 3,2 | 3,0 |

| Mesures | Qwen voix décrite | Qwen Uncle_Fu | Piper Tom |
|---|---|---|---|
| Temps de calcul / durée de l'audio | ≈ 0,5 | ≈ 0,5 | 0,2 à 0,37 |
| Mémoire GPU au pic | 4,58 Go | 4,4 Go | aucune (processeur) |
| Rend l'audio par morceaux | non | non | oui |

**Défauts entendus sur la voix décrite :** un écho, des fins qui partent en silence puis en sons parasites (une phrase de 4,5 s ressortait en 12,6 s), et une voix réinventée à chaque appel.

## Tour 2 — concevoir la voix une fois, puis la cloner

C'est le mode d'emploi documenté par Qwen :
1. **Concevoir.** Quatre prises d'une phrase de référence, générées avec VoiceDesign. La description ajoutait : « enregistrement de studio, voix sèche et proche du micro, sans écho, sans réverbération ni bruit de fond ». David a retenu la **prise n°1**.
2. **Cloner.** L'empreinte de la voix est calculée une seule fois avec `create_voice_clone_prompt` (1,0 s). Chaque phrase est ensuite générée par `generate_voice_clone`, avec le modèle `Qwen/Qwen3-TTS-12Hz-1.7B-Base`.

**Verdict de David :** « ça reste bien la même personne », « il n'y a pas d'écho », « les fins sont propres ».

| Phrase | Calcul | Audio généré | Audio gardé | Coupe du garde-fou |
|---|---|---|---|---|
| 1 | 2,92 s | 5,36 s | 2,30 s | silence puis parasites retirés |
| 2 | 3,60 s | 7,20 s | 7,20 s | aucune |
| 3 | 2,88 s | 5,76 s | 5,76 s | aucune |
| 4 | 2,92 s | 5,84 s | 5,84 s | aucune |
| 5 | 3,21 s | 6,32 s | 6,32 s | aucune |

Mémoire GPU au pic : **4,69 Go**.

## Décision

- **Moteur :** Qwen3-TTS, modèle `Base` 1.7B, par clonage de la prise de référence n°1. Pour recréer la voix, il faut le fichier audio **et** le texte exact prononcé dans la prise :
  > Bonjour, je m'appelle Atlas. Je suis là pour t'aider à organiser tes journées, à suivre tes projets et à répondre à tes questions, calmement et clairement.
- **Exception à la spec, approuvée par David :** Qwen3 ne rend l'audio qu'une fois le morceau entier généré, alors que la spec §6.4 exigeait un flux par morceaux. Atlas accepte environ une seconde de plus avant le premier mot, en échange d'une voix nettement plus naturelle.
- **Repli :** Piper reste disponible derrière la même interface `/synthesize`. Depuis le correctif du 22/09, la fréquence de chaque voix est lue dans sa configuration.

## Conséquences pour l'intégration

1. **La prise de référence est irremplaçable.** La génération n'est pas déterministe : une référence perdue ne se recrée pas à l'identique. Il faut la sauvegarder, puis la monter dans le service.
2. **Charger le modèle et calculer l'empreinte une seule fois, au démarrage**, pas à chaque requête.
3. **Arrêter la génération tôt, pas seulement couper après.** La phrase 1 a coûté 2,92 s de calcul pour 2,30 s d'audio utile : le modèle continuait à produire du silence et des parasites. Couper après coup protège l'oreille, mais pas le délai. Il faut un plafond `max_new_tokens` proportionnel à la longueur du texte. Le nombre de jetons par seconde d'audio reste à mesurer : la documentation ne le donne pas.
4. **Garder le garde-fou de fin** (`couper_fin`) comme filet de sécurité.
5. **Découper les réponses en morceaux courts côté Core**, par exemple aux virgules, pour raccourcir le premier morceau et donc le délai.
6. **Mémoire GPU :** environ 4,7 Go pour Qwen, plus Whisper, soit environ 8 à 9 Go sur 12. ComfyUI doit être au repos tant que la RTX 3090 n'est pas installée. Le service `atlas-tts` passe sur GPU.
7. **Débit :** le calcul prend environ la moitié de la durée de l'audio. Les phrases suivantes sont donc prêtes avant la fin de la précédente, et la voix s'enchaîne sans trou.
8. **Débit de parole :** cette voix posée parle à environ 0,08 s par caractère, contre 0,07 dans le garde-fou du spike. Il faut recalibrer.

## Point encore ouvert

La phrase 1, « Bonjour David, il est quatorze heures trente-deux. », a été raccourcie de 5,36 s à 2,30 s par le garde-fou. David juge la fin propre, mais il reste à confirmer que « trente-deux » est entendu en entier. Un garde-fou trop agressif amputerait la fin des phrases courtes.

# Spike S1 — Verdict : la voix d'Atlas

**Date :** 22 septembre 2026
**Statut :** tranché par David
**Code du spike (jetable) :** branche `spike-s1-tts`, dossier `spikes/s1-tts/`
**Voix retenue :** `services/tts/voix/atlas_reference.wav` et son texte exact `atlas_reference.txt`

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

**Défauts entendus sur la voix décrite :** un écho, des fins qui partent en silence puis en sons parasites, et une voix réinventée à chaque appel.

## Tour 2 — concevoir la voix une fois, puis la cloner

C'est le mode d'emploi documenté par Qwen :
1. **Concevoir.** Quatre prises d'une phrase de référence, générées avec VoiceDesign. La description ajoutait : « enregistrement de studio, voix sèche et proche du micro, sans écho, sans réverbération ni bruit de fond ». David a retenu la **prise n°1**.
2. **Cloner.** L'empreinte de la voix est calculée une seule fois avec `create_voice_clone_prompt` (1,0 s). Chaque phrase est ensuite générée par `generate_voice_clone`, avec le modèle `Qwen/Qwen3-TTS-12Hz-1.7B-Base`.

### Le bug trouvé en route, et sa cause

La première série de clonage semblait réussie : même voix, pas d'écho, fins propres. En la réécoutant, David a entendu la phrase 1 dire seulement « calmement et clairement ».

Les extraits ont été transcrits par le service `atlas-stt`, et la cause est apparue :
- Le garde-fou de fin du spike, qui coupait au premier long silence, avait **retiré « calmement et clairement » de la prise de référence** : il avait confondu la pause à la virgule avec la fin de la phrase.
- Le clonage recevait pourtant le texte complet. Le modèle croyait donc la référence inachevée, et **commençait chaque phrase en la terminant** : les cinq phrases débutaient par « calmement et clairement ».
- Sur la phrase 1, le garde-fou avait ensuite gardé ce préfixe et supprimé la vraie phrase.

**Le correctif :** donner au clonage le texte qui correspond **exactement** à l'audio de la référence. C'était la seule variable modifiée. Après correction, le préfixe a disparu des cinq phrases.

### Résultats après correction

Transcriptions de `atlas-stt` sur l'audio **brut**, avant tout garde-fou :

| Phrase | Calcul | Audio | Transcription |
|---|---|---|---|
| 1 | 1,71 s | 2,88 s | « Bonjour David, il est 14h32. » |
| 2 | 3,63 s | 7,28 s | « Le workflow « Veille concurrence » a échoué à 3 heures du matin. Erreur d'authentification sur l'API. » |
| 3 | 2,09 s | 4,16 s | « J'ai noté ça dans projet Atlas MD. Tu veux que je te le relise ? » |
| 4 | 2,36 s | 4,72 s | « Attention, cette action va envoyer un mail à Paul Durand. Je confirme. » |
| 5 | 2,17 s | 4,32 s | « D'accord. Alors reprenons. Tu disais que l'offre devait tenir en une page. » |

Les cinq phrases sont complètes et ne contiennent rien de plus. Mémoire GPU au pic : **4,69 Go**.

**Le garde-fou de fin s'est révélé nuisible.** Appliqué à ces mêmes phrases, il a encore coupé « Erreur d'authentification sur l'API » (phrase 2) et « Je confirme » (phrase 4), en prenant les pauses naturelles pour la fin de la phrase. Au total, il a amputé du contenu réel 3 fois sur 11 : la référence, la phrase 2 et la phrase 4. Les fins parasites qu'il devait corriger venaient surtout du préfixe fantôme, et elles n'apparaissent pas dans le clonage corrigé.

## Décision

- **Moteur :** Qwen3-TTS, modèle `Base` 1.7B, par clonage de la prise de référence n°1.
- **La voix d'Atlas est une paire indissociable :** `atlas_reference.wav` (7,1 s, 24 kHz, mono) et `atlas_reference.txt`, son texte exact :
  > Bonjour, je m'appelle Atlas. Je suis là pour t'aider à organiser tes journées, à suivre tes projets et à répondre à tes questions.
- **Exception à la spec, approuvée par David :** Qwen3 ne rend l'audio qu'une fois le morceau entier généré, alors que la spec §6.4 exigeait un flux par morceaux. Atlas accepte environ une seconde de plus avant le premier mot, en échange d'une voix nettement plus naturelle.
- **Repli :** Piper reste disponible derrière la même interface `/synthesize`. Depuis le correctif du 22/09, la fréquence de chaque voix est lue dans sa configuration.

## Conséquences pour l'intégration

1. **Garder la paire audio-texte intacte.** Le texte doit correspondre exactement à l'audio, sinon chaque phrase commence par le texte manquant. Et la génération n'étant pas déterministe, une référence perdue ne se recrée pas : c'est pour ça qu'elle est versionnée.
2. **Charger le modèle et calculer l'empreinte une seule fois, au démarrage**, pas à chaque requête.
3. **Pas de coupe sur les silences.** Seulement un plafond de durée très large, par exemple 2,5 fois la durée attendue, qui ne touche jamais une phrase normale et qui arrête une génération qui boucle. Le rapport entre jetons générés et secondes d'audio reste à mesurer pour régler `max_new_tokens`.
4. **Découper les réponses en morceaux courts côté Core**, par exemple aux virgules, pour raccourcir le premier morceau. À traiter avec la refonte du découpeur de phrases prévue en phase 2.
5. **Mémoire GPU :** environ 4,7 Go pour Qwen, plus Whisper, soit environ 8 à 9 Go sur 12. ComfyUI doit être au repos tant que la RTX 3090 n'est pas installée. Le service `atlas-tts` passe sur GPU.
6. **Débit :** le calcul prend environ la moitié de la durée de l'audio. Les phrases suivantes sont donc prêtes avant la fin de la précédente, et la voix s'enchaîne sans trou.
7. **Débit de parole :** environ 0,06 s par caractère. Une première version de ce verdict annonçait 0,08, à tort : la seconde en trop était le préfixe fantôme.

## Leçon de méthode

Le garde-fou devait protéger l'écoute. Il a d'abord créé le bug, puis l'a masqué, parce qu'il ne gardait que la version rognée. Désormais, **on garde toujours la version brute à côté de la version traitée**, et on vérifie le contenu par transcription plutôt qu'à l'oreille seule.

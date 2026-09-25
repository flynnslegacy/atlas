# La voix dans le navigateur — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** La page d'Atlas, ouverte sur l'iPhone, l'iPad ou le Mac, écoute (« Hey Atlas », ou l'orbe touchée) et répond à voix haute, comme le client audio du M5 ; celui-ci continue de marcher à côté.

**Architecture:** La page n'est qu'un terminal audio. Deux processeurs AudioWorklet ramènent le micro à 16 kHz en blocs de 20 ms et jouent les trames du Core ; `voix.js` les relie à une connexion `/ws/voix`. Pour chaque page, le Core fait tourner le `ClientAudio` du Mac — mot de réveil, détection de voix, fin de phrase, coupure, relance —, avec un `PeripheriqueNavigateur` pour périphérique, branché en mémoire à sa propre `Session` et servi par le même `servir_connexion` que sur le Mac. La régie garde toutes les sessions audio : une question tapée va à la voix de sa page, le muet les fait toutes taire.

**Tech Stack:** Python 3.12+ (venv en 3.13), FastAPI/Starlette, pydantic v2, openWakeWord et Silero (onnxruntime), pytest (asyncio auto) ; JavaScript sans dépendance (modules ES, Web Audio, AudioWorklet, Wake Lock), `node --test` (Node 26).

**Spec:** `docs/superpowers/specs/2026-09-25-voix-navigateur-design.md` (à lire avec ce plan : elle fait foi en cas de doute), et le verdict du spike S4 : `docs/superpowers/spikes/2026-09-25-s4-voix-navigateur.md`.

## Global Constraints

- Code, identifiants, messages et commentaires en français, comme le reste du dépôt ; Python en lignes de 100 caractères au plus (ruff) ; JavaScript dans le style des fichiers voisins (pas de formateur).
- Aucune nouvelle dépendance, ni Python ni JavaScript. La page ne charge rien de l'extérieur, n'insère jamais de HTML (`innerHTML`…) ; la politique de sécurité du Core ne change pas.
- L'annulation d'écho n'est jamais coupée : le micro se demande avec `{ echoCancellation: true, noiseSuppression: true, autoGainControl: true }` (spike S4 : sans elle, iOS baisse la voix d'Atlas).
- Réglages : `ATLAS_VOIX_MARGE_S` (0,2 s par défaut, de 0 à 2), `ATLAS_VOIX_BARGEIN_DBFS` (−40 par défaut, de −120 à 0) ; amorçage de l'annuleur : `AMORCAGE_S = 10.0` secondes de voix d'Atlas jouée, après l'ouverture de `/ws/voix` ou un message `reprise`. Les autres réglages des pages sont ceux du client du Mac (`ATLAS_REVEIL_SEUIL`, `ATLAS_SILENCE_MS`, `ATLAS_BARGEIN_MS`, `ATLAS_RELANCE_S`).
- `/ws/voix` : origine vérifiée avant d'accepter (`1008`) ; premier message `authentification` `{cle, page, hey_atlas}` avec la clé des pages (`ATLAS_WEB_CLE`) sous 5 s, comparée en temps constant (`4401` sinon) ; sans clé configurée, `erreur` `cle_absente` puis `4000` ; modèles absents, `erreur` `modeles_absents` puis `4000` ; la voix de la page en panne, `1011`. Clé acceptée : `pret`.
- L'audio de `/ws/voix` est brut : exactement 640 octets (20 ms, 16 kHz, s16le) dans les deux sens. L'identifiant de page suit `^[A-Za-z0-9_-]{1,64}$` ; la page tire 12 octets au hasard, en hexadécimal.
- Ne jamais lancer ce qui ouvre un micro (`make run-audio`, les scripts de `scripts/mot_reveil/`, une page avec le micro allumé) ni le binaire Swift : c'est David qui le fait, à l'essai final.
- Dépôt public : aucune adresse IP, aucun domaine (seulement `atlas.example.com`), nom ou courriel privé, aucun jeton dans ce qui est commité. `.env` n'est jamais commité.
- Git : ajouter les fichiers par leur chemin, jamais `git add -A` (le dossier `spikes/` n'est pas suivi et reste privé). Messages de commit en français, terminés par la ligne `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Avant chaque commit : `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .`, `node --test "tests/web/*.test.mjs"`. Si `ruff format --check` échoue, lancer `uv run ruff format <fichiers>` : la mise en forme fait foi.
- Fichiers de moins de 500 lignes : `src/atlas_audio/client.py` finit à 499, il ne doit pas grossir d'une ligne de plus ; `src/atlas_core/session.py` (552) ne change pas.
- **Copier le code programmatiquement.** Les fichiers neufs sont donnés en entier, les autres par des diffs unifiés exacts (`git apply` les accepte tels quels, copiés d'un bloc) : ne rien retaper à la main. En phase 2a, une apostrophe typographique (’) perdue en recopiant a coûté une reprise.
- Le code de ce plan a été vérifié tel quel avant d'être écrit ici : appliquées dans l'ordre, les 10 tâches donnent 656 tests Python et 119 tests JavaScript qui passent, un lint propre, et chaque tâche laisse la suite entière au vert. Les tests ont en outre été mis à l'épreuve par mutations : chaque comportement clé, retiré du code, fait échouer au moins un test. Un écart entre le plan et ce que vous observez est donc à signaler, pas à contourner.

## Review Focus

Les cinq situations que la spec implique sans les décrire, les plus susceptibles de surprendre David ; chacune a son test dans la tâche qui en porte le code.

1. **Le micro se coupe en cours d'usage** (un appel, un casque débranché, l'autorisation retirée) : la page le dit (« Touche ici pour réactiver le micro ») et un toucher le rouvre, au lieu de rester sourde en silence. Task 8 : « un micro coupé (appel, casque débranché) se rouvre d'un toucher », « un micro qui se coupe le signale, et reprendre le rouvre ».
2. **La question suivante, sans « Hey Atlas »**, juste après une réponse sur la page : la relance l'entend, comme sur le Mac. Task 4 : `test_apres_sa_reponse_la_page_ecoute_encore_sans_hey_atlas`.
3. **« Muet » touché sur un appareil pendant qu'Atlas parle sur un autre** : le son de cet autre appareil s'arrête net. Task 4 : `test_le_muet_d_une_page_coupe_la_voix_d_une_autre`.
4. **Un contexte audio à 24 ou 16 kHz** (certains casques Bluetooth) : les blocs restent de 20 ms à 16 kHz, la voix intacte, et la lecture à la bonne vitesse. Task 7 : les tests « à … Hz » pour 48 000, 44 100, 24 000 et 16 000 Hz.
5. **Une page fermée pendant qu'Atlas lui parle** : le Core range sa session sans laisser d'erreur au journal, et les autres appareils continuent. Task 5 : `test_une_page_partie_pendant_qu_atlas_lui_parle_ne_laisse_aucune_erreur`.

## Décisions prises en écrivant le plan

La spec fait foi ; voici ce qu'elle laissait ouvert et ce que le plan en a fait. Les quatre premières l'ont modifiée (spec §12).

1. **L'audio de `/ws/voix` passe brut**, 640 octets dans les deux sens : tout ce qui est binaire y est de l'audio, et le client que le Core fait tourner pour la page a déjà écarté les trames d'un énoncé coupé.
2. **`pret` confirme l'entrée d'une page** : la page n'envoie son micro qu'une fois acceptée (`Connexion` passe « en ligne » au premier message qui n'est pas une erreur).
3. **Toucher l'orbe va directement au `ClientAudio`** (`demander_la_parole`), traité au bloc suivant, dans la tâche de capture : au repos il ouvre l'écoute, pendant qu'Atlas parle il le coupe comme un barge-in (`_interrompre`, que le barge-in à la voix utilise aussi). Le `ReveilleurPage` n'écoute que « Hey Atlas » ; éteint, il ne consulte même pas le modèle.
4. **Les calculs purs de l'audio vivent dans `voix_worklet.js`** (classes exportées) ; les processeurs ne s'y déclarent que si `registerProcessor` existe. Le module de l'AudioWorklet reste d'un seul tenant, sans import.
5. **Le client de la page est servi comme celui du Mac** : `FluxSession` met en file ce que la session envoie et se lit comme le flux d'une WebSocket, pour `servir_connexion` (ordre gardé, `StopAudio` d'abord) ; `TransportSession` passe ce que le client envoie directement à la session.
6. **L'amorçage se compte en trames entières** (500 trames pour 10 s) : additionner 0,02 s dépasse d'une trame. Il finit quand la dernière trame amorcée a fini de jouer (`_fin_amorcage`). Une connexion neuve est un `ClientAudio` neuf, donc un amorçage neuf ; `reprise` appelle `reamorcer()`.
7. **Chaque page a ses modèles** (Silero et openWakeWord gardent un état), chargés à l'allumage du micro quel que soit l'interrupteur, dans un fil à part (`asyncio.to_thread`) : le premier chargement d'openWakeWord prend près d'une seconde, les suivants 50 ms.
8. **Au plus 5 s de micro en attente par page** (250 blocs) : si le Core prend du retard, les plus vieux blocs se perdent.
9. **Une panne de la voix d'une page ferme `/ws/voix` en `1011`** ; la page se rebranche. Un envoi qui échoue (`PeripheriqueEnPanne`) dit seulement que la page est partie : une ligne d'information au journal, et pas de fermeture en plus. Cette dernière garde ne sert que dans une course (l'envoi échoue juste avant que la déconnexion n'arrive) qu'un test ne peut pas provoquer sans se bloquer.
10. **La régie garde une liste ordonnée `(page, session)`** : pour une page, la session la plus récente l'emporte (une page rebranchée avant que l'ancienne connexion ne soit détachée).
11. **Le Core lit `lire_reglages()` à son démarrage**, comme sa `Config` : une valeur invalide de `ATLAS_REVEIL_SEUIL`, `ATLAS_SILENCE_MS`, `ATLAS_BARGEIN_MS`, `ATLAS_BARGEIN_DBFS` ou `ATLAS_RELANCE_S` dans son `.env` l'empêche désormais de démarrer.
12. **L'interface** : le micro est un bouton-icône (un SVG en ligne, qui prend la couleur d'accent allumé) dans la barre, avec `aria-pressed` ; l'orbe à toucher est un bouton rond et transparent posé sur elle (`#parler`), visible micro allumé ; l'interrupteur « Hey Atlas » ouvre les Paramètres, éteint par défaut, retenu sous `atlas.hey_atlas` ; les messages de la voix s'affichent sous la barre (`#message-voix`), qu'on touche pour réactiver le micro.
13. **Sans HTTPS**, la page ne demande même pas le micro et le dit (« Le micro ne s'ouvre qu'à l'adresse HTTPS d'Atlas. ») ; un micro refusé affiche l'erreur du navigateur.
14. **Le verrou d'écran** n'est demandé que micro allumé et « Hey Atlas » allumé ; redemandé au retour sur la page.

## Carte des fichiers

| Fichier | Tâche | Rôle |
|---|---|---|
| `src/atlas_audio/client.py` | 1 | Marge de sortie réglable, amorçage de l'annuleur, orbe touchée |
| `src/atlas_core/protocole_voix.py`, `src/atlas_core/protocole_web.py` | 2 | Messages de `/ws/voix` ; `page` dans l'authentification de `/ws/web` |
| `src/atlas_core/regie.py` | 3 | Plusieurs sessions audio, routage par page, muet pour toutes |
| `src/atlas_core/voix.py` | 4 | `PeripheriqueNavigateur`, `ReveilleurPage`, `TransportSession`, `FluxSession`, `monter_page` |
| `src/atlas_core/config.py`, `src/atlas_core/hub.py` | 5 | `voix_marge_s`, `voix_bargein_dbfs` ; la route `/ws/voix` |
| `src/atlas_web/connexion.js`, `src/atlas_web/app.js` | 6, 9 | Connexion généralisée, identifiant de page ; la voix dans la page |
| `src/atlas_web/voix_worklet.js` | 7 | Processeurs de capture et de lecture |
| `src/atlas_web/voix.js` | 8 | Micro, lecture, reprise après iOS, verrou d'écran |
| `src/atlas_web/index.html`, `src/atlas_web/style.css` | 9 | Bouton Micro, orbe à toucher, « Hey Atlas », message de la voix |
| `.env.example`, `scripts/neo/LISEZMOI.md`, `docs/superpowers/specs/2026-09-22-atlas-design.md` | 10 | Réglages, HTTPS par Nginx Proxy Manager, modèles du Core, spec parente |
| `tests/test_client_page.py`, `test_protocole_voix.py`, `test_regie.py`, `test_voix.py`, `test_config.py`, `test_hub_voix.py`, `test_hub_web.py` | 1–5 | Tests Python |
| `tests/web/connexion.test.mjs`, `app.test.mjs`, `voix_worklet.test.mjs`, `voix.test.mjs`, `faux_audio.mjs`, `faux_dom.mjs` | 6–9 | Tests JavaScript |

---

### Task 1: Le client audio d'une page : marge, amorçage, orbe touchée

Le `ClientAudio` du Mac servira aussi les pages. Il lui faut trois choses : une marge de sortie réglable (la
latence d'un navigateur n'est pas celle du haut-parleur du Mac), l'amorçage de l'annuleur d'écho (pendant les 10
premières secondes de voix d'Atlas, la voix ne le coupe pas : spike S4) et l'orbe touchée, traitée au bloc suivant.
Sans ces paramètres, le client du Mac ne change pas (`amorcage_s=0.0`, marge de 0,15 s).

**Files:**
- Modify: `src/atlas_audio/client.py`
- Create: `tests/test_client_page.py`

**Interfaces:**
- Consumes: rien de neuf ; les tests réutilisent les doublures de `tests/test_client_audio.py` (`BLOC`, `BLOC_FORT`,
  `DetecteurScript`, `FausseHorloge`, `FauxPeripherique`, `FauxTransport`, `ReveilleurScript`, `_client`, `_jouer`).
- Produces: `ClientAudio(..., marge_sortie_s: float = MARGE_SORTIE_S, amorcage_s: float = 0.0)` ;
  `ClientAudio.reamorcer() -> None` (l'amorçage repart de zéro) ; `ClientAudio.demander_la_parole() -> None` (au
  prochain bloc : l'écoute s'ouvre au repos, Atlas est coupé s'il parle, rien pendant une écoute déjà ouverte) ;
  `ClientAudio._interrompre(pre_roulement)`, la coupure commune au barge-in et à l'orbe. L'amorçage se compte en
  trames jouées (`round(amorcage_s / 0.02)`), et finit quand la dernière a fini de jouer.

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/test_client_page.py` :

```python
"""Le client audio au service d'une page : marge de sortie, amorçage de l'annuleur
d'écho du navigateur, et l'orbe touchée."""

from test_client_audio import (
    BLOC,
    BLOC_FORT,
    DetecteurScript,
    FausseHorloge,
    FauxPeripherique,
    FauxTransport,
    ReveilleurScript,
    _client,
    _jouer,
)

from atlas_audio.client import ClientAudio
from atlas_audio.vad import Endpointeur
from atlas_core.protocole import Etat, Interruption, Reveil, decoder_audio_entrant


def _client_page(t, p, parole, horloge, amorcage_s=0.0, marge_sortie_s=0.15, reveil_au=None):
    return ClientAudio(
        transport=t,
        peripherique=p,
        detecteur=DetecteurScript(parole),
        endpointeur=Endpointeur(silence_ms=60, parole_min_ms=40),
        reveilleur=ReveilleurScript(reveil_au),
        bargein=Endpointeur(silence_ms=60, parole_min_ms=40),
        horloge=horloge,
        amorcage_s=amorcage_s,
        marge_sortie_s=marge_sortie_s,
    )


def _interrompu(t: FauxTransport) -> bool:
    return any(isinstance(m, Interruption) for m in t.json)


async def test_la_marge_de_sortie_se_regle():
    h = FausseHorloge()
    t, p = FauxTransport(), FauxPeripherique([BLOC] * 6)
    c = _client_page(t, p, parole=[False] * 6, horloge=h, marge_sortie_s=0.5, reveil_au=0)
    await _jouer(c, id_enonce=1, blocs=10)  # 0,2 s de son
    await c.sur_message(Etat(valeur="repos"))
    h.avancer(0.2 + 0.4)  # au-delà de 0,15 s de marge, en deçà de 0,5 s

    await c.boucle_capture()

    assert t.json == [], "le mot de réveil n'est pas encore écouté : Atlas parle encore"
    p.ajouter([BLOC] * 2)
    h.avancer(0.2)
    await c.boucle_capture()
    assert isinstance(t.json[0], Reveil)


async def test_la_voix_ne_coupe_pas_atlas_pendant_l_amorcage():
    h = FausseHorloge()
    t, p = FauxTransport(), FauxPeripherique([BLOC_FORT] * 6)
    c = _client_page(t, p, parole=[True] * 20, horloge=h, amorcage_s=1.0)
    await _jouer(c, id_enonce=1, blocs=100)  # 2 s de voix, dont la première seconde amorce

    await c.boucle_capture()
    assert not _interrompu(t), "pendant la première seconde jouée, l'écho n'est pas une coupure"

    h.avancer(1.1)  # la seconde amorcée a fini de jouer
    p.ajouter([BLOC_FORT] * 6)
    await c.boucle_capture()
    assert _interrompu(t)


async def test_reamorcer_rouvre_l_amorcage():
    h = FausseHorloge()
    t, p = FauxTransport(), FauxPeripherique([])
    c = _client_page(t, p, parole=[True] * 20, horloge=h, amorcage_s=0.2)
    await _jouer(c, id_enonce=1, blocs=10)
    h.avancer(0.3)  # l'amorçage est passé
    c.reamorcer()  # la page revient d'une interruption d'iOS
    await _jouer(c, id_enonce=1, blocs=50, rang=2)
    p.ajouter([BLOC_FORT] * 6)

    await c.boucle_capture()

    assert not _interrompu(t)


async def test_toucher_l_orbe_au_repos_ouvre_l_ecoute_des_ce_bloc():
    t, p = FauxTransport(), FauxPeripherique([BLOC_FORT, BLOC, BLOC])
    c = _client(t, p, parole=[True, True, True], reveil_au=None)
    c.demander_la_parole()

    await c.boucle_capture()

    assert t.types()[0] == "reveil"
    assert decoder_audio_entrant(t.binaire[0]) == BLOC_FORT, "le premier mot n'est pas perdu"
    assert len(t.binaire) == 3


async def test_toucher_l_orbe_pendant_qu_atlas_parle_le_coupe():
    h = FausseHorloge()
    t, p = FauxTransport(), FauxPeripherique([BLOC, BLOC])
    c = _client_page(t, p, parole=[False, False], horloge=h, amorcage_s=10.0)
    await _jouer(c, id_enonce=1, blocs=50)
    c.demander_la_parole()  # même pendant l'amorçage : toucher coupe toujours

    await c.boucle_capture()

    assert t.types()[0] == "interruption"
    assert p.vidages == 1
    assert len(t.binaire) == 2, "l'écoute est ouverte : les blocs partent au Core"


async def test_toucher_l_orbe_pendant_l_ecoute_ne_rouvre_rien():
    t, p = FauxTransport(), FauxPeripherique([BLOC] * 4)
    c = _client(t, p, parole=[True] * 4, reveil_au=0)  # « Hey Atlas » au premier bloc
    await c.boucle_capture()
    c.demander_la_parole()
    p.ajouter([BLOC] * 2)

    await c.boucle_capture()

    assert t.types().count("reveil") == 1
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `uv run pytest tests/test_client_page.py -q`
Expected: FAIL — 6 échecs : `TypeError: ClientAudio.__init__() got an unexpected keyword argument 'amorcage_s'`,
et `AttributeError: 'ClientAudio' object has no attribute 'demander_la_parole'` pour les trois tests de l'orbe.

- [ ] **Step 3: Écrire le code**

`client.py` finit à 499 lignes : ne rien ajouter d'autre (Global Constraints).

Modifier `src/atlas_audio/client.py` :

```diff
--- a/src/atlas_audio/client.py
+++ b/src/atlas_audio/client.py
@@ -157,6 +157,8 @@ class ClientAudio:
         seuil_bargein_dbfs: float = _SEUIL_BARGEIN_DBFS_DEFAUT,
         relance_s: float = 0.0,
         attendre: Callable[[float], Awaitable[None]] | None = None,
+        marge_sortie_s: float = MARGE_SORTIE_S,
+        amorcage_s: float = 0.0,
     ) -> None:
         self._transport = transport
         self._peripherique = peripherique
@@ -203,11 +205,35 @@ class ClientAudio:
         self._relance_s = relance_s
         self._reponse_jouee = False
         self._relance_due = False
+        # La latence de sortie : celle du haut-parleur du Mac, ou d'une page (spike S4).
+        self._marge_sortie_s = marge_sortie_s
+        # L'annuleur d'écho d'un navigateur laisse passer l'écho le temps de s'installer
+        # (spike S4) : pendant `amorcage_s` s de voix jouée, la voix ne coupe pas Atlas.
+        self._trames_a_amorcer = round(amorcage_s / DUREE_BLOC_S)  # compte entier, sans arrondi
+        self._trames_amorcees = 0  # jouées depuis l'ouverture (ou la reprise) du micro
+        self._fin_amorcage = 0.0  # heure où finit de jouer la dernière trame amorcée
+        # L'orbe touchée : au prochain bloc, l'écoute s'ouvre, ou Atlas est coupé.
+        self._parole_demandee = False
 
     def _atlas_parle_encore(self) -> bool:
         # Une échéance expire d'elle-même, et tout état autre que « parole » désarme le
         # Core : le micro ne peut jamais rester sourd.
-        return self._core_parle or self._horloge() < self._fin_lecture + MARGE_SORTIE_S
+        return self._core_parle or self._horloge() < self._fin_lecture + self._marge_sortie_s
+
+    def _amorcage_en_cours(self) -> bool:
+        en_cours = self._trames_amorcees < self._trames_a_amorcer
+        return en_cours or self._horloge() < self._fin_amorcage
+
+    def reamorcer(self) -> None:
+        """Le micro de la page vient de rouvrir (ou le son de reprendre après une
+        interruption d'iOS) : l'annuleur d'écho s'installe à nouveau."""
+        self._trames_amorcees = 0
+        self._fin_amorcage = 0.0
+
+    def demander_la_parole(self) -> None:
+        """L'orbe a été touchée : au prochain bloc (dans la tâche de capture, donc sans
+        croiser un bloc en cours), l'écoute s'ouvre, ou Atlas est coupé s'il parle."""
+        self._parole_demandee = True
 
     # --- micro vers Core --------------------------------------------------
 
@@ -224,6 +250,18 @@ class ClientAudio:
                 await self._traiter_bloc(bloc)
 
     async def _traiter_bloc(self, bloc: bytes) -> None:
+        if self._parole_demandee:
+            self._parole_demandee = False
+            if self._atlas_parle_encore():
+                await self._interrompre([])
+            elif not self._capture:
+                self._relance_due = False
+                self._ouvrir_capture()
+                await self._annoncer_ecoute()
+            if self._capture:
+                await self._capturer(bloc, self._detecteur.parle(bloc))
+            return
+
         if self._atlas_parle_encore():
             await self._surveiller_bargein(bloc)
             return
@@ -288,10 +326,15 @@ class ClientAudio:
         # porte d'énergie en a laissé passer.
         self._pre_roulement.append((bloc, parle))
         niveau = self._fenetre_energie.ajouter(bloc)
+        if self._amorcage_en_cours():
+            return  # l'écho de l'annuleur qui s'installe n'est pas une interruption
         if self._bargein.ajouter(parle and niveau > self._seuil_bargein_dbfs) != "debut":
             return
         _journal.info("interruption détectée (%.1f dBFS sur 300 ms)", niveau)
-        pre_roulement = list(self._pre_roulement)
+        await self._interrompre(list(self._pre_roulement))
+
+    async def _interrompre(self, pre_roulement: list[tuple[bytes, bool]]) -> None:
+        """Coupe Atlas et ouvre l'écoute : barge-in à la voix, ou orbe touchée."""
         self._couper()
         # Le Core d'abord : il arrête la synthèse et Claude pendant que le son se vide.
         await self._transport.envoyer_json(Interruption(horodatage=time.time()))
@@ -373,6 +416,11 @@ class ClientAudio:
         if self._a_jouer(identifiant):
             # Sinon, coupée pendant l'écriture : le vidage l'a suivie, l'horloge n'avance pas.
             self._fin_lecture = max(self._horloge(), self._fin_lecture) + DUREE_BLOC_S
+            if self._trames_amorcees < self._trames_a_amorcer:
+                self._trames_amorcees += 1
+                if self._trames_amorcees == self._trames_a_amorcer:
+                    # La dernière trame amorcée ne finira de jouer qu'à cette heure-là.
+                    self._fin_amorcage = self._fin_lecture
 
     def _a_jouer(self, identifiant: int) -> bool:
         return identifiant > self._id_coupe and identifiant == self._id_courant
```

- [ ] **Step 4: Vérifier que tout passe**

Run: `uv run pytest tests/test_client_page.py tests/test_client_audio.py tests/test_client_parole.py tests/test_integration_boucle.py -q`
Expected: PASS — le client du Mac ne change pas de comportement.

Run: `uv run pytest -q && uv run ruff check . && uv run ruff format --check . && node --test "tests/web/*.test.mjs"`
Expected: 596 tests Python passent, 72 tests JavaScript passent, ruff ne dit rien.

- [ ] **Step 5: Commit**

```bash
git add src/atlas_audio/client.py tests/test_client_page.py
git commit -F - <<'MSG'
Client audio : marge de sortie réglable, amorçage de l'annuleur, orbe touchée

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

### Task 2: Le protocole de `/ws/voix`, et l'identifiant de page

Les messages de la nouvelle connexion, et l'identifiant de page que `/ws/web` accepte désormais dans son
authentification (facultatif), pour qu'une question tapée trouve la voix de sa page.

**Files:**
- Create: `src/atlas_core/protocole_voix.py`
- Modify: `src/atlas_core/protocole_web.py`
- Create: `tests/test_protocole_voix.py`

**Interfaces:**
- Consumes: `protocole.TAILLE_BLOC_OCTETS` (640), `protocole_web.TAILLE_MAX_CLE` (256).
- Produces: `protocole_web.MOTIF_PAGE = r"^[A-Za-z0-9_-]{1,64}$"` ; `Authentification.page: str | None = None`.
  `atlas_core.protocole_voix` : `AuthentificationVoix(cle, page, hey_atlas=False)`, `Parler()`, `HeyAtlas(actif)`,
  `Reprise()`, `Pret()`, `Vider()` ; `decoder_message_voix(brut: str)` (lève `ValueError("message de voix invalide :
  …")`) ; `verifier_bloc_page(donnees: bytes) -> bytes` (lève `ValueError("bloc de N octets, attendu 640")`).

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/test_protocole_voix.py` :

```python
import pytest

from atlas_core.protocole_voix import (
    AuthentificationVoix,
    HeyAtlas,
    Parler,
    Pret,
    Reprise,
    Vider,
    decoder_message_voix,
    verifier_bloc_page,
)
from atlas_core.protocole_web import Authentification, decoder_message_page


def test_l_authentification_porte_la_cle_la_page_et_hey_atlas():
    msg = decoder_message_voix(
        '{"type":"authentification","cle":"c","page":"a1-B_2","hey_atlas":true}'
    )
    assert msg == AuthentificationVoix(cle="c", page="a1-B_2", hey_atlas=True)


def test_hey_atlas_est_eteint_par_defaut():
    msg = decoder_message_voix('{"type":"authentification","cle":"c","page":"p"}')
    assert msg.hey_atlas is False


@pytest.mark.parametrize(
    ("brut", "attendu"),
    [
        ('{"type":"parler"}', Parler()),
        ('{"type":"hey_atlas","actif":false}', HeyAtlas(actif=False)),
        ('{"type":"reprise"}', Reprise()),
    ],
)
def test_les_messages_de_la_page_se_decodent(brut, attendu):
    assert decoder_message_voix(brut) == attendu


@pytest.mark.parametrize(
    "brut",
    [
        '{"type":"authentification","cle":"c"}',
        '{"type":"authentification","cle":"c","page":"../etc"}',
        '{"type":"authentification","cle":"c","page":""}',
        '{"type":"authentification","cle":"' + "x" * 300 + '","page":"p"}',
        '{"type":"saisie","texte":"bonjour"}',
        "pas du json",
    ],
)
def test_un_message_invalide_leve_value_error(brut):
    with pytest.raises(ValueError, match="message de voix invalide"):
        decoder_message_voix(brut)


def test_le_core_confirme_et_vide():
    assert Pret().model_dump_json() == '{"type":"pret"}'
    assert Vider().model_dump_json() == '{"type":"vider"}'


def test_un_bloc_de_micro_fait_exactement_640_octets():
    assert verifier_bloc_page(b"\x00" * 640) == b"\x00" * 640
    for taille in (0, 639, 641, 1280):
        with pytest.raises(ValueError, match="attendu 640"):
            verifier_bloc_page(b"\x00" * taille)


def test_l_authentification_des_pages_peut_porter_l_identifiant():
    assert decoder_message_page('{"type":"authentification","cle":"c"}') == Authentification(
        cle="c"
    )
    avec = decoder_message_page('{"type":"authentification","cle":"c","page":"p1"}')
    assert avec.page == "p1"
    with pytest.raises(ValueError):
        decoder_message_page('{"type":"authentification","cle":"c","page":"a b"}')
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `uv run pytest tests/test_protocole_voix.py -q`
Expected: FAIL — erreur de collecte : `ModuleNotFoundError: No module named 'atlas_core.protocole_voix'`.

- [ ] **Step 3: Écrire le protocole**

Créer `src/atlas_core/protocole_voix.py` :

```python
"""Messages de la connexion /ws/voix, entre une page qui a allumé son micro et le Core.

L'audio y passe en binaire dans les deux sens, en blocs bruts de 20 ms à 16 kHz
(640 octets, s16le) : sur cette connexion, tout ce qui est binaire est de l'audio. Les
messages de contrôle passent en JSON.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from .protocole import TAILLE_BLOC_OCTETS
from .protocole_web import MOTIF_PAGE, TAILLE_MAX_CLE

# --- page vers Core -----------------------------------------------------


class AuthentificationVoix(BaseModel):
    """Le premier message : la clé des pages, l'identifiant de la page, et l'état de son
    interrupteur « Hey Atlas »."""

    type: Literal["authentification"] = "authentification"
    cle: str = Field(max_length=TAILLE_MAX_CLE)
    page: str = Field(pattern=MOTIF_PAGE)
    hey_atlas: bool = False


class Parler(BaseModel):
    """L'orbe a été touchée : écouter, ou couper Atlas s'il parle."""

    type: Literal["parler"] = "parler"


class HeyAtlas(BaseModel):
    type: Literal["hey_atlas"] = "hey_atlas"
    actif: bool


class Reprise(BaseModel):
    """Le son de la page reprend après une interruption d'iOS (écran verrouillé…)."""

    type: Literal["reprise"] = "reprise"


# --- Core vers page -----------------------------------------------------


class Pret(BaseModel):
    """La clé est acceptée : la page peut envoyer son micro."""

    type: Literal["pret"] = "pret"


class Vider(BaseModel):
    """Le son en cours s'arrête net."""

    type: Literal["vider"] = "vider"


MessageVoix = Annotated[
    AuthentificationVoix | Parler | HeyAtlas | Reprise, Field(discriminator="type")
]
_adaptateur_voix = TypeAdapter(MessageVoix)


def decoder_message_voix(brut: str) -> MessageVoix:
    """Décode un message de /ws/voix. Lève ValueError sur tout ce qui n'est pas valide."""
    try:
        return _adaptateur_voix.validate_json(brut)
    except ValidationError as e:
        raise ValueError(f"message de voix invalide : {e.errors()[0].get('msg')}") from e


def verifier_bloc_page(donnees: bytes) -> bytes:
    """Un bloc de micro reçu d'une page : exactement 20 ms à 16 kHz, en s16le."""
    if len(donnees) != TAILLE_BLOC_OCTETS:
        raise ValueError(f"bloc de {len(donnees)} octets, attendu {TAILLE_BLOC_OCTETS}")
    return donnees
```

Modifier `src/atlas_core/protocole_web.py` :

```diff
--- a/src/atlas_core/protocole_web.py
+++ b/src/atlas_core/protocole_web.py
@@ -12,6 +12,9 @@ from pydantic import BaseModel, Field, TypeAdapter, ValidationError, field_valid
 
 LONGUEUR_MAX_SAISIE = 1000
 TAILLE_MAX_CLE = 256
+# L'identifiant qu'une page tire au hasard à son ouverture, le même sur /ws/web et sur
+# /ws/voix : une question tapée trouve ainsi la voix de sa page.
+MOTIF_PAGE = r"^[A-Za-z0-9_-]{1,64}$"
 
 Source = Literal["voix", "clavier"]
 
@@ -69,6 +72,7 @@ class Historique(BaseModel):
 class Authentification(BaseModel):
     type: Literal["authentification"] = "authentification"
     cle: str = Field(max_length=TAILLE_MAX_CLE)
+    page: str | None = Field(default=None, pattern=MOTIF_PAGE)
 
 
 class Saisie(BaseModel):
```

- [ ] **Step 4: Vérifier que tout passe**

Run: `uv run pytest -q && uv run ruff check . && uv run ruff format --check . && node --test "tests/web/*.test.mjs"`
Expected: 610 tests Python passent, 72 tests JavaScript passent, ruff ne dit rien.

- [ ] **Step 5: Commit**

```bash
git add src/atlas_core/protocole_voix.py src/atlas_core/protocole_web.py tests/test_protocole_voix.py
git commit -F - <<'MSG'
Protocole de /ws/voix, et identifiant de page sur /ws/web

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

### Task 3: La régie à plusieurs sessions

Aujourd'hui la régie ne connaît que la dernière session audio. Elle les garde désormais toutes, chacune avec sa page
(`None` pour le client du Mac) : une question tapée va à la session de sa page, sinon à la plus récente, sinon à la
session écrite ; le muet les fait toutes taire.

**Files:**
- Modify: `src/atlas_core/regie.py`
- Modify: `tests/test_hub_web.py`
- Modify: `tests/test_regie.py`

**Interfaces:**
- Consumes: rien de neuf.
- Produces: `Regie.rattacher(session, page: str | None = None)`, `Regie.detacher(session)`,
  `Regie.saisie(texte: str, page: str | None = None)` ; `basculer_muet(True)` appelle `taire()` sur toutes les
  sessions audio. `Regie._sessions: list[tuple[str | None, SessionPilotable]]`, de la plus ancienne à la plus
  récente (les tests du hub la lisent). Dans `tests/test_hub_web.py`, `RegieEspionne` accepte `page` et note
  `pages`.

- [ ] **Step 1: Écrire les tests qui échouent**

Modifier `tests/test_hub_web.py` :

```diff
--- a/tests/test_hub_web.py
+++ b/tests/test_hub_web.py
@@ -17,18 +17,20 @@ class RegieEspionne:
         self.diffuseur = Diffuseur()
         self.saisies: list[str] = []
         self.muets: list[bool] = []
+        self.pages: list[str | None] = []
 
     def voix_active(self) -> bool:
         return True
 
-    def rattacher(self, session) -> None:
+    def rattacher(self, session, page: str | None = None) -> None:
         pass
 
     def detacher(self, session) -> None:
         pass
 
-    async def saisie(self, texte: str) -> None:
+    async def saisie(self, texte: str, page: str | None = None) -> None:
         self.saisies.append(texte)
+        self.pages.append(page)
 
     async def basculer_muet(self, actif: bool) -> None:
         self.muets.append(actif)
@@ -158,6 +160,6 @@ def test_le_client_audio_est_rattache_puis_detache_de_la_regie(monkeypatch):
         ws.send_text(Bonjour(client="test", cle="cle-audio").model_dump_json())
         ws.send_text('{"type":"nimporte_quoi"}')
         assert ws.receive_json()["code"] == "message_invalide"  # la boucle est atteinte
-        assert hub._regie._session_audio is fake
+        assert hub._regie._sessions == [(None, fake)]
         ws.close()
-    assert hub._regie._session_audio is None
+    assert hub._regie._sessions == []
```

Modifier `tests/test_regie.py` :

```diff
--- a/tests/test_regie.py
+++ b/tests/test_regie.py
@@ -83,3 +83,47 @@ async def test_le_muet_sans_client_audio_ne_plante_pas():
     regie, _ = _regie()
     await regie.basculer_muet(True)
     assert regie.muet is True
+
+
+async def test_une_question_tapee_va_a_la_session_de_sa_page():
+    regie, creees = _regie()
+    mac, ipad, iphone = SessionEspionne(), SessionEspionne(), SessionEspionne()
+    regie.rattacher(mac)
+    regie.rattacher(iphone, page="iphone")
+    regie.rattacher(ipad, page="ipad")
+    await regie.saisie("pour l'iPhone", page="iphone")
+    await regie.saisie("pour l'iPad", page="ipad")
+    assert iphone.saisies == ["pour l'iPhone"] and ipad.saisies == ["pour l'iPad"]
+    assert mac.saisies == [] and creees == []
+
+
+async def test_une_page_sans_micro_passe_a_la_session_audio_la_plus_recente():
+    regie, creees = _regie()
+    mac, ipad = SessionEspionne(), SessionEspionne()
+    regie.rattacher(mac)
+    regie.rattacher(ipad, page="ipad")
+    await regie.saisie("sans micro", page="iphone")
+    await regie.saisie("sans identifiant")
+    assert ipad.saisies == ["sans micro", "sans identifiant"] and mac.saisies == []
+    regie.detacher(ipad)
+    await regie.saisie("l'iPad est parti", page="ipad")
+    assert mac.saisies == ["l'iPad est parti"] and creees == []
+
+
+async def test_une_page_rebranchee_repond_par_sa_session_la_plus_recente():
+    regie, _ = _regie()
+    ancienne, nouvelle = SessionEspionne(), SessionEspionne()
+    regie.rattacher(ancienne, page="ipad")
+    regie.rattacher(nouvelle, page="ipad")  # l'ancienne connexion n'est pas encore détachée
+    await regie.saisie("bonjour", page="ipad")
+    assert nouvelle.saisies == ["bonjour"] and ancienne.saisies == []
+
+
+async def test_le_muet_fait_taire_toutes_les_sessions_audio():
+    regie, _ = _regie()
+    sessions = [SessionEspionne() for _ in range(3)]
+    regie.rattacher(sessions[0])
+    regie.rattacher(sessions[1], page="ipad")
+    regie.rattacher(sessions[2], page="iphone")
+    await regie.basculer_muet(True)
+    assert [s.taire_appels for s in sessions] == [1, 1, 1]
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `uv run pytest tests/test_regie.py tests/test_hub_web.py -q`
Expected: FAIL — 5 échecs : `TypeError: Regie.rattacher() got an unexpected keyword argument 'page'` (quatre
tests de la régie) et `AttributeError: 'Regie' object has no attribute '_sessions'` (le test du client audio
dans `test_hub_web.py`).

- [ ] **Step 3: Écrire la régie**

Remplacer tout `src/atlas_core/regie.py` par :

```python
"""La régie : ce que partagent toutes les connexions du Core.

Le diffuseur des pages, le mode muet, et les sessions qui reçoivent les questions
tapées : celle de la page qui l'a tapée si son micro est allumé, sinon la plus récente
des sessions audio (le client du Mac ou une page), pour qu'Atlas réponde à voix haute,
ou à défaut une session sans voix.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from .diffuseur import Diffuseur
from .protocole_web import Muet


class SessionPilotable(Protocol):
    async def sur_saisie(self, texte: str) -> None: ...

    async def taire(self) -> None: ...


class Regie:
    def __init__(
        self, diffuseur: Diffuseur, fabrique_session_ecrite: Callable[[], SessionPilotable]
    ) -> None:
        self.diffuseur = diffuseur
        self._fabrique_session_ecrite = fabrique_session_ecrite
        # Les sessions audio, de la plus ancienne à la plus récente, avec la page qui
        # les porte (None : le client audio du Mac).
        self._sessions: list[tuple[str | None, SessionPilotable]] = []
        self._session_ecrite: SessionPilotable | None = None
        self._muet = False

    @property
    def muet(self) -> bool:
        return self._muet

    def voix_active(self) -> bool:
        return not self._muet

    def rattacher(self, session: SessionPilotable, page: str | None = None) -> None:
        """Un client audio vient de se connecter, ou une page d'allumer son micro."""
        self._sessions.append((page, session))

    def detacher(self, session: SessionPilotable) -> None:
        self._sessions = [(p, s) for p, s in self._sessions if s is not session]

    def _session_pour(self, page: str | None) -> SessionPilotable:
        if page is not None:
            for p, session in reversed(self._sessions):
                if p == page:
                    return session
        if self._sessions:
            return self._sessions[-1][1]
        if self._session_ecrite is None:
            self._session_ecrite = self._fabrique_session_ecrite()
        return self._session_ecrite

    async def saisie(self, texte: str, page: str | None = None) -> None:
        await self._session_pour(page).sur_saisie(texte)

    async def basculer_muet(self, actif: bool) -> None:
        self._muet = actif
        self.diffuseur.publier(Muet(actif=actif))
        if actif:
            for _, session in list(self._sessions):
                await session.taire()
```

- [ ] **Step 4: Vérifier que tout passe**

Run: `uv run pytest -q && uv run ruff check . && uv run ruff format --check . && node --test "tests/web/*.test.mjs"`
Expected: 614 tests Python passent, 72 tests JavaScript passent, ruff ne dit rien.

- [ ] **Step 5: Commit**

```bash
git add src/atlas_core/regie.py tests/test_hub_web.py tests/test_regie.py
git commit -F - <<'MSG'
Régie : plusieurs sessions audio, question tapée routée par page, muet pour toutes

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

### Task 4: La voix d'une page, côté Core

Le montage d'une page : son périphérique (les blocs reçus de `/ws/voix`, le son qui y repart), son réveilleur
(« Hey Atlas » si l'interrupteur est allumé), son `ClientAudio` et sa `Session`, reliés en mémoire. Le test
d'intégration branche le vrai client à une vraie session, la page remplacée par deux listes.

**Files:**
- Create: `src/atlas_core/voix.py`
- Create: `tests/test_voix.py`

**Interfaces:**
- Consumes: Task 1 (`ClientAudio(..., marge_sortie_s, amorcage_s)`, `demander_la_parole`, `reamorcer`) ; Task 2
  (`Vider`) ; Task 3 (`Regie`, dans un test) ; `atlas_audio.client.Reglages`, `atlas_audio.connexion.servir_connexion`,
  `atlas_audio.vad.CHEMIN_MODELE`.
- Produces: `atlas_core.voix` : `AMORCAGE_S = 10.0`, `FILE_MAX_BLOCS = 250` ;
  `charger_modeles(seuil_reveil: float) -> tuple[DetecteurVoix, ReveilleurMotCle]` (lève `FileNotFoundError` si un
  modèle manque) ; `PeripheriqueNavigateur(envoyer_json, envoyer_binaire)` avec `recevoir(bloc)`, `lire_bloc()`,
  `jouer(pcm)`, `vider()` ; `ReveilleurPage(mot_cle, actif)` et son attribut `actif` ; `TransportSession(session)` ;
  `FluxSession` ; `PageVoix` (`peripherique`, `reveilleur`, `client`, `session`, `flux`, `async servir()`) ;
  `monter_page(envoyer_json, envoyer_binaire, fabrique_session, modeles, reglages, marge_sortie_s, hey_atlas,
  horloge=None, attendre=None) -> PageVoix`, où `fabrique_session(envoyer_json, envoyer_binaire)` rend la session.

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/test_voix.py` :

```python
"""La voix d'une page, côté Core : ses pièces, puis le vrai client audio branché à une
vraie session, la page étant remplacée par deux listes (ce qu'elle envoie, ce qu'elle
reçoit) et le temps par une horloge qu'on avance à la main."""

import asyncio
import contextlib
import struct
from collections.abc import AsyncIterator
from dataclasses import replace

import pytest

from atlas_audio.client import Reglages
from atlas_core import voix
from atlas_core.diffuseur import Diffuseur
from atlas_core.protocole import Etat, Interruption, Reveil, encoder_audio_entrant
from atlas_core.protocole_voix import Vider
from atlas_core.regie import Regie
from atlas_core.session import Session
from atlas_core.voix import (
    FILE_MAX_BLOCS,
    FluxSession,
    PeripheriqueNavigateur,
    ReveilleurPage,
    TransportSession,
    charger_modeles,
    monter_page,
)

SILENCE = b"\x00" * 640
PAROLE = struct.pack("<h", 8000) * 320  # -12 dBFS : bien au-dessus de la porte de -40 dBFS
REGLAGES = Reglages(
    seuil_reveil=0.5, silence_ms=400, bargein_ms=300, bargein_dbfs=-40.0, relance_s=0.0
)
QUESTION = [PAROLE] * 25 + [SILENCE] * 25  # une demi-seconde de parole, puis le silence


async def _laisser_tourner(tours: int = 30) -> None:
    for _ in range(tours):
        await asyncio.sleep(0)


async def _attendre(condition, message: str) -> None:
    for _ in range(50_000):
        if condition():
            return
        await asyncio.sleep(0)
    raise AssertionError(message)


# --- les pièces -----------------------------------------------------------


class Envois:
    def __init__(self) -> None:
        self.recus: list = []

    async def json(self, msg) -> None:
        self.recus.append(msg)

    async def binaire(self, pcm: bytes) -> None:
        self.recus.append(pcm)


async def test_le_peripherique_rend_les_blocs_de_la_page_dans_l_ordre():
    envois = Envois()
    peripherique = PeripheriqueNavigateur(envois.json, envois.binaire)
    lecture = asyncio.create_task(peripherique.lire_bloc())
    await _laisser_tourner()
    assert not lecture.done()  # rien reçu : il attend
    peripherique.recevoir(b"\x01" * 640)
    peripherique.recevoir(b"\x02" * 640)
    assert await lecture == b"\x01" * 640
    assert await peripherique.lire_bloc() == b"\x02" * 640


async def test_si_le_core_prend_du_retard_les_plus_vieux_blocs_se_perdent():
    peripherique = PeripheriqueNavigateur(Envois().json, Envois().binaire)
    for i in range(FILE_MAX_BLOCS + 10):
        peripherique.recevoir(struct.pack("<h", i) * 320)
    assert await peripherique.lire_bloc() == struct.pack("<h", 10) * 320


async def test_le_peripherique_joue_et_vide_par_la_page():
    envois = Envois()
    peripherique = PeripheriqueNavigateur(envois.json, envois.binaire)
    await peripherique.jouer(b"\x07" * 640)
    await peripherique.vider()
    assert envois.recus == [b"\x07" * 640, Vider()]


class MotCleEspion:
    """Se déclenche au premier bloc examiné, puis plus jamais."""

    def __init__(self) -> None:
        self.examens = 0

    def examiner(self, bloc: bytes) -> bool:
        self.examens += 1
        return self.examens == 1


def test_interrupteur_eteint_le_mot_de_reveil_n_est_meme_pas_consulte():
    mot_cle = MotCleEspion()
    reveilleur = ReveilleurPage(mot_cle, actif=False)
    assert reveilleur.examiner(SILENCE) is False and mot_cle.examens == 0
    reveilleur.actif = True
    assert reveilleur.examiner(SILENCE) is True and mot_cle.examens == 1


class SessionEspionne:
    def __init__(self) -> None:
        self.messages: list = []
        self.audio: list[bytes] = []

    async def sur_message(self, msg) -> None:
        self.messages.append(msg)

    async def sur_audio(self, pcm: bytes) -> None:
        self.audio.append(pcm)


async def test_le_client_de_la_page_parle_directement_a_sa_session():
    session = SessionEspionne()
    transport = TransportSession(session)
    reveil = Reveil(confiance=1.0, horodatage=0.0)
    await transport.envoyer_json(reveil)
    await transport.envoyer_binaire(encoder_audio_entrant(PAROLE))
    assert session.messages == [reveil] and session.audio == [PAROLE]


async def test_la_session_parle_a_son_client_comme_une_websocket():
    flux = FluxSession()
    await flux.envoyer_json(Etat(valeur="ecoute"))
    await flux.envoyer_binaire(b"\x02trame")
    assert await anext(flux) == Etat(valeur="ecoute").model_dump_json()
    assert await anext(flux) == b"\x02trame"


def test_sans_silero_sur_la_machine_du_core_le_message_le_dit(monkeypatch, tmp_path):
    monkeypatch.setattr(voix, "CHEMIN_MODELE", str(tmp_path / "absent.onnx"))
    with pytest.raises(FileNotFoundError, match="absent.onnx"):
        charger_modeles(0.5)


# --- la page branchée à une vraie session ---------------------------------


class FausseHorloge:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def avancer(self, secondes: float) -> None:
        self.t += secondes


class DetecteurParContenu:
    def parle(self, bloc: bytes) -> bool:
        return bloc != SILENCE


class FausseTranscription:
    def __init__(self) -> None:
        self.appels = 0

    async def transcrire(self, pcm: bytes) -> str:
        self.appels += 1
        return "Raconte-moi quelque chose."


class FausseSynthese:
    def __init__(self, trames_par_phrase: int) -> None:
        self._n = trames_par_phrase

    async def synthetiser(self, texte: str) -> AsyncIterator[bytes]:
        for _ in range(self._n):
            yield SILENCE


class CerveauBavard:
    async def repondre(self, texte: str) -> AsyncIterator[str]:
        for mot in "Voici une phrase. En voici une autre. Et une troisième.".split(" "):
            yield mot + " "
            await asyncio.sleep(0)


class DiffuseurEspion(Diffuseur):
    def __init__(self) -> None:
        super().__init__()
        self.etats: list[str] = []

    def publier(self, msg) -> None:
        if isinstance(msg, Etat):
            self.etats.append(msg.valeur)
        super().publier(msg)


class Banc:
    def __init__(
        self, hey_atlas: bool, trames_par_phrase: int, porte_dbfs: float, relance_s: float
    ) -> None:
        self.horloge = FausseHorloge()
        self.page_recoit = Envois()
        self.mot_cle = MotCleEspion()
        self.transcription = FausseTranscription()
        self.diffuseur = DiffuseurEspion()
        self.interruptions = 0

        def fabrique(envoyer_json, envoyer_binaire) -> Session:
            self.session = Session(
                envoyer_json=envoyer_json,
                envoyer_binaire=envoyer_binaire,
                transcription=self.transcription,
                synthese=FausseSynthese(trames_par_phrase),
                cerveau=CerveauBavard(),
                diffuseur=self.diffuseur,
            )
            sur_message = self.session.sur_message

            async def compter(msg) -> None:
                self.interruptions += isinstance(msg, Interruption)
                await sur_message(msg)

            self.session.sur_message = compter
            return self.session

        async def attendre(secondes: float) -> None:
            self.horloge.avancer(secondes)  # le haut-parleur joue pendant qu'on attend
            await asyncio.sleep(0)

        self.page = monter_page(
            self.page_recoit.json,
            self.page_recoit.binaire,
            fabrique,
            (DetecteurParContenu(), self.mot_cle),
            replace(REGLAGES, bargein_dbfs=porte_dbfs, relance_s=relance_s),
            marge_sortie_s=0.2,
            hey_atlas=hey_atlas,
            horloge=self.horloge,
            attendre=attendre,
        )

    @property
    def trames(self) -> list[bytes]:
        return [m for m in self.page_recoit.recus if isinstance(m, bytes)]

    @property
    def vidages(self) -> int:
        return sum(isinstance(m, Vider) for m in self.page_recoit.recus)

    async def dire(self, blocs: list[bytes]) -> None:
        for bloc in blocs:
            self.page.peripherique.recevoir(bloc)
            self.horloge.avancer(0.02)
            await _laisser_tourner()

    async def attendre_la_reponse(self, trames: int) -> None:
        await _attendre(
            lambda: len(self.trames) == trames,
            f"la page a reçu {len(self.trames)} trames sur {trames}",
        )


@contextlib.asynccontextmanager
async def _banc(
    hey_atlas: bool = False,
    trames_par_phrase: int = 50,
    porte_dbfs: float = -40.0,
    relance_s: float = 0.0,
):
    banc = Banc(hey_atlas, trames_par_phrase, porte_dbfs, relance_s)
    service = asyncio.create_task(banc.page.servir())
    try:
        yield banc
    finally:
        service.cancel()
        await asyncio.wait([service])
        await banc.session.fermer()


async def test_hey_atlas_puis_la_question_la_reponse_sort_de_la_page():
    async with _banc(hey_atlas=True) as banc:
        await banc.dire([SILENCE] + QUESTION)  # le mot de réveil se déclenche au 1er bloc
        await banc.attendre_la_reponse(3 * 50)
        assert banc.transcription.appels == 1
        # La page reçoit du son brut, 20 ms à 16 kHz, sans l'en-tête de /ws/audio.
        assert {len(t) for t in banc.trames} == {640}


async def test_interrupteur_eteint_la_page_ne_se_reveille_jamais_seule():
    async with _banc(hey_atlas=False) as banc:
        await banc.dire([SILENCE] + QUESTION)
        assert banc.mot_cle.examens == 0 and banc.transcription.appels == 0
        assert banc.trames == []


async def test_toucher_l_orbe_au_repos_ouvre_l_ecoute():
    async with _banc(hey_atlas=False) as banc:
        banc.page.client.demander_la_parole()
        await banc.dire(QUESTION)
        await banc.attendre_la_reponse(3 * 50)
        assert banc.transcription.appels == 1


async def test_une_question_tapee_repond_sur_la_page():
    async with _banc() as banc:
        await banc.session.sur_saisie("Raconte-moi quelque chose.")
        await banc.attendre_la_reponse(3 * 50)


async def test_toucher_l_orbe_coupe_atlas_meme_pendant_l_amorcage():
    async with _banc(hey_atlas=True) as banc:
        await banc.dire([SILENCE] + QUESTION)
        await banc.attendre_la_reponse(3 * 50)
        await banc.dire([PAROLE] * 20)  # l'annuleur s'installe : la voix ne coupe pas
        assert banc.vidages == 0 and banc.interruptions == 0
        banc.page.client.demander_la_parole()
        await banc.dire([PAROLE])
        # La page vide son son deux fois, comme le Mac : à la coupure, puis au StopAudio
        # de la session.
        assert banc.vidages >= 1 and banc.interruptions == 1
        assert banc.diffuseur.etats[-1] == "ecoute"


@pytest.mark.parametrize(("porte_dbfs", "coupe"), [(-40.0, True), (-10.0, False)])
async def test_la_voix_coupe_atlas_une_fois_passees_dix_secondes_de_sa_voix(porte_dbfs, coupe):
    # À -10 dBFS, la porte d'énergie de la page arrête une voix à -12 dBFS.
    async with _banc(hey_atlas=True, trames_par_phrase=200, porte_dbfs=porte_dbfs) as banc:
        await banc.dire([SILENCE] + QUESTION)
        # 12 s de voix, confiées à la page avec 5 s d'avance au plus : la dernière trame
        # partie, Atlas en est à 7 s de voix jouée.
        await banc.attendre_la_reponse(3 * 200)
        await banc.dire([PAROLE] * 20)  # à 7,4 s : l'annuleur s'installe encore
        assert banc.vidages == 0 and banc.interruptions == 0
        banc.horloge.avancer(2.8)  # à 10,2 s : Atlas parle toujours, l'amorçage est fini
        await banc.dire([PAROLE] * 20)
        assert banc.interruptions == (1 if coupe else 0)


async def test_apres_sa_reponse_la_page_ecoute_encore_sans_hey_atlas():
    async with _banc(hey_atlas=False, relance_s=10.0) as banc:
        banc.page.client.demander_la_parole()
        await banc.dire(QUESTION)
        await banc.attendre_la_reponse(3 * 50)
        await _laisser_tourner()
        banc.horloge.avancer(3.5)  # la réponse a fini de jouer sur la page
        await banc.dire(QUESTION)  # la question suivante, sans mot de réveil ni toucher
        await _attendre(lambda: banc.transcription.appels == 2, "la relance n'a rien entendu")
        assert banc.mot_cle.examens == 0


async def test_le_muet_d_une_page_coupe_la_voix_d_une_autre():
    async with _banc(hey_atlas=True) as banc:
        regie = Regie(Diffuseur(), lambda: None)
        regie.rattacher(banc.session, page="ipad")
        await banc.dire([SILENCE] + QUESTION)
        await banc.attendre_la_reponse(3 * 50)
        await regie.basculer_muet(True)  # touché sur l'iPhone
        await _laisser_tourner()
        assert banc.vidages == 1
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `uv run pytest tests/test_voix.py -q`
Expected: FAIL — erreur de collecte : `ImportError: cannot import name 'voix' from 'atlas_core'`.

- [ ] **Step 3: Écrire la voix d'une page**

Créer `src/atlas_core/voix.py` :

```python
"""La voix d'une page : le Core écoute pour elle.

Une page qui allume son micro n'est qu'un terminal audio : elle envoie ses blocs de micro
par /ws/voix et joue le son qui lui revient. Le Core fait tourner pour elle le client
audio du Mac (`ClientAudio`) — mot de réveil, détection de voix, fin de phrase, coupure de
parole, relance —, branché en mémoire à sa propre `Session`. Le client reçoit la session
exactement comme il reçoit le Core sur le Mac, par `servir_connexion`.
"""

from __future__ import annotations

import asyncio
import os
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from atlas_audio.client import ClientAudio, Reglages
from atlas_audio.connexion import servir_connexion
from atlas_audio.reveilleur import PredicteurOpenWakeWord, Reveilleur, ReveilleurMotCle
from atlas_audio.vad import CHEMIN_MODELE, DetecteurVoix, Endpointeur

from .protocole import decoder_audio_entrant
from .protocole_voix import Vider

# Spike S4 : l'annuleur d'écho d'un navigateur laisse passer l'écho le temps de
# s'installer (0,7 s sur iOS, 7 à 10 s dans Chrome sur macOS).
AMORCAGE_S = 10.0
# Au plus 5 s de micro en attente : si le Core prend du retard, les plus vieux blocs se
# perdent plutôt que de s'accumuler.
FILE_MAX_BLOCS = 250


def charger_modeles(seuil_reveil: float) -> tuple[DetecteurVoix, ReveilleurMotCle]:
    """Silero et « Hey Atlas », propres à une page (ils gardent un état). Près d'une
    seconde la première fois : le Core les charge hors de sa boucle."""
    if not os.path.isfile(CHEMIN_MODELE):
        raise FileNotFoundError(
            f"Modèle Silero introuvable sur la machine du Core : {CHEMIN_MODELE} "
            "(voir scripts/neo/LISEZMOI.md)."
        )
    mot_cle = ReveilleurMotCle(PredicteurOpenWakeWord(), seuil=seuil_reveil)
    return DetecteurVoix(chemin=CHEMIN_MODELE), mot_cle


class PeripheriqueNavigateur:
    """Le périphérique audio du client, quand c'est une page : le micro arrive par
    /ws/voix (`recevoir`), le son y repart (`jouer`, `vider`)."""

    def __init__(
        self,
        envoyer_json: Callable[[object], Awaitable[None]],
        envoyer_binaire: Callable[[bytes], Awaitable[None]],
    ) -> None:
        self._envoyer_json = envoyer_json
        self._envoyer_binaire = envoyer_binaire
        self._blocs: deque[bytes] = deque(maxlen=FILE_MAX_BLOCS)
        self._arrivee = asyncio.Event()

    def recevoir(self, bloc: bytes) -> None:
        self._blocs.append(bloc)
        self._arrivee.set()

    async def lire_bloc(self) -> bytes:
        while not self._blocs:
            self._arrivee.clear()
            await self._arrivee.wait()
        return self._blocs.popleft()

    async def jouer(self, pcm: bytes) -> None:
        await self._envoyer_binaire(pcm)

    async def vider(self) -> None:
        await self._envoyer_json(Vider())


class ReveilleurPage:
    """« Hey Atlas » pour une page, si son interrupteur est allumé. Toucher l'orbe ne
    passe pas par ici, mais par `ClientAudio.demander_la_parole`."""

    def __init__(self, mot_cle: Reveilleur, actif: bool) -> None:
        self._mot_cle = mot_cle
        self.actif = actif

    def examiner(self, bloc: bytes) -> bool:
        return self.actif and self._mot_cle.examiner(bloc)


class TransportSession:
    """Ce que le client de la page envoie « au Core » arrive directement dans sa session."""

    def __init__(self, session) -> None:
        self._session = session

    async def envoyer_json(self, msg) -> None:
        await self._session.sur_message(msg)

    async def envoyer_binaire(self, trame: bytes) -> None:
        await self._session.sur_audio(decoder_audio_entrant(trame))


class FluxSession:
    """Ce que la session envoie à son client, en file, lu comme le flux d'une WebSocket :
    `servir_connexion` en garde l'ordre, et fait passer `StopAudio` devant."""

    def __init__(self) -> None:
        self._file: asyncio.Queue[str | bytes] = asyncio.Queue()

    async def envoyer_json(self, msg) -> None:
        self._file.put_nowait(msg.model_dump_json())

    async def envoyer_binaire(self, trame: bytes) -> None:
        self._file.put_nowait(trame)

    def __aiter__(self) -> FluxSession:
        return self

    async def __anext__(self) -> str | bytes:
        return await self._file.get()


@dataclass
class PageVoix:
    peripherique: PeripheriqueNavigateur
    reveilleur: ReveilleurPage
    client: ClientAudio
    session: object
    flux: FluxSession

    async def servir(self) -> None:
        """Fait tourner le client de la page jusqu'à ce qu'on l'annule."""
        await servir_connexion(self.flux, self.client)


def monter_page(
    envoyer_json: Callable[[object], Awaitable[None]],
    envoyer_binaire: Callable[[bytes], Awaitable[None]],
    fabrique_session: Callable[..., object],
    modeles: tuple[object, Reveilleur],
    reglages: Reglages,
    marge_sortie_s: float,
    hey_atlas: bool,
    horloge: Callable[[], float] | None = None,
    attendre: Callable[[float], Awaitable[None]] | None = None,
) -> PageVoix:
    """Le client audio d'une page et sa session. `envoyer_json` et `envoyer_binaire`
    parlent à la page ; `fabrique_session` reçoit les deux fonctions par lesquelles la
    session parle à son client."""
    detecteur, mot_cle = modeles
    flux = FluxSession()
    session = fabrique_session(flux.envoyer_json, flux.envoyer_binaire)
    peripherique = PeripheriqueNavigateur(envoyer_json, envoyer_binaire)
    reveilleur = ReveilleurPage(mot_cle, hey_atlas)
    client = ClientAudio(
        transport=TransportSession(session),
        peripherique=peripherique,
        detecteur=detecteur,
        endpointeur=Endpointeur(silence_ms=reglages.silence_ms),
        reveilleur=reveilleur,
        bargein=Endpointeur(parole_min_ms=reglages.bargein_ms),
        horloge=horloge,
        seuil_bargein_dbfs=reglages.bargein_dbfs,
        relance_s=reglages.relance_s,
        attendre=attendre,
        marge_sortie_s=marge_sortie_s,
        amorcage_s=AMORCAGE_S,
    )
    return PageVoix(peripherique, reveilleur, client, session, flux)
```

- [ ] **Step 4: Vérifier que tout passe**

Run: `uv run pytest -q && uv run ruff check . && uv run ruff format --check . && node --test "tests/web/*.test.mjs"`
Expected: 630 tests Python passent, 72 tests JavaScript passent, ruff ne dit rien.

- [ ] **Step 5: Commit**

```bash
git add src/atlas_core/voix.py tests/test_voix.py
git commit -F - <<'MSG'
Voix des pages côté Core : périphérique navigateur, réveilleur, montage

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

### Task 5: La route `/ws/voix` et les réglages du navigateur

Les deux réglages du navigateur, la route `/ws/voix` (sur le modèle de `/ws/web`, dont l'entrée est mise en commun),
et l'identifiant de page transmis avec les questions tapées de `/ws/web`.

**Files:**
- Modify: `src/atlas_core/config.py`
- Modify: `src/atlas_core/hub.py`
- Modify: `tests/test_config.py`
- Create: `tests/test_hub_voix.py`
- Modify: `tests/test_hub_web.py`

**Interfaces:**
- Consumes: Task 2 (`AuthentificationVoix`, `Parler`, `HeyAtlas`, `Reprise`, `Pret`, `decoder_message_voix`,
  `verifier_bloc_page`, `Authentification.page`) ; Task 3 (`Regie.rattacher(session, page)`, `saisie(texte, page)`,
  `RegieEspionne`, qui note ici aussi `rattachees` et `detachees`) ; Task 4 (`charger_modeles`, `monter_page`,
  `PageVoix`) ; `atlas_audio.client.lire_reglages`,
  `atlas_audio.connexion.PeripheriqueEnPanne`.
- Produces: `Config.voix_marge_s: float = 0.2` (`ATLAS_VOIX_MARGE_S`, de 0 à 2) et
  `Config.voix_bargein_dbfs: float = -40.0` (`ATLAS_VOIX_BARGEIN_DBFS`, de −120 à 0) ; une valeur invalide lève
  `ValueError` qui nomme la variable. `hub` : la route `/ws/voix` ; `FERMETURE_PANNE = 1011` ; `hub.charger_modeles`
  et `hub.monter_page` importés par nom (les tests les remplacent) ; `hub._reglages = lire_reglages()` ;
  `_ouvrir_page(ws)` et `_page_authentifiee(ws, decoder, attendu)`, communs à `/ws/web` et `/ws/voix`.

- [ ] **Step 1: Écrire les tests qui échouent**

Modifier `tests/test_config.py` :

```diff
--- a/tests/test_config.py
+++ b/tests/test_config.py
@@ -58,3 +58,36 @@ def test_la_cle_audio_vient_de_l_environnement(monkeypatch):
 def test_sans_cle_audio_la_valeur_est_vide(monkeypatch):
     monkeypatch.delenv("ATLAS_AUDIO_CLE", raising=False)
     assert Config.depuis_environnement().audio_cle == ""
+
+
+def test_les_reglages_de_la_voix_des_pages_ont_les_valeurs_du_spike(monkeypatch):
+    monkeypatch.delenv("ATLAS_VOIX_MARGE_S", raising=False)
+    monkeypatch.delenv("ATLAS_VOIX_BARGEIN_DBFS", raising=False)
+    config = Config.depuis_environnement()
+    assert config.voix_marge_s == 0.2 and config.voix_bargein_dbfs == -40.0
+
+
+def test_les_reglages_de_la_voix_des_pages_viennent_de_l_environnement(monkeypatch):
+    monkeypatch.setenv("ATLAS_VOIX_MARGE_S", "0.35")
+    monkeypatch.setenv("ATLAS_VOIX_BARGEIN_DBFS", "-45.5")
+    config = Config.depuis_environnement()
+    assert config.voix_marge_s == 0.35 and config.voix_bargein_dbfs == -45.5
+
+
+@pytest.mark.parametrize(
+    ("nom", "brute"),
+    [
+        ("ATLAS_VOIX_MARGE_S", "vite"),
+        ("ATLAS_VOIX_MARGE_S", "-0.1"),
+        ("ATLAS_VOIX_MARGE_S", "3"),
+        ("ATLAS_VOIX_MARGE_S", "nan"),
+        ("ATLAS_VOIX_BARGEIN_DBFS", "fort"),
+        ("ATLAS_VOIX_BARGEIN_DBFS", "5"),
+        ("ATLAS_VOIX_BARGEIN_DBFS", "-200"),
+        ("ATLAS_VOIX_BARGEIN_DBFS", "-inf"),
+    ],
+)
+def test_un_reglage_de_la_voix_des_pages_invalide_est_refuse(monkeypatch, nom, brute):
+    monkeypatch.setenv(nom, brute)
+    with pytest.raises(ValueError, match=nom):
+        Config.depuis_environnement()
```

Créer `tests/test_hub_voix.py` :

```python
"""La route /ws/voix : l'entrée d'une page, et ce qu'elle transmet au client audio que le
Core fait tourner pour elle (remplacé ici par un espion)."""

import asyncio
from dataclasses import replace
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from test_hub_web import RegieEspionne

from atlas_audio.connexion import PeripheriqueEnPanne
from atlas_core import hub

ORIGINE = {"origin": "http://testserver"}
CLE = "cle-de-test"
BLOC = b"\x01" * 640


class PageEspionne:
    def __init__(self, fabrique_session, modeles, reglages, marge_sortie_s, hey_atlas, panne):
        self.fabrique_session = fabrique_session
        self.modeles = modeles
        self.reglages = reglages
        self.marge_sortie_s = marge_sortie_s
        self.blocs: list[bytes] = []
        self.peripherique = SimpleNamespace(recevoir=self.blocs.append)
        self.reveilleur = SimpleNamespace(actif=hey_atlas)
        self.paroles = 0
        self.reprises = 0
        self.client = SimpleNamespace(demander_la_parole=self._parler, reamorcer=self._reprendre)
        self.session = SimpleNamespace(fermee=False, fermer=self._fermer)
        self.servie_jusqu_au_bout = False
        self._panne = panne

    def _parler(self) -> None:
        self.paroles += 1

    def _reprendre(self) -> None:
        self.reprises += 1

    async def _fermer(self) -> None:
        self.session.fermee = True

    async def servir(self) -> None:
        if self._panne:
            raise self._panne
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.servie_jusqu_au_bout = True
            raise


@pytest.fixture
def banc(monkeypatch):
    banc = SimpleNamespace(regie=RegieEspionne(), pages=[], panne=None)

    def monter(envoyer_json, envoyer_binaire, fabrique, modeles, reglages, marge, hey_atlas):
        banc.pages.append(PageEspionne(fabrique, modeles, reglages, marge, hey_atlas, banc.panne))
        return banc.pages[-1]

    monkeypatch.setattr(hub, "_regie", banc.regie)
    config = replace(hub._config, web_cle=CLE, voix_marge_s=0.3, voix_bargein_dbfs=-33.0)
    monkeypatch.setattr(hub, "_config", config)
    monkeypatch.setattr(hub, "charger_modeles", lambda seuil: ("detecteur", "mot-cle"))
    monkeypatch.setattr(hub, "monter_page", monter)
    return banc


def _entrer(ws, hey_atlas: bool = True) -> None:
    ws.send_json({"type": "authentification", "cle": CLE, "page": "ipad", "hey_atlas": hey_atlas})
    assert ws.receive_json() == {"type": "pret"}


def test_une_page_entre_avec_les_reglages_du_navigateur(banc):
    with TestClient(hub.app) as client, client.websocket_connect("/ws/voix", headers=ORIGINE) as ws:
        _entrer(ws, hey_atlas=False)
        [page] = banc.pages
        assert page.modeles == ("detecteur", "mot-cle")
        assert page.fabrique_session is hub.creer_session
        assert page.marge_sortie_s == 0.3 and page.reglages.bargein_dbfs == -33.0
        assert page.reveilleur.actif is False
        assert banc.regie.rattachees == [("ipad", page.session)]


def test_les_messages_de_la_page_arrivent_a_son_client(banc):
    with TestClient(hub.app) as client, client.websocket_connect("/ws/voix", headers=ORIGINE) as ws:
        _entrer(ws)
        ws.send_bytes(BLOC)
        ws.send_json({"type": "parler"})
        ws.send_json({"type": "hey_atlas", "actif": False})
        ws.send_json({"type": "reprise"})
        ws.send_bytes(BLOC)
        ws.send_json({"type": "nimporte_quoi"})  # sa réponse prouve que tout est traité
        assert ws.receive_json()["code"] == "message_invalide"
    [page] = banc.pages
    assert page.blocs == [BLOC, BLOC]
    assert page.paroles == 1 and page.reprises == 1 and page.reveilleur.actif is False


def test_un_bloc_de_la_mauvaise_taille_est_signale_et_jete(banc):
    with TestClient(hub.app) as client, client.websocket_connect("/ws/voix", headers=ORIGINE) as ws:
        _entrer(ws)
        ws.send_bytes(BLOC[:-1])
        ws.send_json({"type": "nimporte_quoi"})  # répond à coup sûr : le test ne bloque jamais
        erreur = ws.receive_json()
    assert erreur["code"] == "trame_invalide" and "attendu 640" in erreur["message"]
    assert banc.pages[0].blocs == []


def test_quand_la_page_part_sa_session_est_fermee_et_detachee(banc):
    with TestClient(hub.app) as client, client.websocket_connect("/ws/voix", headers=ORIGINE) as ws:
        _entrer(ws)
        ws.close()
    [page] = banc.pages
    assert page.servie_jusqu_au_bout and page.session.fermee
    assert banc.regie.detachees == [page.session]


def test_si_la_voix_de_la_page_tombe_en_panne_la_connexion_se_ferme(banc, caplog):
    banc.panne = RuntimeError("le détecteur de voix a planté")
    with TestClient(hub.app) as client, client.websocket_connect("/ws/voix", headers=ORIGINE) as ws:
        _entrer(ws)
        ws.send_bytes(BLOC)
        with pytest.raises(WebSocketDisconnect) as fermeture:
            ws.receive_json()
    assert fermeture.value.code == hub.FERMETURE_PANNE
    [page] = banc.pages
    assert page.session.fermee and banc.regie.detachees == [page.session]
    assert "le détecteur de voix a planté" in caplog.text


def test_une_page_partie_pendant_qu_atlas_lui_parle_ne_laisse_aucune_erreur(banc, caplog):
    # Le son envoyé à une page déjà partie échoue avant que sa déconnexion n'arrive.
    banc.panne = PeripheriqueEnPanne("le périphérique audio est mort")
    with TestClient(hub.app) as client, client.websocket_connect("/ws/voix", headers=ORIGINE) as ws:
        _entrer(ws)
        ws.close()
    [page] = banc.pages
    assert page.session.fermee and banc.regie.detachees == [page.session]
    assert not [r for r in caplog.records if r.levelname == "ERROR"]


def test_sans_les_modeles_sur_la_machine_du_core_la_page_est_prevenue(banc, monkeypatch):
    def absents(seuil):
        raise FileNotFoundError("Modèle Silero introuvable sur la machine du Core")

    monkeypatch.setattr(hub, "charger_modeles", absents)
    with TestClient(hub.app) as client, client.websocket_connect("/ws/voix", headers=ORIGINE) as ws:
        ws.send_json({"type": "authentification", "cle": CLE, "page": "ipad"})
        erreur = ws.receive_json()
        with pytest.raises(WebSocketDisconnect) as fermeture:
            ws.receive_json()
    assert erreur["code"] == "modeles_absents" and "Silero" in erreur["message"]
    assert fermeture.value.code == hub.FERMETURE_CLE_ABSENTE
    assert banc.pages == [] and banc.regie.rattachees == []


@pytest.mark.parametrize(
    "entree",
    [
        {"type": "authentification", "cle": "pas-la-bonne", "page": "ipad"},
        {"type": "authentification", "cle": CLE},  # l'entrée de /ws/web, sans page
        {"type": "authentification", "cle": CLE, "page": "../ipad"},
        {"type": "parler"},
    ],
)
def test_une_entree_refusee_ferme_la_connexion_sans_rien_monter(banc, entree):
    with TestClient(hub.app) as client, client.websocket_connect("/ws/voix", headers=ORIGINE) as ws:
        ws.send_json(entree)
        with pytest.raises(WebSocketDisconnect) as fermeture:
            ws.receive_json()
    assert fermeture.value.code == hub.FERMETURE_NON_AUTORISE
    assert banc.pages == []


def test_sans_authentification_a_temps_la_connexion_se_ferme(banc, monkeypatch):
    monkeypatch.setattr(hub, "DELAI_AUTHENTIFICATION_S", 0.05)
    with TestClient(hub.app) as client, client.websocket_connect("/ws/voix", headers=ORIGINE) as ws:
        with pytest.raises(WebSocketDisconnect) as fermeture:
            ws.receive_json()
    assert fermeture.value.code == hub.FERMETURE_NON_AUTORISE


def test_sans_cle_configuree_la_page_est_prevenue(banc, monkeypatch):
    monkeypatch.setattr(hub, "_config", replace(hub._config, web_cle=""))
    with TestClient(hub.app) as client, client.websocket_connect("/ws/voix", headers=ORIGINE) as ws:
        erreur = ws.receive_json()
        with pytest.raises(WebSocketDisconnect) as fermeture:
            ws.receive_json()
    assert erreur["code"] == "cle_absente"
    assert fermeture.value.code == hub.FERMETURE_CLE_ABSENTE


def test_une_autre_origine_est_refusee_avant_meme_d_accepter(banc):
    with TestClient(hub.app) as client:
        with pytest.raises(WebSocketDisconnect) as fermeture:
            with client.websocket_connect(
                "/ws/voix", headers={"origin": "http://ailleurs.example"}
            ):
                pass
    assert fermeture.value.code == hub.FERMETURE_ORIGINE
```

Modifier `tests/test_hub_web.py` :

```diff
--- a/tests/test_hub_web.py
+++ b/tests/test_hub_web.py
@@ -18,15 +18,17 @@ class RegieEspionne:
         self.saisies: list[str] = []
         self.muets: list[bool] = []
         self.pages: list[str | None] = []
+        self.rattachees: list[tuple[str | None, object]] = []
+        self.detachees: list = []
 
     def voix_active(self) -> bool:
         return True
 
     def rattacher(self, session, page: str | None = None) -> None:
-        pass
+        self.rattachees.append((page, session))
 
     def detacher(self, session) -> None:
-        pass
+        self.detachees.append(session)
 
     async def saisie(self, texte: str, page: str | None = None) -> None:
         self.saisies.append(texte)
@@ -66,6 +68,18 @@ def test_saisie_et_muet_arrivent_a_la_regie(regie):
     assert regie.saisies == ["quelle heure est-il"] and regie.muets == [True]
 
 
+@pytest.mark.parametrize("page", [None, "ipad-1"])
+def test_une_question_tapee_porte_l_identifiant_de_sa_page(regie, page):
+    entree = {"type": "authentification", "cle": CLE} | ({"page": page} if page else {})
+    with TestClient(hub.app) as client, client.websocket_connect("/ws/web", headers=ORIGINE) as ws:
+        ws.send_json(entree)
+        [ws.receive_json() for _ in range(3)]
+        ws.send_json({"type": "saisie", "texte": "quelle heure est-il"})
+        ws.send_json({"type": "saisie", "texte": ""})  # sa réponse prouve que tout est traité
+        ws.receive_json()
+    assert regie.saisies == ["quelle heure est-il"] and regie.pages == [page]
+
+
 def test_une_mauvaise_cle_ferme_la_connexion(regie):
     with TestClient(hub.app) as client, client.websocket_connect("/ws/web", headers=ORIGINE) as ws:
         ws.send_json({"type": "authentification", "cle": "pas-la-bonne"})
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `uv run pytest tests/test_config.py tests/test_hub_voix.py tests/test_hub_web.py -q`
Expected: FAIL — 11 échecs et 14 erreurs : `AttributeError: 'Config' object has no attribute 'voix_marge_s'`,
`DID NOT RAISE ValueError` pour les valeurs invalides, `TypeError: Config.__init__() got an unexpected keyword
argument 'voix_marge_s'` dans la fixture de `test_hub_voix.py`, et une question tapée qui arrive sans sa page
dans `test_hub_web.py`.

- [ ] **Step 3: Écrire les réglages et la route**

Modifier `src/atlas_core/config.py` :

```diff
--- a/src/atlas_core/config.py
+++ b/src/atlas_core/config.py
@@ -25,6 +25,10 @@ class Config:
     cerveau_modele: str = MODELE_PAR_DEFAUT
     cerveau_oubli_min: float = 30.0  # au-delà, sans échange, la conversation repart de zéro
     audio_cle: str = ""  # vide : /ws/audio refuse tout client audio
+    # La voix des pages (spike S4) : la latence de sortie d'un navigateur, et la porte
+    # d'énergie de la coupure à la voix, l'écho résiduel n'étant pas celui du Mac.
+    voix_marge_s: float = 0.2
+    voix_bargein_dbfs: float = -40.0
 
     @staticmethod
     def depuis_environnement() -> Config:
@@ -38,6 +42,8 @@ class Config:
             cerveau_modele=os.environ.get("ATLAS_CERVEAU_MODELE", "").strip() or MODELE_PAR_DEFAUT,
             cerveau_oubli_min=_lire_oubli_min(),
             audio_cle=os.environ.get("ATLAS_AUDIO_CLE", "").strip(),
+            voix_marge_s=_lire_nombre("ATLAS_VOIX_MARGE_S", "0.2", 0.0, 2.0),
+            voix_bargein_dbfs=_lire_nombre("ATLAS_VOIX_BARGEIN_DBFS", "-40", -120.0, 0.0),
         )
 
 
@@ -62,3 +68,14 @@ def _lire_oubli_min() -> float:
             f"ATLAS_CERVEAU_OUBLI_MIN invalide : {brute!r} doit être un nombre de minutes positif"
         )
     return valeur
+
+
+def _lire_nombre(nom: str, defaut: str, mini: float, maxi: float) -> float:
+    brute = os.environ.get(nom, defaut)
+    try:
+        valeur = float(brute)
+    except ValueError as erreur:
+        raise ValueError(f"{nom} invalide : {brute!r} n'est pas un nombre") from erreur
+    if not math.isfinite(valeur) or not (mini <= valeur <= maxi):
+        raise ValueError(f"{nom} invalide : {brute!r} doit être entre {mini:g} et {maxi:g}")
+    return valeur
```

Modifier `src/atlas_core/hub.py` :

```diff
--- a/src/atlas_core/hub.py
+++ b/src/atlas_core/hub.py
@@ -1,4 +1,5 @@
-"""Serveur du Core : route de santé, WebSocket audio, WebSocket et page web."""
+"""Serveur du Core : route de santé, WebSocket audio, WebSocket et page web, et la voix
+des pages."""
 
 from __future__ import annotations
 
@@ -6,6 +7,7 @@ import asyncio
 import logging
 import os
 from contextlib import asynccontextmanager
+from dataclasses import replace
 from pathlib import Path
 
 import httpx
@@ -13,20 +15,35 @@ from claude_agent_sdk import ClaudeSDKClient
 from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
 from fastapi.staticfiles import StaticFiles
 
+from atlas_audio.client import lire_reglages
+from atlas_audio.connexion import PeripheriqueEnPanne
+
 from .cerveau import Cerveau, CerveauBouchon
 from .cerveau_claude import CerveauClaude, options_cerveau, purger_cles_api
 from .config import Config
 from .diffuseur import Diffuseur
 from .protocole import Bonjour, Erreur, decoder_audio_entrant, decoder_message
+from .protocole_voix import (
+    AuthentificationVoix,
+    HeyAtlas,
+    Parler,
+    Pret,
+    Reprise,
+    decoder_message_voix,
+    verifier_bloc_page,
+)
 from .protocole_web import Authentification, Muet, Saisie, decoder_message_page
 from .regie import Regie
 from .session import Session, sans_destinataire
 from .synthese import ClientSynthese
 from .transcription import ClientTranscription
+from .voix import charger_modeles, monter_page
 from .web import cle_valide, origine_autorisee, politique_securite
 
 _journal = logging.getLogger(__name__)
 _config = Config.depuis_environnement()
+# Les réglages du client audio du Mac, que le Core applique aussi aux pages.
+_reglages = lire_reglages()
 _http: httpx.AsyncClient | None = None
 _cerveau: Cerveau | None = None
 
@@ -37,6 +54,7 @@ DELAI_AUTHENTIFICATION_S = 5.0
 FERMETURE_CLE_ABSENTE = 4000
 FERMETURE_NON_AUTORISE = 4401
 FERMETURE_ORIGINE = 1008  # « policy violation », avant même d'accepter la connexion
+FERMETURE_PANNE = 1011  # « internal error » : la voix d'une page s'est arrêtée, elle se rebranche
 
 
 def creer_cerveau(config: Config) -> Cerveau:
@@ -204,11 +222,12 @@ async def _client_audio_authentifie(ws: WebSocket) -> bool | None:
     return isinstance(bonjour, Bonjour) and cle_valide(bonjour.cle, _config.audio_cle)
 
 
-@app.websocket("/ws/web")
-async def ws_web(ws: WebSocket) -> None:
+async def _ouvrir_page(ws: WebSocket) -> bool:
+    """Accepte la connexion d'une page de la bonne origine, si la clé des pages est
+    configurée ; sinon la ferme et rend False."""
     if not origine_autorisee(ws.headers.get("origin"), ws.headers.get("host")):
         await ws.close(code=FERMETURE_ORIGINE)
-        return
+        return False
     await ws.accept()
     if not _config.web_cle:
         message = (
@@ -217,20 +236,35 @@ async def ws_web(ws: WebSocket) -> None:
         )
         await ws.send_text(Erreur(code="cle_absente", message=message).model_dump_json())
         await ws.close(code=FERMETURE_CLE_ABSENTE)
-        return
+        return False
+    return True
+
 
+async def _page_authentifiee(ws: WebSocket, decoder, attendu: type):
+    """Le premier message de la page s'il arrive à temps, du type attendu, avec la clé
+    des pages ; sinon la connexion est fermée (4401) et None est rendu."""
     try:
         premier = await asyncio.wait_for(_recevoir_texte(ws), DELAI_AUTHENTIFICATION_S)
     except TimeoutError:
         premier = ""
     if premier is None:
-        return  # la page est déjà partie
+        return None  # la page est déjà partie
     try:
-        demande = decoder_message_page(premier)
+        demande = decoder(premier)
     except ValueError:
         demande = None
-    if not isinstance(demande, Authentification) or not cle_valide(demande.cle, _config.web_cle):
+    if not isinstance(demande, attendu) or not cle_valide(demande.cle, _config.web_cle):
         await ws.close(code=FERMETURE_NON_AUTORISE)
+        return None
+    return demande
+
+
+@app.websocket("/ws/web")
+async def ws_web(ws: WebSocket) -> None:
+    if not await _ouvrir_page(ws):
+        return
+    demande = await _page_authentifiee(ws, decoder_message_page, Authentification)
+    if demande is None:
         return
 
     async def envoyer(msg) -> None:
@@ -245,7 +279,7 @@ async def ws_web(ws: WebSocket) -> None:
                 abonnement.envoyer_prive(Erreur(code="message_invalide", message=str(e)))
                 continue
             if isinstance(msg, Saisie):
-                await _regie.saisie(msg.texte)
+                await _regie.saisie(msg.texte, demande.page)
             elif isinstance(msg, Muet):
                 await _regie.basculer_muet(msg.actif)
     except WebSocketDisconnect:
@@ -254,5 +288,80 @@ async def ws_web(ws: WebSocket) -> None:
         await abonnement.fermer()
 
 
+@app.websocket("/ws/voix")
+async def ws_voix(ws: WebSocket) -> None:
+    """La voix d'une page qui a allumé son micro : le Core écoute pour elle (voix.py)."""
+    if not await _ouvrir_page(ws):
+        return
+    demande = await _page_authentifiee(ws, decoder_message_voix, AuthentificationVoix)
+    if demande is None:
+        return
+
+    async def envoyer_json(msg) -> None:
+        await ws.send_text(msg.model_dump_json())
+
+    async def envoyer_binaire(pcm: bytes) -> None:
+        await ws.send_bytes(pcm)
+
+    try:
+        modeles = await asyncio.to_thread(charger_modeles, _reglages.seuil_reveil)
+    except FileNotFoundError as e:
+        await envoyer_json(Erreur(code="modeles_absents", message=str(e)))
+        await ws.close(code=FERMETURE_CLE_ABSENTE)
+        return
+    page = monter_page(
+        envoyer_json,
+        envoyer_binaire,
+        creer_session,
+        modeles,
+        replace(_reglages, bargein_dbfs=_config.voix_bargein_dbfs),
+        _config.voix_marge_s,
+        demande.hey_atlas,
+    )
+    await envoyer_json(Pret())
+    _regie.rattacher(page.session, demande.page)
+    service = asyncio.create_task(page.servir())
+    try:
+        while True:
+            if service.done():
+                # Le client de la page s'est arrêté. Une panne : la page se rebranche,
+                # plutôt que de parler dans le vide. Un envoi qui a échoué : elle est partie.
+                if not isinstance(service.exception(), PeripheriqueEnPanne):
+                    await ws.close(code=FERMETURE_PANNE)
+                break
+            recu = await ws.receive()
+            if recu["type"] == "websocket.disconnect":
+                break
+            if (binaire := recu.get("bytes")) is not None:
+                try:
+                    page.peripherique.recevoir(verifier_bloc_page(binaire))
+                except ValueError as e:
+                    await envoyer_json(Erreur(code="trame_invalide", message=str(e)))
+                continue
+            try:
+                msg = decoder_message_voix(recu.get("text") or "")
+            except ValueError as e:
+                await envoyer_json(Erreur(code="message_invalide", message=str(e)))
+                continue
+            if isinstance(msg, Parler):
+                page.client.demander_la_parole()
+            elif isinstance(msg, HeyAtlas):
+                page.reveilleur.actif = msg.actif
+            elif isinstance(msg, Reprise):
+                page.client.reamorcer()
+    except WebSocketDisconnect:
+        pass
+    finally:
+        service.cancel()
+        await asyncio.wait([service])
+        erreur = None if service.cancelled() else service.exception()
+        if isinstance(erreur, PeripheriqueEnPanne):
+            _journal.info("la page est partie pendant qu'Atlas lui parlait")
+        elif erreur is not None:
+            _journal.error("la voix d'une page s'est arrêtée", exc_info=erreur)
+        _regie.detacher(page.session)
+        await page.session.fermer()
+
+
 # Toujours en dernier : monté sur « / », il capterait sinon les routes déclarées après lui.
 app.mount("/", StaticFiles(directory=RACINE_WEB, html=True), name="web")
```

La garde `if not isinstance(service.exception(), PeripheriqueEnPanne)` devant la fermeture en `1011` ne sert que
dans une course qu'aucun test ne peut provoquer sans se bloquer (décision 9) : la garder telle quelle.

- [ ] **Step 4: Vérifier que tout passe**

Run: `uv run pytest -q && uv run ruff check . && uv run ruff format --check . && node --test "tests/web/*.test.mjs"`
Expected: 656 tests Python passent, 72 tests JavaScript passent, ruff ne dit rien.

- [ ] **Step 5: Commit**

```bash
git add src/atlas_core/config.py src/atlas_core/hub.py tests/test_config.py tests/test_hub_voix.py tests/test_hub_web.py
git commit -F - <<'MSG'
Route /ws/voix, réglages de la voix des pages, page des questions tapées

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

### Task 6: La connexion de la page, généralisée

`connexion.js` sert désormais aux deux connexions : l'authentification peut porter plus que la clé, le son reçu va à
son propre rappel, et la page peut envoyer du binaire. La page tire son identifiant à l'ouverture et l'annonce sur
`/ws/web`.

**Files:**
- Modify: `src/atlas_web/app.js`
- Modify: `src/atlas_web/connexion.js`
- Modify: `tests/web/app.test.mjs`
- Modify: `tests/web/connexion.test.mjs`

**Interfaces:**
- Consumes: Task 2 (le format de l'identifiant de page).
- Produces: `identifiantDePage(aleatoire = globalThis.crypto) -> string` (24 caractères hexadécimaux) ;
  `new Connexion({ url, lireCle, entree = () => ({}), surMessage, surBinaire = () => {}, surStatut,
  FabriqueWebSocket, planifier })` : `entree()` est relue à chaque connexion et fusionnée dans l'authentification ;
  `binaryType = "arraybuffer"` ; `surBinaire(donnees)` n'est appelé qu'en ligne ; `envoyerBinaire(donnees) ->
  boolean` (faux hors ligne). `app.js` : `const page = identifiantDePage()`, et `entree: () => ({ page })` pour
  `/ws/web`.

- [ ] **Step 1: Écrire les tests qui échouent**

Modifier `tests/web/app.test.mjs` :

```diff
--- a/tests/web/app.test.mjs
+++ b/tests/web/app.test.mjs
@@ -90,10 +90,11 @@ function fauxDocumentDeLaPage() {
 
 // Charge app.js dans un faux navigateur, avec un fond dont le dessin lève à chaque image.
 // Rend la file des rappels que le vrai navigateur aurait donnés à requestAnimationFrame.
-async function chargerPage() {
+async function chargerPage({ stockage = fauxStockage(), FabriqueWebSocket } = {}) {
   const file = [];
   globalThis.document = fauxDocumentDeLaPage();
-  globalThis.window = { localStorage: fauxStockage(), matchMedia: () => ({ matches: false }) };
+  globalThis.window = { localStorage: stockage, matchMedia: () => ({ matches: false }) };
+  globalThis.WebSocket = FabriqueWebSocket;
   globalThis.location = { protocol: "http:", host: "atlas.test" };
   globalThis.requestAnimationFrame = (rappel) => {
     file.push(rappel);
@@ -129,3 +130,24 @@ test("la boucle d'animation survit à un dessin qui lève, sans inonder la conso
     console.error = erreurOriginale;
   }
 });
+
+test("la page s'annonce sur /ws/web avec son identifiant", async () => {
+  const ouvertes = [];
+  class FauxWebSocket {
+    constructor(url) {
+      this.url = url;
+      this.envoyes = [];
+      ouvertes.push(this);
+    }
+
+    send(texte) {
+      this.envoyes.push(JSON.parse(texte));
+    }
+  }
+  await chargerPage({ stockage: fauxStockage({ "atlas.cle": "cle" }), FabriqueWebSocket: FauxWebSocket });
+  const [ws] = ouvertes;
+  assert.equal(ws.url, "ws://atlas.test/ws/web");
+  ws.onopen();
+  assert.equal(ws.envoyes[0].cle, "cle");
+  assert.match(ws.envoyes[0].page, /^[0-9a-f]{24}$/);
+});
```

Modifier `tests/web/connexion.test.mjs` :

```diff
--- a/tests/web/connexion.test.mjs
+++ b/tests/web/connexion.test.mjs
@@ -6,6 +6,7 @@ import {
   DELAIS_RECONNEXION_MS,
   FERMETURE_CLE_ABSENTE,
   FERMETURE_NON_AUTORISE,
+  identifiantDePage,
 } from "../../src/atlas_web/connexion.js";
 
 class FauxWebSocket {
@@ -19,8 +20,8 @@ class FauxWebSocket {
     FauxWebSocket.crees.push(this);
   }
 
-  send(texte) {
-    this.envoyes.push(JSON.parse(texte));
+  send(donnees) {
+    this.envoyes.push(typeof donnees === "string" ? JSON.parse(donnees) : donnees);
   }
 
   close() {
@@ -38,26 +39,33 @@ class FauxWebSocket {
     this.onmessage?.({ data: JSON.stringify(message) });
   }
 
+  recevoirBinaire(donnees) {
+    this.onmessage?.({ data: donnees });
+  }
+
   couper(code) {
     this.readyState = 3;
     this.onclose?.({ code });
   }
 }
 
-function monter({ cle = "cle" } = {}) {
+function monter({ cle = "cle", entree } = {}) {
   FauxWebSocket.crees = [];
   const statuts = [];
   const messages = [];
+  const binaires = [];
   const planifies = [];
   const connexion = new Connexion({
     url: "ws://atlas.local:8080/ws/web",
     lireCle: () => cle,
+    entree,
     surMessage: (message) => messages.push(message),
+    surBinaire: (donnees) => binaires.push(donnees),
     surStatut: (statut) => statuts.push(statut),
     FabriqueWebSocket: FauxWebSocket,
     planifier: (rappel, delai) => planifies.push({ rappel, delai }),
   });
-  return { connexion, statuts, messages, planifies, derniere: () => FauxWebSocket.crees.at(-1) };
+  return { connexion, statuts, messages, binaires, planifies, derniere: () => FauxWebSocket.crees.at(-1) };
 }
 
 test("la clé part dans le premier message, puis la page est en ligne", () => {
@@ -162,3 +170,51 @@ test("un message illisible est ignoré", () => {
   ws.onmessage({ data: "pas du json" });
   assert.deepEqual(m.messages, []);
 });
+
+test("l'entrée porte aussi ce que la page y ajoute, relu à chaque connexion", () => {
+  let heyAtlas = true;
+  const m = monter({ entree: () => ({ page: "p1", hey_atlas: heyAtlas }) });
+  m.connexion.demarrer();
+  m.derniere().ouvrir();
+  assert.deepEqual(m.derniere().envoyes, [{ type: "authentification", cle: "cle", page: "p1", hey_atlas: true }]);
+  heyAtlas = false;
+  m.derniere().couper(1006);
+  m.planifies.at(-1).rappel();
+  m.derniere().ouvrir();
+  assert.equal(m.derniere().envoyes[0].hey_atlas, false);
+});
+
+test("le son reçu va à surBinaire, une fois en ligne seulement", () => {
+  const m = monter();
+  m.connexion.demarrer();
+  const ws = m.derniere();
+  assert.equal(ws.binaryType, "arraybuffer");
+  ws.ouvrir();
+  const avant = new ArrayBuffer(640);
+  ws.recevoirBinaire(avant);
+  ws.recevoir({ type: "pret" });
+  const apres = new ArrayBuffer(640);
+  ws.recevoirBinaire(apres);
+  assert.deepEqual(m.binaires, [apres]);
+  assert.deepEqual(m.messages, [{ type: "pret" }]);
+});
+
+test("envoyerBinaire ne part qu'une fois en ligne", () => {
+  const m = monter();
+  m.connexion.demarrer();
+  const ws = m.derniere();
+  const bloc = new ArrayBuffer(640);
+  ws.ouvrir();
+  assert.equal(m.connexion.envoyerBinaire(bloc), false);
+  ws.recevoir({ type: "pret" });
+  assert.equal(m.connexion.envoyerBinaire(bloc), true);
+  assert.equal(ws.envoyes.at(-1), bloc);
+});
+
+test("l'identifiant de page est tiré au hasard, dans le format que le Core accepte", () => {
+  const a = identifiantDePage();
+  assert.match(a, /^[0-9a-f]{24}$/);
+  assert.notEqual(identifiantDePage(), a);
+  const fixe = { getRandomValues: (octets) => octets.fill(0xab) };
+  assert.equal(identifiantDePage(fixe), "ab".repeat(12));
+});
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `node --test tests/web/connexion.test.mjs tests/web/app.test.mjs`
Expected: FAIL — `SyntaxError: The requested module '../../src/atlas_web/connexion.js' does not provide an export
named 'identifiantDePage'`, et « la page s'annonce sur /ws/web avec son identifiant » échoue (pas de `page` dans
l'authentification).

- [ ] **Step 3: Écrire la connexion**

Modifier `src/atlas_web/app.js` :

```diff
--- a/src/atlas_web/app.js
+++ b/src/atlas_web/app.js
@@ -1,6 +1,6 @@
 // Le démarrage de la page : relie la connexion, l'état, l'orbe, le fond et les panneaux.
 
-import { Connexion } from "./connexion.js";
+import { Connexion, identifiantDePage } from "./connexion.js";
 import { dimensionner, rgba } from "./dessin.js";
 import { LIBELLES, appliquerMessage, avancer, creerEtat, sceneDe } from "./etat.js";
 import { fonds } from "./fonds/index.js";
@@ -34,6 +34,7 @@ try {
   stockage = null; // stockage interdit : les choix ne seront pas mémorisés, la page marche quand même
 }
 let cleEnMemoire = null;
+const page = identifiantDePage();
 
 const etat = creerEtat();
 let statut = "connexion";
@@ -49,6 +50,7 @@ const sousTitres = { conteneur: $("sous-titres"), question: $("st-question"), re
 const connexion = new Connexion({
   url: `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/web`,
   lireCle: () => cleEnMemoire ?? lireStockage(stockage, CLE_STOCKAGE),
+  entree: () => ({ page }),
   surMessage(message) {
     appliquerMessage(etat, message, Date.now());
     if (message.type === "muet") $("muet").checked = message.actif;
```

Modifier `src/atlas_web/connexion.js` :

```diff
--- a/src/atlas_web/connexion.js
+++ b/src/atlas_web/connexion.js
@@ -1,22 +1,33 @@
-// La connexion à /ws/web : authentification, messages, reconnexion espacée.
+// Une connexion au Core (/ws/web, /ws/voix) : authentification, messages, reconnexion espacée.
 
 export const DELAIS_RECONNEXION_MS = [1000, 2000, 4000, 8000, 16000, 30000];
 export const FERMETURE_CLE_ABSENTE = 4000;
 export const FERMETURE_NON_AUTORISE = 4401;
 const OUVERT = 1;
 
+// L'identifiant que la page tire à son ouverture, le même sur /ws/web et sur /ws/voix : une
+// question tapée trouve ainsi la voix de sa page.
+export function identifiantDePage(aleatoire = globalThis.crypto) {
+  const octets = aleatoire.getRandomValues(new Uint8Array(12));
+  return Array.from(octets, (octet) => octet.toString(16).padStart(2, "0")).join("");
+}
+
 export class Connexion {
   constructor({
     url,
     lireCle,
+    entree = () => ({}),
     surMessage,
+    surBinaire = () => {},
     surStatut,
     FabriqueWebSocket = globalThis.WebSocket,
     planifier = (rappel, delai) => setTimeout(rappel, delai),
   }) {
     this._url = url;
     this._lireCle = lireCle;
+    this._entree = entree;
     this._surMessage = surMessage;
+    this._surBinaire = surBinaire;
     this._surStatut = surStatut;
     this._Fabrique = FabriqueWebSocket;
     this._planifier = planifier;
@@ -44,6 +55,12 @@ export class Connexion {
     return true;
   }
 
+  envoyerBinaire(donnees) {
+    if (!this._ws || this._ws.readyState !== OUVERT || !this._enLigne) return false;
+    this._ws.send(donnees);
+    return true;
+  }
+
   _abandonner() {
     const ancienne = this._ws;
     this._ws = null;
@@ -66,8 +83,14 @@ export class Connexion {
     const ws = new this._Fabrique(this._url);
     this._ws = ws;
     this._enLigne = false;
-    ws.onopen = () => ws.send(JSON.stringify({ type: "authentification", cle }));
+    ws.binaryType = "arraybuffer";
+    // L'entrée est relue à chaque connexion : elle porte l'état du moment (« Hey Atlas »…).
+    ws.onopen = () => ws.send(JSON.stringify({ type: "authentification", cle, ...this._entree() }));
     ws.onmessage = (evenement) => {
+      if (typeof evenement.data !== "string") {
+        if (this._enLigne) this._surBinaire(evenement.data);
+        return;
+      }
       let message;
       try {
         message = JSON.parse(evenement.data);
```

- [ ] **Step 4: Vérifier que tout passe**

Run: `uv run pytest -q && uv run ruff check . && uv run ruff format --check . && node --test "tests/web/*.test.mjs"`
Expected: 656 tests Python passent, 77 tests JavaScript passent, ruff ne dit rien.

- [ ] **Step 5: Commit**

```bash
git add src/atlas_web/app.js src/atlas_web/connexion.js tests/web/app.test.mjs tests/web/connexion.test.mjs
git commit -F - <<'MSG'
Page : connexion généralisée et identifiant de page

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

### Task 7: Les processeurs audio de la page

Les deux processeurs validés par le spike S4, dont les calculs deviennent des classes pures testées dans Node :
`Decimateur` (le micro, de la fréquence du contexte à des blocs de 320 échantillons à 16 kHz, avec un passe-bas à
7,2 kHz) et `TamponLecture` (les trames du Core, jouées à la fréquence du contexte, vidables d'un coup).

**Files:**
- Create: `src/atlas_web/voix_worklet.js`
- Create: `tests/web/voix_worklet.test.mjs`

**Interfaces:**
- Consumes: rien.
- Produces: `voix_worklet.js` : `FREQUENCE_CORE = 16000`, `TAILLE_BLOC = 320`, `noyauPasseBas(taps, coupure)`,
  `new Decimateur(frequence).ajouter(Float32Array) -> Int16Array[]`, `new TamponLecture(frequence)` avec
  `ajouter(ArrayBuffer)`, `vider()`, `remplir(Float32Array) -> nombre d'échantillons joués`. Dans le navigateur, les
  processeurs `"capture-16k"` (poste l'`ArrayBuffer` de chaque bloc, transféré) et `"lecture-16k"` (reçoit un
  `ArrayBuffer` à jouer, ou la chaîne `"vider"`).

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/web/voix_worklet.test.mjs` :

```javascript
import assert from "node:assert/strict";
import { test } from "node:test";

import { Decimateur, TAILLE_BLOC, TamponLecture } from "../../src/atlas_web/voix_worklet.js";

// Une seconde de sinusoïde, découpée comme le navigateur la livre au processeur (128).
function sinusoide(frequence, hz, amplitude, secondes = 1) {
  const n = Math.round(frequence * secondes);
  const tout = Float32Array.from({ length: n }, (_, i) => amplitude * Math.sin((2 * Math.PI * hz * i) / frequence));
  const morceaux = [];
  for (let i = 0; i < n; i += 128) morceaux.push(tout.subarray(i, i + 128));
  return morceaux;
}

function decimer(frequence, morceaux) {
  const decimateur = new Decimateur(frequence);
  const blocs = morceaux.flatMap((morceau) => decimateur.ajouter(morceau));
  const tout = new Int16Array(blocs.length * TAILLE_BLOC);
  blocs.forEach((bloc, i) => tout.set(bloc, i * TAILLE_BLOC));
  return { blocs, tout };
}

const efficace = (x) => Math.sqrt(x.reduce((s, v) => s + v * v, 0) / x.length);
const passagesParZero = (x) => x.slice(1).filter((v, i) => (x[i] < 0) !== (v < 0)).length;

// 48 et 44,1 kHz d'ordinaire ; 24 et 16 kHz derrière certains casques Bluetooth.
for (const frequence of [48000, 44100, 24000, 16000]) {
  test(`à ${frequence} Hz, une voix à 1 kHz sort à 16 kHz, en blocs de 20 ms, intacte`, () => {
    const { blocs, tout } = decimer(frequence, sinusoide(frequence, 1000, 0.5));
    assert.ok(blocs.length >= 49 && blocs.length <= 50, `${blocs.length} blocs`);
    assert.ok(blocs.every((bloc) => bloc instanceof Int16Array && bloc.length === TAILLE_BLOC));
    const passages = passagesParZero(tout);
    assert.ok(Math.abs(passages - 2 * 1000 * (tout.length / 16000)) <= 4, `${passages} passages par zéro`);
    const attendu = (0.5 / Math.SQRT2) * 32767;
    assert.ok(Math.abs(efficace(tout.subarray(320)) / attendu - 1) < 0.02);
  });
}

test("les aigus au-dessus de 8 kHz ne se replient pas dans la voix", () => {
  const { tout } = decimer(48000, sinusoide(48000, 12000, 0.5));
  const attenuation = 20 * Math.log10(efficace(tout.subarray(320)) / ((0.5 / Math.SQRT2) * 32767));
  assert.ok(attenuation < -40, `${attenuation.toFixed(1)} dB`);
});

test("la capture oublie ce qu'elle a décimé", () => {
  const decimateur = new Decimateur(48000);
  for (const morceau of sinusoide(48000, 1000, 0.5, 2)) decimateur.ajouter(morceau);
  assert.ok(decimateur._entree.length < 200, `${decimateur._entree.length} gardés`);
});

test("un son trop fort est écrêté, jamais retourné", () => {
  const { tout } = decimer(48000, [new Float32Array(48000).fill(1.5)]);
  assert.equal(Math.min(...tout.subarray(320)), 32767);
});

function trame(valeur, n = TAILLE_BLOC) {
  return new Int16Array(n).fill(valeur).buffer;
}

for (const frequence of [48000, 44100, 24000, 16000]) {
  test(`à ${frequence} Hz, une trame de 20 ms se joue en 20 ms`, () => {
    const tampon = new TamponLecture(frequence);
    tampon.ajouter(trame(16384));
    let joues = 0;
    const sortie = new Float32Array(128);
    for (let i = 0; i < 10; i++) {
      joues += tampon.remplir(sortie);
      if (i === 0) assert.ok(sortie.every((v) => Math.abs(v - 0.5) < 1e-6));
    }
    // Le dernier échantillon attend le suivant pour s'interpoler.
    const pas = frequence / 16000;
    assert.ok(joues >= (TAILLE_BLOC - 1) * pas && joues <= TAILLE_BLOC * pas, `${joues} joués`);
  });
}

test("sans rien à jouer, la sortie est du silence", () => {
  const tampon = new TamponLecture(48000);
  const sortie = new Float32Array(128).fill(0.9);
  assert.equal(tampon.remplir(sortie), 0);
  assert.ok(sortie.every((v) => v === 0));
});

test("vider coupe le son d'un coup", () => {
  const tampon = new TamponLecture(48000);
  for (let i = 0; i < 50; i++) tampon.ajouter(trame(8000));
  const sortie = new Float32Array(128);
  assert.equal(tampon.remplir(sortie), 128);
  tampon.vider();
  assert.equal(tampon.remplir(sortie), 0);
  assert.ok(sortie.every((v) => v === 0));
  tampon.ajouter(trame(8000));
  assert.equal(tampon.remplir(sortie), 128);
});

test("la lecture oublie ce qu'elle a joué", () => {
  const tampon = new TamponLecture(48000);
  for (let i = 0; i < 100; i++) tampon.ajouter(trame(1000)); // 2 s de voix
  const sortie = new Float32Array(128);
  for (let i = 0; i < 300; i++) tampon.remplir(sortie); // 0,8 s jouées
  assert.ok(tampon._echantillons.length < 32000 - 12000, `${tampon._echantillons.length} gardés`);
});

test("le module se charge hors du navigateur sans déclarer de processeur", async () => {
  assert.equal(typeof globalThis.registerProcessor, "undefined");
  await import("../../src/atlas_web/voix_worklet.js");
});
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `node --test tests/web/voix_worklet.test.mjs`
Expected: FAIL — `Error [ERR_MODULE_NOT_FOUND]: Cannot find module '…/src/atlas_web/voix_worklet.js'`.

- [ ] **Step 3: Écrire les processeurs**

Créer `src/atlas_web/voix_worklet.js` :

```javascript
// Les deux processeurs AudioWorklet de la voix (validés par le spike S4) : la capture
// ramène le micro à 16 kHz mono, en blocs de 20 ms ; la lecture joue les trames 16 kHz du
// Core à la fréquence du contexte, et se vide d'un coup. Leurs calculs sont des classes
// pures, testées avec node --test ; les processeurs ne se déclarent que dans le navigateur.

export const FREQUENCE_CORE = 16000;
export const TAILLE_BLOC = 320; // 20 ms à 16 kHz

// Filtre passe-bas (sinus cardinal fenêtré) : coupe au-dessus de 7,2 kHz avant de décimer,
// pour que les aigus du micro ne se replient pas dans la bande de la voix.
export function noyauPasseBas(taps, coupure) {
  const h = new Float32Array(taps);
  const m = (taps - 1) / 2;
  let somme = 0;
  for (let i = 0; i < taps; i++) {
    const x = i - m;
    const sinc = x === 0 ? 2 * coupure : Math.sin(2 * Math.PI * coupure * x) / (Math.PI * x);
    const fenetre = 0.54 - 0.46 * Math.cos((2 * Math.PI * i) / (taps - 1));
    h[i] = sinc * fenetre;
    somme += h[i];
  }
  for (let i = 0; i < taps; i++) h[i] /= somme;
  return h;
}

// Le micro, de la fréquence du contexte (44,1 ou 48 kHz) à des blocs de 320 échantillons
// 16 bits à 16 kHz.
export class Decimateur {
  constructor(frequence) {
    this._pas = frequence / FREQUENCE_CORE;
    this._h = noyauPasseBas(63, 7200 / frequence);
    this._demi = (this._h.length - 1) / 2;
    this._entree = new Float32Array(0);
    this._origine = 0; // indice absolu de _entree[0]
    this._prochain = this._demi; // position absolue (fractionnaire) du prochain échantillon
    this._bloc = new Int16Array(TAILLE_BLOC);
    this._n = 0;
  }

  _filtrer(i) {
    let s = 0;
    const base = i - this._demi - this._origine;
    for (let k = 0; k < this._h.length; k++) s += this._h[k] * this._entree[base + k];
    return s;
  }

  // Ajoute des échantillons du micro ; rend les blocs complétés (Int16Array de 320).
  ajouter(echantillons) {
    const suite = new Float32Array(this._entree.length + echantillons.length);
    suite.set(this._entree);
    suite.set(echantillons, this._entree.length);
    this._entree = suite;
    const blocs = [];
    const fin = this._origine + this._entree.length;
    while (Math.floor(this._prochain) + 1 + this._demi < fin) {
      const i = Math.floor(this._prochain);
      const f = this._prochain - i;
      const v = (1 - f) * this._filtrer(i) + f * this._filtrer(i + 1);
      this._bloc[this._n++] = Math.max(-32768, Math.min(32767, Math.round(v * 32767)));
      if (this._n === TAILLE_BLOC) {
        blocs.push(this._bloc);
        this._bloc = new Int16Array(TAILLE_BLOC);
        this._n = 0;
      }
      this._prochain += this._pas;
    }
    const consommes = Math.floor(this._prochain) - this._demi - this._origine;
    if (consommes > 0) {
      this._entree = this._entree.slice(consommes);
      this._origine += consommes;
    }
    return blocs;
  }
}

// Le son du Core : des trames 16 bits à 16 kHz, jouées à la fréquence du contexte.
export class TamponLecture {
  constructor(frequence) {
    this._pas = FREQUENCE_CORE / frequence; // échantillons 16 kHz lus par échantillon joué
    this._echantillons = new Float32Array(0);
    this._position = 0;
  }

  ajouter(pcm) {
    const i16 = new Int16Array(pcm);
    const suite = new Float32Array(this._echantillons.length + i16.length);
    suite.set(this._echantillons);
    for (let k = 0; k < i16.length; k++) suite[this._echantillons.length + k] = i16[k] / 32768;
    this._echantillons = suite;
  }

  vider() {
    this._echantillons = new Float32Array(0);
    this._position = 0;
  }

  // Remplit la sortie ; du silence quand il n'y a plus rien à jouer. Rend le nombre
  // d'échantillons joués.
  remplir(sortie) {
    let ecrits = 0;
    for (let k = 0; k < sortie.length; k++) {
      const i = Math.floor(this._position);
      if (i + 1 >= this._echantillons.length) break;
      const f = this._position - i;
      sortie[k] = (1 - f) * this._echantillons[i] + f * this._echantillons[i + 1];
      this._position += this._pas;
      ecrits++;
    }
    sortie.fill(0, ecrits);
    const joues = Math.floor(this._position);
    if (joues > 4096) {
      // Ce qui est joué s'oublie : le tampon ne garde que ce qui reste à jouer.
      this._echantillons = this._echantillons.slice(joues);
      this._position -= joues;
    }
    return ecrits;
  }
}

if (typeof registerProcessor === "function") {
  class Capture16k extends AudioWorkletProcessor {
    constructor() {
      super();
      this.decimateur = new Decimateur(sampleRate);
    }

    process(inputs) {
      const canal = inputs[0]?.[0];
      if (canal) {
        for (const bloc of this.decimateur.ajouter(canal)) this.port.postMessage(bloc.buffer, [bloc.buffer]);
      }
      return true;
    }
  }

  class Lecture16k extends AudioWorkletProcessor {
    constructor() {
      super();
      this.tampon = new TamponLecture(sampleRate);
      this.port.onmessage = (e) => {
        if (e.data === "vider") this.tampon.vider();
        else this.tampon.ajouter(e.data);
      };
    }

    process(_entrees, sorties) {
      this.tampon.remplir(sorties[0][0]);
      return true;
    }
  }

  registerProcessor("capture-16k", Capture16k);
  registerProcessor("lecture-16k", Lecture16k);
}
```

- [ ] **Step 4: Vérifier que tout passe**

Run: `uv run pytest -q && uv run ruff check . && uv run ruff format --check . && node --test "tests/web/*.test.mjs"`
Expected: 656 tests Python passent, 92 tests JavaScript passent, ruff ne dit rien.

- [ ] **Step 5: Commit**

```bash
git add src/atlas_web/voix_worklet.js tests/web/voix_worklet.test.mjs
git commit -F - <<'MSG'
Page : processeurs AudioWorklet de capture et de lecture

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

### Task 8: La voix de la page

`voix.js` relie le micro et le haut-parleur à `/ws/voix` : ouverture au geste de l'utilisateur, envoi du micro une
fois la voix prête, lecture et vidage, `parler` et `hey_atlas`, reprise après une interruption d'iOS, micro coupé,
page non sécurisée, verrou d'écran. `ouvrirAudioNavigateur` est le seul morceau qui touche au vrai navigateur ; il
se teste avec un faux (`tests/web/faux_audio.mjs`, repris par la Task 9).

**Files:**
- Create: `src/atlas_web/voix.js`
- Create: `tests/web/faux_audio.mjs`
- Create: `tests/web/voix.test.mjs`

**Interfaces:**
- Consumes: Task 6 (`Connexion` avec `entree`, `surBinaire`, `envoyerBinaire`) ; Task 7 (les processeurs
  `"capture-16k"`, `"lecture-16k"` et leurs messages).
- Produces: `DELAI_REPRISE_MS = 1500` ; `new Voix({ url, lireCle, page, heyAtlas, surStatut, ouvrirAudio =
  ouvrirAudioNavigateur, verrou = new VerrouEcran(), FabriqueWebSocket, planifier })`, où `heyAtlas()` rend l'état
  de l'interrupteur ; `voix.allumee`, `voix.statut`, `voix.derniereErreur` ; `allumer()`, `eteindre()`,
  `toucherOrbe() -> boolean`, `changerHeyAtlas(actif)`, `surVisibilite(visible)`, `reactiver()`. Les statuts :
  `eteinte`, `ouverture`, `micro_refuse`, `https_requis`, `connexion`, `hors_ligne`, `cle_requise`, `cle_refusee`,
  `cle_absente`, `active`, `interrompue`, `a_reactiver`. `new VerrouEcran(navigateur)` : `demander()`, `relacher()`,
  `surVisible()`. `ouvrirAudioNavigateur({ surBloc, surEtat }, nav = globalThis)` rend `{ etat, jouer(pcm), vider(),
  reprendre(), fermer() }` ; `surEtat` reçoit les états du contexte audio, et `"micro_coupe"`. Dans les tests :
  `fauxNavigateurAudio({ micro, securisee }) -> { trace, nav }`.

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/web/faux_audio.mjs` :

```javascript
// Un navigateur audio minimal pour node --test : contexte, processeurs et micro, qui
// gardent trace de ce que la page leur demande.

export function fauxNavigateurAudio({ micro = "accorde", securisee = true } = {}) {
  const trace = { contraintes: null, modules: [], pistes: [], contextes: [], postes: [] };
  class Port {
    postMessage(message, transferts) {
      trace.postes.push({ message, transferts });
    }
  }
  class Noeud {
    constructor(contexte, nom, options) {
      this.nom = nom;
      this.options = options;
      this.port = new Port();
      this.gain = { value: 1 };
    }

    connect(cible) {
      return cible;
    }
  }
  class AudioContext {
    constructor() {
      this.state = "suspended";
      this.destination = new Noeud();
      this.fermee = false;
      this.audioWorklet = { addModule: async (url) => trace.modules.push(String(url)) };
      trace.contextes.push(this);
    }

    addEventListener() {}

    async resume() {
      this.state = "running";
    }

    close() {
      this.fermee = true;
    }

    createGain() {
      return new Noeud();
    }

    createMediaStreamSource() {
      return new Noeud();
    }
  }
  return {
    trace,
    nav: {
      isSecureContext: securisee,
      AudioContext,
      AudioWorkletNode: Noeud,
      navigator: {
        mediaDevices: {
          async getUserMedia(contraintes) {
            trace.contraintes = contraintes;
            if (micro === "refuse") throw Object.assign(new Error("non"), { name: "NotAllowedError" });
            const piste = fauxPiste();
            trace.pistes.push(piste);
            return { getTracks: () => [piste], getAudioTracks: () => [piste] };
          },
        },
      },
    },
  };
}

// Une piste de micro : `stop()` la termine sans prévenir (comme le navigateur) ;
// `terminer()` simule une fin venue d'ailleurs (un appel, un casque débranché).
function fauxPiste() {
  const ecouteurs = [];
  return {
    readyState: "live",
    stop() {
      this.readyState = "ended";
    },
    addEventListener(type, rappel) {
      if (type === "ended") ecouteurs.push(rappel);
    },
    terminer() {
      this.readyState = "ended";
      for (const rappel of ecouteurs) rappel();
    },
  };
}
```

Créer `tests/web/voix.test.mjs` :

```javascript
import assert from "node:assert/strict";
import { test } from "node:test";

import { DELAI_REPRISE_MS, VerrouEcran, Voix, ouvrirAudioNavigateur } from "../../src/atlas_web/voix.js";
import { fauxNavigateurAudio } from "./faux_audio.mjs";

class FauxWebSocket {
  static crees = [];

  constructor(url) {
    this.url = url;
    this.envoyes = [];
    this.readyState = 0;
    this.fermee = false;
    FauxWebSocket.crees.push(this);
  }

  send(donnees) {
    this.envoyes.push(typeof donnees === "string" ? JSON.parse(donnees) : donnees);
  }

  close() {
    this.fermee = true;
    this.readyState = 3;
  }

  ouvrir() {
    this.readyState = 1;
    this.onopen?.();
  }

  recevoir(message) {
    this.onmessage?.({ data: JSON.stringify(message) });
  }

  recevoirBinaire(donnees) {
    this.onmessage?.({ data: donnees });
  }

  couper(code) {
    this.readyState = 3;
    this.onclose?.({ code });
  }
}

class FauxAudio {
  constructor(rappels) {
    this.rappels = rappels;
    this.etat = "running";
    this.joues = [];
    this.vidages = 0;
    this.reprises = 0;
    this.fermee = false;
  }

  jouer(pcm) {
    this.joues.push(pcm);
  }

  vider() {
    this.vidages += 1;
  }

  async reprendre() {
    this.reprises += 1;
  }

  fermer() {
    this.fermee = true;
  }
}

class FauxVerrou {
  constructor() {
    this.appels = [];
  }

  demander() {
    this.appels.push("demander");
  }

  relacher() {
    this.appels.push("relacher");
  }

  surVisible() {
    this.appels.push("visible");
  }
}

function monter({ heyAtlas = true, ouvrirAudio } = {}) {
  FauxWebSocket.crees = [];
  const m = { statuts: [], planifies: [], audios: [], verrou: new FauxVerrou(), heyAtlas };
  m.voix = new Voix({
    url: "wss://atlas.example.com/ws/voix",
    lireCle: () => "cle",
    page: "p1",
    heyAtlas: () => m.heyAtlas,
    surStatut: (statut) => m.statuts.push(statut),
    ouvrirAudio:
      ouvrirAudio ??
      (async (rappels) => {
        m.audios.push(new FauxAudio(rappels));
        return m.audios.at(-1);
      }),
    verrou: m.verrou,
    FabriqueWebSocket: FauxWebSocket,
    planifier: (rappel, delai) => m.planifies.push({ rappel, delai }),
  });
  m.ws = () => FauxWebSocket.crees.at(-1);
  return m;
}

async function enLigne(m) {
  await m.voix.allumer();
  m.ws().ouvrir();
  m.ws().recevoir({ type: "pret" });
}

test("allumer ouvre le micro, puis /ws/voix avec la page et « Hey Atlas »", async () => {
  const m = monter({ heyAtlas: false });
  await m.voix.allumer();
  assert.equal(m.audios.length, 1);
  assert.equal(m.ws().url, "wss://atlas.example.com/ws/voix");
  m.ws().ouvrir();
  assert.deepEqual(m.ws().envoyes, [{ type: "authentification", cle: "cle", page: "p1", hey_atlas: false }]);
  m.ws().recevoir({ type: "pret" });
  assert.deepEqual(m.statuts, ["ouverture", "connexion", "active"]);
  assert.equal(m.voix.allumee, true);
});

test("un deuxième toucher pendant l'ouverture n'ouvre pas un deuxième micro", async () => {
  const m = monter();
  await Promise.all([m.voix.allumer(), m.voix.allumer()]);
  assert.equal(m.audios.length, 1);
  assert.equal(FauxWebSocket.crees.length, 1);
});

test("micro refusé : rien ne se connecte, et la page le dit", async () => {
  const refus = Object.assign(new Error("Permission refusée"), { name: "NotAllowedError" });
  const m = monter({ ouvrirAudio: async () => Promise.reject(refus) });
  await m.voix.allumer();
  assert.deepEqual(m.statuts, ["ouverture", "micro_refuse"]);
  assert.equal(FauxWebSocket.crees.length, 0);
  assert.equal(m.voix.allumee, false);
  assert.match(m.voix.derniereErreur, /NotAllowedError/);
});

test("éteint pendant l'ouverture, le micro à peine ouvert se referme", async () => {
  let ouvrir;
  const m = monter({ ouvrirAudio: () => new Promise((resoudre) => (ouvrir = resoudre)) });
  const allumage = m.voix.allumer();
  m.voix.eteindre();
  const audio = new FauxAudio({});
  ouvrir(audio);
  await allumage;
  assert.equal(audio.fermee, true);
  assert.equal(FauxWebSocket.crees.length, 0);
});

test("le micro ne part au Core qu'une fois la voix prête", async () => {
  const m = monter();
  await m.voix.allumer();
  const bloc = new ArrayBuffer(640);
  m.audios[0].rappels.surBloc(bloc);
  m.ws().ouvrir();
  m.audios[0].rappels.surBloc(bloc);
  m.ws().recevoir({ type: "pret" });
  m.audios[0].rappels.surBloc(bloc);
  assert.deepEqual(
    m.ws().envoyes.filter((envoi) => envoi instanceof ArrayBuffer),
    [bloc],
  );
});

test("le son du Core se joue, et « vider » le coupe net", async () => {
  const m = monter();
  await enLigne(m);
  const trame = new ArrayBuffer(640);
  m.ws().recevoirBinaire(trame);
  m.ws().recevoir({ type: "vider" });
  assert.deepEqual(m.audios[0].joues, [trame]);
  assert.equal(m.audios[0].vidages, 1);
});

test("toucher l'orbe et l'interrupteur « Hey Atlas » partent au Core", async () => {
  const m = monter();
  assert.equal(m.voix.toucherOrbe(), false); // éteinte : rien ne part
  await enLigne(m);
  assert.equal(m.voix.toucherOrbe(), true);
  m.voix.changerHeyAtlas(false);
  assert.deepEqual(m.ws().envoyes.slice(1), [{ type: "parler" }, { type: "hey_atlas", actif: false }]);
});

test("l'écran reste allumé tant que « Hey Atlas » écoute", async () => {
  const m = monter({ heyAtlas: true });
  m.voix.changerHeyAtlas(true); // micro éteint : l'écran peut s'éteindre
  assert.deepEqual(m.verrou.appels, ["relacher"]);
  m.verrou.appels = [];
  await enLigne(m);
  m.heyAtlas = false;
  m.voix.changerHeyAtlas(false);
  m.heyAtlas = true;
  m.voix.changerHeyAtlas(true);
  m.voix.eteindre();
  assert.deepEqual(m.verrou.appels, ["demander", "relacher", "demander", "relacher"]);
  const n = monter({ heyAtlas: false });
  await enLigne(n);
  assert.deepEqual(n.verrou.appels, []);
});

test("après une interruption d'iOS, la reprise du son est signalée au Core", async () => {
  const m = monter();
  await enLigne(m);
  const { surEtat } = m.audios[0].rappels;
  surEtat("running"); // pas d'interruption : rien à signaler
  surEtat("interrupted");
  assert.equal(m.voix.statut, "interrompue");
  surEtat("running");
  assert.equal(m.voix.statut, "active");
  assert.deepEqual(m.ws().envoyes.slice(1), [{ type: "reprise" }]);
});

test("rebranchée pendant une interruption, la voix reste en pause jusqu'à la reprise", async () => {
  const m = monter();
  await enLigne(m);
  m.audios[0].rappels.surEtat("interrupted");
  m.ws().couper(1006);
  m.planifies.at(-1).rappel();
  m.ws().ouvrir();
  m.ws().recevoir({ type: "pret" });
  assert.equal(m.voix.statut, "interrompue");
  m.audios[0].rappels.surEtat("running");
  assert.equal(m.voix.statut, "active");
  assert.deepEqual(m.ws().envoyes.at(-1), { type: "reprise" });
});

test("si le son ne repart pas au retour sur la page, un toucher le rouvre", async () => {
  const m = monter();
  await enLigne(m);
  m.audios[0].etat = "interrupted";
  m.voix.surVisibilite(true);
  assert.deepEqual(m.verrou.appels.at(-1), "visible");
  const { rappel, delai } = m.planifies.at(-1);
  assert.equal(delai, DELAI_REPRISE_MS);
  rappel();
  assert.equal(m.voix.statut, "a_reactiver");
  await m.voix.reactiver();
  assert.equal(m.audios[0].reprises, 1);
});

test("un micro coupé (appel, casque débranché) se rouvre d'un toucher", async () => {
  const m = monter();
  await enLigne(m);
  const { surEtat } = m.audios[0].rappels;
  surEtat("micro_coupe");
  assert.equal(m.voix.statut, "a_reactiver");
  await m.voix.reactiver();
  assert.equal(m.audios[0].reprises, 1);
  surEtat("running");
  assert.equal(m.voix.statut, "active");
  assert.deepEqual(m.ws().envoyes.at(-1), { type: "reprise" });
});

test("au retour sur la page, un son reparti seul ne demande rien", async () => {
  const m = monter();
  await enLigne(m);
  m.voix.surVisibilite(true);
  m.planifies.at(-1).rappel();
  assert.equal(m.voix.statut, "active");
});

test("éteindre ferme le micro et la connexion", async () => {
  const m = monter();
  await enLigne(m);
  m.voix.eteindre();
  assert.equal(m.audios[0].fermee, true);
  assert.equal(m.ws().fermee, true);
  assert.equal(m.voix.statut, "eteinte");
  assert.equal(m.voix.allumee, false);
});

test("une clé refusée éteint le micro ; une coupure le garde et se rebranche", async () => {
  const m = monter();
  await enLigne(m);
  m.ws().couper(1006);
  assert.equal(m.voix.statut, "hors_ligne");
  assert.equal(m.audios[0].fermee, false);
  m.planifies.at(-1).rappel();
  m.ws().couper(4401);
  assert.equal(m.voix.statut, "cle_refusee");
  assert.equal(m.audios[0].fermee, true);
  assert.equal(m.voix.allumee, false);
});

test("l'explication du Core est gardée quand il ferme la voix", async () => {
  const m = monter();
  await m.voix.allumer();
  m.ws().ouvrir();
  m.ws().recevoir({ type: "erreur", code: "modeles_absents", message: "Modèle Silero introuvable" });
  m.ws().couper(4000);
  assert.equal(m.voix.statut, "cle_absente");
  assert.equal(m.voix.derniereErreur, "Modèle Silero introuvable");
});

// --- le verrou d'écran ---------------------------------------------------------------

function fauxNavigateur({ refuse = false } = {}) {
  const nav = { demandes: 0, verrous: [] };
  nav.wakeLock = {
    async request(type) {
      assert.equal(type, "screen");
      nav.demandes += 1;
      if (refuse) throw new Error("refusé");
      const verrou = {
        released: false,
        async release() {
          verrou.released = true;
        },
      };
      nav.verrous.push(verrou);
      return verrou;
    },
  };
  return nav;
}

test("le verrou d'écran se demande une fois, et se redemande au retour s'il a été relâché", async () => {
  const nav = fauxNavigateur();
  const verrou = new VerrouEcran(nav);
  await verrou.demander();
  await verrou.demander();
  assert.equal(nav.demandes, 1);
  nav.verrous[0].released = true; // la page a été cachée
  await verrou.surVisible();
  assert.equal(nav.demandes, 2);
  verrou.relacher();
  assert.equal(nav.verrous[1].released, true);
  await verrou.surVisible();
  assert.equal(nav.demandes, 2);
});

test("relâché pendant sa demande, le verrou est rendu dès qu'il arrive", async () => {
  const nav = fauxNavigateur();
  const verrou = new VerrouEcran(nav);
  const demande = verrou.demander();
  verrou.relacher();
  await demande;
  assert.equal(nav.verrous[0].released, true);
});

test("sans API, ou refusé, le verrou d'écran ne casse rien", async () => {
  await new VerrouEcran({}).demander();
  await new VerrouEcran(undefined).demander();
  await new VerrouEcran(fauxNavigateur({ refuse: true })).demander();
});

// --- le micro et le haut-parleur du navigateur -----------------------------------------

test("le micro garde toujours l'annulation d'écho, et le son se joue et se vide", async () => {
  const { trace, nav } = fauxNavigateurAudio();
  const audio = await ouvrirAudioNavigateur({ surBloc() {}, surEtat() {} }, nav);
  assert.deepEqual(trace.contraintes, {
    audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
  });
  assert.match(trace.modules[0], /\/voix_worklet\.js$/);
  assert.equal(audio.etat, "running");
  const trame = new ArrayBuffer(640);
  audio.jouer(trame);
  audio.vider();
  assert.deepEqual(trace.postes, [
    { message: trame, transferts: [trame] },
    { message: "vider", transferts: undefined },
  ]);
  audio.fermer();
  assert.equal(trace.pistes[0].readyState, "ended");
  assert.equal(trace.contextes[0].fermee, true);
});

test("sans HTTPS, le micro n'est même pas demandé", async () => {
  const { trace, nav } = fauxNavigateurAudio({ securisee: false });
  await assert.rejects(ouvrirAudioNavigateur({ surBloc() {}, surEtat() {} }, nav), { name: "PageNonSecurisee" });
  assert.equal(trace.contextes.length, 0);
  assert.equal(trace.contraintes, null);
});

test("sans HTTPS, la voix dit pourquoi elle ne s'allume pas", async () => {
  const refus = Object.assign(new Error("HTTPS"), { name: "PageNonSecurisee" });
  const m = monter({ ouvrirAudio: async () => Promise.reject(refus) });
  await m.voix.allumer();
  assert.equal(m.voix.statut, "https_requis");
});

test("un micro qui se coupe le signale, et reprendre le rouvre", async () => {
  const { trace, nav } = fauxNavigateurAudio();
  const etats = [];
  const audio = await ouvrirAudioNavigateur({ surBloc() {}, surEtat: (etat) => etats.push(etat) }, nav);
  trace.pistes[0].terminer();
  assert.deepEqual(etats, ["micro_coupe"]);
  await audio.reprendre();
  assert.equal(trace.pistes.length, 2);
  assert.deepEqual(etats, ["micro_coupe", "running"]);
  await audio.reprendre();
  assert.equal(trace.pistes.length, 2); // micro vivant : rien à rouvrir
});

test("micro refusé : le contexte audio se referme et l'erreur remonte", async () => {
  const { trace, nav } = fauxNavigateurAudio({ micro: "refuse" });
  await assert.rejects(ouvrirAudioNavigateur({ surBloc() {}, surEtat() {} }, nav), { name: "NotAllowedError" });
  assert.equal(trace.contextes[0].fermee, true);
});
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `node --test tests/web/voix.test.mjs`
Expected: FAIL — `Error [ERR_MODULE_NOT_FOUND]: Cannot find module '…/src/atlas_web/voix.js'`.

- [ ] **Step 3: Écrire la voix de la page**

Créer `src/atlas_web/voix.js` :

```javascript
// La voix de la page : le micro part au Core par /ws/voix, le son d'Atlas en revient. La
// page n'est qu'un terminal audio : le mot de réveil, la détection de voix et la coupure de
// parole tournent sur le Core (voix.py).

import { Connexion } from "./connexion.js";

// Au retour sur la page, le son d'iOS repart seul (spike S4) ; sinon, un toucher le rouvre.
export const DELAI_REPRISE_MS = 1500;
// Les fins de connexion qui ne se retentent pas : le micro n'a plus de raison de rester ouvert.
const FINS = new Set(["cle_requise", "cle_refusee", "cle_absente"]);

export class Voix {
  constructor({
    url,
    lireCle,
    page,
    heyAtlas,
    surStatut,
    ouvrirAudio = ouvrirAudioNavigateur,
    verrou = new VerrouEcran(),
    FabriqueWebSocket,
    planifier = (rappel, delai) => setTimeout(rappel, delai),
  }) {
    this._heyAtlas = heyAtlas;
    this._surStatut = surStatut;
    this._ouvrirAudio = ouvrirAudio;
    this._verrou = verrou;
    this._planifier = planifier;
    this._audio = null;
    this._voulue = false; // le bouton « Micro » est allumé
    this._interrompue = false; // iOS a coupé le son de la page
    this.statut = "eteinte";
    this.derniereErreur = null; // l'explication du Core avant qu'il ne ferme, s'il en donne une
    this._connexion = new Connexion({
      url,
      lireCle,
      entree: () => ({ page, hey_atlas: this._heyAtlas() }),
      surMessage: (message) => this._surMessage(message),
      surBinaire: (pcm) => this._audio?.jouer(pcm),
      surStatut: (statut) => this._surStatutConnexion(statut),
      FabriqueWebSocket,
      planifier,
    });
  }

  get allumee() {
    return this._voulue;
  }

  // À appeler depuis un geste de l'utilisateur : iOS n'ouvre le micro et le son qu'ainsi.
  async allumer() {
    if (this._voulue) return;
    this._voulue = true;
    this.derniereErreur = null;
    this._changer("ouverture");
    let audio;
    try {
      audio = await this._ouvrirAudio({
        surBloc: (bloc) => this._connexion.envoyerBinaire(bloc),
        surEtat: (etat) => this._surEtatAudio(etat),
      });
    } catch (e) {
      this._voulue = false;
      this.derniereErreur = `${e.name} : ${e.message}`;
      this._changer(e.name === "PageNonSecurisee" ? "https_requis" : "micro_refuse");
      return;
    }
    if (!this._voulue) {
      audio.fermer(); // éteinte pendant l'ouverture
      return;
    }
    this._audio = audio;
    this._interrompue = false;
    this._connexion.demarrer();
    if (this._heyAtlas()) this._verrou.demander();
  }

  eteindre() {
    this._voulue = false;
    this._connexion.arreter();
    this._fermerAudio();
    this._changer("eteinte");
  }

  toucherOrbe() {
    return this._connexion.envoyer({ type: "parler" });
  }

  changerHeyAtlas(actif) {
    // Hors ligne, rien ne part : la prochaine connexion lira l'état du moment.
    this._connexion.envoyer({ type: "hey_atlas", actif });
    if (actif && this._voulue) this._verrou.demander();
    else this._verrou.relacher();
  }

  surVisibilite(visible) {
    if (!visible || !this._audio) return;
    if (this._heyAtlas()) this._verrou.surVisible();
    this._planifier(() => {
      if (this._audio && this._audio.etat !== "running") this._changer("a_reactiver");
    }, DELAI_REPRISE_MS);
  }

  // Le toucher qui rouvre le son quand iOS ne l'a pas relancé seul.
  async reactiver() {
    await this._audio?.reprendre();
  }

  _surMessage(message) {
    if (message.type === "vider") this._audio?.vider();
    else if (message.type === "erreur") this.derniereErreur = message.message;
  }

  _surStatutConnexion(statut) {
    if (statut === "en_ligne") {
      this._changer(this._interrompue ? "interrompue" : "active");
      return;
    }
    if (FINS.has(statut)) {
      this._voulue = false;
      this._fermerAudio();
    }
    this._changer(statut);
  }

  _surEtatAudio(etat) {
    if (etat !== "running") {
      this._interrompue = true;
      // Un micro coupé (appel, casque débranché…) ne revient jamais seul : un toucher le rouvre.
      this._changer(etat === "micro_coupe" ? "a_reactiver" : "interrompue");
      return;
    }
    if (!this._interrompue) return;
    this._interrompue = false;
    // Le Core laisse à l'annuleur d'écho le temps de se réinstaller.
    this._connexion.envoyer({ type: "reprise" });
    this._changer("active");
  }

  _fermerAudio() {
    this._audio?.fermer();
    this._audio = null;
    this._verrou.relacher();
  }

  _changer(statut) {
    this.statut = statut;
    this._surStatut(statut);
  }
}

// Garde l'écran allumé tant que « Hey Atlas » écoute. Le navigateur relâche le verrou
// quand la page est cachée : il se redemande à son retour.
export class VerrouEcran {
  constructor(navigateur = globalThis.navigator) {
    this._navigateur = navigateur;
    this._verrou = null;
    this._voulu = false;
  }

  async demander() {
    this._voulu = true;
    if (!this._navigateur?.wakeLock || (this._verrou && !this._verrou.released)) return;
    let verrou;
    try {
      verrou = await this._navigateur.wakeLock.request("screen");
    } catch {
      return; // refusé (économie d'énergie…) : la page marche quand même, écran compris
    }
    if (this._voulu) this._verrou = verrou;
    else verrou.release().catch(() => {}); // relâché pendant la demande
  }

  relacher() {
    this._voulu = false;
    this._verrou?.release().catch(() => {});
    this._verrou = null;
  }

  async surVisible() {
    if (this._voulu) await this.demander();
  }
}

// Le micro et le haut-parleur, dans le navigateur. Le micro garde les réglages par défaut
// (spike S4) : jamais sans annulation d'écho, sinon iOS baisse la voix d'Atlas.
export async function ouvrirAudioNavigateur({ surBloc, surEtat }, nav = globalThis) {
  if (!nav.isSecureContext) {
    // Page ouverte par l'ancienne adresse en HTTP : le navigateur n'y donne pas le micro.
    throw Object.assign(new Error("le micro ne s'ouvre que sur une page en HTTPS"), { name: "PageNonSecurisee" });
  }
  const contexte = new nav.AudioContext();
  let flux = null;
  try {
    await contexte.audioWorklet.addModule(new URL("./voix_worklet.js", import.meta.url));
    const lecture = new nav.AudioWorkletNode(contexte, "lecture-16k", {
      numberOfInputs: 0,
      outputChannelCount: [1],
    });
    lecture.connect(contexte.destination);
    const capture = new nav.AudioWorkletNode(contexte, "capture-16k");
    capture.port.onmessage = (evenement) => surBloc(evenement.data);
    // Un nœud n'est calculé que s'il mène au haut-parleur : la capture y va, muette.
    const muet = contexte.createGain();
    muet.gain.value = 0;
    capture.connect(muet).connect(contexte.destination);
    contexte.addEventListener("statechange", () => surEtat(contexte.state));
    await contexte.resume();
    const ouvrirMicro = async () => {
      flux = await nav.navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      contexte.createMediaStreamSource(flux).connect(capture);
      for (const piste of flux.getAudioTracks()) piste.addEventListener("ended", () => surEtat("micro_coupe"));
    };
    await ouvrirMicro();
    return {
      get etat() {
        return contexte.state;
      },
      jouer: (pcm) => lecture.port.postMessage(pcm, [pcm]),
      vider: () => lecture.port.postMessage("vider"),
      async reprendre() {
        await contexte.resume();
        if (flux.getAudioTracks().every((piste) => piste.readyState === "ended")) await ouvrirMicro();
        surEtat(contexte.state); // un micro rouvert ne change pas l'état du contexte
      },
      fermer() {
        for (const piste of flux.getTracks()) piste.stop();
        contexte.close();
      },
    };
  } catch (e) {
    for (const piste of flux?.getTracks() ?? []) piste.stop();
    contexte.close();
    throw e;
  }
}
```

- [ ] **Step 4: Vérifier que tout passe**

Run: `uv run pytest -q && uv run ruff check . && uv run ruff format --check . && node --test "tests/web/*.test.mjs"`
Expected: 656 tests Python passent, 116 tests JavaScript passent, ruff ne dit rien.

- [ ] **Step 5: Commit**

```bash
git add src/atlas_web/voix.js tests/web/faux_audio.mjs tests/web/voix.test.mjs
git commit -F - <<'MSG'
Page : la voix (micro, lecture, reprise après iOS, verrou d'écran)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

### Task 9: Le micro, l'orbe et « Hey Atlas » dans la page

L'interface : le bouton Micro dans la barre, l'orbe à toucher, l'interrupteur « Hey Atlas » en tête des Paramètres,
et les messages de la voix sous la barre. `app.js` crée la `Voix` et relaie la visibilité de la page.

**Files:**
- Modify: `src/atlas_web/app.js`
- Modify: `src/atlas_web/index.html`
- Modify: `src/atlas_web/style.css`
- Modify: `tests/web/app.test.mjs`
- Modify: `tests/web/faux_dom.mjs`

**Interfaces:**
- Consumes: Task 6 (`page`) ; Task 8 (`Voix`, `fauxNavigateurAudio`).
- Produces: les éléments `#micro` (bouton, `aria-pressed`, classe `allume`), `#parler` (bouton, caché micro éteint),
  `#message-voix` (bouton, caché sans message ; le toucher réactive le micro quand le statut est `a_reactiver`) et
  `#hey-atlas` (case à cocher, retenue sous `atlas.hey_atlas`, « 1 » ou « 0 »). `fauxElement` (tests) gagne
  `attributs` et `setAttribute`.

- [ ] **Step 1: Écrire les tests qui échouent**

Modifier `tests/web/app.test.mjs` :

```diff
--- a/tests/web/app.test.mjs
+++ b/tests/web/app.test.mjs
@@ -3,6 +3,7 @@
 import assert from "node:assert/strict";
 import { test } from "node:test";
 
+import { fauxNavigateurAudio } from "./faux_audio.mjs";
 import { fauxElement, fauxStockage } from "./faux_dom.mjs";
 
 // Tous les identifiants cherchés par app.js via $("…") (voir tests/web/page.test.mjs).
@@ -12,15 +13,19 @@ const IDENTIFIANTS = [
   "formulaire-cle",
   "galerie-fonds",
   "galerie-orbes",
+  "hey-atlas",
   "libelle-etat",
   "liste-historique",
   "message-cle",
+  "message-voix",
+  "micro",
   "muet",
   "ouvrir-historique",
   "ouvrir-parametres",
   "panneau-cle",
   "panneau-historique",
   "panneau-parametres",
+  "parler",
   "pastille",
   "saisie",
   "sous-titres",
@@ -74,6 +79,7 @@ function fauxDocumentDeLaPage() {
   }
   elements.fond = canevasQuiLeve();
   elements.orbe = canevasSain();
+  const ecouteurs = {};
   return {
     hidden: false,
     getElementById(id) {
@@ -84,7 +90,12 @@ function fauxDocumentDeLaPage() {
     createElement: (tag) => fauxElement(tag),
     querySelectorAll: () => [],
     querySelector: () => null,
-    addEventListener() {},
+    addEventListener(type, rappel) {
+      (ecouteurs[type] ??= []).push(rappel);
+    },
+    declencher(type, evenement = {}) {
+      for (const rappel of ecouteurs[type] ?? []) rappel(evenement);
+    },
   };
 }
 
@@ -151,3 +162,110 @@ test("la page s'annonce sur /ws/web avec son identifiant", async () => {
   assert.equal(ws.envoyes[0].cle, "cle");
   assert.match(ws.envoyes[0].page, /^[0-9a-f]{24}$/);
 });
+
+class FauxWebSocket {
+  static ouvertes = [];
+
+  constructor(url) {
+    this.url = url;
+    this.envoyes = [];
+    this.readyState = 0;
+    FauxWebSocket.ouvertes.push(this);
+  }
+
+  send(donnees) {
+    this.envoyes.push(typeof donnees === "string" ? JSON.parse(donnees) : donnees);
+  }
+
+  close() {
+    this.readyState = 3;
+  }
+
+  ouvrir() {
+    this.readyState = 1;
+    this.onopen();
+  }
+
+  recevoir(message) {
+    this.onmessage({ data: JSON.stringify(message) });
+  }
+}
+
+// Le micro et le haut-parleur du faux navigateur, là où voix.js les cherche.
+function installerAudio(options) {
+  const { trace, nav } = fauxNavigateurAudio(options);
+  globalThis.isSecureContext = nav.isSecureContext;
+  globalThis.AudioContext = nav.AudioContext;
+  globalThis.AudioWorkletNode = nav.AudioWorkletNode;
+  Object.defineProperty(globalThis, "navigator", { value: nav.navigator, configurable: true });
+  return trace;
+}
+
+const tourner = () => new Promise((resoudre) => setImmediate(resoudre));
+
+test("le micro, l'orbe et « Hey Atlas » de la page passent par /ws/voix", async () => {
+  FauxWebSocket.ouvertes = [];
+  const trace = installerAudio();
+  const stockage = fauxStockage({ "atlas.cle": "cle", "atlas.hey_atlas": "1" });
+  await chargerPage({ stockage, FabriqueWebSocket: FauxWebSocket });
+  const $ = (id) => document.getElementById(id);
+  assert.equal($("hey-atlas").checked, true);
+  const [web] = FauxWebSocket.ouvertes;
+  web.ouvrir();
+
+  $("micro").declencher("click");
+  await tourner();
+  const voix = FauxWebSocket.ouvertes.find((ws) => ws.url === "ws://atlas.test/ws/voix");
+  voix.ouvrir();
+  assert.deepEqual(voix.envoyes[0], { type: "authentification", cle: "cle", page: web.envoyes[0].page, hey_atlas: true });
+  voix.recevoir({ type: "pret" });
+  assert.equal($("micro").attributs["aria-pressed"], "true");
+  assert.equal($("parler").hidden, false);
+  assert.equal($("message-voix").hidden, true);
+
+  $("parler").declencher("click");
+  $("hey-atlas").checked = false;
+  $("hey-atlas").declencher("change");
+  assert.deepEqual(voix.envoyes.slice(1), [{ type: "parler" }, { type: "hey_atlas", actif: false }]);
+  assert.equal(stockage.getItem("atlas.hey_atlas"), "0");
+
+  $("micro").declencher("click");
+  assert.equal($("micro").attributs["aria-pressed"], "false");
+  assert.equal($("parler").hidden, true);
+  assert.equal(trace.contextes[0].fermee, true);
+});
+
+test("sans HTTPS, le bouton Micro dit pourquoi il ne s'allume pas", async () => {
+  FauxWebSocket.ouvertes = [];
+  const trace = installerAudio({ securisee: false });
+  await chargerPage({ stockage: fauxStockage({ "atlas.cle": "cle" }), FabriqueWebSocket: FauxWebSocket });
+  const $ = (id) => document.getElementById(id);
+  $("micro").declencher("click");
+  await tourner();
+  assert.equal($("message-voix").hidden, false);
+  assert.match($("message-voix").textContent, /HTTPS/);
+  assert.equal($("micro").attributs["aria-pressed"], "false");
+  assert.equal(trace.contextes.length, 0);
+});
+
+test("au retour sur la page, un son resté coupé se rouvre d'un toucher", async (t) => {
+  t.mock.timers.enable({ apis: ["setTimeout"] });
+  FauxWebSocket.ouvertes = [];
+  const trace = installerAudio();
+  await chargerPage({ stockage: fauxStockage({ "atlas.cle": "cle" }), FabriqueWebSocket: FauxWebSocket });
+  const $ = (id) => document.getElementById(id);
+  $("micro").declencher("click");
+  await tourner();
+  const voix = FauxWebSocket.ouvertes.find((ws) => ws.url === "ws://atlas.test/ws/voix");
+  voix.ouvrir();
+  voix.recevoir({ type: "pret" });
+  const [contexte] = trace.contextes;
+  contexte.state = "interrupted"; // iOS ne l'a pas relancé
+  document.declencher("visibilitychange");
+  t.mock.timers.tick(1500);
+  assert.equal($("message-voix").hidden, false);
+  assert.match($("message-voix").textContent, /réactiver/);
+  $("message-voix").declencher("click");
+  await tourner();
+  assert.equal(contexte.state, "running");
+});
```

Modifier `tests/web/faux_dom.mjs` :

```diff
--- a/tests/web/faux_dom.mjs
+++ b/tests/web/faux_dom.mjs
@@ -12,6 +12,10 @@ export function fauxElement(tag) {
     textContent: "",
     type: "",
     hidden: false,
+    attributs: {},
+    setAttribute(nom, valeur) {
+      this.attributs[nom] = String(valeur);
+    },
     classList: {
       add: (nom) => classes.add(nom),
       remove: (nom) => classes.delete(nom),
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `node --test tests/web/app.test.mjs`
Expected: FAIL — les trois nouveaux tests échouent (`Cannot read properties of undefined (reading 'ouvrir')` : la
page n'ouvre pas `/ws/voix` ; pas de message HTTPS ; pas de message de réactivation) ; les deux tests existants
passent.

- [ ] **Step 3: Écrire l'interface**

Modifier `src/atlas_web/app.js` :

```diff
--- a/src/atlas_web/app.js
+++ b/src/atlas_web/app.js
@@ -1,4 +1,4 @@
-// Le démarrage de la page : relie la connexion, l'état, l'orbe, le fond et les panneaux.
+// Le démarrage de la page : relie la connexion, la voix, l'état, l'orbe, le fond et les panneaux.
 
 import { Connexion, identifiantDePage } from "./connexion.js";
 import { dimensionner, rgba } from "./dessin.js";
@@ -9,9 +9,11 @@ import { orbes } from "./orbes/index.js";
 import { ouvrirGalerie } from "./parametres.js";
 import { ecrireStockage, lireStockage } from "./registre.js";
 import { afficherSousTitres } from "./sous_titres.js";
+import { Voix } from "./voix.js";
 
 const $ = (id) => document.getElementById(id);
 const CLE_STOCKAGE = "atlas.cle";
+const CLE_HEY_ATLAS = "atlas.hey_atlas";
 const SEUIL_GLISSEMENT_PX = 60;
 const TOUCHENT_HISTORIQUE = new Set(["question", "reponse", "erreur", "latences", "historique"]);
 const STATUTS = {
@@ -26,6 +28,16 @@ const MESSAGES_CLE = {
   cle_refusee: "Le Core a refusé cette clé. Vérifie ATLAS_WEB_CLE dans son .env.",
   cle_absente: "Le Core n'a pas de clé : ajoute ATLAS_WEB_CLE dans son .env, redémarre-le, puis entre-la ici.",
 };
+const MESSAGES_VOIX = {
+  ouverture: "Ouverture du micro…",
+  https_requis: "Le micro ne s'ouvre qu'à l'adresse HTTPS d'Atlas.",
+  connexion: "Connexion de la voix…",
+  hors_ligne: "Voix hors ligne — nouvelle tentative…",
+  cle_requise: "Entre d'abord la clé d'accès d'Atlas.",
+  cle_refusee: "Le Core a refusé la clé.",
+  interrompue: "Micro en pause : écran verrouillé ou autre app.",
+  a_reactiver: "Touche ici pour réactiver le micro.",
+};
 
 let stockage = null;
 try {
@@ -65,6 +77,48 @@ const connexion = new Connexion({
   },
 });
 
+// --- La voix ----------------------------------------------------------------------
+
+const voix = new Voix({
+  url: `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/voix`,
+  lireCle: () => cleEnMemoire ?? lireStockage(stockage, CLE_STOCKAGE),
+  page,
+  heyAtlas: () => $("hey-atlas").checked,
+  surStatut: afficherVoix,
+});
+
+function messageVoix(statut) {
+  if (statut === "micro_refuse") {
+    return `Micro indisponible (${voix.derniereErreur}) : autorise-le pour ce site dans les réglages du navigateur.`;
+  }
+  // 4000 : la clé ou les modèles manquent sur le Core, qui l'a dit juste avant de fermer.
+  if (statut === "cle_absente") return voix.derniereErreur ?? "Le Core n'a pas de clé.";
+  return MESSAGES_VOIX[statut] ?? "";
+}
+
+function afficherVoix(statut) {
+  $("micro").setAttribute("aria-pressed", String(voix.allumee));
+  $("micro").classList.toggle("allume", voix.allumee);
+  $("parler").hidden = !voix.allumee;
+  const message = messageVoix(statut);
+  $("message-voix").textContent = message;
+  $("message-voix").hidden = !message;
+}
+
+$("micro").addEventListener("click", () => {
+  if (voix.allumee) voix.eteindre();
+  else voix.allumer();
+});
+$("parler").addEventListener("click", () => voix.toucherOrbe());
+$("message-voix").addEventListener("click", () => {
+  if (voix.statut === "a_reactiver") voix.reactiver();
+});
+$("hey-atlas").checked = lireStockage(stockage, CLE_HEY_ATLAS) === "1";
+$("hey-atlas").addEventListener("change", () => {
+  ecrireStockage(stockage, CLE_HEY_ATLAS, $("hey-atlas").checked ? "1" : "0");
+  voix.changerHeyAtlas($("hey-atlas").checked);
+});
+
 function demanderCle(message) {
   fermerPanneaux();
   $("message-cle").textContent = message;
@@ -209,6 +263,7 @@ function image(ms) {
 
 // Onglet caché : plus aucune image, ni de l'orbe ni du fond.
 document.addEventListener("visibilitychange", () => {
+  voix.surVisibilite(!document.hidden);
   if (document.hidden) {
     cancelAnimationFrame(idImage);
     idImage = null;
```

Modifier `src/atlas_web/index.html` :

```diff
--- a/src/atlas_web/index.html
+++ b/src/atlas_web/index.html
@@ -22,10 +22,18 @@
       <input type="checkbox" id="muet">
       <span>Muet</span>
     </label>
+    <button type="button" class="icone" id="micro" aria-label="Micro" aria-pressed="false">
+      <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
+        <path fill="currentColor" d="M12 14a3 3 0 0 0 3-3V5a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3Zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-3.08A7 7 0 0 0 19 11h-2Z"/>
+      </svg>
+    </button>
     <button type="button" class="icone" id="ouvrir-historique" aria-label="Historique">☰</button>
     <button type="button" class="icone" id="ouvrir-parametres" aria-label="Paramètres">⚙</button>
   </header>
 
+  <button type="button" id="message-voix" hidden></button>
+  <button type="button" id="parler" aria-label="Parler à Atlas" hidden></button>
+
   <section id="sous-titres" aria-live="polite">
     <p id="st-question"></p>
     <p id="st-reponse"></p>
@@ -49,6 +57,11 @@
       <h2>Paramètres</h2>
       <button type="button" class="icone fermer" aria-label="Fermer">✕</button>
     </header>
+    <h3>Voix</h3>
+    <label class="interrupteur">
+      <input type="checkbox" id="hey-atlas">
+      <span>Écouter « Hey Atlas » quand le micro est allumé</span>
+    </label>
     <h3>Orbe</h3>
     <div id="galerie-orbes" class="galerie"></div>
     <h3>Fond</h3>
```

Modifier `src/atlas_web/style.css` :

```diff
--- a/src/atlas_web/style.css
+++ b/src/atlas_web/style.css
@@ -111,7 +111,47 @@ button {
   background: rgba(255, 255, 255, 0.06);
 }
 
-/* L'interrupteur « muet » : une case à cocher habillée. */
+/* Le micro allumé : la page écoute. */
+.icone.allume {
+  color: var(--accent);
+  background: rgba(251, 191, 36, 0.14);
+}
+
+/* La voix : ce qu'elle a à dire (micro refusé, en pause…), sous la barre. */
+#message-voix {
+  position: fixed;
+  top: calc(max(12px, env(safe-area-inset-top)) + 52px);
+  left: 50%;
+  transform: translateX(-50%);
+  max-width: calc(100vw - 32px);
+  padding: 8px 16px;
+  border-radius: 16px;
+  background: var(--verre);
+  font-size: 14px;
+  color: var(--texte-doux);
+  text-align: center;
+  backdrop-filter: blur(12px);
+  -webkit-backdrop-filter: blur(12px);
+}
+
+/* L'orbe à toucher, micro allumé : un bouton rond et transparent, posé sur son cœur. */
+#parler {
+  position: fixed;
+  left: 50%;
+  top: 42%;
+  width: min(40vh, 60vw);
+  height: min(40vh, 60vw);
+  transform: translate(-50%, -50%);
+  border-radius: 50%;
+  -webkit-tap-highlight-color: transparent;
+}
+
+#parler:focus-visible {
+  outline: 2px solid var(--accent);
+  outline-offset: 4px;
+}
+
+/* Les interrupteurs « muet » et « Hey Atlas » : une case à cocher habillée. */
 .interrupteur {
   display: flex;
   align-items: center;
```

Facultatif, si l'exécutant dispose d'un navigateur : vérifier à l'œil, à la largeur d'un iPhone (375 px), `python3 -m http.server 8765 --bind
127.0.0.1` depuis `src/atlas_web`, puis `http://127.0.0.1:8765/`. La barre tient sur une ligne (l'état peut passer
sur deux), l'icône du micro prend la couleur d'accent quand on lui ajoute la classe `allume`, et « Voix » ouvre les
Paramètres. Arrêter ensuite le serveur.

- [ ] **Step 4: Vérifier que tout passe**

Run: `uv run pytest -q && uv run ruff check . && uv run ruff format --check . && node --test "tests/web/*.test.mjs"`
Expected: 656 tests Python passent, 119 tests JavaScript passent, ruff ne dit rien.

- [ ] **Step 5: Commit**

```bash
git add src/atlas_web/app.js src/atlas_web/index.html src/atlas_web/style.css tests/web/app.test.mjs tests/web/faux_dom.mjs
git commit -F - <<'MSG'
Page : bouton Micro, orbe à toucher, interrupteur « Hey Atlas »

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

### Task 10: Le déploiement : HTTPS, modèles, spec parente

La documentation de ce que David fera à la main : le Proxy Host de Nginx Proxy Manager, le DNS, les modèles sur la
machine du Core, l'usage de la page ; les deux réglages dans `.env.example` ; les amendements de la spec parente
(spec §11).

**Files:**
- Modify: `.env.example`
- Modify: `docs/superpowers/specs/2026-09-22-atlas-design.md`
- Modify: `scripts/neo/LISEZMOI.md`

**Interfaces:**
- Consumes: les valeurs de Task 5 (réglages) et le comportement des Tasks 8–9 (ce que la page affiche).
- Produces: rien pour le code.

- [ ] **Step 1: Écrire la documentation**

Modifier `.env.example` :

```diff
--- a/.env.example
+++ b/.env.example
@@ -35,13 +35,15 @@ ATLAS_RELANCE_S=10
 # Client audio (MacBook) — chemins et choix de composants
 # Déclencheur du réveil : « touche » (Entrée au clavier) ou « motcle » (openWakeWord).
 ATLAS_REVEILLEUR=touche
-# Modèle du mot de réveil entraîné (voir scripts/mot_reveil/LISEZMOI.md).
+# Modèle du mot de réveil entraîné (voir scripts/mot_reveil/LISEZMOI.md). Le Core s'en
+# sert aussi pour écouter les pages (voir scripts/neo/LISEZMOI.md).
 ATLAS_MOT_REVEIL=models/hey_atlas.onnx
 # Périphérique audio : « aec » (binaire Swift avec annulation d'écho) ou « sounddevice ».
 ATLAS_AUDIO_PERIPHERIQUE=aec
 # Binaire Swift d'annulation d'écho, construit par swift build -c release.
 ATLAS_AEC_BINAIRE=src/atlas_aec/.build/release/atlas-aec
-# Modèle Silero de détection de voix (voir bench/LISEZMOI.md pour le télécharger).
+# Modèle Silero de détection de voix (voir bench/LISEZMOI.md pour le télécharger). Le Core
+# s'en sert aussi pour écouter les pages.
 ATLAS_VAD_MODELE=models/silero_vad.onnx
 
 # Page web d'Atlas (orbe et conversation), servie par le Core à sa racine.
@@ -50,6 +52,17 @@ ATLAS_VAD_MODELE=models/silero_vad.onnx
 # (la vraie valeur ne va que dans le .env du Core, jamais dans ce fichier).
 ATLAS_WEB_CLE=
 
+# La voix des pages : le micro de l'iPhone, de l'iPad ou du Mac, que le Core écoute pour
+# elles (seulement en HTTPS, voir scripts/neo/LISEZMOI.md). Le Core leur applique les
+# réglages du client audio (ATLAS_REVEIL_SEUIL, ATLAS_SILENCE_MS, ATLAS_BARGEIN_MS,
+# ATLAS_RELANCE_S), sauf ces deux-là, mesurés par le spike S4.
+# Latence de sortie d'un navigateur, en secondes (de 0 à 2) : le temps que le son met à
+# sortir du haut-parleur après son envoi.
+ATLAS_VOIX_MARGE_S=0.2
+# Porte d'énergie de la coupure à la voix sur une page, en dBFS (de -120 à 0), comme
+# ATLAS_BARGEIN_DBFS pour le client audio.
+ATLAS_VOIX_BARGEIN_DBFS=-40
+
 # Le cerveau d'Atlas. « claude » : Claude, par le SDK Agent et le CLI claude connecté à
 # l'abonnement. « bouchon » : les réponses figées de la phase 1, pour faire tourner Atlas
 # sans Claude.
```

Modifier `docs/superpowers/specs/2026-09-22-atlas-design.md` :

```diff
--- a/docs/superpowers/specs/2026-09-22-atlas-design.md
+++ b/docs/superpowers/specs/2026-09-22-atlas-design.md
@@ -267,6 +267,9 @@ dessinée en Canvas 2D, sans Three.js : 12 orbes et 6 fonds animés au choix, av
 conversation en sous-titres et une saisie au clavier (voir
 `2026-09-24-interface-orbe-design.md`). Puis le tableau de bord : état des workflows n8n,
 contenu de la mémoire, documents produits, erreurs.
+**Amendé le 25/09/2026 (la voix dans le navigateur).** La page capte aussi la voix : un
+bouton « Micro », « Hey Atlas » écouté pour elle, et l'orbe à toucher pour parler. Le Core
+écoute pour elle, avec le code du client audio. Voir `2026-09-25-voix-navigateur-design.md`.
 
 ### 6.6 Protocole entre le client audio et le Core
 
@@ -438,6 +441,9 @@ corriger de façon fiable. La source de vérité reste les fichiers Markdown d'A
 
 - Communication entre machines en **WSS et HTTPS**, derrière le reverse proxy Unraid
   existant, sous le domaine déjà en place.
+  **Amendé le 25/09/2026 (la voix dans le navigateur)** : la page passe en HTTPS derrière
+  Nginx Proxy Manager, accès limité au réseau local et au VPN ; `/ws/voix` rejoint les
+  routes protégées par la clé des pages.
 - **Vérification de l'origine** sur toutes les routes qui modifient un état.
 - **`/ws/audio` protégé par une clé** (amendé le 24/09/2026, phase 2a) : `ATLAS_AUDIO_CLE`,
   dans le `hello` du client audio, comparée en temps constant. Les navigateurs restent
@@ -497,6 +503,9 @@ et le document produit se relit sans retouche.
 **Amendé le 24/09/2026.** La phase 2 est découpée en trois étapes, chacune avec sa spec,
 son plan et sa fusion : 2a, le cerveau branché (`2026-09-24-phase-2a-cerveau-design.md`) ;
 2b, la mémoire ; 2c, outils et permissions.
+**Amendé le 25/09/2026.** Une étape « la voix dans le navigateur »
+(`2026-09-25-voix-navigateur-design.md`) s'insère entre 2a et 2b : la page de l'iPhone ou
+de l'iPad écoute et répond à voix haute, pas seulement le M5.
 
 **Phase 3 — Les outils.** Registre d'outils, routeur d'intention, Ollama, supervision n8n,
 point quotidien, déclenchement vocal, diagnostic.
```

Modifier `scripts/neo/LISEZMOI.md` :

````diff
--- a/scripts/neo/LISEZMOI.md
+++ b/scripts/neo/LISEZMOI.md
@@ -2,10 +2,12 @@
 
 Le Core quitte le Mac de développement pour le MacBook néo de la baie : il y tourne en
 service, démarre avec la machine et redémarre s'il tombe. Le client audio reste sur le M5,
-et la page s'ouvre à l'adresse du néo.
+et la page s'ouvre à l'adresse du néo — en HTTPS, par Nginx Proxy Manager, pour que
+l'iPhone et l'iPad puissent parler à Atlas.
 
-Dans ce guide, `neo.local` désigne le néo sur le réseau local : remplace-le par son nom ou
-son adresse chez toi. Rien de ce qui suit ne sort du réseau local.
+Dans ce guide, `neo.local` désigne le néo sur le réseau local, et `atlas.example.com` le
+sous-domaine d'Atlas : remplace-les par leur nom ou leur adresse chez toi. Rien de ce qui
+suit ne sort du réseau local et du VPN.
 
 ## 1. Installer les outils et le dépôt
 
@@ -99,6 +101,59 @@ Puis `make run-audio`. Si le Core disparaît (redémarrage du néo, coupure du r
 client audio se reconnecte seul : 1, 2, 4, 8, 16 puis 30 secondes entre les tentatives.
 Une clé refusée est signalée dans son journal.
 
-## 8. Ouvrir la page
+## 8. Les modèles de la voix des pages
 
-Sur l'iPhone, l'iPad ou le Mac : `http://neo.local:8080/`, avec la clé `ATLAS_WEB_CLE`.
+Le Core écoute les pages avec les mêmes modèles que le client audio du M5 : « Hey Atlas »
+et Silero. Copie-les depuis le M5, puis télécharge une fois les modèles de traits
+d'openWakeWord sur le néo :
+
+```bash
+# sur le M5, dans ~/atlas
+scp models/hey_atlas.onnx models/silero_vad.onnx neo.local:atlas/models/
+# sur le néo, dans ~/atlas
+uv run python -c "import openwakeword.utils; openwakeword.utils.download_models()"
+```
+
+Redémarre ensuite le Core. S'il manque un modèle, la page le dit quand on allume son
+micro, et le reste d'Atlas marche comme avant.
+
+## 9. Le HTTPS, par Nginx Proxy Manager
+
+Safari n'ouvre le micro que sur une page en HTTPS. Dans Nginx Proxy Manager, sur l'Unraid,
+un « Proxy Host » (si celui du spike S4 existe déjà, change seulement sa destination) :
+
+- **Details** : le domaine `atlas.example.com`, vers `http`, `neo.local`, port `8080` ;
+  coche « Websockets Support » ; laisse passer l'en-tête `Host` tel quel (le réglage par
+  défaut) : le Core s'en sert pour reconnaître sa page ;
+- **Access List** : une liste qui n'autorise que le réseau local et le VPN ;
+- **SSL** : un certificat Let's Encrypt, obtenu par le défi DNS (le sous-domaine n'est pas
+  joignable depuis Internet), ou le certificat générique du domaine s'il existe déjà ;
+  coche « Force SSL » ;
+- **Advanced** : sans ces deux lignes, nginx ferme au bout de 60 s une connexion restée
+  silencieuse :
+
+  ```nginx
+  proxy_read_timeout 3600s;
+  proxy_send_timeout 3600s;
+  ```
+
+Le DNS : `atlas.example.com` pointe vers l'adresse de l'Unraid sur le réseau local (un
+enregistrement DNS local, ou un enregistrement public vers une adresse privée). Le client
+audio du M5, lui, continue de parler directement au Core (`ws://neo.local:8080/ws/audio`).
+
+## 10. Ouvrir la page et lui parler
+
+Sur l'iPhone, l'iPad ou le Mac : `https://atlas.example.com/`, avec la clé
+`ATLAS_WEB_CLE`. L'adresse `http://neo.local:8080/` marche encore, mais sans micro.
+
+- **Le micro** (l'icône à côté de « Muet ») : à toucher à chaque ouverture de la page ;
+  Safari demande l'autorisation la première fois. Allumé, la page envoie le son au Core
+  (iOS affiche son point orange).
+- **Toucher l'orbe**, micro allumé : Atlas t'écoute ; pendant qu'il parle, ça le coupe.
+- **« Hey Atlas »** : l'interrupteur des Paramètres, retenu par l'appareil. Allumé, le Core
+  écoute le mot de réveil pour cette page, et l'écran reste allumé : un iPad sur son
+  support, un iPhone posé sur le bureau. iOS coupe le micro quand l'écran se verrouille ;
+  au retour, il repart seul, sinon la page demande un toucher.
+- Chaque appareil répond pour lui-même, et le client du M5 marche toujours à côté.
+- Les dix premières secondes de voix d'Atlas après l'allumage du micro, on ne le coupe
+  qu'en touchant l'orbe : l'annulation d'écho du navigateur s'installe.
````

Vérifier qu'aucune donnée privée n'y est entrée : `git diff | grep -nE "[0-9]{1,3}(\.[0-9]{1,3}){3}|\.com"` ne doit
montrer que `atlas.example.com`.

- [ ] **Step 2: Vérifier que tout passe**

Run: `uv run pytest -q && uv run ruff check . && uv run ruff format --check . && node --test "tests/web/*.test.mjs"`
Expected: 656 tests Python passent, 119 tests JavaScript passent, ruff ne dit rien.

- [ ] **Step 3: Commit**

```bash
git add .env.example docs/superpowers/specs/2026-09-22-atlas-design.md scripts/neo/LISEZMOI.md
git commit -F - <<'MSG'
Documentation : HTTPS par Nginx Proxy Manager, modèles du Core, spec parente

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

## L'essai avec David, sur le vrai matériel

Après la Task 10, sur la branche `voix-navigateur`, avant la PR. C'est David qui ouvre les micros ; les critères
sont ceux du §1 de la spec.

1. **Le proxy.** Dans Nginx Proxy Manager, le Proxy Host du spike S4 pointe désormais vers la machine du Core, port
   `8080` (Websockets Support, Access List, certificat et délais longs : `scripts/neo/LISEZMOI.md`, étape 9).
2. **Les modèles.** Sur la machine du Core : `models/hey_atlas.onnx`, `models/silero_vad.onnx` et les modèles de
   traits d'openWakeWord (étape 8). Puis `make run-core` (ou le redémarrage du service).
3. **L'iPad sur son support** : la page à l'adresse HTTPS, le micro allumé, « Hey Atlas » allumé dans les
   Paramètres. « Hey Atlas, quelle heure est-il ? » : la réponse sort de l'iPad. Puis « attends » pendant qu'Atlas
   parle, passées ses dix premières secondes de voix : il se tait. (L'iPad n'a pas été mesuré au spike S4 : c'est ici
   qu'on le vérifie, verrou d'écran compris.)
4. **L'iPhone, bouton** : « Hey Atlas » éteint, toucher l'orbe, poser la question : la réponse sort de l'iPhone.
   Toucher l'orbe pendant qu'Atlas parle le coupe.
5. **Le clavier** : sur l'iPhone, micro allumé, une question tapée reçoit sa réponse à voix haute sur l'iPhone.
6. **L'écran verrouillé** : verrouiller l'iPhone, micro allumé ; au retour, le son repart seul (ou la page demande
   un toucher, qui le rouvre).
7. **Le Mac** : `make run-audio` sur le M5 en même temps que les pages ; « Hey Atlas » au M5 répond toujours au M5.
8. **Le muet** : touché sur l'iPhone pendant qu'Atlas parle sur l'iPad, il coupe l'iPad.
9. **Non-régression** : `make test` au vert.

Ce qui ne va pas devient une correction sur la branche, avec son test, avant la PR.

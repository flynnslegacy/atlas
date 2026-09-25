# Le Core d'Atlas sur le néo

Le Core quitte le Mac de développement pour le MacBook néo de la baie : il y tourne en
service, démarre avec la machine et redémarre s'il tombe. Le client audio reste sur le M5,
et la page s'ouvre à l'adresse du néo — en HTTPS, par Nginx Proxy Manager, pour que
l'iPhone et l'iPad puissent parler à Atlas.

Dans ce guide, `neo.local` désigne le néo sur le réseau local, et `atlas.example.com` le
sous-domaine d'Atlas : remplace-les par leur nom ou leur adresse chez toi. Rien de ce qui
suit ne sort du réseau local et du VPN.

## 1. Installer les outils et le dépôt

Sur le néo, dans un terminal (ou par SSH) :

```bash
xcode-select --install          # make et git, si ce n'est pas déjà fait
curl -LsSf https://astral.sh/uv/install.sh | sh
curl -fsSL https://claude.ai/install.sh | bash
git clone https://github.com/flynnslegacy/atlas.git ~/atlas
cd ~/atlas
make install
```

Ouvre un nouveau terminal après les deux installateurs, pour que `uv` et `claude` soient
dans le `PATH`.

## 2. Garder le néo éveillé

Le Core doit répondre à toute heure : le néo ne doit pas se mettre en veille. Vérifie-le
dans Réglages Système, ou avec `pmset -g` (la ligne `sleep` doit valoir 0).

## 3. Connecter Claude à l'abonnement

```bash
claude setup-token
```

La commande ouvre la connexion à ton compte Claude dans un navigateur ; par SSH, elle
affiche une adresse à ouvrir ailleurs et un code à recoller dans le terminal. Elle affiche
ensuite un jeton valable un an.

**Ce jeton est un secret.** Il ne va que dans le `.env` du néo (étape 4), jamais dans le
dépôt, jamais dans un message. Note dans ton agenda de le renouveler (même commande) avant
son échéance, dans un an.

## 4. Écrire le `.env` du néo

```bash
cp .env.example .env
chmod 600 .env
```

Puis, dans `.env` :

- `ATLAS_STT_URL` et `ATLAS_TTS_URL` : les adresses des services sur l'Unraid ;
- `ATLAS_WEB_CLE` : la clé de la page (la même que sur le M5 si tu veux garder tes
  appareils déjà connectés, sinon une nouvelle) ;
- `ATLAS_AUDIO_CLE` : une nouvelle clé, que tu recopieras sur le M5 (étape 7) ;
- `CLAUDE_CODE_OAUTH_TOKEN` : décommente la ligne et colle le jeton de l'étape 3 ;
- `ATLAS_CERVEAU=claude`, et au besoin `ATLAS_CERVEAU_MODELE` et `ATLAS_CERVEAU_OUBLI_MIN`.

Pour générer une clé :

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(24))"
```

## 5. Essayer le Core à la main

```bash
make run-core
```

Depuis le M5 : `curl http://neo.local:8080/sante` doit répondre `{"ok":true,…}`. Arrête
ensuite le Core avec Ctrl-C.

## 6. Installer le service

```bash
./scripts/neo/installer_service.sh
```

Le script vérifie le `.env`, demande ton mot de passe (sudo) et installe le service
`fr.atlas.core`. Le Core démarre aussitôt, puis à chaque démarrage du néo, même sans
session ouverte ; launchd le relance s'il tombe.

- Le journal : `tail -f ~/atlas/donnees/logs/core.log`
- Redémarrer le Core : `sudo launchctl kickstart -k system/fr.atlas.core`
- Arrêter le service : `sudo launchctl bootout system/fr.atlas.core`
- Mettre Atlas à jour : `git pull && make install`, puis redémarrer le Core.

## 7. Brancher le M5 sur le néo

Sur le M5, arrête le Core s'il tourne encore, puis, dans le `.env` du M5 :

- `ATLAS_CORE_URL=ws://neo.local:8080/ws/audio`
- `ATLAS_AUDIO_CLE` : la même clé que sur le néo.

Puis `make run-audio`. Si le Core disparaît (redémarrage du néo, coupure du réseau), le
client audio se reconnecte seul : 1, 2, 4, 8, 16 puis 30 secondes entre les tentatives.
Une clé refusée est signalée dans son journal.

## 8. Les modèles de la voix des pages

Le Core écoute les pages avec les mêmes modèles que le client audio du M5 : « Hey Atlas »
et Silero. Copie-les depuis le M5, puis télécharge une fois les modèles de traits
d'openWakeWord sur le néo :

```bash
# sur le M5, dans ~/atlas
scp models/hey_atlas.onnx models/silero_vad.onnx neo.local:atlas/models/
# sur le néo, dans ~/atlas
uv run python -c "import openwakeword.utils; openwakeword.utils.download_models()"
```

Redémarre ensuite le Core. S'il manque un modèle, la page le dit quand on allume son
micro, et le reste d'Atlas marche comme avant.

## 9. Le HTTPS, par Nginx Proxy Manager

Safari n'ouvre le micro que sur une page en HTTPS. Dans Nginx Proxy Manager, sur l'Unraid,
un « Proxy Host » (si celui du spike S4 existe déjà, change seulement sa destination) :

- **Details** : le domaine `atlas.example.com`, vers `http`, `neo.local`, port `8080` ;
  coche « Websockets Support » ; laisse passer l'en-tête `Host` tel quel (le réglage par
  défaut) : le Core s'en sert pour reconnaître sa page ;
- **Access List** : une liste qui n'autorise que le réseau local et le VPN ;
- **SSL** : un certificat Let's Encrypt, obtenu par le défi DNS (le sous-domaine n'est pas
  joignable depuis Internet), ou le certificat générique du domaine s'il existe déjà ;
  coche « Force SSL » ;
- **Advanced** : sans ces deux lignes, nginx ferme au bout de 60 s une connexion restée
  silencieuse :

  ```nginx
  proxy_read_timeout 3600s;
  proxy_send_timeout 3600s;
  ```

Le DNS : `atlas.example.com` pointe vers l'adresse de l'Unraid sur le réseau local (un
enregistrement DNS local, ou un enregistrement public vers une adresse privée). Le client
audio du M5, lui, continue de parler directement au Core (`ws://neo.local:8080/ws/audio`).

## 10. Ouvrir la page et lui parler

Sur l'iPhone, l'iPad ou le Mac : `https://atlas.example.com/`, avec la clé
`ATLAS_WEB_CLE`. L'adresse `http://neo.local:8080/` marche encore, mais sans micro.

- **Le micro** (l'icône à côté de « Muet ») : à toucher à chaque ouverture de la page ;
  Safari demande l'autorisation la première fois. Allumé, la page envoie le son au Core
  (iOS affiche son point orange).
- **Toucher l'orbe**, micro allumé : Atlas t'écoute ; pendant qu'il parle, ça le coupe.
- **« Hey Atlas »** : l'interrupteur des Paramètres, retenu par l'appareil. Allumé, le Core
  écoute le mot de réveil pour cette page, et l'écran reste allumé : un iPad sur son
  support, un iPhone posé sur le bureau. iOS coupe le micro quand l'écran se verrouille ;
  au retour, il repart seul, sinon la page demande un toucher.
- Chaque appareil répond pour lui-même, et le client du M5 marche toujours à côté.
- Les dix premières secondes de voix d'Atlas après l'allumage du micro, on ne le coupe
  qu'en touchant l'orbe : l'annulation d'écho du navigateur s'installe.

## 11. La mémoire d'Atlas

Atlas tient sa mémoire dans `~/.atlas/memoire` sur la machine du Core : son profil de toi,
ses fiches (entreprise, projets, personnes) et le journal de vos conversations. C'est un
dépôt git local, qui n'a aucun distant et n'est jamais poussé ; sa sauvegarde est celle de
la machine. Tu peux lire et corriger les fichiers à la main.

Pour passer du M5 au néo, Core arrêté des deux côtés, copie-la avant de démarrer le Core
sur le néo :

```bash
# sur le M5
rsync -a ~/.atlas/memoire/ neo.local:.atlas/memoire/
```

Sans `git` sur la machine, Atlas marche sans mémoire ; le journal du Core le dit au
démarrage.

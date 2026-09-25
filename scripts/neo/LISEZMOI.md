# Le Core d'Atlas sur le néo

Le Core quitte le Mac de développement pour le MacBook néo de la baie : il y tourne en
service, démarre avec la machine et redémarre s'il tombe. Le client audio reste sur le M5,
et la page s'ouvre à l'adresse du néo.

Dans ce guide, `neo.local` désigne le néo sur le réseau local : remplace-le par son nom ou
son adresse chez toi. Rien de ce qui suit ne sort du réseau local.

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

## 8. Ouvrir la page

Sur l'iPhone, l'iPad ou le Mac : `http://neo.local:8080/`, avec la clé `ATLAS_WEB_CLE`.

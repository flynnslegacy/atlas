# Gmail et Google Agenda : mettre en route

Atlas parle à Gmail et à Google Agenda avec **ton propre projet Google Cloud** et une autorisation
que tu lui donnes une fois. Compte une dizaine de minutes, sur un Mac qui a un navigateur. Tout est
gratuit.

## 1. Le projet Google Cloud

1. Ouvre [console.cloud.google.com](https://console.cloud.google.com) avec ton compte Google.
2. En haut, **Sélectionner un projet** › **Nouveau projet** ; nom : `Atlas` ; **Créer**, puis
   sélectionne-le.
3. **API et services** › **Bibliothèque** : cherche **Gmail API**, **Activer** ; puis **Google
   Calendar API**, **Activer**.

## 2. L'écran d'autorisation

Dans **Google Auth Platform** (anciennement « Écran de consentement OAuth ») :

1. **Commencer** : nom de l'application `Atlas`, ton adresse comme adresse d'assistance ; public
   **Externe** ; ton adresse comme contact ; accepte les conditions ; **Créer**.
2. **Audience** : **Publier l'application**, puis confirme. L'état doit dire **En production**.
   En « Test », Google retirerait l'autorisation d'Atlas au bout de 7 jours.

Google ne vérifiera pas l'application : c'est normal pour un usage personnel. Il te montrera un
avertissement une seule fois, au moment d'autoriser.

## 3. Le client OAuth

1. **Clients** › **Créer un client** ; type **Application de bureau** ; nom `Atlas` ; **Créer**.
2. Google affiche l'**ID client** (il finit par `.apps.googleusercontent.com`) et le **Code secret
   du client**. Garde la fenêtre ouverte.
3. Dans la page d'Atlas : **Paramètres** › **Connecteurs** › **Gmail** › **Réglages…** : colle
   l'ID client dans `ATLAS_GOOGLE_ID_CLIENT` et le code secret dans `ATLAS_GOOGLE_SECRET_CLIENT`,
   puis **Enregistrer**. Google Agenda les partage : pas besoin de les saisir deux fois.

## 4. L'autorisation

Sur le Mac où tourne le Core, dans le dossier d'Atlas :

```bash
make google
```

Ton navigateur s'ouvre sur Google :

1. Choisis ton compte.
2. Google dit que l'application n'est pas vérifiée : clique sur **Paramètres avancés**, puis sur
   **Accéder à Atlas**.
3. Coche les accès demandés (lire, écrire et envoyer tes mails ; voir et modifier ton agenda) et
   **Continuer**.
4. La page dit « Atlas est autorisé : tu peux fermer cette page. ».

Le jeton est dans le `.env`. Redémarre le Core depuis la page (**Paramètres** › **Le Core** ›
**Redémarrer…**), puis active **Gmail** et **Google Agenda** dans **Connecteurs**.

**Si le Core tourne sur le néo** (sans écran) : lance `make google AFFICHER=1` sur ton Mac, copie
le jeton qu'il affiche, et colle-le dans **Réglages…** de Gmail sur la page du néo
(`ATLAS_GOOGLE_JETON`) : il vaut aussitôt pour les deux connecteurs.

## Retirer l'accès

Sur [myaccount.google.com](https://myaccount.google.com) › **Sécurité** › **Accès tiers** (ou
« Vos connexions à des applis et services tiers ») › **Atlas** › **Supprimer l'accès**. Atlas te
dira alors de relancer `make google`. Changer le mot de passe de ton compte Google retire aussi
l'accès.

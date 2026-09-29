# Les Paramètres : un menu à gauche, la rubrique à droite — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Les Paramètres de la page deviennent une fenêtre comme les Réglages Système du Mac : une colonne de rubriques (Connecteurs, Voix, Orbe, Fond, Le Core, une icône et un mot chacune) et la rubrique choisie à droite ; sur un écran étroit, la liste des rubriques, puis la rubrique, avec « ‹ Paramètres ».

**Architecture:** `rubriques.js` tient la rubrique affichée (retenue sur l'appareil) et dit « la liste » ou « la rubrique » (`data-vue`) ; la largeur (720 px) est une règle CSS. `index.html` porte la colonne (des boutons avec leur icône SVG) et une section par rubrique ; `parametres.css` la disposition, `rubriques.css` le contenu des rubriques. `app.js` branche la navigation, n'anime une galerie que dans sa rubrique et tient les valeurs de la liste à jour ; `connecteurs.js` et `core.js` dessinent leurs cartes. Rien ne change côté Core.

**Tech Stack:** HTML, CSS, JavaScript en modules ES sans dépendance, testé par `node --test` (un faux DOM) ; la suite Python ne change pas.

**Spec:** `docs/superpowers/specs/2026-09-29-parametres-menu-design.md` (à lire avec ce plan : elle fait foi en cas de doute).

## Global Constraints

- Code, identifiants, textes et commentaires en français, comme le reste du dépôt.
- Aucune nouvelle dépendance ; la page ne charge rien de l'extérieur, n'insère jamais de HTML (`tests/web/page.test.mjs`) ; les icônes sont des SVG écrits dans `index.html`, jamais un emoji ni une image.
- Rien ne change côté Core : les mêmes messages, les mêmes réponses.
- Les rubriques, dans cet ordre : Connecteurs, Voix, Orbe, Fond, Le Core ; leurs phrases, mot pour mot : « Les liens d'Atlas vers l'extérieur. Un connecteur de la communauté demande confirmation avant de s'activer. » ; « Le micro de la page, et le mot qui réveille Atlas. » ; « L'orbe au centre de la page. Un clic l'applique tout de suite. » ; « Le fond derrière l'orbe. » ; « Le Core d'Atlas, sur cette machine ou sur le néo. ».
- Les autres textes, mot pour mot : « ‹ Paramètres » ; « Réglages… » ; « « Hey Atlas » », « Écouter « Hey Atlas » quand le micro est allumé. » ; « Version », « Redémarrer », « La conversation en cours se clôt, avec son résumé au journal. », « Redémarrer… », « Mettre à jour et redémarrer », « Récupère la dernière version, installe ce qui manque, puis redémarre. », « Mettre à jour… » ; les valeurs de la liste : « Aucun actif », « 1 actif », « N actifs », « Hey Atlas », le nom de l'orbe, le nom du fond, la version du Core.
- Écran large : 720 px et plus (Mac, iPad en portrait comme en paysage) ; écran étroit : moins de 720 px (iPhone).
- La dernière rubrique est retenue sur l'appareil (`atlas.rubrique`) ; la première fois, ou si le choix retenu n'existe pas, Connecteurs ; sur un écran étroit, les Paramètres s'ouvrent sur la liste.
- « Muet » reste dans la barre du haut.
- Git : ajouter les fichiers par leur chemin, jamais `git add -A` (le dossier `spikes/` n'est pas suivi et reste privé). Messages de commit en français, terminés par la ligne `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Avant chaque commit : `uv run pytest -q`, `uv run ruff check . --extend-exclude spikes`, `uv run ruff format --check . --extend-exclude spikes`, `node --test "tests/web/*.test.mjs"`.
- Fichiers de moins de 500 lignes : `app.js` finit à 432 ; les styles des Paramètres sont en deux feuilles (`parametres.css` 304, `rubriques.css` 292), `documents.css` passe à 199, `style.css` reste à 439.
- **Copier le code programmatiquement.** Les fichiers neufs sont donnés en entier, les autres par des diffs unifiés exacts (`git apply` les accepte tels quels, copiés d'un bloc) : ne rien retaper à la main.
- Le code de ce plan a été vérifié tel quel avant d'être écrit ici : appliquées dans l'ordre, les 4 tâches donnent 178 tests JavaScript et 1 286 tests Python (1 283, et 3 ignorés, sans `models/silero_vad.onnx`) qui passent, un lint propre, et chaque tâche laisse la suite entière au vert ; la page a été regardée dans un navigateur, en large et en 375 × 812. Les tests ont en outre été mis à l'épreuve par mutations : chaque comportement clé, retiré du code, fait échouer au moins un test. Un écart entre le plan et ce que vous observez est donc à signaler, pas à contourner.

## Review Focus

Les cinq situations que la spec implique sans les décrire, les plus susceptibles de surprendre David ; chacune a son test dans la tâche qui en porte le code.

1. **Remonter au doigt une longue rubrique (iPhone, iPad)** : les Paramètres ne se ferment pas ; seul un geste vers le bas quand la colonne et la rubrique sont en haut les ferme ; les autres panneaux gardent leur geste. Task 2 : `remonter une rubrique au doigt ne ferme pas les Paramètres`.
2. **Un choix retenu qui n'existe plus, ou un navigateur qui interdit le stockage** (navigation privée) : Connecteurs, et la navigation marche sans rien retenir. Task 1 : `un choix retenu qui n'existe plus, ou un stockage interdit, ramène aux connecteurs`.
3. **Passer d'une galerie à une autre rubrique** : la galerie quittée s'arrête (la batterie de l'iPhone). Task 2 : `les Paramètres s'ouvrent sur la dernière rubrique ; une galerie ne tourne que dans la sienne`.
4. **Une liste de connecteurs qui arrive pendant qu'une autre rubrique est affichée** : on la retrouve à jour, et sa valeur dans la liste aussi. Task 2 : `la liste des rubriques dit la valeur de chacune, à jour`.
5. **« ‹ Paramètres » sur un écran large** (la fenêtre élargie, un iPad qui tourne) : la rubrique reste affichée à côté de la colonne ; sur un écran étroit, la liste s'ouvre d'abord et aucune galerie ne tourne derrière. Task 1 : `sur un écran large, le retour ne cache rien` et `sur un écran étroit : la liste d'abord, puis la rubrique, puis le retour`.

## Décisions prises en écrivant le plan

La spec fait foi ; voici ce qu'elle laissait ouvert et ce que le plan en a fait.

1. **La colonne est écrite dans `index.html`** (des boutons `data-rubrique`, leur icône en SVG, leur valeur) : `rubriques.js` les branche, et aucun SVG n'est construit par script.
2. **La largeur est une règle CSS** (`max-width: 719px`) sur `data-vue` ; `app.js` n'interroge la largeur (`matchMedia`) que pour savoir si une rubrique est affichée, et donc si sa galerie doit tourner.
3. **Deux feuilles de styles** : `parametres.css` (la fenêtre, la colonne, l'écran étroit) et `rubriques.css` (les connecteurs, leurs réglages, « Le Core », déplacés de `documents.css`) : une seule dépasserait 500 lignes.
4. **Le bouton courant porte `aria-current="page"`, les autres `"false"`** : le faux DOM des tests n'a pas `removeAttribute`, et `"false"` est une valeur valable.
5. **Le geste de fermeture** : pour les Paramètres, « en haut » veut dire la colonne et la rubrique en haut ; les autres panneaux gardent leur règle.
6. **La carte d'un connecteur** : « Réglages… » (le libellé gagne ses points de suspension) et l'interrupteur à droite ; sur un écran étroit, sous le texte ; « À configurer » et « À installer » en ambre.
7. **La carte « Le Core »** : « Redémarrer… » et « Mettre à jour… » sur les boutons, les titres et les phrases de la maquette ; « … » tant que la version n'est pas arrivée.
8. **Les guides ne changent pas** : « Paramètres › Le Core › « Redémarrer » » et « Paramètres › Connecteurs › Réglages » y restent justes.

## Carte des fichiers

| Fichier | Tâche | Rôle |
|---|---|---|
| `src/atlas_web/rubriques.js` (nouveau) ; `tests/web/faux_dom.mjs` | 1 | La navigation des rubriques |
| `src/atlas_web/index.html`, `parametres.css` et `rubriques.css` (nouveaux), `documents.css`, `app.js`, `connecteurs.js` | 2 | La fenêtre, la colonne, les pages des rubriques, leurs valeurs, le geste de fermeture |
| `src/atlas_web/connecteurs.js`, `reglages.js`, `rubriques.css` | 3 | Les cartes des connecteurs |
| `src/atlas_web/core.js`, `rubriques.css` | 4 | La carte « Le Core » |
| `tests/web/rubriques.test.mjs` (nouveau) ; `tests/web/app.test.mjs`, `connecteurs.test.mjs`, `core.test.mjs` | 1–4 | Tests |

---

### Task 1: La navigation des rubriques

`Rubriques` choisit la rubrique affichée : la dernière retenue sur l'appareil (Connecteurs la première fois, ou si
le choix retenu n'existe plus), un clic dans la colonne, « ‹ Paramètres » ; elle marque le bouton courant
(`aria-current="page"`), remonte la rubrique en haut, et dit à la page quelle rubrique est affichée (null : la liste
seule, sur un écran étroit), pour qu'une galerie n'anime ses aperçus que dans la sienne. La page ne dit que
`data-vue="menu"` ou `"rubrique"` : la largeur est une règle CSS (Task 2). Review Focus 2 et 5.

**Files:**
- Create: `src/atlas_web/rubriques.js`
- Modify: `tests/web/faux_dom.mjs`
- Create: `tests/web/rubriques.test.mjs`

**Interfaces:**
- Consumes: `registre.js` (`lireStockage`, `ecrireStockage`).
- Produces: `src/atlas_web/rubriques.js` : `RUBRIQUES = ["connecteurs", "voix", "orbe", "fond", "core"]`,
  `PAR_DEFAUT = "connecteurs"`, `CLE_RUBRIQUE = "atlas.rubrique"`, `Rubriques({ boutons, pages, panneau, contenu,
  stockage, estEtroit, surChoix })` avec `ouvrir()`, `choisir(id)`, `retour()`, `courante` ; `fauxElement` de
  `tests/web/faux_dom.mjs` gagne `dataset`.

- [ ] **Step 1: Écrire les tests qui échouent**

Modifier `tests/web/faux_dom.mjs` :

```diff
--- a/tests/web/faux_dom.mjs
+++ b/tests/web/faux_dom.mjs
@@ -13,6 +13,7 @@ export function fauxElement(tag) {
     type: "",
     hidden: false,
     attributs: {},
+    dataset: {},
     setAttribute(nom, valeur) {
       this.attributs[nom] = String(valeur);
     },
```

Créer `tests/web/rubriques.test.mjs` :

```javascript
import assert from "node:assert/strict";
import { test } from "node:test";

import { CLE_RUBRIQUE, PAR_DEFAUT, RUBRIQUES, Rubriques } from "../../src/atlas_web/rubriques.js";
import { fauxElement, fauxStockage, stockageCasse } from "./faux_dom.mjs";

function monter({ stockage = fauxStockage(), etroit = false } = {}) {
  const boutons = RUBRIQUES.map((id) => {
    const bouton = fauxElement("button");
    bouton.dataset.rubrique = id;
    return bouton;
  });
  const pages = Object.fromEntries(RUBRIQUES.map((id) => [id, fauxElement("section")]));
  const panneau = fauxElement("section");
  const contenu = fauxElement("div");
  const choix = [];
  const rubriques = new Rubriques({
    boutons,
    pages,
    panneau,
    contenu,
    stockage,
    estEtroit: () => etroit,
    surChoix: (id) => choix.push(id),
  });
  const visibles = () => RUBRIQUES.filter((id) => !pages[id].hidden);
  const courants = () => boutons.filter((b) => b.attributs["aria-current"] === "page").map((b) => b.dataset.rubrique);
  return { rubriques, boutons, pages, panneau, contenu, stockage, choix, visibles, courants };
}

test("cinq rubriques, dans l'ordre de la spec", () => {
  assert.deepEqual(RUBRIQUES, ["connecteurs", "voix", "orbe", "fond", "core"]);
  assert.equal(PAR_DEFAUT, "connecteurs");
});

test("la première ouverture montre les connecteurs", () => {
  const { rubriques, panneau, choix, visibles, courants } = monter();
  rubriques.ouvrir();
  assert.equal(rubriques.courante, "connecteurs");
  assert.deepEqual(visibles(), ["connecteurs"]);
  assert.deepEqual(courants(), ["connecteurs"]);
  assert.equal(panneau.dataset.vue, "menu");
  assert.deepEqual(choix, ["connecteurs"]);
});

test("un clic montre sa rubrique, la marque, la retient et remonte en haut", () => {
  const { rubriques, boutons, panneau, contenu, stockage, choix, visibles, courants } = monter();
  rubriques.ouvrir();
  contenu.scrollTop = 420;
  boutons[3].declencher("click");
  assert.deepEqual(visibles(), ["fond"]);
  assert.deepEqual(courants(), ["fond"]);
  assert.equal(boutons[0].attributs["aria-current"], "false");
  assert.equal(panneau.dataset.vue, "rubrique");
  assert.equal(contenu.scrollTop, 0);
  assert.equal(stockage.getItem(CLE_RUBRIQUE), "fond");
  assert.deepEqual(choix, ["connecteurs", "fond"]);
});

test("rouverts, les Paramètres montrent la dernière rubrique choisie", () => {
  const stockage = fauxStockage({ [CLE_RUBRIQUE]: "core" });
  const { rubriques, visibles } = monter({ stockage });
  rubriques.ouvrir();
  assert.deepEqual(visibles(), ["core"]);
});

test("un choix retenu qui n'existe plus, ou un stockage interdit, ramène aux connecteurs", () => {
  const inconnu = monter({ stockage: fauxStockage({ [CLE_RUBRIQUE]: "meteo" }) });
  inconnu.rubriques.ouvrir();
  assert.deepEqual(inconnu.visibles(), ["connecteurs"]);
  const casse = monter({ stockage: stockageCasse });
  casse.rubriques.ouvrir();
  casse.boutons[1].declencher("click");
  assert.deepEqual(casse.visibles(), ["voix"], "le choix marche, même sans être retenu");
  casse.rubriques.choisir("meteo");
  assert.deepEqual(casse.visibles(), ["voix"], "une rubrique inconnue ne change rien");
});

test("sur un écran étroit : la liste d'abord, puis la rubrique, puis le retour", () => {
  const { rubriques, boutons, panneau, choix } = monter({ etroit: true });
  rubriques.ouvrir();
  assert.equal(panneau.dataset.vue, "menu");
  assert.deepEqual(choix, [null], "aucune rubrique affichée : aucune galerie ne tourne");
  boutons[2].declencher("click");
  assert.equal(panneau.dataset.vue, "rubrique");
  assert.deepEqual(choix, [null, "orbe"]);
  rubriques.retour();
  assert.equal(panneau.dataset.vue, "menu");
  assert.deepEqual(choix, [null, "orbe", null]);
});

test("sur un écran large, le retour ne cache rien", () => {
  const { rubriques, choix } = monter();
  rubriques.ouvrir();
  rubriques.retour();
  assert.deepEqual(choix, ["connecteurs"], "la rubrique reste affichée à côté de la liste");
});
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `node --test tests/web/rubriques.test.mjs`
Expected: FAIL — `Cannot find module '…/src/atlas_web/rubriques.js'`.

- [ ] **Step 3: Écrire la navigation**

Créer `src/atlas_web/rubriques.js` :

```javascript
// Les rubriques des Paramètres (spec des Paramètres, §3) : une colonne à gauche, la rubrique
// choisie à droite ; sur un écran étroit, la liste d'abord, puis la rubrique, avec un retour.
// La page ne dit que « la liste » ou « la rubrique » (`data-vue`) : la largeur est une règle CSS,
// et un écran large montre les deux.

import { ecrireStockage, lireStockage } from "./registre.js";

export const RUBRIQUES = ["connecteurs", "voix", "orbe", "fond", "core"];
export const PAR_DEFAUT = "connecteurs";
export const CLE_RUBRIQUE = "atlas.rubrique";

// `boutons` : ceux de la colonne, chacun avec `data-rubrique` ; `pages` : la section de chaque
// rubrique ; `contenu` : ce qui défile ; `estEtroit()` : l'écran montre-t-il une seule colonne ?
// `surChoix(id)` : la rubrique affichée (null : aucune, la liste seule).
export class Rubriques {
  constructor({ boutons, pages, panneau, contenu, stockage, estEtroit = () => false, surChoix = () => {} }) {
    this._boutons = boutons;
    this._pages = pages;
    this._panneau = panneau;
    this._contenu = contenu;
    this._stockage = stockage;
    this._estEtroit = estEtroit;
    this._surChoix = surChoix;
    this.courante = null;
    for (const bouton of boutons) {
      bouton.addEventListener("click", () => this.choisir(bouton.dataset.rubrique));
    }
  }

  // À l'ouverture des Paramètres : la dernière rubrique choisie sur cet appareil ; sur un
  // écran étroit, la liste d'abord.
  ouvrir() {
    const retenue = lireStockage(this._stockage, CLE_RUBRIQUE);
    this._afficher(RUBRIQUES.includes(retenue) ? retenue : PAR_DEFAUT);
    this._panneau.dataset.vue = "menu";
    this._surChoix(this._estEtroit() ? null : this.courante);
  }

  choisir(id) {
    if (!RUBRIQUES.includes(id)) return;
    ecrireStockage(this._stockage, CLE_RUBRIQUE, id);
    this._afficher(id);
    this._panneau.dataset.vue = "rubrique";
    this._contenu.scrollTop = 0;
    this._surChoix(id);
  }

  // « ‹ Paramètres » : la liste ; sur un écran large, la rubrique reste à côté.
  retour() {
    this._panneau.dataset.vue = "menu";
    if (this._estEtroit()) this._surChoix(null);
  }

  _afficher(id) {
    this.courante = id;
    for (const bouton of this._boutons) {
      bouton.setAttribute("aria-current", bouton.dataset.rubrique === id ? "page" : "false");
    }
    for (const [cle, page] of Object.entries(this._pages)) page.hidden = cle !== id;
  }
}
```

- [ ] **Step 4: Vérifier que tout passe**

Run: `uv run pytest -q && uv run ruff check . --extend-exclude spikes && uv run ruff format --check . --extend-exclude spikes && node --test "tests/web/*.test.mjs"`
Expected: 1286 tests Python passent (3 de moins, et 3 ignorés, si `models/silero_vad.onnx` manque, comme dans une copie neuve), 174 tests JavaScript passent, ruff ne dit rien.

- [ ] **Step 5: Commit**

```bash
git add src/atlas_web/rubriques.js tests/web/faux_dom.mjs tests/web/rubriques.test.mjs
git commit -F - <<'MSG'
Page : la navigation des rubriques des Paramètres

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

### Task 2: La fenêtre des Paramètres : la colonne des rubriques et leurs pages

La nouvelle page : dans `index.html`, la colonne des rubriques (une icône SVG et un mot chacune, et leur valeur pour
l'écran étroit) et une section par rubrique, chacune avec son titre et sa phrase ; `parametres.css` porte la
fenêtre, la colonne et l'écran étroit, `rubriques.css` le contenu des rubriques (déplacé de `documents.css`) ;
`app.js` branche `Rubriques`, n'ouvre une galerie que dans sa rubrique, tient les valeurs de la liste à jour, et
ne ferme les Paramètres d'un geste vers le bas que quand la colonne et la rubrique sont en haut. Review Focus 1, 3
et 4.

**Files:**
- Modify: `src/atlas_web/app.js`
- Modify: `src/atlas_web/connecteurs.js`
- Modify: `src/atlas_web/documents.css`
- Modify: `src/atlas_web/index.html`
- Create: `src/atlas_web/parametres.css`
- Create: `src/atlas_web/rubriques.css`
- Modify: `tests/web/app.test.mjs`
- Modify: `tests/web/connecteurs.test.mjs`

**Interfaces:**
- Consumes: Task 1 (`Rubriques`, `RUBRIQUES`).
- Produces: `connecteurs.js` : `resumeConnecteurs(message) -> string` ; dans `index.html` :
  `#menu-parametres [data-rubrique]`, `#contenu-parametres`, `#retour-parametres`, `#page-connecteurs`, `#page-voix`,
  `#page-orbe`, `#page-fond`, `#page-core`, `#valeur-connecteurs`, `#valeur-voix`, `#valeur-orbe`, `#valeur-fond`,
  `#valeur-core` (les identifiants d'avant restent) ; `parametres.css`, `rubriques.css` ; le faux document de
  `tests/web/app.test.mjs` rend les boutons de la colonne et le panneau ouvert.

- [ ] **Step 1: Écrire les tests qui échouent**

Modifier `tests/web/app.test.mjs` :

```diff
--- a/tests/web/app.test.mjs
+++ b/tests/web/app.test.mjs
@@ -4,6 +4,8 @@ import assert from "node:assert/strict";
 import { test } from "node:test";
 
 import { fauxNavigateurAudio } from "./faux_audio.mjs";
+import { fonds } from "../../src/atlas_web/fonds/index.js";
+import { orbes } from "../../src/atlas_web/orbes/index.js";
 import { fauxElement, fauxStockage } from "./faux_dom.mjs";
 
 // Tous les identifiants cherchés par app.js via $("…") (voir tests/web/page.test.mjs).
@@ -14,6 +16,7 @@ const IDENTIFIANTS = [
   "champ-cle",
   "confirmation",
   "confirmer",
+  "contenu-parametres",
   "formulaire-cle",
   "galerie-fonds",
   "galerie-orbes",
@@ -23,6 +26,7 @@ const IDENTIFIANTS = [
   "liste-connecteurs",
   "liste-documents",
   "liste-historique",
+  "menu-parametres",
   "message-cle",
   "message-voix",
   "micro",
@@ -34,10 +38,16 @@ const IDENTIFIANTS = [
   "panneau-cle",
   "panneau-documents",
   "panneau-historique",
+  "page-connecteurs",
+  "page-core",
+  "page-fond",
+  "page-orbe",
+  "page-voix",
   "panneau-parametres",
   "parler",
   "pastille",
   "retour-documents",
+  "retour-parametres",
   "rubrique-core",
   "saisie",
   "sous-titres",
@@ -46,7 +56,13 @@ const IDENTIFIANTS = [
   "stop-mission",
   "texte-confirmation",
   "texte-mission",
+  "valeur-connecteurs",
+  "valeur-core",
+  "valeur-fond",
+  "valeur-orbe",
+  "valeur-voix",
 ];
+const RUBRIQUES = ["connecteurs", "voix", "orbe", "fond", "core"];
 
 // Un contexte 2D qui lève sur le moindre appel : simule un dessin cassé, quelle qu'en
 // soit la cause (canevas absent, valeur invalide, bogue dans une orbe…).
@@ -94,6 +110,13 @@ function fauxDocumentDeLaPage({ fondSain = false } = {}) {
   }
   elements.fond = fondSain ? canevasSain() : canevasQuiLeve();
   elements.orbe = canevasSain();
+  // Les boutons de la colonne des Paramètres, que app.js cherche par leur data-rubrique.
+  const boutonsRubriques = RUBRIQUES.map((id) => {
+    const bouton = fauxElement("button");
+    bouton.dataset.rubrique = id;
+    return bouton;
+  });
+  const panneaux = ["panneau-historique", "panneau-documents", "panneau-parametres"];
   const ecouteurs = {};
   return {
     hidden: false,
@@ -103,8 +126,9 @@ function fauxDocumentDeLaPage({ fondSain = false } = {}) {
       return element;
     },
     createElement: (tag) => (fondSain && tag === "canvas" ? canevasSain() : fauxElement(tag)),
-    querySelectorAll: () => [],
-    querySelector: () => null,
+    querySelectorAll: (selecteur) => (selecteur === "#menu-parametres [data-rubrique]" ? boutonsRubriques : []),
+    querySelector: (selecteur) =>
+      selecteur === ".panneau:not([hidden])" ? (panneaux.map((id) => elements[id]).find((e) => !e.hidden) ?? null) : null,
     addEventListener(type, rappel) {
       (ecouteurs[type] ??= []).push(rappel);
     },
@@ -551,3 +575,92 @@ test("le Core se redémarre depuis les Paramètres, et la barre du haut suit son
   image();
   assert.notEqual($("libelle-etat").textContent, "Le Core ne revient pas");
 });
+
+async function ouvrirLesParametres(stockage) {
+  FauxWebSocket.ouvertes = [];
+  await chargerPage({ stockage, FabriqueWebSocket: FauxWebSocket });
+  const $ = (id) => document.getElementById(id);
+  const [web] = FauxWebSocket.ouvertes;
+  web.ouvrir();
+  web.recevoir({ type: "historique", echanges: [] });
+  for (const id of ["panneau-historique", "panneau-documents", "panneau-parametres", "panneau-cle"]) {
+    $(id).hidden = true; // fermés, comme au chargement de la vraie page
+  }
+  $("ouvrir-parametres").declencher("click");
+  return { $, web };
+}
+
+test("les Paramètres s'ouvrent sur la dernière rubrique ; une galerie ne tourne que dans la sienne", async () => {
+  const stockage = fauxStockage({ "atlas.cle": "cle", "atlas.rubrique": "orbe" });
+  const { $ } = await ouvrirLesParametres(stockage);
+  const visibles = () => RUBRIQUES.filter((id) => !$(`page-${id}`).hidden);
+  assert.deepEqual(visibles(), ["orbe"]);
+  assert.ok($("galerie-orbes").children.length > 0, "la galerie des orbes tourne");
+  assert.equal($("galerie-fonds").children.length, 0, "celle des fonds attend sa rubrique");
+  const fond = document.querySelectorAll("#menu-parametres [data-rubrique]")[3];
+  fond.declencher("click");
+  assert.deepEqual(visibles(), ["fond"]);
+  assert.ok($("galerie-fonds").children.length > 0);
+  assert.equal($("galerie-orbes").children.length, 0, "la galerie des orbes s'est arrêtée");
+  assert.equal(stockage.getItem("atlas.rubrique"), "fond");
+  assert.equal($("panneau-parametres").dataset.vue, "rubrique");
+  $("retour-parametres").declencher("click");
+  assert.equal($("panneau-parametres").dataset.vue, "menu", "« ‹ Paramètres » revient à la liste");
+});
+
+test("la liste des rubriques dit la valeur de chacune, à jour", async () => {
+  const stockage = fauxStockage({ "atlas.cle": "cle", "atlas.hey_atlas": "1", "atlas.rubrique": "voix" });
+  const { $, web } = await ouvrirLesParametres(stockage);
+  assert.equal($("page-connecteurs").hidden, true, "la rubrique Voix est affichée");
+  assert.equal($("valeur-voix").textContent, "Hey Atlas");
+  assert.equal($("valeur-orbe").textContent, orbes.choisi(stockage).nom);
+  assert.equal($("valeur-fond").textContent, fonds.choisi(stockage).nom);
+  const connecteur = { id: "a", nom: "A", origine: "atlas", etat: "actif", reglages: [] };
+  const connecteurs = [connecteur, { ...connecteur, id: "b" }, { ...connecteur, id: "c", etat: "coupe" }];
+  web.recevoir({ type: "liste_connecteurs", disponible: true, connecteurs });
+  assert.equal($("valeur-connecteurs").textContent, "2 actifs");
+  assert.equal($("liste-connecteurs").children[0].children.length, 3, "à jour, même cachée");
+  web.recevoir({
+    type: "etat_core",
+    version: "ce65d2a",
+    date: "2026-09-29",
+    occupe: false,
+    mise_a_jour_possible: true,
+    raison: "",
+  });
+  assert.equal($("valeur-core").textContent, "ce65d2a");
+  $("hey-atlas").checked = false;
+  $("hey-atlas").declencher("change");
+  assert.equal($("valeur-voix").textContent, "");
+  const orbe = document.querySelectorAll("#menu-parametres [data-rubrique]")[2];
+  orbe.declencher("click");
+  const autre = orbes.tous.find((o) => o.nom !== $("valeur-orbe").textContent);
+  $("galerie-orbes").children[orbes.tous.indexOf(autre)].declencher("click");
+  assert.equal($("valeur-orbe").textContent, autre.nom);
+});
+
+test("remonter une rubrique au doigt ne ferme pas les Paramètres", async () => {
+  const { $ } = await ouvrirLesParametres(fauxStockage({ "atlas.cle": "cle" }));
+  const glisser = () => {
+    document.declencher("touchstart", { touches: [{ clientY: 100 }] });
+    document.declencher("touchend", { changedTouches: [{ clientY: 300 }] });
+  };
+  $("menu-parametres").scrollTop = 0;
+  $("contenu-parametres").scrollTop = 300;
+  glisser();
+  assert.equal($("panneau-parametres").hidden, false, "la rubrique défile vers le haut");
+  $("contenu-parametres").scrollTop = 0;
+  $("menu-parametres").scrollTop = 120;
+  glisser();
+  assert.equal($("panneau-parametres").hidden, false, "la colonne aussi");
+  $("menu-parametres").scrollTop = 0;
+  glisser();
+  assert.equal($("panneau-parametres").hidden, true, "tout en haut, le geste ferme");
+  $("ouvrir-documents").declencher("click"); // un autre panneau défile, lui, tout entier
+  $("panneau-documents").scrollTop = 200;
+  glisser();
+  assert.equal($("panneau-documents").hidden, false);
+  $("panneau-documents").scrollTop = 0;
+  glisser();
+  assert.equal($("panneau-documents").hidden, true);
+});
```

Modifier `tests/web/connecteurs.test.mjs` :

```diff
--- a/tests/web/connecteurs.test.mjs
+++ b/tests/web/connecteurs.test.mjs
@@ -7,6 +7,7 @@ import {
   EN_ATTENTE,
   MEMOIRE_ABSENTE,
   rendreConnecteurs,
+  resumeConnecteurs,
 } from "../../src/atlas_web/connecteurs.js";
 import { fauxDocument } from "./faux_dom.mjs";
 
@@ -169,3 +170,12 @@ test("un connecteur qui a des réglages les ouvre d'un bouton, et les garde ouve
   [, ligne] = rendu();
   assert.equal(ligne.reste.at(-1).hidden, true, "refermé, il le reste");
 });
+
+test("le résumé des connecteurs, pour la liste des rubriques", () => {
+  const liste = (...etats) => ({ disponible: true, connecteurs: etats.map((etat, i) => ({ ...POSTE, id: `c${i}`, etat })) });
+  assert.equal(resumeConnecteurs({ disponible: false, connecteurs: [] }), "");
+  assert.equal(resumeConnecteurs(null), "", "avant la première liste");
+  assert.equal(resumeConnecteurs(liste("coupe", "en_erreur")), "Aucun actif");
+  assert.equal(resumeConnecteurs(liste("actif", "coupe")), "1 actif");
+  assert.equal(resumeConnecteurs(liste("actif", "actif", "actif")), "3 actifs");
+});
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `node --test tests/web/app.test.mjs tests/web/connecteurs.test.mjs`
Expected: FAIL — `connecteurs.js` n'exporte pas `resumeConnecteurs`, et les 3 tests neufs de la page échouent.

- [ ] **Step 3: Écrire la fenêtre et la brancher**

Modifier `src/atlas_web/app.js` :

```diff
--- a/src/atlas_web/app.js
+++ b/src/atlas_web/app.js
@@ -1,6 +1,6 @@
 // Le démarrage de la page : relie la connexion, la voix, l'état, l'orbe, le fond et les panneaux.
 
-import { rendreConnecteurs } from "./connecteurs.js";
+import { rendreConnecteurs, resumeConnecteurs } from "./connecteurs.js";
 import { Connexion, identifiantDePage } from "./connexion.js";
 import { SuiviCore, rendreCore } from "./core.js";
 import { dimensionner, rgba } from "./dessin.js";
@@ -11,6 +11,7 @@ import { rendreHistorique } from "./historique.js";
 import { orbes } from "./orbes/index.js";
 import { ouvrirGalerie } from "./parametres.js";
 import { ecrireStockage, lireStockage } from "./registre.js";
+import { Rubriques } from "./rubriques.js";
 import { afficherSousTitres } from "./sous_titres.js";
 import { Voix } from "./voix.js";
 
@@ -77,6 +78,7 @@ let listeConnecteurs = null;
 function montrerConnecteurs() {
   const surBascule = (id, actif) => connexion.envoyer({ type: "activer_connecteur", id, actif });
   rendreConnecteurs(document, $("liste-connecteurs"), listeConnecteurs, surBascule, reglages);
+  $("valeur-connecteurs").textContent = resumeConnecteurs(listeConnecteurs);
 }
 
 // Le Core : sa version, ses deux boutons, les étapes ; et son retour, attendu après un redémarrage.
@@ -84,6 +86,7 @@ const suiviCore = new SuiviCore({ envoyer: (message) => connexion.envoyer(messag
 
 function montrerCore() {
   rendreCore(document, $("rubrique-core"), suiviCore.etat, (type) => connexion.envoyer({ type }));
+  $("valeur-core").textContent = suiviCore.etat.version?.version ?? "";
 }
 
 const connexion = new Connexion({
@@ -164,9 +167,11 @@ $("message-voix").addEventListener("click", () => {
   if (voix.statut === "a_reactiver") voix.reactiver();
 });
 $("hey-atlas").checked = lireStockage(stockage, CLE_HEY_ATLAS) === "1";
+$("valeur-voix").textContent = $("hey-atlas").checked ? "Hey Atlas" : "";
 $("hey-atlas").addEventListener("change", () => {
   ecrireStockage(stockage, CLE_HEY_ATLAS, $("hey-atlas").checked ? "1" : "0");
   voix.changerHeyAtlas($("hey-atlas").checked);
+  $("valeur-voix").textContent = $("hey-atlas").checked ? "Hey Atlas" : "";
 });
 
 function demanderCle(message) {
@@ -265,31 +270,54 @@ $("retour-documents").addEventListener("click", montrerLaListe);
 
 // --- Les panneaux -----------------------------------------------------------------
 
+// Les rubriques des Paramètres : une colonne à gauche, la rubrique à droite ; sur un écran
+// étroit, la liste puis la rubrique. Chacune dit sa valeur dans la liste.
+const rubriques = new Rubriques({
+  boutons: [...document.querySelectorAll("#menu-parametres [data-rubrique]")],
+  pages: {
+    connecteurs: $("page-connecteurs"),
+    voix: $("page-voix"),
+    orbe: $("page-orbe"),
+    fond: $("page-fond"),
+    core: $("page-core"),
+  },
+  panneau: $("panneau-parametres"),
+  contenu: $("contenu-parametres"),
+  stockage,
+  estEtroit: () => window.matchMedia("(max-width: 719px)").matches,
+  surChoix: montrerGalerie,
+});
+$("retour-parametres").addEventListener("click", () => rubriques.retour());
+$("valeur-orbe").textContent = orbes.choisi(stockage).nom;
+$("valeur-fond").textContent = fonds.choisi(stockage).nom;
+
 function ouvrirParametres() {
   connexion.envoyer({ type: "connecteurs" }); // relus à chaque ouverture : un dossier a pu être déposé
   reglages.ouverts.clear(); // chaque ouverture repart d'une liste fermée, sans vieux message
   reglages.resultats.clear();
   suiviCore.demander();
   montrerCore();
+  rubriques.ouvrir();
+}
+
+// Une galerie n'anime ses aperçus que tant que sa rubrique est affichée (`id`, ou null : aucune).
+function montrerGalerie(id) {
+  for (const galerie of galeries) galerie.fermer();
+  galeries = [];
   const commun = { document, stockage, scene: () => sceneCourante };
-  galeries = [
-    ouvrirGalerie({
-      ...commun,
-      conteneur: $("galerie-orbes"),
-      registre: orbes,
-      surChoix: (choix) => {
-        orbe = choix.creer($("orbe"));
-      },
-    }),
-    ouvrirGalerie({
-      ...commun,
-      conteneur: $("galerie-fonds"),
-      registre: fonds,
-      surChoix: (choix) => {
-        fond = choix.creer($("fond"));
-      },
-    }),
-  ];
+  if (id === "orbe") {
+    const surChoix = (choix) => {
+      orbe = choix.creer($("orbe"));
+      $("valeur-orbe").textContent = choix.nom;
+    };
+    galeries = [ouvrirGalerie({ ...commun, conteneur: $("galerie-orbes"), registre: orbes, surChoix })];
+  } else if (id === "fond") {
+    const surChoix = (choix) => {
+      fond = choix.creer($("fond"));
+      $("valeur-fond").textContent = choix.nom;
+    };
+    galeries = [ouvrirGalerie({ ...commun, conteneur: $("galerie-fonds"), registre: fonds, surChoix })];
+  }
 }
 
 function ouvrirPanneau(panneau) {
@@ -322,6 +350,12 @@ document.addEventListener("keydown", (evenement) => {
 });
 
 // Glisser vers le haut ouvre l'historique ; vers le bas, depuis le haut d'un panneau, le ferme.
+// Les Paramètres ne défilent pas eux-mêmes : leur colonne et leur rubrique, si.
+function enHautDe(panneau) {
+  if (panneau !== $("panneau-parametres")) return panneau.scrollTop === 0;
+  return $("menu-parametres").scrollTop === 0 && $("contenu-parametres").scrollTop === 0;
+}
+
 let depart = null;
 document.addEventListener(
   "touchstart",
@@ -331,7 +365,7 @@ document.addEventListener(
       return;
     }
     const ouvert = document.querySelector(".panneau:not([hidden])");
-    depart = { y: evenement.touches[0].clientY, ouvert, enHaut: !ouvert || ouvert.scrollTop === 0 };
+    depart = { y: evenement.touches[0].clientY, ouvert, enHaut: !ouvert || enHautDe(ouvert) };
   },
   { passive: true },
 );
```

Modifier `src/atlas_web/connecteurs.js` :

```diff
--- a/src/atlas_web/connecteurs.js
+++ b/src/atlas_web/connecteurs.js
@@ -31,6 +31,14 @@ function bouton(document, classe, contenu) {
   return element;
 }
 
+// La valeur de « Connecteurs » dans la liste des rubriques (écran étroit) : combien sont actifs.
+export function resumeConnecteurs(message) {
+  if (!message?.disponible) return "";
+  const actifs = message.connecteurs.filter((connecteur) => connecteur.etat === "actif").length;
+  if (actifs === 0) return "Aucun actif";
+  return actifs === 1 ? "1 actif" : `${actifs} actifs`;
+}
+
 // La liste (message `liste_connecteurs`) ; `surBascule(id, actif)` envoie l'interrupteur au Core.
 // `reglages` : `surRegler(id, valeurs, effacer)`, et ce qui survit à un nouveau rendu de la
 // liste : les réglages ouverts (`ouverts`, des identifiants) et les dernières réponses du Core
```

Modifier `src/atlas_web/documents.css` :

```diff
--- a/src/atlas_web/documents.css
+++ b/src/atlas_web/documents.css
@@ -1,6 +1,5 @@
 /* Le panneau « Documents » et la confirmation d'une action (N3) : spec 2c §7 ; la barre de
-   mission : spec du poste §5 ; la rubrique « Connecteurs » des Paramètres : spec des
-   connecteurs §6. */
+   mission : spec du poste §5. Les Paramètres ont leurs feuilles : parametres.css, rubriques.css. */
 
 /* Les documents : la liste, puis la lecture d'un document mis en forme. */
 .panneau > header #retour-documents {
@@ -198,211 +197,3 @@
   outline: 2px solid var(--accent);
   outline-offset: 2px;
 }
-
-/* Les connecteurs : une ligne chacun, son état, son interrupteur, et l'avertissement d'un
-   connecteur de la communauté. */
-#liste-connecteurs .connecteurs {
-  list-style: none;
-  margin: 0;
-  padding: 0;
-}
-
-#liste-connecteurs .connecteur {
-  padding: 10px 0;
-  border-top: 1px solid var(--bord);
-}
-
-#liste-connecteurs .tete {
-  display: flex;
-  align-items: center;
-  gap: 8px;
-}
-
-#liste-connecteurs .nom {
-  flex: 1;
-  font-weight: 600;
-}
-
-#liste-connecteurs .badge {
-  padding: 1px 8px;
-  border-radius: 10px;
-  border: 1px solid var(--bord);
-  font-size: 12px;
-  color: var(--texte-doux);
-}
-
-#liste-connecteurs .badge.communaute {
-  border-color: rgba(251, 191, 36, 0.5);
-  color: var(--accent);
-}
-
-#liste-connecteurs p {
-  margin: 4px 0 0;
-}
-
-#liste-connecteurs .description,
-#liste-connecteurs .signature,
-#liste-connecteurs .vide {
-  color: var(--texte-doux);
-}
-
-#liste-connecteurs .signature,
-#liste-connecteurs .etat,
-#liste-connecteurs .attente {
-  font-size: 12px;
-}
-
-#liste-connecteurs .etat.en_erreur {
-  color: var(--erreur);
-}
-
-#liste-connecteurs .attente {
-  color: var(--accent);
-}
-
-#liste-connecteurs .avertissement {
-  margin-top: 8px;
-  padding: 10px 12px;
-  border-radius: 12px;
-  border: 1px solid rgba(251, 191, 36, 0.5);
-}
-
-#liste-connecteurs .avertissement button {
-  margin: 8px 8px 0 0;
-  padding: 6px 14px;
-  border-radius: 16px;
-  border: 1px solid var(--bord);
-}
-
-#liste-connecteurs .avertissement .activer {
-  background: var(--accent);
-  border-color: var(--accent);
-  color: #02030a;
-}
-
-/* Les réglages d'un connecteur : un champ chacun ; la valeur d'un secret n'y est jamais. */
-#liste-connecteurs .ouvrir-reglages {
-  margin-top: 6px;
-  font-size: 12px;
-  color: var(--accent);
-}
-
-#liste-connecteurs .reglages {
-  margin-top: 8px;
-  padding: 10px 12px;
-  border-radius: 12px;
-  border: 1px solid var(--bord);
-}
-
-#liste-connecteurs .reglage label {
-  display: flex;
-  flex-direction: column;
-  gap: 4px;
-  font-size: 13px;
-}
-
-#liste-connecteurs .reglage + .reglage {
-  margin-top: 10px;
-}
-
-#liste-connecteurs .reglage .variable,
-#liste-connecteurs .reglage .statut {
-  font-size: 11px;
-  color: var(--texte-doux);
-}
-
-#liste-connecteurs .reglage input {
-  padding: 8px 12px;
-  border-radius: 10px;
-  border: 1px solid var(--bord);
-  background: var(--verre);
-  color: var(--texte);
-  font: inherit;
-}
-
-#liste-connecteurs .reglage input:focus {
-  outline: none;
-  border-color: rgba(251, 191, 36, 0.6);
-}
-
-#liste-connecteurs .reglages button {
-  margin: 8px 8px 0 0;
-  padding: 6px 14px;
-  border-radius: 16px;
-  border: 1px solid var(--bord);
-}
-
-#liste-connecteurs .reglages .enregistrer {
-  background: var(--accent);
-  border-color: var(--accent);
-  color: #02030a;
-}
-
-#liste-connecteurs .reglages .resultat {
-  font-size: 12px;
-  color: var(--accent);
-}
-
-#liste-connecteurs .reglages .resultat.refus {
-  color: var(--erreur);
-}
-
-/* La rubrique « Le Core » : sa version, ses deux boutons, leur confirmation, et les étapes
-   d'un redémarrage ou d'une mise à jour. */
-#rubrique-core p {
-  margin: 4px 0 0;
-  font-size: 13px;
-}
-
-#rubrique-core .version,
-#rubrique-core .raison,
-#rubrique-core .nouveautes {
-  font-size: 12px;
-  color: var(--texte-doux);
-}
-
-#rubrique-core button {
-  margin: 8px 8px 0 0;
-  padding: 6px 14px;
-  border-radius: 16px;
-  border: 1px solid var(--bord);
-}
-
-#rubrique-core button:disabled {
-  opacity: 0.4;
-  cursor: not-allowed;
-}
-
-#rubrique-core .confirmation-core {
-  margin-top: 8px;
-  padding: 10px 12px;
-  border-radius: 12px;
-  border: 1px solid rgba(251, 191, 36, 0.5);
-}
-
-#rubrique-core .confirmer {
-  background: var(--accent);
-  border-color: var(--accent);
-  color: #02030a;
-}
-
-#rubrique-core .etape,
-#rubrique-core .fin.ok {
-  color: var(--accent);
-}
-
-#rubrique-core .fin.refus {
-  color: var(--erreur);
-}
-
-#rubrique-core .nouveautes {
-  margin: 4px 0 0;
-  padding-left: 18px;
-}
-
-#rubrique-core .details {
-  margin: 6px 0 0;
-  font-size: 11px;
-  white-space: pre-wrap;
-  color: var(--texte-doux);
-}
```

Modifier `src/atlas_web/index.html` :

```diff
--- a/src/atlas_web/index.html
+++ b/src/atlas_web/index.html
@@ -8,6 +8,8 @@
   <link rel="icon" href="data:,">
   <link rel="stylesheet" href="style.css">
   <link rel="stylesheet" href="documents.css">
+  <link rel="stylesheet" href="parametres.css">
+  <link rel="stylesheet" href="rubriques.css">
   <script type="module" src="app.js"></script>
 </head>
 <body>
@@ -81,24 +83,79 @@
     <article id="lecture-document" hidden></article>
   </section>
 
-  <section id="panneau-parametres" class="panneau" aria-label="Paramètres" hidden>
-    <header>
-      <h2>Paramètres</h2>
-      <button type="button" class="icone fermer" aria-label="Fermer">✕</button>
-    </header>
-    <h3>Connecteurs</h3>
-    <div id="liste-connecteurs"></div>
-    <h3>Voix</h3>
-    <label class="interrupteur">
-      <input type="checkbox" id="hey-atlas">
-      <span>Écouter « Hey Atlas » quand le micro est allumé</span>
-    </label>
-    <h3>Orbe</h3>
-    <div id="galerie-orbes" class="galerie"></div>
-    <h3>Fond</h3>
-    <div id="galerie-fonds" class="galerie fonds"></div>
-    <h3>Le Core</h3>
-    <div id="rubrique-core"></div>
+  <section id="panneau-parametres" class="panneau" aria-label="Paramètres" data-vue="menu" hidden>
+    <nav id="menu-parametres" aria-label="Rubriques des Paramètres">
+      <header>
+        <h2>Paramètres</h2>
+        <button type="button" class="icone fermer" aria-label="Fermer">✕</button>
+      </header>
+      <div class="rubriques">
+        <button type="button" data-rubrique="connecteurs">
+          <span class="icone-rubrique connecteurs"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 3v4M15 3v4M7 7h10v3a5 5 0 0 1-10 0V7zM12 15v6"/></svg></span>
+          <span class="nom">Connecteurs</span>
+          <span class="valeur" id="valeur-connecteurs"></span>
+        </button>
+        <button type="button" data-rubrique="voix">
+          <span class="icone-rubrique voix"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 10v4M8 7v10M12 4v16M16 7v10M20 10v4"/></svg></span>
+          <span class="nom">Voix</span>
+          <span class="valeur" id="valeur-voix"></span>
+        </button>
+        <button type="button" data-rubrique="orbe">
+          <span class="icone-rubrique orbe"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M16 12a4 4 0 1 1-8 0a4 4 0 1 1 8 0zM22 12c0 2.2-4.5 4-10 4S2 14.2 2 12s4.5-4 10-4s10 1.8 10 4z"/></svg></span>
+          <span class="nom">Orbe</span>
+          <span class="valeur" id="valeur-orbe"></span>
+        </button>
+        <button type="button" data-rubrique="fond">
+          <span class="icone-rubrique fond"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5h16a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1zM3 16l5-5 4 4 3-3 6 6"/></svg></span>
+          <span class="nom">Fond</span>
+          <span class="valeur" id="valeur-fond"></span>
+        </button>
+        <button type="button" data-rubrique="core">
+          <span class="icone-rubrique core"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 4h16v7H4zM4 13h16v7H4zM8 7.5h.01M8 16.5h.01"/></svg></span>
+          <span class="nom">Le Core</span>
+          <span class="valeur" id="valeur-core"></span>
+        </button>
+      </div>
+    </nav>
+    <div id="contenu-parametres">
+      <header>
+        <button type="button" id="retour-parametres" class="retour">‹ Paramètres</button>
+        <button type="button" class="icone fermer" aria-label="Fermer">✕</button>
+      </header>
+      <section id="page-connecteurs" class="page" aria-label="Connecteurs">
+        <h2>Connecteurs</h2>
+        <p class="phrase">Les liens d'Atlas vers l'extérieur. Un connecteur de la communauté demande confirmation avant de s'activer.</p>
+        <div id="liste-connecteurs"></div>
+      </section>
+      <section id="page-voix" class="page" aria-label="Voix" hidden>
+        <h2>Voix</h2>
+        <p class="phrase">Le micro de la page, et le mot qui réveille Atlas.</p>
+        <div class="groupe">
+          <label class="interrupteur ligne">
+            <span class="texte">
+              <span class="titre">« Hey Atlas »</span>
+              <span class="detail">Écouter « Hey Atlas » quand le micro est allumé.</span>
+            </span>
+            <input type="checkbox" id="hey-atlas">
+          </label>
+        </div>
+      </section>
+      <section id="page-orbe" class="page" aria-label="Orbe" hidden>
+        <h2>Orbe</h2>
+        <p class="phrase">L'orbe au centre de la page. Un clic l'applique tout de suite.</p>
+        <div id="galerie-orbes" class="galerie"></div>
+      </section>
+      <section id="page-fond" class="page" aria-label="Fond" hidden>
+        <h2>Fond</h2>
+        <p class="phrase">Le fond derrière l'orbe.</p>
+        <div id="galerie-fonds" class="galerie fonds"></div>
+      </section>
+      <section id="page-core" class="page" aria-label="Le Core" hidden>
+        <h2>Le Core</h2>
+        <p class="phrase">Le Core d'Atlas, sur cette machine ou sur le néo.</p>
+        <div id="rubrique-core"></div>
+      </section>
+    </div>
   </section>
 
   <section id="panneau-cle" class="cle" hidden>
```

Créer `src/atlas_web/parametres.css` :

```css
/* Les Paramètres (spec des Paramètres) : comme les Réglages Système du Mac, une colonne de
   rubriques à gauche (une icône et un mot) et la rubrique choisie à droite, dans une fenêtre
   par-dessus l'orbe. Sous 720 px, une seule colonne : la liste (data-vue="menu"), puis la
   rubrique (data-vue="rubrique"), avec « ‹ Paramètres ». */
#panneau-parametres {
  top: 50%;
  bottom: auto;
  transform: translate(-50%, -50%);
  display: flex;
  width: min(920px, calc(100vw - 32px));
  height: min(640px, calc(100vh - 32px));
  max-height: none;
  padding: 0;
  overflow: hidden;
  border-bottom: 1px solid var(--bord);
  border-radius: 18px;
  box-shadow: 0 30px 80px rgba(0, 0, 0, 0.6);
}

#menu-parametres {
  width: 236px;
  flex-shrink: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 18px 12px;
  background: rgba(255, 255, 255, 0.03);
  border-right: 1px solid var(--bord);
}

#menu-parametres > header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 2px 10px 14px;
}

#menu-parametres .fermer {
  display: none;
}

#menu-parametres .rubriques {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

#menu-parametres [data-rubrique] {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  min-height: 44px;
  padding: 0 10px;
  border-radius: 10px;
  font-size: 15px;
  text-align: left;
}

#menu-parametres [data-rubrique][aria-current="page"] {
  background: rgba(251, 191, 36, 0.16);
  color: #fde68a;
}

#menu-parametres [data-rubrique]:focus-visible,
#contenu-parametres .retour:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: -2px;
}

#menu-parametres .nom {
  flex-grow: 1;
}

#menu-parametres .valeur {
  display: none;
  color: var(--texte-doux);
}

/* L'icône d'une rubrique : un trait blanc sur un carré arrondi de couleur. */
.icone-rubrique {
  width: 28px;
  height: 28px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 7px;
}

.icone-rubrique svg {
  width: 18px;
  height: 18px;
  fill: none;
  stroke: #ffffff;
  stroke-width: 1.9;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.icone-rubrique.connecteurs {
  background: #2563eb;
}

.icone-rubrique.voix {
  background: #db2777;
}

.icone-rubrique.orbe {
  background: #b45309;
}

.icone-rubrique.fond {
  background: #0f766e;
}

.icone-rubrique.core {
  background: #475569;
}

#contenu-parametres {
  flex-grow: 1;
  min-width: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 0 28px 28px;
}

#contenu-parametres > header {
  position: sticky;
  top: 0;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding: 14px 0 4px;
  background: var(--verre-fort);
}

#contenu-parametres .retour {
  display: none;
  align-items: center;
  min-height: 44px;
  padding: 0;
  font-size: 17px;
  color: var(--accent);
}

.page h2 {
  margin: 0 0 6px;
  font-size: 22px;
  font-weight: 650;
}

.page .phrase {
  margin: 0 0 16px;
  font-size: 13px;
  color: var(--texte-doux);
}

/* Une carte groupée, comme dans les Réglages Système : un fond à peine plus clair, un bord fin. */
.page .groupe {
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
}

#page-voix .ligne {
  justify-content: space-between;
  gap: 16px;
  padding: 14px 16px;
  font-size: 15px;
  color: var(--texte);
}

.page .ligne .texte {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.page .ligne .titre {
  font-weight: 600;
}

.page .ligne .detail {
  font-size: 13px;
  color: var(--texte-doux);
}

#galerie-orbes {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

#galerie-fonds {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

/* Un écran étroit (iPhone) : les Paramètres couvrent l'écran, une colonne à la fois. */
@media (max-width: 719px) {
  #panneau-parametres {
    inset: 0;
    transform: none;
    display: block;
    width: auto;
    height: auto;
    border: 0;
    border-radius: 0;
  }

  #panneau-parametres[data-vue="menu"] #contenu-parametres,
  #panneau-parametres[data-vue="rubrique"] #menu-parametres {
    display: none;
  }

  #menu-parametres,
  #contenu-parametres {
    width: auto;
    height: 100%;
    padding: max(12px, env(safe-area-inset-top)) var(--marge) max(32px, env(safe-area-inset-bottom));
    border-right: 0;
    background: none;
  }

  #menu-parametres > header {
    padding: 8px 0 16px;
  }

  #menu-parametres h2,
  .page h2 {
    font-size: 30px;
    font-weight: 700;
  }

  #menu-parametres .fermer,
  #contenu-parametres .retour {
    display: inline-flex;
  }

  #menu-parametres .rubriques {
    gap: 0;
    overflow: hidden;
    border-radius: 12px;
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.08);
  }

  #menu-parametres [data-rubrique] {
    min-height: 52px;
    padding: 0 14px;
    border-radius: 0;
    font-size: 17px;
  }

  #menu-parametres [data-rubrique] + [data-rubrique] {
    border-top: 1px solid rgba(255, 255, 255, 0.08);
  }

  #menu-parametres [data-rubrique][aria-current="page"] {
    background: none;
    color: var(--texte);
  }

  #menu-parametres [data-rubrique]::after {
    content: "›";
    font-size: 22px;
    color: var(--texte-doux);
  }

  #menu-parametres .valeur {
    display: inline;
    font-size: 15px;
  }

  #contenu-parametres > header {
    justify-content: space-between;
    padding: 0 0 4px;
  }

  #galerie-orbes {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  #galerie-fonds {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  /* Des interrupteurs plus grands, pour le doigt. */
  #panneau-parametres .interrupteur input {
    width: 51px;
    height: 31px;
    border-radius: 16px;
  }

  #panneau-parametres .interrupteur input::after {
    width: 27px;
    height: 27px;
    top: 2px;
    left: 2px;
  }

  #panneau-parametres .interrupteur input:checked::after {
    transform: translateX(20px);
  }
}
```

Créer `src/atlas_web/rubriques.css` :

```css
/* Le contenu des rubriques des Paramètres : les connecteurs et leurs réglages, et « Le Core ».
   La disposition des Paramètres est dans parametres.css. */

/* Les connecteurs : une ligne chacun, son état, son interrupteur, et l'avertissement d'un
   connecteur de la communauté. */
#liste-connecteurs .connecteurs {
  list-style: none;
  margin: 0;
  padding: 0;
}

#liste-connecteurs .connecteur {
  padding: 10px 0;
  border-top: 1px solid var(--bord);
}

#liste-connecteurs .tete {
  display: flex;
  align-items: center;
  gap: 8px;
}

#liste-connecteurs .nom {
  flex: 1;
  font-weight: 600;
}

#liste-connecteurs .badge {
  padding: 1px 8px;
  border-radius: 10px;
  border: 1px solid var(--bord);
  font-size: 12px;
  color: var(--texte-doux);
}

#liste-connecteurs .badge.communaute {
  border-color: rgba(251, 191, 36, 0.5);
  color: var(--accent);
}

#liste-connecteurs p {
  margin: 4px 0 0;
}

#liste-connecteurs .description,
#liste-connecteurs .signature,
#liste-connecteurs .vide {
  color: var(--texte-doux);
}

#liste-connecteurs .signature,
#liste-connecteurs .etat,
#liste-connecteurs .attente {
  font-size: 12px;
}

#liste-connecteurs .etat.en_erreur {
  color: var(--erreur);
}

#liste-connecteurs .attente {
  color: var(--accent);
}

#liste-connecteurs .avertissement {
  margin-top: 8px;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid rgba(251, 191, 36, 0.5);
}

#liste-connecteurs .avertissement button {
  margin: 8px 8px 0 0;
  padding: 6px 14px;
  border-radius: 16px;
  border: 1px solid var(--bord);
}

#liste-connecteurs .avertissement .activer {
  background: var(--accent);
  border-color: var(--accent);
  color: #02030a;
}

/* Les réglages d'un connecteur : un champ chacun ; la valeur d'un secret n'y est jamais. */
#liste-connecteurs .ouvrir-reglages {
  margin-top: 6px;
  font-size: 12px;
  color: var(--accent);
}

#liste-connecteurs .reglages {
  margin-top: 8px;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid var(--bord);
}

#liste-connecteurs .reglage label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
}

#liste-connecteurs .reglage + .reglage {
  margin-top: 10px;
}

#liste-connecteurs .reglage .variable,
#liste-connecteurs .reglage .statut {
  font-size: 11px;
  color: var(--texte-doux);
}

#liste-connecteurs .reglage input {
  padding: 8px 12px;
  border-radius: 10px;
  border: 1px solid var(--bord);
  background: var(--verre);
  color: var(--texte);
  font: inherit;
}

#liste-connecteurs .reglage input:focus {
  outline: none;
  border-color: rgba(251, 191, 36, 0.6);
}

#liste-connecteurs .reglages button {
  margin: 8px 8px 0 0;
  padding: 6px 14px;
  border-radius: 16px;
  border: 1px solid var(--bord);
}

#liste-connecteurs .reglages .enregistrer {
  background: var(--accent);
  border-color: var(--accent);
  color: #02030a;
}

#liste-connecteurs .reglages .resultat {
  font-size: 12px;
  color: var(--accent);
}

#liste-connecteurs .reglages .resultat.refus {
  color: var(--erreur);
}

/* La rubrique « Le Core » : sa version, ses deux boutons, leur confirmation, et les étapes
   d'un redémarrage ou d'une mise à jour. */
#rubrique-core p {
  margin: 4px 0 0;
  font-size: 13px;
}

#rubrique-core .version,
#rubrique-core .raison,
#rubrique-core .nouveautes {
  font-size: 12px;
  color: var(--texte-doux);
}

#rubrique-core button {
  margin: 8px 8px 0 0;
  padding: 6px 14px;
  border-radius: 16px;
  border: 1px solid var(--bord);
}

#rubrique-core button:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

#rubrique-core .confirmation-core {
  margin-top: 8px;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid rgba(251, 191, 36, 0.5);
}

#rubrique-core .confirmer {
  background: var(--accent);
  border-color: var(--accent);
  color: #02030a;
}

#rubrique-core .etape,
#rubrique-core .fin.ok {
  color: var(--accent);
}

#rubrique-core .fin.refus {
  color: var(--erreur);
}

#rubrique-core .nouveautes {
  margin: 4px 0 0;
  padding-left: 18px;
}

#rubrique-core .details {
  margin: 6px 0 0;
  font-size: 11px;
  white-space: pre-wrap;
  color: var(--texte-doux);
}
```

Vérifier aussi à l'œil, dans un navigateur, la page servie telle quelle (`src/atlas_web/`, sans Core : fermer la
demande de clé, puis ⚙) : en large, la fenêtre et sa colonne ; en 375 × 812, la liste des rubriques, une rubrique
et « ‹ Paramètres ».

- [ ] **Step 4: Vérifier que tout passe**

Run: `uv run pytest -q && uv run ruff check . --extend-exclude spikes && uv run ruff format --check . --extend-exclude spikes && node --test "tests/web/*.test.mjs"`
Expected: 1286 tests Python passent (3 de moins, et 3 ignorés, si `models/silero_vad.onnx` manque, comme dans une copie neuve), 178 tests JavaScript passent, ruff ne dit rien.

- [ ] **Step 5: Commit**

```bash
git add src/atlas_web/app.js src/atlas_web/connecteurs.js src/atlas_web/documents.css src/atlas_web/index.html src/atlas_web/parametres.css src/atlas_web/rubriques.css tests/web/app.test.mjs tests/web/connecteurs.test.mjs
git commit -F - <<'MSG'
Page : les Paramètres en fenêtre, une colonne de rubriques et la rubrique à droite

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

### Task 3: Les cartes des connecteurs

Chaque connecteur devient une carte, comme dans les Réglages Système : à gauche son nom, son badge, sa description,
sa signature et son état (« À configurer » et « À installer » en ambre) ; à droite « Réglages… » (s'il en a) et son
interrupteur ; dessous l'avertissement « Communauté » et ses réglages, sous une ligne de séparation. Sur un écran
étroit, les actions passent sous le texte.

**Files:**
- Modify: `src/atlas_web/connecteurs.js`
- Modify: `src/atlas_web/reglages.js`
- Modify: `src/atlas_web/rubriques.css`
- Modify: `tests/web/app.test.mjs`
- Modify: `tests/web/connecteurs.test.mjs`

**Interfaces:**
- Consumes: Task 2 (`rubriques.css`), `reglages.js` (`rendreReglages`, `REGLAGES`).
- Produces: une carte `li.connecteur` = `[div.entete [div.texte [div.titre [nom, badge], infos…], div.actions
  [« Réglages… » ?, label.interrupteur]], div.avertissement, form.reglages ?]` ; `REGLAGES = "Réglages…"`.

- [ ] **Step 1: Écrire les tests qui échouent**

Modifier `tests/web/app.test.mjs` :

```diff
--- a/tests/web/app.test.mjs
+++ b/tests/web/app.test.mjs
@@ -472,8 +472,8 @@ test("les Paramètres demandent les connecteurs, les montrent, et envoient une b
   };
   web.recevoir({ type: "liste_connecteurs", disponible: true, connecteurs: [poste] });
   const [liste] = $("liste-connecteurs").children;
-  const [tete] = liste.children[0].children;
-  const interrupteur = tete.children[2].children[0];
+  const [entete] = liste.children[0].children;
+  const interrupteur = entete.children[1].children.at(-1).children[0];
   interrupteur.checked = true;
   interrupteur.declencher("change");
   assert.deepEqual(web.envoyes.at(-1), { type: "activer_connecteur", id: "poste", actif: true });
@@ -505,7 +505,9 @@ test("les réglages d'un connecteur partent au Core, et sa réponse s'affiche ju
     reglages: [nom],
   };
   const regle = { ...bonjour, etat: "coupe", detail: "", reglages: [{ ...nom, defini: true, valeur: "David" }] };
-  const derniers = () => $("liste-connecteurs").children[0].children[0].children.slice(-2);
+  // La carte : [entête [texte, actions [« Réglages… », interrupteur]], avertissement, réglages].
+  const carte = () => $("liste-connecteurs").children[0].children[0];
+  const derniers = () => [carte().children[0].children[1].children[0], carte().children.at(-1)];
   web.recevoir({ type: "liste_connecteurs", disponible: true, connecteurs: [bonjour] });
   let [ouvrir, formulaire] = derniers();
   ouvrir.declencher("click");
```

Modifier `tests/web/connecteurs.test.mjs` :

```diff
--- a/tests/web/connecteurs.test.mjs
+++ b/tests/web/connecteurs.test.mjs
@@ -44,20 +44,31 @@ function lignes(conteneur) {
   return conteneur.children[0].children;
 }
 
+// Une carte : [entête [texte [titre [nom, badge], infos…], actions [« Réglages… » ?, interrupteur]],
+// avertissement, réglages ?].
 function morceaux(ligne) {
-  const [tete, ...reste] = ligne.children;
-  const [nom, badge, bascule] = tete.children;
-  return { nom, badge, bascule, interrupteur: bascule.children[0], reste };
+  const [entete, avertissement, formulaire] = ligne.children;
+  const [texte, actions] = entete.children;
+  const [titre, ...infos] = texte.children;
+  const [nom, badge] = titre.children;
+  const bascule = actions.children.at(-1);
+  const ouvrir = actions.children.length > 1 ? actions.children[0] : undefined;
+  return { entete, nom, badge, infos, actions, ouvrir, bascule, interrupteur: bascule.children[0], avertissement, formulaire };
 }
 
-test("chaque connecteur a sa ligne : nom, badge, description, signature, état, interrupteur", () => {
+test("chaque connecteur a sa carte : nom, badge, description, signature, état, et son interrupteur à droite", () => {
   const { conteneur } = rendre([POSTE, METEO]);
   assert.equal(conteneur.children[0].tagName, "UL");
   const [poste, meteo] = lignes(conteneur).map(morceaux);
+  assert.deepEqual(
+    [poste.entete.className, poste.actions.className, poste.actions.children.length],
+    ["entete", "actions", 1],
+    "sans réglages, l'interrupteur seul",
+  );
   assert.equal(poste.nom.textContent, "Le poste du Mac");
   assert.deepEqual([poste.badge.className, poste.badge.textContent], ["badge atlas", "Atlas"]);
   assert.deepEqual(
-    poste.reste.slice(0, 3).map((p) => [p.className, p.textContent]),
+    poste.infos.slice(0, 3).map((p) => [p.className, p.textContent]),
     [
       ["description", "Atlas pilote le Mac."],
       ["signature", "version 1.0.0 · Atlas"],
@@ -71,7 +82,8 @@ test("chaque connecteur a sa ligne : nom, badge, description, signature, état,
     "habillé comme « Hey Atlas »",
   );
   assert.deepEqual([poste.interrupteur.checked, poste.interrupteur.disabled], [false, false]);
-  assert.ok(!poste.reste.some((p) => p.className === "attente"), "rien n'attend : rien à dire");
+  assert.ok(!poste.infos.some((p) => p.className === "attente"), "rien n'attend : rien à dire");
+  assert.equal(poste.formulaire, undefined);
   assert.equal(meteo.badge.textContent, "Communauté");
   assert.equal(meteo.nom.textContent, "<b>Météo</b>", "le texte d'un manifeste reste du texte");
 });
@@ -85,14 +97,14 @@ test("un connecteur qui n'est pas activable a son interrupteur grisé, et dit po
   ];
   const [actif, aConfigurer, aInstaller, enErreur] = lignes(rendre(cas).conteneur).map(morceaux);
   assert.deepEqual([actif.interrupteur.checked, actif.interrupteur.disabled], [true, false]);
-  assert.ok(actif.reste.some((p) => p.className === "attente" && p.textContent === EN_ATTENTE));
+  assert.ok(actif.infos.some((p) => p.className === "attente" && p.textContent === EN_ATTENTE));
   for (const [ligne, texte] of [
     [aConfigurer, "À configurer : il manque ATLAS_POSTE_CLE dans le .env du Core"],
     [aInstaller, "À installer : lance make install (il manque caldav)"],
     [enErreur, "En erreur : connecteur.toml absent"],
   ]) {
     assert.equal(ligne.interrupteur.disabled, true);
-    assert.ok(ligne.reste.some((p) => p.textContent === texte), texte);
+    assert.ok(ligne.infos.some((p) => p.textContent === texte), texte);
   }
 });
 
@@ -112,7 +124,8 @@ test("un connecteur d'Atlas s'active et se coupe d'un toucher", () => {
 test("un connecteur de la communauté demande confirmation avant de s'activer, jamais pour se couper", () => {
   const { conteneur, bascules } = rendre([METEO, { ...METEO, id: "radio", etat: "actif" }]);
   const [meteo, radio] = lignes(conteneur).map(morceaux);
-  const avertissement = meteo.reste.at(-1);
+  const avertissement = meteo.avertissement;
+  assert.equal(avertissement.className, "avertissement");
   assert.equal(avertissement.hidden, true);
   meteo.interrupteur.checked = true;
   meteo.interrupteur.declencher("change");
@@ -151,15 +164,16 @@ test("un connecteur qui a des réglages les ouvre d'un bouton, et les garde ouve
     return lignes(conteneur).map(morceaux);
   };
   let [poste, ligne] = rendu();
-  assert.ok(!poste.reste.some((e) => e.className === "ouvrir-reglages"), "sans réglages, pas de bouton");
-  let [ouvrir, formulaire] = ligne.reste.slice(-2);
-  assert.deepEqual([ouvrir.textContent, ouvrir.type, formulaire.tagName], ["Réglages", "button", "FORM"]);
+  assert.equal(poste.ouvrir, undefined, "sans réglages, pas de bouton");
+  let { ouvrir, formulaire } = ligne;
+  assert.deepEqual([ouvrir.textContent, ouvrir.type, formulaire.tagName], ["Réglages…", "button", "FORM"]);
+  assert.equal(ligne.actions.children[1], ligne.bascule, "« Réglages… » à côté de l'interrupteur");
   assert.deepEqual([formulaire.hidden, ouvrir.attributs["aria-expanded"]], [true, "false"]);
   ouvrir.declencher("click");
   assert.deepEqual([formulaire.hidden, ouvrir.attributs["aria-expanded"]], [false, "true"]);
   etat.resultats.set("bonjour", { ok: true, message: "Enregistré." });
   [, ligne] = rendu();
-  [ouvrir, formulaire] = ligne.reste.slice(-2);
+  ({ ouvrir, formulaire } = ligne);
   assert.equal(formulaire.hidden, false, "toujours ouvert après un nouveau rendu");
   assert.equal(formulaire.children.at(-1).textContent, "Enregistré.");
   formulaire.children[0].children[0].children[2].value = "David";
@@ -168,7 +182,7 @@ test("un connecteur qui a des réglages les ouvre d'un bouton, et les garde ouve
   ouvrir.declencher("click");
   assert.equal(etat.ouverts.has("bonjour"), false);
   [, ligne] = rendu();
-  assert.equal(ligne.reste.at(-1).hidden, true, "refermé, il le reste");
+  assert.equal(ligne.formulaire.hidden, true, "refermé, il le reste");
 });
 
 test("le résumé des connecteurs, pour la liste des rubriques", () => {
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `node --test tests/web/connecteurs.test.mjs tests/web/app.test.mjs`
Expected: FAIL — `7 failed` : les tests lisent la carte, que la page ne dessine pas encore.

- [ ] **Step 3: Écrire la carte**

Modifier `src/atlas_web/connecteurs.js` :

```diff
--- a/src/atlas_web/connecteurs.js
+++ b/src/atlas_web/connecteurs.js
@@ -56,50 +56,42 @@ export function rendreConnecteurs(document, conteneur, message, surBascule, regl
   const liste = document.createElement("ul");
   liste.className = "connecteurs";
   for (const connecteur of message.connecteurs) {
-    const element = ligne(document, connecteur, surBascule);
-    if (connecteur.reglages?.length) {
-      element.append(...lesReglages(document, connecteur, surRegler, ouverts, resultats));
-    }
-    liste.append(element);
+    liste.append(carte(document, connecteur, surBascule, surRegler, ouverts, resultats));
   }
   conteneur.replaceChildren(liste);
 }
 
-// Le bouton « Réglages » et son formulaire, ouvert ou fermé comme avant le nouveau rendu.
-function lesReglages(document, connecteur, surRegler, ouverts, resultats) {
-  const ouvrir = bouton(document, "ouvrir-reglages", REGLAGES);
-  const formulaire = rendreReglages(document, connecteur, surRegler, resultats.get(connecteur.id));
-  const montrer = (ouvert) => {
-    formulaire.hidden = !ouvert;
-    ouvrir.setAttribute("aria-expanded", String(ouvert));
-    if (ouvert) ouverts.add(connecteur.id);
-    else ouverts.delete(connecteur.id);
-  };
-  montrer(ouverts.has(connecteur.id));
-  ouvrir.addEventListener("click", () => montrer(formulaire.hidden));
-  return [ouvrir, formulaire];
-}
-
-function ligne(document, connecteur, surBascule) {
+// Une carte : l'entête (le texte à gauche ; « Réglages… » et l'interrupteur à droite),
+// l'avertissement « Communauté », puis les réglages, sous une ligne de séparation.
+function carte(document, connecteur, surBascule, surRegler, ouverts, resultats) {
   const element = document.createElement("li");
   element.className = "connecteur";
-  const interrupteur = document.createElement("input");
-  interrupteur.type = "checkbox";
-  interrupteur.checked = connecteur.etat === "actif";
-  interrupteur.disabled = connecteur.etat !== "actif" && connecteur.etat !== "coupe";
-  interrupteur.setAttribute("aria-label", `Activer ${connecteur.nom}`);
-  // Habillé comme « Muet » et « Hey Atlas » : une glissière, pas une case.
-  const bascule = document.createElement("label");
-  bascule.className = "interrupteur";
-  bascule.append(interrupteur);
-  const tete = document.createElement("div");
-  tete.className = "tete";
-  tete.append(
+  const { bascule, interrupteur } = lInterrupteur(document, connecteur);
+  const actions = document.createElement("div");
+  actions.className = "actions";
+  const entete = document.createElement("div");
+  entete.className = "entete";
+  entete.append(leTexte(document, connecteur), actions);
+  element.append(entete, lAvertissement(document, connecteur, interrupteur, surBascule));
+  if (connecteur.reglages?.length) {
+    const [ouvrir, formulaire] = lesReglages(document, connecteur, surRegler, ouverts, resultats);
+    actions.append(ouvrir);
+    element.append(formulaire);
+  }
+  actions.append(bascule);
+  return element;
+}
+
+function leTexte(document, connecteur) {
+  const titre = document.createElement("div");
+  titre.className = "titre";
+  titre.append(
     texte(document, "span", "nom", connecteur.nom),
     texte(document, "span", `badge ${connecteur.origine}`, ORIGINES[connecteur.origine]),
-    bascule,
   );
-  element.append(tete);
+  const element = document.createElement("div");
+  element.className = "texte";
+  element.append(titre);
   if (connecteur.description) element.append(texte(document, "p", "description", connecteur.description));
   const signature = [connecteur.version && `version ${connecteur.version}`, connecteur.auteur];
   const quoi = signature.filter(Boolean).join(" · ");
@@ -107,16 +99,30 @@ function ligne(document, connecteur, surBascule) {
   const etat = [ETATS[connecteur.etat], connecteur.detail].filter(Boolean).join(" : ");
   element.append(texte(document, "p", `etat ${connecteur.etat}`, etat));
   if (connecteur.en_attente) element.append(texte(document, "p", "attente", EN_ATTENTE));
+  return element;
+}
+
+function lInterrupteur(document, connecteur) {
+  const interrupteur = document.createElement("input");
+  interrupteur.type = "checkbox";
+  interrupteur.checked = connecteur.etat === "actif";
+  interrupteur.disabled = connecteur.etat !== "actif" && connecteur.etat !== "coupe";
+  interrupteur.setAttribute("aria-label", `Activer ${connecteur.nom}`);
+  // Habillé comme « Muet » et « Hey Atlas » : une glissière, pas une case.
+  const bascule = document.createElement("label");
+  bascule.className = "interrupteur";
+  bascule.append(interrupteur);
+  return { bascule, interrupteur };
+}
 
-  // Un connecteur de la communauté : l'avertissement d'abord, l'activation ensuite.
+// Un connecteur de la communauté : l'avertissement d'abord, l'activation ensuite.
+function lAvertissement(document, connecteur, interrupteur, surBascule) {
   const avertissement = document.createElement("div");
   avertissement.className = "avertissement";
   avertissement.hidden = true;
   const activer = bouton(document, "activer", "Activer quand même");
   const annuler = bouton(document, "annuler", "Annuler");
   avertissement.append(texte(document, "p", "", AVERTISSEMENT), activer, annuler);
-  element.append(avertissement);
-
   interrupteur.addEventListener("change", () => {
     if (interrupteur.checked && connecteur.origine === "communaute") {
       interrupteur.checked = false;
@@ -132,5 +138,20 @@ function ligne(document, connecteur, surBascule) {
   annuler.addEventListener("click", () => {
     avertissement.hidden = true;
   });
-  return element;
+  return avertissement;
+}
+
+// Le bouton « Réglages… » et son formulaire, ouvert ou fermé comme avant le nouveau rendu.
+function lesReglages(document, connecteur, surRegler, ouverts, resultats) {
+  const ouvrir = bouton(document, "ouvrir-reglages", REGLAGES);
+  const formulaire = rendreReglages(document, connecteur, surRegler, resultats.get(connecteur.id));
+  const montrer = (ouvert) => {
+    formulaire.hidden = !ouvert;
+    ouvrir.setAttribute("aria-expanded", String(ouvert));
+    if (ouvert) ouverts.add(connecteur.id);
+    else ouverts.delete(connecteur.id);
+  };
+  montrer(ouverts.has(connecteur.id));
+  ouvrir.addEventListener("click", () => montrer(formulaire.hidden));
+  return [ouvrir, formulaire];
 }
```

Modifier `src/atlas_web/reglages.js` :

```diff
--- a/src/atlas_web/reglages.js
+++ b/src/atlas_web/reglages.js
@@ -2,7 +2,7 @@
 // un champ par réglage. La valeur d'un secret n'arrive jamais dans la page : elle dit seulement
 // s'il est défini, et un champ masqué le remplace. Le Core vérifie tout.
 
-export const REGLAGES = "Réglages";
+export const REGLAGES = "Réglages…";
 export const ENREGISTRER = "Enregistrer";
 export const EFFACER = "Effacer";
 export const DEFINI = "Défini";
```

Modifier `src/atlas_web/rubriques.css` :

```diff
--- a/src/atlas_web/rubriques.css
+++ b/src/atlas_web/rubriques.css
@@ -1,30 +1,54 @@
 /* Le contenu des rubriques des Paramètres : les connecteurs et leurs réglages, et « Le Core ».
    La disposition des Paramètres est dans parametres.css. */
 
-/* Les connecteurs : une ligne chacun, son état, son interrupteur, et l'avertissement d'un
-   connecteur de la communauté. */
+/* Les connecteurs : une carte chacun ; à gauche son nom, sa description et son état, à droite
+   « Réglages… » et son interrupteur ; dessous, l'avertissement « Communauté » et ses réglages. */
 #liste-connecteurs .connecteurs {
+  display: flex;
+  flex-direction: column;
+  gap: 12px;
   list-style: none;
   margin: 0;
   padding: 0;
 }
 
 #liste-connecteurs .connecteur {
-  padding: 10px 0;
-  border-top: 1px solid var(--bord);
+  padding: 14px 16px;
+  border-radius: 12px;
+  background: rgba(255, 255, 255, 0.04);
+  border: 1px solid rgba(255, 255, 255, 0.08);
+}
+
+#liste-connecteurs .entete {
+  display: flex;
+  align-items: flex-start;
+  gap: 16px;
+}
+
+#liste-connecteurs .texte {
+  flex-grow: 1;
+  min-width: 0;
 }
 
-#liste-connecteurs .tete {
+#liste-connecteurs .titre {
   display: flex;
+  flex-wrap: wrap;
   align-items: center;
   gap: 8px;
 }
 
 #liste-connecteurs .nom {
-  flex: 1;
+  font-size: 15px;
   font-weight: 600;
 }
 
+#liste-connecteurs .actions {
+  display: flex;
+  flex-shrink: 0;
+  align-items: center;
+  gap: 12px;
+}
+
 #liste-connecteurs .badge {
   padding: 1px 8px;
   border-radius: 10px;
@@ -48,12 +72,21 @@
   color: var(--texte-doux);
 }
 
+#liste-connecteurs .description {
+  font-size: 13px;
+}
+
 #liste-connecteurs .signature,
 #liste-connecteurs .etat,
 #liste-connecteurs .attente {
   font-size: 12px;
 }
 
+#liste-connecteurs .etat.a_configurer,
+#liste-connecteurs .etat.a_installer {
+  color: var(--accent);
+}
+
 #liste-connecteurs .etat.en_erreur {
   color: var(--erreur);
 }
@@ -84,16 +117,23 @@
 
 /* Les réglages d'un connecteur : un champ chacun ; la valeur d'un secret n'y est jamais. */
 #liste-connecteurs .ouvrir-reglages {
-  margin-top: 6px;
-  font-size: 12px;
-  color: var(--accent);
+  height: 30px;
+  padding: 0 12px;
+  border-radius: 15px;
+  border: 1px solid rgba(255, 255, 255, 0.14);
+  background: rgba(255, 255, 255, 0.06);
+  font-size: 13px;
+}
+
+#liste-connecteurs .ouvrir-reglages:focus-visible {
+  outline: 2px solid var(--accent);
+  outline-offset: 2px;
 }
 
 #liste-connecteurs .reglages {
-  margin-top: 8px;
-  padding: 10px 12px;
-  border-radius: 12px;
-  border: 1px solid var(--bord);
+  margin-top: 12px;
+  padding-top: 12px;
+  border-top: 1px solid rgba(255, 255, 255, 0.08);
 }
 
 #liste-connecteurs .reglage label {
@@ -149,6 +189,24 @@
   color: var(--erreur);
 }
 
+/* Sur un écran étroit, les actions passent sous le texte : « Réglages… » à gauche,
+   l'interrupteur à droite. */
+@media (max-width: 719px) {
+  #liste-connecteurs .entete {
+    flex-direction: column;
+    gap: 12px;
+  }
+
+  #liste-connecteurs .actions {
+    align-self: stretch;
+    justify-content: flex-end;
+  }
+
+  #liste-connecteurs .ouvrir-reglages {
+    margin-right: auto;
+  }
+}
+
 /* La rubrique « Le Core » : sa version, ses deux boutons, leur confirmation, et les étapes
    d'un redémarrage ou d'une mise à jour. */
 #rubrique-core p {
```

- [ ] **Step 4: Vérifier que tout passe**

Run: `uv run pytest -q && uv run ruff check . --extend-exclude spikes && uv run ruff format --check . --extend-exclude spikes && node --test "tests/web/*.test.mjs"`
Expected: 1286 tests Python passent (3 de moins, et 3 ignorés, si `models/silero_vad.onnx` manque, comme dans une copie neuve), 178 tests JavaScript passent, ruff ne dit rien.

- [ ] **Step 5: Commit**

```bash
git add src/atlas_web/connecteurs.js src/atlas_web/reglages.js src/atlas_web/rubriques.css tests/web/app.test.mjs tests/web/connecteurs.test.mjs
git commit -F - <<'MSG'
Page : une carte par connecteur, « Réglages… » à côté de son interrupteur

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

### Task 4: La carte « Le Core »

La rubrique « Le Core » devient une carte : la version, puis une ligne par action, sa phrase à gauche, son bouton à
droite (« Redémarrer… », « Mettre à jour… », grisé avec sa raison dessous quand ce n'est pas possible) ; la
confirmation, les étapes et la fin restent dessous.

**Files:**
- Modify: `src/atlas_web/core.js`
- Modify: `src/atlas_web/rubriques.css`
- Modify: `tests/web/app.test.mjs`
- Modify: `tests/web/core.test.mjs`

**Interfaces:**
- Consumes: Task 2 (`rubriques.css`), `SuiviCore` (inchangé).
- Produces: `core.js` : `REDEMARRER = "Redémarrer…"`, `METTRE_A_JOUR = "Mettre à jour…"`, `ACTIONS` (titre et
  phrase de chaque action) ; la rubrique = `[div.groupe [ligne version [« Version », valeur], ligne « Redémarrer »,
  ligne « Mettre à jour et redémarrer »], p.raison ?, div.confirmation-core, …]`.

- [ ] **Step 1: Écrire les tests qui échouent**

Modifier `tests/web/app.test.mjs` :

```diff
--- a/tests/web/app.test.mjs
+++ b/tests/web/app.test.mjs
@@ -554,9 +554,9 @@ test("le Core se redémarre depuis les Paramètres, et la barre du haut suit son
     mise_a_jour_possible: true,
     raison: "",
   });
-  const [version, boutons, confirmation] = $("rubrique-core").children;
-  assert.equal(version.textContent, "Version ce65d2a, du 2026-09-29");
-  boutons.children[0].declencher("click"); // « Redémarrer »
+  const [groupe, confirmation] = $("rubrique-core").children;
+  assert.equal(groupe.children[0].children[1].textContent, "ce65d2a, du 2026-09-29");
+  groupe.children[1].children[1].declencher("click"); // « Redémarrer… »
   confirmation.children[1].declencher("click"); // « Confirmer »
   assert.deepEqual(web.envoyes.at(-1), { type: "redemarrer_core" });
 
```

Modifier `tests/web/core.test.mjs` :

```diff
--- a/tests/web/core.test.mjs
+++ b/tests/web/core.test.mjs
@@ -27,13 +27,22 @@ function rendre(etat) {
   const actions = [];
   rendreCore(document, conteneur, etat, (type) => actions.push(type));
   const par = (classe) => conteneur.children.find((e) => e.className === classe);
-  const [redemarrer, mettreAJour] = par("boutons").children;
-  return { conteneur, par, redemarrer, mettreAJour, actions };
+  // La carte : la version, puis une ligne par action : [texte [titre, phrase], bouton].
+  const lignes = par("groupe").children;
+  const [redemarrer, mettreAJour] = lignes.slice(1).map((ligne) => ligne.children[1]);
+  return { conteneur, par, lignes, version: lignes[0].children[1], redemarrer, mettreAJour, actions };
 }
 
-test("la version qui tourne, et deux boutons qui demandent confirmation", () => {
-  const { par, redemarrer, mettreAJour, actions } = rendre({ version: VERSION, enCours: null, fin: null });
-  assert.equal(par("version").textContent, "Version ce65d2a, du 2026-09-29");
+test("la version qui tourne, et deux actions qui demandent confirmation", () => {
+  const { par, lignes, version, redemarrer, mettreAJour, actions } = rendre({ version: VERSION, enCours: null, fin: null });
+  assert.deepEqual([lignes[0].children[0].textContent, version.textContent], ["Version", "ce65d2a, du 2026-09-29"]);
+  assert.deepEqual(
+    lignes.slice(1).map((ligne) => [...ligne.children[0].children.map((e) => e.textContent), ligne.children[1].textContent]),
+    [
+      ["Redémarrer", "La conversation en cours se clôt, avec son résumé au journal.", "Redémarrer…"],
+      ["Mettre à jour et redémarrer", "Récupère la dernière version, installe ce qui manque, puis redémarre.", "Mettre à jour…"],
+    ],
+  );
   assert.deepEqual([redemarrer.disabled, mettreAJour.disabled], [false, false]);
   const confirmation = par("confirmation-core");
   assert.equal(confirmation.hidden, true);
@@ -56,8 +65,8 @@ test("la mise à jour impossible est grisée, avec sa raison", () => {
 });
 
 test("avant la version, ou pendant une étape, les boutons attendent", () => {
-  let { par, redemarrer, mettreAJour } = rendre({ version: null, enCours: null, fin: null });
-  assert.equal(par("version").textContent, "Version…");
+  let { par, version, redemarrer, mettreAJour } = rendre({ version: null, enCours: null, fin: null });
+  assert.equal(version.textContent, "…");
   assert.deepEqual([redemarrer.disabled, mettreAJour.disabled], [true, true]);
   const enCours = { etape: "installation", texte: "Installation…", nouveautes: ["Deux", "Un"] };
   ({ par, redemarrer, mettreAJour } = rendre({ version: VERSION, enCours, fin: null }));
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `node --test tests/web/core.test.mjs tests/web/app.test.mjs`
Expected: FAIL — `5 failed` : les tests lisent la carte, que la page ne dessine pas encore.

- [ ] **Step 3: Écrire la carte**

Modifier `src/atlas_web/core.js` :

```diff
--- a/src/atlas_web/core.js
+++ b/src/atlas_web/core.js
@@ -2,8 +2,16 @@
 // qui tourne, « Redémarrer » et « Mettre à jour et redémarrer », chacun confirmé ; les étapes et
 // la fin, que toutes les pages voient ; et, pendant un redémarrage, le retour du Core attendu.
 
-export const REDEMARRER = "Redémarrer";
-export const METTRE_A_JOUR = "Mettre à jour et redémarrer";
+export const REDEMARRER = "Redémarrer…";
+export const METTRE_A_JOUR = "Mettre à jour…";
+// Chaque action de la carte : son titre, et ce qu'elle fait.
+export const ACTIONS = {
+  redemarrer_core: ["Redémarrer", "La conversation en cours se clôt, avec son résumé au journal."],
+  mettre_a_jour_core: [
+    "Mettre à jour et redémarrer",
+    "Récupère la dernière version, installe ce qui manque, puis redémarre.",
+  ],
+};
 export const CONFIRMATIONS = {
   redemarrer_core:
     "Redémarrer le Core ? La conversation en cours se clôt, avec son résumé au journal. Atlas revient dans une dizaine de secondes.",
@@ -102,23 +110,42 @@ function bouton(document, classe, contenu) {
   return element;
 }
 
+function ligneAction(document, [titre, phrase], action) {
+  const libelles = document.createElement("span");
+  libelles.className = "texte";
+  libelles.append(texte(document, "span", "titre", titre), texte(document, "span", "detail", phrase));
+  const ligne = document.createElement("div");
+  ligne.className = "ligne";
+  ligne.append(libelles, action);
+  return ligne;
+}
+
 // La rubrique ; `surAction(type)` envoie « redemarrer_core » ou « mettre_a_jour_core », une
 // fois confirmé.
 export function rendreCore(document, conteneur, etat, surAction) {
   const { version, enCours, fin } = etat;
   const elements = [];
   const quand = version?.date ? `, du ${version.date}` : "";
-  elements.push(texte(document, "p", "version", version ? `Version ${version.version}${quand}` : "Version…"));
-
   const occupe = Boolean(enCours) || Boolean(version?.occupe);
   const redemarrer = bouton(document, "redemarrer", REDEMARRER);
   const mettreAJour = bouton(document, "mettre-a-jour", METTRE_A_JOUR);
   redemarrer.disabled = !version || occupe;
   mettreAJour.disabled = !version || occupe || !version.mise_a_jour_possible;
-  const boutons = document.createElement("div");
-  boutons.className = "boutons";
-  boutons.append(redemarrer, mettreAJour);
-  elements.push(boutons);
+  // Une carte : la version, puis une ligne par action, sa phrase à gauche, son bouton à droite.
+  const ligneVersion = document.createElement("div");
+  ligneVersion.className = "ligne version";
+  ligneVersion.append(
+    texte(document, "span", "", "Version"),
+    texte(document, "span", "valeur", version ? `${version.version}${quand}` : "…"),
+  );
+  const groupe = document.createElement("div");
+  groupe.className = "groupe";
+  groupe.append(
+    ligneVersion,
+    ligneAction(document, ACTIONS.redemarrer_core, redemarrer),
+    ligneAction(document, ACTIONS.mettre_a_jour_core, mettreAJour),
+  );
+  elements.push(groupe);
   if (version && !version.mise_a_jour_possible && version.raison) {
     elements.push(texte(document, "p", "raison", version.raison));
   }
```

Modifier `src/atlas_web/rubriques.css` :

```diff
--- a/src/atlas_web/rubriques.css
+++ b/src/atlas_web/rubriques.css
@@ -207,20 +207,38 @@
   }
 }
 
-/* La rubrique « Le Core » : sa version, ses deux boutons, leur confirmation, et les étapes
-   d'un redémarrage ou d'une mise à jour. */
+/* La rubrique « Le Core » : une carte (la version, puis une ligne par action, sa phrase à
+   gauche, son bouton à droite), la confirmation, et les étapes d'un redémarrage ou d'une mise
+   à jour. */
 #rubrique-core p {
   margin: 4px 0 0;
   font-size: 13px;
 }
 
-#rubrique-core .version,
+#rubrique-core .ligne {
+  display: flex;
+  align-items: center;
+  justify-content: space-between;
+  gap: 16px;
+  padding: 14px 16px;
+  font-size: 15px;
+}
+
+#rubrique-core .ligne + .ligne {
+  border-top: 1px solid rgba(255, 255, 255, 0.08);
+}
+
+#rubrique-core .version .valeur,
 #rubrique-core .raison,
 #rubrique-core .nouveautes {
   font-size: 12px;
   color: var(--texte-doux);
 }
 
+#rubrique-core .version .valeur {
+  font-size: 14px;
+}
+
 #rubrique-core button {
   margin: 8px 8px 0 0;
   padding: 6px 14px;
@@ -228,6 +246,12 @@
   border: 1px solid var(--bord);
 }
 
+#rubrique-core .ligne button {
+  flex-shrink: 0;
+  margin: 0;
+  background: rgba(255, 255, 255, 0.06);
+}
+
 #rubrique-core button:disabled {
   opacity: 0.4;
   cursor: not-allowed;
```

Vérifier aussi à l'œil la rubrique « Le Core » (la même page servie telle quelle, la carte dessinée avec un état
d'exemple) : la version, les deux actions, la raison et la confirmation.

- [ ] **Step 4: Vérifier que tout passe**

Run: `uv run pytest -q && uv run ruff check . --extend-exclude spikes && uv run ruff format --check . --extend-exclude spikes && node --test "tests/web/*.test.mjs"`
Expected: 1286 tests Python passent (3 de moins, et 3 ignorés, si `models/silero_vad.onnx` manque, comme dans une copie neuve), 178 tests JavaScript passent, ruff ne dit rien.

- [ ] **Step 5: Commit**

```bash
git add src/atlas_web/core.js src/atlas_web/rubriques.css tests/web/app.test.mjs tests/web/core.test.mjs
git commit -F - <<'MSG'
Page : la carte « Le Core », une ligne par action

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

---

## L'essai avec David

Après la Task 4, sur la branche `parametres-menu`, avant la PR. Les critères sont ceux du §1 de la spec.

1. **Mac** : `make run-core`, la page ouverte ; ⚙ : la fenêtre, la colonne (Connecteurs, Voix, Orbe, Fond, Le Core,
   chacune avec son icône) ; chaque rubrique s'affiche à droite ; fermer, rouvrir : la dernière rubrique choisie.
2. **Rien de perdu** : un connecteur s'active et se coupe ; ses réglages s'ouvrent par « Réglages… » ; la
   confirmation « Communauté » ; « Hey Atlas » ; une orbe, un fond ; « Redémarrer… ».
3. **iPad**, en portrait et en paysage : les deux colonnes.
4. **iPhone** : la liste des rubriques et leurs valeurs ; un toucher ouvre la rubrique ; « ‹ Paramètres » revient ;
   remonter une longue rubrique au doigt ne ferme pas les Paramètres.
5. `make test` au vert.

Ce qui ne va pas devient une correction sur la branche, avec son test, avant la PR.

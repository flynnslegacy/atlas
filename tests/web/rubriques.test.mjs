import assert from "node:assert/strict";
import { test } from "node:test";

import { CLE_RUBRIQUE, PAR_DEFAUT, RUBRIQUES, Rubriques } from "../../src/atlas_web/rubriques.js";
import { fauxElement, fauxStockage, stockageCasse } from "./faux_dom.mjs";

function monter({ stockage = fauxStockage(), etroit = false } = {}) {
  const focus = []; // qui a reçu le focus, dans l'ordre
  const boutons = RUBRIQUES.map((id) => {
    const bouton = fauxElement("button");
    bouton.dataset.rubrique = id;
    bouton.focus = () => focus.push(id);
    return bouton;
  });
  const boutonRetour = fauxElement("button");
  boutonRetour.focus = () => focus.push("retour");
  const pages = Object.fromEntries(RUBRIQUES.map((id) => [id, fauxElement("section")]));
  const panneau = fauxElement("section");
  const contenu = fauxElement("div");
  const menu = fauxElement("nav");
  const choix = [];
  const ecran = { etroit };
  const rubriques = new Rubriques({
    boutons,
    pages,
    panneau,
    contenu,
    menu,
    boutonRetour,
    stockage,
    estEtroit: () => ecran.etroit,
    surChoix: (id) => choix.push(id),
  });
  const visibles = () => RUBRIQUES.filter((id) => !pages[id].hidden);
  const courants = () => boutons.filter((b) => b.attributs["aria-current"] === "page").map((b) => b.dataset.rubrique);
  return { rubriques, boutons, pages, panneau, contenu, menu, stockage, choix, ecran, focus, visibles, courants };
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

test("une largeur qui change pendant que les Paramètres sont ouverts : la galerie suit", () => {
  const stockage = fauxStockage({ [CLE_RUBRIQUE]: "orbe" });
  const { rubriques, ecran, choix } = monter({ stockage });
  rubriques.ouvrir(); // large : l'orbe à droite
  ecran.etroit = true; // la fenêtre rétrécit : la liste seule
  rubriques.surLargeur();
  ecran.etroit = false; // elle s'élargit : la rubrique revient à droite
  rubriques.surLargeur();
  assert.deepEqual(choix, ["orbe", null, "orbe"]);
  ecran.etroit = true;
  rubriques.choisir("fond"); // étroit, la rubrique affichée
  rubriques.surLargeur();
  assert.deepEqual(choix.slice(-2), ["fond", "fond"], "étroit, dans une rubrique : elle reste");
});

test("sur un écran étroit, le focus suit : la liste, la rubrique, puis la liste", () => {
  // La colonne et la rubrique se cachent l'une l'autre : sans cela, le focus tomberait derrière
  // les Paramètres, qui couvrent l'écran (VoiceOver perdrait sa place).
  const { rubriques, boutons, focus } = monter({ etroit: true });
  rubriques.ouvrir();
  assert.deepEqual(focus, ["connecteurs"], "à l'ouverture, la rubrique courante de la liste");
  boutons[2].declencher("click");
  assert.equal(focus.at(-1), "retour", "dans la rubrique : « ‹ Paramètres »");
  rubriques.retour();
  assert.equal(focus.at(-1), "orbe", "de retour : la rubrique qu'on vient de quitter");
});

test("sur un écran large, le bouton cliqué garde le focus", () => {
  const { rubriques, boutons, focus } = monter();
  rubriques.ouvrir();
  boutons[1].declencher("click");
  assert.deepEqual(focus, ["connecteurs"], "seule l'ouverture le déplace");
});

test("rouverts, les Paramètres repartent en haut, la colonne comme la rubrique", () => {
  // Comme avant la refonte ; sinon, le geste vers le bas ne les fermerait plus.
  const { rubriques, contenu, menu } = monter();
  contenu.scrollTop = 500;
  menu.scrollTop = 120;
  rubriques.ouvrir();
  assert.deepEqual([contenu.scrollTop, menu.scrollTop], [0, 0]);
});

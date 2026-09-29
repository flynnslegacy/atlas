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

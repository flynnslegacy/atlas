import assert from "node:assert/strict";
import { test } from "node:test";

import { fonds } from "../../src/atlas_web/fonds/index.js";
import { orbes } from "../../src/atlas_web/orbes/index.js";
import { ouvrirGalerie } from "../../src/atlas_web/parametres.js";
import { fauxDocument, fauxStockage } from "./faux_dom.mjs";

const SCENE = { etat: "ecoute", volume: 0.5, couleur: [34, 211, 238], syllabe: false, dt: 1 / 60 };

function monter(registre) {
  const document = fauxDocument();
  const conteneur = document.createElement("div");
  const stockage = fauxStockage();
  const images = [];
  const annulees = [];
  const choix = [];
  const galerie = ouvrirGalerie({
    document,
    conteneur,
    registre,
    stockage,
    scene: () => SCENE,
    surChoix: (element) => choix.push(element.id),
    planifier: (rappel) => images.push(rappel), // l'identifiant rendu : la longueur de la file
    annuler: (id) => annulees.push(id),
  });
  return { document, conteneur, stockage, images, annulees, choix, galerie };
}

const marquees = (conteneur) => conteneur.children.filter((carte) => carte.classList.contains("choisie"));

test("la galerie des orbes montre les douze, l'aurore marquée", () => {
  const m = monter(orbes);
  assert.equal(m.conteneur.children.length, 12);
  const [aurore] = marquees(m.conteneur);
  assert.equal(marquees(m.conteneur).length, 1);
  assert.equal(aurore.children[1].textContent, "Aurore boréale");
});

test("les aperçus s'animent à chaque image", () => {
  const m = monter(fonds);
  m.images.shift()(0);
  m.images.shift()(16);
  assert.equal(m.document.canevas.length, 6);
  for (const { bilan } of m.document.canevas) assert.ok(bilan.dessins > 0);
  assert.equal(m.images.length, 1); // l'image suivante est déjà demandée
});

test("un clic applique le choix, le mémorise et déplace la marque", () => {
  const m = monter(orbes);
  const plasma = m.conteneur.children[7];
  plasma.declencher("click");
  assert.deepEqual(m.choix, ["plasma"]);
  assert.equal(m.stockage.getItem("atlas.orbe"), "plasma");
  assert.deepEqual(marquees(m.conteneur), [plasma]);
});

test("fermer arrête les aperçus et vide la galerie", () => {
  const m = monter(orbes);
  const enAttente = m.images.shift();
  m.galerie.fermer();
  assert.deepEqual(m.annulees, [1]);
  assert.equal(m.conteneur.children.length, 0);
  enAttente(16); // une image déjà partie ne relance rien
  assert.equal(m.images.length, 0);
});

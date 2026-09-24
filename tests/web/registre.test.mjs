import assert from "node:assert/strict";
import { test } from "node:test";

import { creerRegistre, ecrireStockage, lireStockage } from "../../src/atlas_web/registre.js";
import { fauxStockage, stockageCasse } from "./faux_dom.mjs";

const ELEMENTS = [{ id: "a" }, { id: "b" }, { id: "c" }];

test("sans choix mémorisé, l'élément par défaut est choisi", () => {
  const registre = creerRegistre(ELEMENTS, "b", "cle");
  assert.equal(registre.choisi(fauxStockage()).id, "b");
  assert.equal(registre.parDefaut.id, "b");
  assert.equal(registre.tous, ELEMENTS);
});

test("un choix mémorisé est retrouvé, un choix inconnu est ignoré", () => {
  const registre = creerRegistre(ELEMENTS, "b", "cle");
  assert.equal(registre.choisi(fauxStockage({ cle: "c" })).id, "c");
  assert.equal(registre.choisi(fauxStockage({ cle: "z" })).id, "b");
});

test("choisir mémorise et rend l'élément", () => {
  const registre = creerRegistre(ELEMENTS, "b", "cle");
  const stockage = fauxStockage();
  assert.equal(registre.choisir(stockage, "a").id, "a");
  assert.equal(stockage.getItem("cle"), "a");
});

test("choisir un élément inconnu lève une erreur", () => {
  assert.throws(() => creerRegistre(ELEMENTS, "b", "cle").choisir(fauxStockage(), "z"), /inconnu/);
});

test("un stockage indisponible ne casse rien", () => {
  const registre = creerRegistre(ELEMENTS, "b", "cle");
  assert.equal(registre.choisi(stockageCasse).id, "b");
  assert.equal(registre.choisi(null).id, "b");
  assert.equal(registre.choisir(stockageCasse, "c").id, "c");
});

test("les identifiants en double et un défaut introuvable sont refusés", () => {
  assert.throws(() => creerRegistre([{ id: "a" }, { id: "a" }], "a", "cle"), /double/);
  assert.throws(() => creerRegistre(ELEMENTS, "z", "cle"), /défaut/);
});

test("lire et écrire le stockage n'échouent jamais", () => {
  assert.equal(lireStockage(stockageCasse, "cle"), null);
  assert.equal(ecrireStockage(stockageCasse, "cle", "v"), false);
  const stockage = fauxStockage();
  assert.equal(ecrireStockage(stockage, "cle", "v"), true);
  assert.equal(lireStockage(stockage, "cle"), "v");
});

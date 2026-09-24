import assert from "node:assert/strict";
import { test } from "node:test";

import { DELAI_SOUS_TITRES_MS, appliquerMessage, creerEtat } from "../../src/atlas_web/etat.js";
import { afficherSousTitres } from "../../src/atlas_web/sous_titres.js";
import { fauxElement } from "./faux_dom.mjs";

const T0 = Date.UTC(2026, 8, 24, 12, 0, 0);

function compterEcritures(element) {
  let valeur = "";
  element.ecritures = 0;
  Object.defineProperty(element, "textContent", {
    get: () => valeur,
    set: (texte) => {
      valeur = texte;
      element.ecritures += 1;
    },
  });
  return element;
}

function elements() {
  return {
    conteneur: fauxElement("section"),
    question: compterEcritures(fauxElement("p")),
    reponse: compterEcritures(fauxElement("p")),
  };
}

test("la question et la réponse s'affichent, l'erreur en rouge à la place de la réponse", () => {
  const e = creerEtat();
  const el = elements();
  appliquerMessage(e, { type: "etat", valeur: "reflexion" }, T0);
  appliquerMessage(e, { type: "question", texte: "Quelle heure ?", source: "clavier" }, T0);
  appliquerMessage(e, { type: "reponse", texte: "Il est midi." }, T0);
  afficherSousTitres(el, e, T0);
  assert.equal(el.question.textContent, "Quelle heure ?");
  assert.equal(el.reponse.textContent, "Il est midi.");
  assert.equal(el.reponse.classList.contains("erreur"), false);
  appliquerMessage(e, { type: "erreur", code: "tour", message: "Je n'ai pas pu répondre : panne" }, T0);
  afficherSousTitres(el, e, T0);
  assert.equal(el.question.textContent, "Quelle heure ?");
  assert.equal(el.reponse.textContent, "Je n'ai pas pu répondre : panne");
  assert.equal(el.reponse.classList.contains("erreur"), true);
});

test("les sous-titres s'effacent après 10 s de repos", () => {
  const e = creerEtat();
  const el = elements();
  appliquerMessage(e, { type: "etat", valeur: "repos" }, T0);
  afficherSousTitres(el, e, T0 + 1000);
  assert.equal(el.conteneur.classList.contains("efface"), false);
  afficherSousTitres(el, e, T0 + DELAI_SOUS_TITRES_MS + 1);
  assert.equal(el.conteneur.classList.contains("efface"), true);
});

test("le texte n'est réécrit que s'il change", () => {
  const e = creerEtat();
  const el = elements();
  appliquerMessage(e, { type: "question", texte: "q", source: "voix" }, T0);
  for (let i = 0; i < 60; i++) afficherSousTitres(el, e, T0);
  assert.equal(el.question.ecritures, 1);
  assert.equal(el.reponse.ecritures, 0);
});

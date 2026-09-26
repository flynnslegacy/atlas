import assert from "node:assert/strict";
import { test } from "node:test";

import {
  AUCUN_DOCUMENT,
  MEMOIRE_ABSENTE,
  rendreDocument,
  rendreListeDocuments,
} from "../../src/atlas_web/documents.js";
import { fauxDocument } from "./faux_dom.mjs";

const OFFRE = {
  chemin: "documents/offre-de-lancement.md",
  titre: "Offre de lancement",
  resume: "Trois formules.",
  modifie: "25 septembre 2026, 21 h 14",
};
const NOTES = { chemin: "documents/notes.md", titre: "Notes", resume: "", modifie: "24 septembre 2026, 9 h 05" };

function textes(element) {
  return element.children.map((enfant) => [enfant.className, enfant.textContent]);
}

test("la liste montre chaque document, et un toucher l'ouvre", () => {
  const document = fauxDocument();
  const conteneur = document.createElement("div");
  const choisis = [];
  rendreListeDocuments(document, conteneur, { disponible: true, documents: [OFFRE, NOTES] }, (chemin) =>
    choisis.push(chemin),
  );
  const [liste] = conteneur.children;
  assert.equal(liste.tagName, "OL");
  const [premier, second] = liste.children.map((li) => li.children[0]);
  assert.equal(premier.tagName, "BUTTON");
  assert.deepEqual(textes(premier), [
    ["titre", "Offre de lancement"],
    ["resume", "Trois formules."],
    ["date", "25 septembre 2026, 21 h 14"],
  ]);
  assert.deepEqual(textes(second), [
    ["titre", "Notes"],
    ["date", "24 septembre 2026, 9 h 05"],
  ]);
  second.declencher("click");
  assert.deepEqual(choisis, ["documents/notes.md"]);
});

test("sans document, ou sans mémoire, la liste le dit", () => {
  const document = fauxDocument();
  const conteneur = document.createElement("div");
  rendreListeDocuments(document, conteneur, { disponible: true, documents: [] }, () => {});
  assert.deepEqual(textes(conteneur), [["vide", AUCUN_DOCUMENT]]);
  rendreListeDocuments(document, conteneur, { disponible: false, documents: [] }, () => {});
  assert.deepEqual(textes(conteneur), [["vide", MEMOIRE_ABSENTE]]);
  assert.equal(MEMOIRE_ABSENTE, "La mémoire n'est pas disponible.");
});

test("un document se met en forme, ou dit son erreur", () => {
  const document = fauxDocument();
  const conteneur = document.createElement("article");
  rendreDocument(document, conteneur, { chemin: OFFRE.chemin, contenu: "# Offre\n\nTrois formules.\n", erreur: null });
  assert.deepEqual(
    conteneur.children.map((bloc) => bloc.tagName),
    ["H1", "P"],
  );
  rendreDocument(document, conteneur, { chemin: OFFRE.chemin, contenu: "", erreur: "documents/offre.md n'existe pas." });
  assert.deepEqual(textes(conteneur), [["erreur", "documents/offre.md n'existe pas."]]);
});

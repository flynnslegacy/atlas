import assert from "node:assert/strict";
import { test } from "node:test";

import { AU_TERMINAL, EFFACER, ENREGISTRER, GARDER, rendreReglages } from "../../src/atlas_web/reglages.js";
import { fauxDocument } from "./faux_dom.mjs";

const NOM = {
  variable: "ATLAS_BONJOUR_NOM",
  description: "Le nom à saluer",
  secret: false,
  defini: true,
  modifiable: true,
  valeur: "David",
};
const CLE = {
  variable: "ATLAS_BONJOUR_CLE",
  description: "La clé du service",
  secret: true,
  defini: true,
  modifiable: true,
  valeur: "",
};
const POSTE = {
  variable: "ATLAS_POSTE_CLE",
  description: "La clé du poste",
  secret: true,
  defini: true,
  modifiable: false,
  valeur: "",
};

function rendre(reglages, resultat = null) {
  const envois = [];
  const formulaire = rendreReglages(
    fauxDocument(),
    { id: "bonjour", reglages },
    (id, valeurs, effacer) => envois.push([id, valeurs, effacer]),
    resultat,
  );
  return { formulaire, envois };
}

// Chaque ligne : [étiquette (description, variable, champ), bouton « Effacer » ou statut].
function champ(formulaire, n) {
  return formulaire.children[n].children[0].children[2];
}

function enregistrer(formulaire) {
  formulaire.declencher("submit", { preventDefault() {} });
}

test("un réglage ordinaire montre sa valeur ; un secret, jamais", () => {
  const { formulaire } = rendre([NOM, { ...CLE, valeur: "fuite" }]);
  const [nom, cle] = [champ(formulaire, 0), champ(formulaire, 1)];
  assert.deepEqual([nom.type, nom.value], ["text", "David"]);
  assert.deepEqual([cle.type, cle.value], ["password", ""]);
  assert.equal(cle.attributs.placeholder, GARDER);
  assert.equal(cle.attributs.autocomplete, "off");
  const [description, variable] = formulaire.children[0].children[0].children;
  assert.deepEqual([description.textContent, variable.textContent], ["Le nom à saluer", "ATLAS_BONJOUR_NOM"]);
  assert.equal(formulaire.children.at(-1).textContent, ENREGISTRER);
});

test("« Enregistrer » n'envoie que ce qui a changé", () => {
  const { formulaire, envois } = rendre([NOM, CLE]);
  enregistrer(formulaire);
  assert.deepEqual(envois, [], "rien de changé : rien d'envoyé");
  champ(formulaire, 1).value = "sésame";
  enregistrer(formulaire);
  assert.deepEqual(envois.at(-1), ["bonjour", { ATLAS_BONJOUR_CLE: "sésame" }, []]);
  champ(formulaire, 0).value = "Camille";
  champ(formulaire, 1).value = "";
  enregistrer(formulaire);
  assert.deepEqual(envois.at(-1), ["bonjour", { ATLAS_BONJOUR_NOM: "Camille" }, []], "un secret vide est gardé");
  champ(formulaire, 0).value = "";
  enregistrer(formulaire);
  assert.deepEqual(envois.at(-1), ["bonjour", {}, ["ATLAS_BONJOUR_NOM"]], "un réglage vidé est effacé");
});

test("un réglage vide jamais défini ne s'efface pas", () => {
  const { formulaire, envois } = rendre([{ ...NOM, defini: false, valeur: "" }]);
  enregistrer(formulaire);
  assert.deepEqual(envois, []);
});

test("un secret défini s'efface d'un bouton ; un secret à définir n'en a pas", () => {
  const { formulaire, envois } = rendre([CLE, { ...CLE, variable: "ATLAS_AUTRE", defini: false }]);
  const effacer = formulaire.children[0].children[1];
  assert.deepEqual([effacer.textContent, effacer.type], [EFFACER, "button"]);
  effacer.declencher("click");
  assert.deepEqual(envois, [["bonjour", {}, ["ATLAS_BONJOUR_CLE"]]]);
  assert.equal(formulaire.children[1].children.length, 1, "pas de bouton");
  assert.equal(champ(formulaire, 1).attributs.placeholder, "À définir");
});

test("une clé d'Atlas n'a pas de champ : elle se change au Terminal", () => {
  const { formulaire, envois } = rendre([POSTE]);
  const [etiquette, statut] = formulaire.children[0].children;
  assert.equal(etiquette.children.length, 2, "ni champ, ni valeur");
  assert.equal(statut.textContent, `Défini, ${AU_TERMINAL}`);
  assert.equal(formulaire.children.length, 1, "rien à enregistrer");
  enregistrer(formulaire);
  assert.deepEqual(envois, []);
});

test("la réponse du Core s'affiche sous le formulaire", () => {
  const ok = rendre([NOM], { ok: true, message: "Enregistré." }).formulaire.children.at(-1);
  assert.deepEqual([ok.className, ok.textContent], ["resultat ok", "Enregistré."]);
  const message = "ATLAS_BONJOUR_NOM : pas d'espace au début ni à la fin.";
  const refus = rendre([NOM], { ok: false, message }).formulaire.children.at(-1);
  assert.deepEqual([refus.className, refus.textContent], ["resultat refus", message]);
});

test("les textes d'un manifeste restent du texte", () => {
  const { formulaire } = rendre([{ ...NOM, description: "<b>Nom</b>" }]);
  assert.equal(formulaire.children[0].children[0].children[0].textContent, "<b>Nom</b>");
});

import assert from "node:assert/strict";
import { test } from "node:test";

import {
  AUCUN_CONNECTEUR,
  AVERTISSEMENT,
  EN_ATTENTE,
  MEMOIRE_ABSENTE,
  rendreConnecteurs,
} from "../../src/atlas_web/connecteurs.js";
import { fauxDocument } from "./faux_dom.mjs";

const POSTE = {
  id: "poste",
  nom: "Le poste du Mac",
  description: "Atlas pilote le Mac.",
  version: "1.0.0",
  auteur: "Atlas",
  origine: "atlas",
  etat: "coupe",
  detail: "",
  en_attente: false,
};
const METEO = {
  ...POSTE,
  id: "meteo",
  nom: "<b>Météo</b>",
  description: "Le temps qu'il fait.",
  version: "0.2",
  auteur: "Camille",
  origine: "communaute",
};

function rendre(connecteurs, disponible = true) {
  const document = fauxDocument();
  const conteneur = document.createElement("div");
  const bascules = [];
  rendreConnecteurs(document, conteneur, { disponible, connecteurs }, (id, actif) => bascules.push([id, actif]));
  return { conteneur, bascules };
}

function lignes(conteneur) {
  return conteneur.children[0].children;
}

function morceaux(ligne) {
  const [tete, ...reste] = ligne.children;
  const [nom, badge, bascule] = tete.children;
  return { nom, badge, bascule, interrupteur: bascule.children[0], reste };
}

test("chaque connecteur a sa ligne : nom, badge, description, signature, état, interrupteur", () => {
  const { conteneur } = rendre([POSTE, METEO]);
  assert.equal(conteneur.children[0].tagName, "UL");
  const [poste, meteo] = lignes(conteneur).map(morceaux);
  assert.equal(poste.nom.textContent, "Le poste du Mac");
  assert.deepEqual([poste.badge.className, poste.badge.textContent], ["badge atlas", "Atlas"]);
  assert.deepEqual(
    poste.reste.slice(0, 3).map((p) => [p.className, p.textContent]),
    [
      ["description", "Atlas pilote le Mac."],
      ["signature", "version 1.0.0 · Atlas"],
      ["etat coupe", "Coupé"],
    ],
  );
  assert.deepEqual([poste.bascule.tagName, poste.bascule.className], ["LABEL", "interrupteur"]);
  assert.deepEqual(
    [poste.interrupteur.tagName, poste.interrupteur.type],
    ["INPUT", "checkbox"],
    "habillé comme « Hey Atlas »",
  );
  assert.deepEqual([poste.interrupteur.checked, poste.interrupteur.disabled], [false, false]);
  assert.ok(!poste.reste.some((p) => p.className === "attente"), "rien n'attend : rien à dire");
  assert.equal(meteo.badge.textContent, "Communauté");
  assert.equal(meteo.nom.textContent, "<b>Météo</b>", "le texte d'un manifeste reste du texte");
});

test("un connecteur qui n'est pas activable a son interrupteur grisé, et dit pourquoi", () => {
  const cas = [
    { ...POSTE, etat: "actif", en_attente: true },
    { ...POSTE, id: "a", etat: "a_configurer", detail: "il manque ATLAS_POSTE_CLE dans le .env du Core" },
    { ...POSTE, id: "b", etat: "a_installer", detail: "lance make install (il manque caldav)" },
    { ...POSTE, id: "c", etat: "en_erreur", detail: "connecteur.toml absent" },
  ];
  const [actif, aConfigurer, aInstaller, enErreur] = lignes(rendre(cas).conteneur).map(morceaux);
  assert.deepEqual([actif.interrupteur.checked, actif.interrupteur.disabled], [true, false]);
  assert.ok(actif.reste.some((p) => p.className === "attente" && p.textContent === EN_ATTENTE));
  for (const [ligne, texte] of [
    [aConfigurer, "À configurer : il manque ATLAS_POSTE_CLE dans le .env du Core"],
    [aInstaller, "À installer : lance make install (il manque caldav)"],
    [enErreur, "En erreur : connecteur.toml absent"],
  ]) {
    assert.equal(ligne.interrupteur.disabled, true);
    assert.ok(ligne.reste.some((p) => p.textContent === texte), texte);
  }
});

test("un connecteur d'Atlas s'active et se coupe d'un toucher", () => {
  const { conteneur, bascules } = rendre([POSTE, { ...POSTE, id: "agenda", etat: "actif" }]);
  const [poste, agenda] = lignes(conteneur).map(morceaux);
  poste.interrupteur.checked = true;
  poste.interrupteur.declencher("change");
  agenda.interrupteur.checked = false;
  agenda.interrupteur.declencher("change");
  assert.deepEqual(bascules, [
    ["poste", true],
    ["agenda", false],
  ]);
});

test("un connecteur de la communauté demande confirmation avant de s'activer, jamais pour se couper", () => {
  const { conteneur, bascules } = rendre([METEO, { ...METEO, id: "radio", etat: "actif" }]);
  const [meteo, radio] = lignes(conteneur).map(morceaux);
  const avertissement = meteo.reste.at(-1);
  assert.equal(avertissement.hidden, true);
  meteo.interrupteur.checked = true;
  meteo.interrupteur.declencher("change");
  assert.deepEqual(bascules, [], "rien ne part avant la confirmation");
  assert.equal(meteo.interrupteur.checked, false);
  assert.equal(avertissement.hidden, false);
  const [texte, activer, annuler] = avertissement.children;
  assert.equal(texte.textContent, AVERTISSEMENT);
  annuler.declencher("click");
  assert.equal(avertissement.hidden, true);
  assert.deepEqual(bascules, []);
  meteo.interrupteur.checked = true;
  meteo.interrupteur.declencher("change");
  activer.declencher("click");
  assert.deepEqual(bascules, [["meteo", true]]);
  assert.equal(avertissement.hidden, true);
  radio.interrupteur.checked = false;
  radio.interrupteur.declencher("change");
  assert.deepEqual(bascules.at(-1), ["radio", false]);
});

test("sans mémoire, ou sans connecteur, la rubrique le dit", () => {
  assert.equal(rendre([], false).conteneur.children[0].textContent, MEMOIRE_ABSENTE);
  assert.equal(rendre([]).conteneur.children[0].textContent, AUCUN_CONNECTEUR);
});

// La boucle d'animation de app.js, dans un faux navigateur minimal : ni document ni
// fenêtre réels, juste ce dont app.js a besoin au chargement pour ne rien lever.
import assert from "node:assert/strict";
import { test } from "node:test";

import { fauxElement, fauxStockage } from "./faux_dom.mjs";

// Tous les identifiants cherchés par app.js via $("…") (voir tests/web/page.test.mjs).
const IDENTIFIANTS = [
  "champ",
  "champ-cle",
  "formulaire-cle",
  "galerie-fonds",
  "galerie-orbes",
  "libelle-etat",
  "liste-historique",
  "message-cle",
  "muet",
  "ouvrir-historique",
  "ouvrir-parametres",
  "panneau-cle",
  "panneau-historique",
  "panneau-parametres",
  "pastille",
  "saisie",
  "sous-titres",
  "st-question",
  "st-reponse",
];

// Un contexte 2D qui lève sur le moindre appel : simule un dessin cassé, quelle qu'en
// soit la cause (canevas absent, valeur invalide, bogue dans une orbe…).
function canevasQuiLeve() {
  const ctx = new Proxy(
    {},
    {
      get() {
        return () => {
          throw new Error("dessin cassé");
        };
      },
      set() {
        throw new Error("dessin cassé");
      },
    },
  );
  return { width: 4, height: 4, clientWidth: 4, clientHeight: 4, getContext: () => ctx };
}

// Un contexte 2D qui accepte tout, sans rien vérifier : pour le canevas qui doit rester sain.
function canevasSain() {
  const etat = {};
  const ctx = new Proxy(etat, {
    get(cible, nom) {
      if (nom in cible) return cible[nom];
      return () => ({ addColorStop() {} });
    },
    set(cible, nom, valeur) {
      cible[nom] = valeur;
      return true;
    },
  });
  return { width: 4, height: 4, clientWidth: 4, clientHeight: 4, getContext: () => ctx };
}

function fauxDocumentDeLaPage() {
  const elements = {};
  for (const id of IDENTIFIANTS) {
    const element = fauxElement("div");
    element.style = {};
    element.value = "";
    element.focus = () => {};
    elements[id] = element;
  }
  elements.fond = canevasQuiLeve();
  elements.orbe = canevasSain();
  return {
    hidden: false,
    getElementById(id) {
      const element = elements[id];
      if (!element) throw new Error(`identifiant absent du faux document : ${id}`);
      return element;
    },
    createElement: (tag) => fauxElement(tag),
    querySelectorAll: () => [],
    querySelector: () => null,
    addEventListener() {},
  };
}

// Charge app.js dans un faux navigateur, avec un fond dont le dessin lève à chaque image.
// Rend la file des rappels que le vrai navigateur aurait donnés à requestAnimationFrame.
async function chargerPage({ stockage = fauxStockage(), FabriqueWebSocket } = {}) {
  const file = [];
  globalThis.document = fauxDocumentDeLaPage();
  globalThis.window = { localStorage: stockage, matchMedia: () => ({ matches: false }) };
  globalThis.WebSocket = FabriqueWebSocket;
  globalThis.location = { protocol: "http:", host: "atlas.test" };
  globalThis.requestAnimationFrame = (rappel) => {
    file.push(rappel);
    return file.length;
  };
  globalThis.cancelAnimationFrame = () => {};
  await import(new URL(`../../src/atlas_web/app.js?u=${Math.random()}`, import.meta.url));
  return file;
}

test("la boucle d'animation survit à un dessin qui lève, sans inonder la console", async () => {
  const erreurOriginale = console.error;
  const erreursConsole = [];
  console.error = (...args) => erreursConsole.push(args);
  try {
    const file = await chargerPage();
    assert.equal(file.length, 1, "la première image doit être programmée au chargement");

    const premiereImage = file.shift();
    assert.doesNotThrow(() => premiereImage(16), "un dessin qui lève ne doit pas figer la boucle");
    assert.equal(file.length, 1, "l'image suivante doit être demandée même si le dessin a levé");
    assert.equal(erreursConsole.length, 1, "la première erreur doit être signalée");

    // Plusieurs images de plus, toutes avec un dessin qui lève : la boucle continue, et la
    // console n'est pas inondée (une seule ligne, pas une par image).
    for (let i = 0; i < 5; i++) {
      const image = file.shift();
      assert.doesNotThrow(() => image(32 + i * 16));
      assert.equal(file.length, 1, "chaque image relance la suivante");
    }
    assert.equal(erreursConsole.length, 1, "une seule erreur signalée, malgré les images suivantes");
  } finally {
    console.error = erreurOriginale;
  }
});

test("la page s'annonce sur /ws/web avec son identifiant", async () => {
  const ouvertes = [];
  class FauxWebSocket {
    constructor(url) {
      this.url = url;
      this.envoyes = [];
      ouvertes.push(this);
    }

    send(texte) {
      this.envoyes.push(JSON.parse(texte));
    }
  }
  await chargerPage({ stockage: fauxStockage({ "atlas.cle": "cle" }), FabriqueWebSocket: FauxWebSocket });
  const [ws] = ouvertes;
  assert.equal(ws.url, "ws://atlas.test/ws/web");
  ws.onopen();
  assert.equal(ws.envoyes[0].cle, "cle");
  assert.match(ws.envoyes[0].page, /^[0-9a-f]{24}$/);
});

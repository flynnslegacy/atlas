// La boucle d'animation de app.js, dans un faux navigateur minimal : ni document ni
// fenêtre réels, juste ce dont app.js a besoin au chargement pour ne rien lever.
import assert from "node:assert/strict";
import { test } from "node:test";

import { fauxNavigateurAudio } from "./faux_audio.mjs";
import { fauxElement, fauxStockage } from "./faux_dom.mjs";

// Tous les identifiants cherchés par app.js via $("…") (voir tests/web/page.test.mjs).
const IDENTIFIANTS = [
  "champ",
  "champ-cle",
  "formulaire-cle",
  "galerie-fonds",
  "galerie-orbes",
  "hey-atlas",
  "libelle-etat",
  "liste-historique",
  "message-cle",
  "message-voix",
  "micro",
  "muet",
  "ouvrir-historique",
  "ouvrir-parametres",
  "panneau-cle",
  "panneau-historique",
  "panneau-parametres",
  "parler",
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
  const ecouteurs = {};
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
    addEventListener(type, rappel) {
      (ecouteurs[type] ??= []).push(rappel);
    },
    declencher(type, evenement = {}) {
      for (const rappel of ecouteurs[type] ?? []) rappel(evenement);
    },
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

class FauxWebSocket {
  static ouvertes = [];

  constructor(url) {
    this.url = url;
    this.envoyes = [];
    this.readyState = 0;
    FauxWebSocket.ouvertes.push(this);
  }

  send(donnees) {
    this.envoyes.push(typeof donnees === "string" ? JSON.parse(donnees) : donnees);
  }

  close() {
    this.readyState = 3;
  }

  ouvrir() {
    this.readyState = 1;
    this.onopen();
  }

  recevoir(message) {
    this.onmessage({ data: JSON.stringify(message) });
  }
}

// Le micro et le haut-parleur du faux navigateur, là où voix.js les cherche.
function installerAudio(options) {
  const { trace, nav } = fauxNavigateurAudio(options);
  globalThis.isSecureContext = nav.isSecureContext;
  globalThis.AudioContext = nav.AudioContext;
  globalThis.AudioWorkletNode = nav.AudioWorkletNode;
  Object.defineProperty(globalThis, "navigator", { value: nav.navigator, configurable: true });
  return trace;
}

const tourner = () => new Promise((resoudre) => setImmediate(resoudre));

test("le micro, l'orbe et « Hey Atlas » de la page passent par /ws/voix", async () => {
  FauxWebSocket.ouvertes = [];
  const trace = installerAudio();
  const stockage = fauxStockage({ "atlas.cle": "cle", "atlas.hey_atlas": "1" });
  await chargerPage({ stockage, FabriqueWebSocket: FauxWebSocket });
  const $ = (id) => document.getElementById(id);
  assert.equal($("hey-atlas").checked, true);
  const [web] = FauxWebSocket.ouvertes;
  web.ouvrir();

  $("micro").declencher("click");
  await tourner();
  const voix = FauxWebSocket.ouvertes.find((ws) => ws.url === "ws://atlas.test/ws/voix");
  voix.ouvrir();
  assert.deepEqual(voix.envoyes[0], { type: "authentification", cle: "cle", page: web.envoyes[0].page, hey_atlas: true });
  voix.recevoir({ type: "pret" });
  assert.equal($("micro").attributs["aria-pressed"], "true");
  assert.equal($("parler").hidden, false);
  assert.equal($("message-voix").hidden, true);

  $("parler").declencher("click");
  $("hey-atlas").checked = false;
  $("hey-atlas").declencher("change");
  assert.deepEqual(voix.envoyes.slice(1), [{ type: "parler" }, { type: "hey_atlas", actif: false }]);
  assert.equal(stockage.getItem("atlas.hey_atlas"), "0");

  $("micro").declencher("click");
  await tourner(); // le contexte fermé le signale après coup
  assert.equal($("micro").attributs["aria-pressed"], "false");
  assert.equal($("parler").hidden, true);
  assert.equal(trace.contextes[0].fermee, true);
  assert.equal($("message-voix").hidden, true, $("message-voix").textContent); // pas « Micro en pause »
});

test("sans HTTPS, le bouton Micro dit pourquoi il ne s'allume pas", async () => {
  FauxWebSocket.ouvertes = [];
  const trace = installerAudio({ securisee: false });
  await chargerPage({ stockage: fauxStockage({ "atlas.cle": "cle" }), FabriqueWebSocket: FauxWebSocket });
  const $ = (id) => document.getElementById(id);
  $("micro").declencher("click");
  await tourner();
  assert.equal($("message-voix").hidden, false);
  assert.match($("message-voix").textContent, /HTTPS/);
  assert.equal($("micro").attributs["aria-pressed"], "false");
  assert.equal(trace.contextes.length, 0);
});

test("au retour sur la page, un son resté coupé se rouvre d'un toucher", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  FauxWebSocket.ouvertes = [];
  const trace = installerAudio();
  await chargerPage({ stockage: fauxStockage({ "atlas.cle": "cle" }), FabriqueWebSocket: FauxWebSocket });
  const $ = (id) => document.getElementById(id);
  $("micro").declencher("click");
  await tourner();
  const voix = FauxWebSocket.ouvertes.find((ws) => ws.url === "ws://atlas.test/ws/voix");
  voix.ouvrir();
  voix.recevoir({ type: "pret" });
  const [contexte] = trace.contextes;
  contexte.state = "interrupted"; // iOS ne l'a pas relancé
  document.declencher("visibilitychange");
  t.mock.timers.tick(1500);
  assert.equal($("message-voix").hidden, false);
  assert.match($("message-voix").textContent, /réactiver/);
  $("message-voix").declencher("click");
  await tourner();
  assert.equal(contexte.state, "running");
});

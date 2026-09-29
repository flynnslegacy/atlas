// La boucle d'animation de app.js, dans un faux navigateur minimal : ni document ni
// fenêtre réels, juste ce dont app.js a besoin au chargement pour ne rien lever.
import assert from "node:assert/strict";
import { test } from "node:test";

import { fauxNavigateurAudio } from "./faux_audio.mjs";
import { fonds } from "../../src/atlas_web/fonds/index.js";
import { orbes } from "../../src/atlas_web/orbes/index.js";
import { fauxElement, fauxStockage } from "./faux_dom.mjs";

// Tous les identifiants cherchés par app.js via $("…") (voir tests/web/page.test.mjs).
const IDENTIFIANTS = [
  "annuler-confirmation",
  "boutons-confirmation",
  "champ",
  "champ-cle",
  "confirmation",
  "confirmer",
  "contenu-parametres",
  "formulaire-cle",
  "galerie-fonds",
  "galerie-orbes",
  "hey-atlas",
  "lecture-document",
  "libelle-etat",
  "liste-connecteurs",
  "liste-documents",
  "liste-historique",
  "menu-parametres",
  "message-cle",
  "message-voix",
  "micro",
  "mission",
  "muet",
  "ouvrir-documents",
  "ouvrir-historique",
  "ouvrir-parametres",
  "panneau-cle",
  "panneau-documents",
  "panneau-historique",
  "page-connecteurs",
  "page-core",
  "page-fond",
  "page-orbe",
  "page-voix",
  "panneau-parametres",
  "parler",
  "pastille",
  "retour-documents",
  "retour-parametres",
  "rubrique-core",
  "saisie",
  "sous-titres",
  "st-question",
  "st-reponse",
  "stop-mission",
  "texte-confirmation",
  "texte-mission",
  "valeur-connecteurs",
  "valeur-core",
  "valeur-fond",
  "valeur-orbe",
  "valeur-voix",
];
const RUBRIQUES = ["connecteurs", "voix", "orbe", "fond", "core"];

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

function fauxDocumentDeLaPage({ fondSain = false } = {}) {
  const elements = {};
  for (const id of IDENTIFIANTS) {
    const element = fauxElement("div");
    element.style = {};
    element.value = "";
    element.focus = () => {};
    elements[id] = element;
  }
  elements.fond = fondSain ? canevasSain() : canevasQuiLeve();
  elements.orbe = canevasSain();
  // Les boutons de la colonne des Paramètres, que app.js cherche par leur data-rubrique.
  const boutonsRubriques = RUBRIQUES.map((id) => {
    const bouton = fauxElement("button");
    bouton.dataset.rubrique = id;
    bouton.focus = () => {};
    return bouton;
  });
  const panneaux = ["panneau-historique", "panneau-documents", "panneau-parametres"];
  const ecouteurs = {};
  return {
    hidden: false,
    getElementById(id) {
      const element = elements[id];
      if (!element) throw new Error(`identifiant absent du faux document : ${id}`);
      return element;
    },
    createElement: (tag) => (fondSain && tag === "canvas" ? canevasSain() : fauxElement(tag)),
    querySelectorAll: (selecteur) => (selecteur === "#menu-parametres [data-rubrique]" ? boutonsRubriques : []),
    querySelector: (selecteur) =>
      selecteur === ".panneau:not([hidden])" ? (panneaux.map((id) => elements[id]).find((e) => !e.hidden) ?? null) : null,
    addEventListener(type, rappel) {
      (ecouteurs[type] ??= []).push(rappel);
    },
    declencher(type, evenement = {}) {
      for (const rappel of ecouteurs[type] ?? []) rappel(evenement);
    },
  };
}

// Charge app.js dans un faux navigateur, avec un fond dont le dessin lève à chaque image (sauf
// `fondSain` : l'image va alors jusqu'à la barre du haut). Rend la file des rappels que le vrai
// navigateur aurait donnés à requestAnimationFrame.
async function chargerPage({ stockage = fauxStockage(), FabriqueWebSocket, fondSain = false } = {}) {
  const file = [];
  globalThis.document = fauxDocumentDeLaPage({ fondSain });
  // Chaque requête média a son objet, que les tests font changer (une fenêtre redimensionnée).
  const medias = {};
  const media = () => ({
    matches: false,
    ecouteurs: [],
    addEventListener(type, rappel) {
      this.ecouteurs.push(rappel);
    },
    changer(matches) {
      this.matches = matches;
      for (const rappel of this.ecouteurs) rappel({ matches });
    },
  });
  globalThis.window = { localStorage: stockage, matchMedia: (requete) => (medias[requete] ??= media()) };
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
  assert.equal($("message-voix").hidden, true, $("message-voix").textContent);
});

const OFFRE = {
  chemin: "documents/offre-de-lancement.md",
  titre: "Offre de lancement",
  resume: "Trois formules.",
  modifie: "25 septembre 2026, 21 h 14",
};

test("le panneau Documents : la liste, un document, le retour, et les changements", async () => {
  FauxWebSocket.ouvertes = [];
  await chargerPage({ stockage: fauxStockage({ "atlas.cle": "cle" }), FabriqueWebSocket: FauxWebSocket });
  const $ = (id) => document.getElementById(id);
  const [web] = FauxWebSocket.ouvertes;
  web.ouvrir();
  web.recevoir({ type: "historique", echanges: [] }); // la page est en ligne
  for (const id of ["panneau-documents", "panneau-historique", "panneau-parametres"]) $(id).hidden = true;

  $("ouvrir-documents").declencher("click");
  assert.equal($("panneau-documents").hidden, false);
  assert.deepEqual(web.envoyes.at(-1), { type: "documents" });
  web.recevoir({ type: "liste_documents", disponible: true, documents: [OFFRE] });
  const [liste] = $("liste-documents").children;
  liste.children[0].children[0].declencher("click");
  assert.deepEqual(web.envoyes.at(-1), { type: "lire_document", chemin: OFFRE.chemin });

  web.recevoir({ type: "document", chemin: OFFRE.chemin, titre: "Offre", contenu: "# Offre\n\nTexte.\n", erreur: null });
  assert.equal($("lecture-document").hidden, false);
  assert.equal($("liste-documents").hidden, true);
  assert.equal($("retour-documents").hidden, false);
  assert.deepEqual(
    $("lecture-document").children.map((bloc) => bloc.tagName),
    ["H1", "P"],
  );
  web.recevoir({ type: "liste_documents", disponible: true, documents: [] }); // une vieille liste
  web.recevoir({ type: "document", chemin: "documents/autre.md", titre: "Autre", contenu: "Autre.", erreur: null });
  assert.equal($("liste-documents").hidden, true);
  assert.equal($("liste-documents").children[0], liste, "la liste en attente reste celle d'avant");
  assert.deepEqual(
    $("lecture-document").children.map((bloc) => bloc.tagName),
    ["H1", "P"],
    "le document d'un autre chemin ne remplace pas celui qu'on lit",
  );
  web.recevoir({ type: "documents_changes" });
  assert.deepEqual(web.envoyes.at(-1), { type: "lire_document", chemin: OFFRE.chemin });

  $("retour-documents").declencher("click");
  assert.equal($("lecture-document").hidden, true);
  assert.equal($("liste-documents").hidden, false);
  assert.equal($("retour-documents").hidden, true);
  assert.deepEqual(web.envoyes.at(-1), { type: "documents" });
  web.recevoir({ type: "documents_changes" });
  assert.deepEqual(web.envoyes.at(-1), { type: "documents" });

  $("ouvrir-documents").declencher("click"); // le même bouton ferme
  assert.equal($("panneau-documents").hidden, true);
  const envoyes = web.envoyes.length;
  web.recevoir({ type: "documents_changes" });
  web.recevoir({ type: "document", chemin: OFFRE.chemin, titre: "Offre", contenu: "# Offre\n", erreur: null });
  assert.equal(web.envoyes.length, envoyes, "panneau fermé : rien n'est redemandé");
});

test("la barre de confirmation : la question, les boutons, puis la fin", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  FauxWebSocket.ouvertes = [];
  await chargerPage({ stockage: fauxStockage({ "atlas.cle": "cle" }), FabriqueWebSocket: FauxWebSocket });
  const $ = (id) => document.getElementById(id);
  const [web] = FauxWebSocket.ouvertes;
  web.ouvrir();

  web.recevoir({ type: "confirmation", texte: "Je supprime le document Offre. Tu confirmes ?" });
  assert.equal($("confirmation").hidden, false);
  assert.equal($("boutons-confirmation").hidden, false);
  assert.equal($("texte-confirmation").textContent, "Je supprime le document Offre. Tu confirmes ?");
  $("confirmer").declencher("click");
  $("annuler-confirmation").declencher("click");
  assert.deepEqual(web.envoyes.slice(-2), [
    { type: "confirmer", oui: true },
    { type: "confirmer", oui: false },
  ]);

  web.recevoir({ type: "confirmation_finie", texte: "Rien n'a été supprimé." });
  assert.equal($("boutons-confirmation").hidden, true);
  assert.equal($("texte-confirmation").textContent, "Rien n'a été supprimé.");
  t.mock.timers.tick(3999);
  assert.equal($("confirmation").hidden, false);
  web.recevoir({ type: "confirmation", texte: "Je supprime ton profil. Tu confirmes ?" });
  t.mock.timers.tick(10);
  assert.equal($("confirmation").hidden, false, "la nouvelle question reste affichée");
  web.recevoir({ type: "confirmation_finie", texte: "Supprimé : ton profil." });
  t.mock.timers.tick(4000);
  assert.equal($("confirmation").hidden, true);
});

test("une page qui se reconnecte oublie une question qui n'attend plus, et une mission finie", async () => {
  FauxWebSocket.ouvertes = [];
  await chargerPage({ stockage: fauxStockage({ "atlas.cle": "cle" }), FabriqueWebSocket: FauxWebSocket });
  const $ = (id) => document.getElementById(id);
  const [web] = FauxWebSocket.ouvertes;
  web.ouvrir();
  web.recevoir({ type: "confirmation", texte: "Je supprime ton profil. Tu confirmes ?" });
  web.recevoir({ type: "mission", texte: "Mission en cours : écrire bonjour dans une note" });
  web.recevoir({ type: "historique", echanges: [] }); // ce que le Core envoie à chaque connexion
  assert.equal($("confirmation").hidden, true);
  assert.equal($("mission").hidden, true);
});

test("la barre de mission : la mission, le bouton Stop, puis la fin", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  FauxWebSocket.ouvertes = [];
  await chargerPage({ stockage: fauxStockage({ "atlas.cle": "cle" }), FabriqueWebSocket: FauxWebSocket });
  const $ = (id) => document.getElementById(id);
  const [web] = FauxWebSocket.ouvertes;
  web.ouvrir();

  web.recevoir({ type: "mission", texte: "Mission en cours : écrire bonjour dans une note" });
  assert.equal($("mission").hidden, false);
  assert.equal($("stop-mission").hidden, false);
  assert.equal($("texte-mission").textContent, "Mission en cours : écrire bonjour dans une note");
  t.mock.timers.tick(60000);
  assert.equal($("mission").hidden, false, "une mission en cours reste affichée");
  $("stop-mission").declencher("click");
  assert.deepEqual(web.envoyes.at(-1), { type: "stop" });

  web.recevoir({ type: "mission_finie", texte: "Mission arrêtée." });
  assert.equal($("stop-mission").hidden, true);
  assert.equal($("texte-mission").textContent, "Mission arrêtée.");
  t.mock.timers.tick(3999);
  assert.equal($("mission").hidden, false);
  web.recevoir({ type: "mission", texte: "Mission en cours : ouvrir la note" });
  t.mock.timers.tick(10);
  assert.equal($("mission").hidden, false, "la nouvelle mission reste affichée");
  web.recevoir({ type: "mission_finie", texte: "Mission terminée." });
  t.mock.timers.tick(4000);
  assert.equal($("mission").hidden, true);
  assert.equal($("confirmation").hidden, false, "la barre de confirmation n'a pas bougé");
});

test("les Paramètres demandent les connecteurs, les montrent, et envoient une bascule", async () => {
  FauxWebSocket.ouvertes = [];
  await chargerPage({ stockage: fauxStockage({ "atlas.cle": "cle" }), FabriqueWebSocket: FauxWebSocket });
  const $ = (id) => document.getElementById(id);
  const [web] = FauxWebSocket.ouvertes;
  web.ouvrir();
  web.recevoir({ type: "historique", echanges: [] }); // ce que le Core envoie à chaque connexion
  $("panneau-parametres").hidden = true; // fermé, comme au chargement de la vraie page
  $("ouvrir-parametres").declencher("click");
  assert.deepEqual(web.envoyes.slice(-2), [{ type: "connecteurs" }, { type: "demande_core" }]);
  const poste = {
    id: "poste",
    nom: "Le poste du Mac",
    description: "",
    version: "1.0.0",
    auteur: "Atlas",
    origine: "atlas",
    etat: "coupe",
    detail: "",
    en_attente: false,
  };
  web.recevoir({ type: "liste_connecteurs", disponible: true, connecteurs: [poste] });
  const [liste] = $("liste-connecteurs").children;
  const [entete] = liste.children[0].children;
  const interrupteur = entete.children[1].children.at(-1).children[0];
  interrupteur.checked = true;
  interrupteur.declencher("change");
  assert.deepEqual(web.envoyes.at(-1), { type: "activer_connecteur", id: "poste", actif: true });
  interrupteur.checked = false;
  interrupteur.declencher("change");
  assert.deepEqual(web.envoyes.at(-1), { type: "activer_connecteur", id: "poste", actif: false });
});

test("les réglages d'un connecteur partent au Core, et sa réponse s'affiche jusqu'à la réouverture", async () => {
  FauxWebSocket.ouvertes = [];
  await chargerPage({ stockage: fauxStockage({ "atlas.cle": "cle" }), FabriqueWebSocket: FauxWebSocket });
  const $ = (id) => document.getElementById(id);
  const [web] = FauxWebSocket.ouvertes;
  web.ouvrir();
  web.recevoir({ type: "historique", echanges: [] });
  $("panneau-parametres").hidden = true;
  $("ouvrir-parametres").declencher("click");
  const nom = { variable: "ATLAS_BONJOUR_NOM", description: "Le nom", secret: false, defini: false, modifiable: true, valeur: "" };
  const bonjour = {
    id: "bonjour",
    nom: "Bonjour",
    description: "",
    version: "0.1",
    auteur: "Quelqu'un",
    origine: "communaute",
    etat: "a_configurer",
    detail: "il manque ATLAS_BONJOUR_NOM dans le .env du Core",
    en_attente: false,
    reglages: [nom],
  };
  const regle = { ...bonjour, etat: "coupe", detail: "", reglages: [{ ...nom, defini: true, valeur: "David" }] };
  // La carte : [entête [texte, actions [« Réglages… », interrupteur]], avertissement, réglages].
  const carte = () => $("liste-connecteurs").children[0].children[0];
  const derniers = () => [carte().children[0].children[1].children[0], carte().children.at(-1)];
  web.recevoir({ type: "liste_connecteurs", disponible: true, connecteurs: [bonjour] });
  let [ouvrir, formulaire] = derniers();
  ouvrir.declencher("click");
  formulaire.children[0].children[0].children[2].value = "David";
  formulaire.declencher("submit", { preventDefault() {} });
  assert.deepEqual(web.envoyes.at(-1), {
    type: "regler_connecteur",
    id: "bonjour",
    valeurs: { ATLAS_BONJOUR_NOM: "David" },
    effacer: [],
  });
  web.recevoir({ type: "resultat_reglage", id: "bonjour", ok: true, message: "Enregistré." });
  [, formulaire] = derniers();
  assert.deepEqual([formulaire.hidden, formulaire.children.at(-1).textContent], [false, "Enregistré."]);
  web.recevoir({ type: "liste_connecteurs", disponible: true, connecteurs: [regle] });
  [, formulaire] = derniers();
  assert.equal(formulaire.children.at(-1).textContent, "Enregistré.", "toujours là, la liste à jour");
  $("ouvrir-parametres").declencher("click"); // referme les Paramètres
  $("ouvrir-parametres").declencher("click"); // les rouvre
  web.recevoir({ type: "liste_connecteurs", disponible: true, connecteurs: [regle] });
  [, formulaire] = derniers();
  assert.equal(formulaire.hidden, true, "une liste fermée");
  assert.ok(!formulaire.children.some((e) => e.className.startsWith("resultat")), "sans vieux message");
});

test("le Core se redémarre depuis les Paramètres, et la barre du haut suit son retour", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  FauxWebSocket.ouvertes = [];
  const stockage = fauxStockage({ "atlas.cle": "cle" });
  const file = await chargerPage({ stockage, FabriqueWebSocket: FauxWebSocket, fondSain: true });
  const $ = (id) => document.getElementById(id);
  const image = () => file[0](0); // l'image de la page (les galeries ont aussi les leurs)
  const [web] = FauxWebSocket.ouvertes;
  web.ouvrir();
  web.recevoir({ type: "historique", echanges: [] });
  $("panneau-parametres").hidden = true;
  $("ouvrir-parametres").declencher("click");
  assert.deepEqual(web.envoyes.at(-1), { type: "demande_core" });
  web.recevoir({
    type: "etat_core",
    version: "ce65d2a",
    date: "2026-09-29",
    occupe: false,
    mise_a_jour_possible: true,
    raison: "",
  });
  const [groupe, confirmation] = $("rubrique-core").children;
  assert.equal(groupe.children[0].children[1].textContent, "ce65d2a, du 2026-09-29");
  groupe.children[1].children[1].declencher("click"); // « Redémarrer… »
  confirmation.children[1].declencher("click"); // « Confirmer »
  assert.deepEqual(web.envoyes.at(-1), { type: "redemarrer_core" });

  web.recevoir({ type: "core_en_cours", etape: "redemarrage", texte: "Redémarrage du Core…", nouveautes: [] });
  web.onclose({ code: 1012 }); // le Core s'arrête
  image();
  assert.equal($("libelle-etat").textContent, "Redémarrage du Core…");
  t.mock.timers.tick(60000);
  image();
  assert.equal($("libelle-etat").textContent, "Le Core ne revient pas");
  assert.match($("rubrique-core").children.at(-1).textContent, /donnees\/logs\/core\.log/);

  const nouvelle = FauxWebSocket.ouvertes.at(-1); // la page a retenté entre-temps
  assert.notEqual(nouvelle, web);
  nouvelle.ouvrir();
  nouvelle.recevoir({ type: "historique", echanges: [] });
  assert.deepEqual(nouvelle.envoyes.at(-1), { type: "demande_core" }, "la version, revenue");
  image();
  assert.notEqual($("libelle-etat").textContent, "Le Core ne revient pas");
});

async function ouvrirLesParametres(stockage) {
  FauxWebSocket.ouvertes = [];
  await chargerPage({ stockage, FabriqueWebSocket: FauxWebSocket });
  const $ = (id) => document.getElementById(id);
  const [web] = FauxWebSocket.ouvertes;
  web.ouvrir();
  web.recevoir({ type: "historique", echanges: [] });
  for (const id of ["panneau-historique", "panneau-documents", "panneau-parametres", "panneau-cle"]) {
    $(id).hidden = true; // fermés, comme au chargement de la vraie page
  }
  $("ouvrir-parametres").declencher("click");
  return { $, web };
}

test("les Paramètres s'ouvrent sur la dernière rubrique ; une galerie ne tourne que dans la sienne", async () => {
  const stockage = fauxStockage({ "atlas.cle": "cle", "atlas.rubrique": "orbe" });
  const { $ } = await ouvrirLesParametres(stockage);
  const visibles = () => RUBRIQUES.filter((id) => !$(`page-${id}`).hidden);
  assert.deepEqual(visibles(), ["orbe"]);
  assert.ok($("galerie-orbes").children.length > 0, "la galerie des orbes tourne");
  assert.equal($("galerie-fonds").children.length, 0, "celle des fonds attend sa rubrique");
  const fond = document.querySelectorAll("#menu-parametres [data-rubrique]")[3];
  fond.declencher("click");
  assert.deepEqual(visibles(), ["fond"]);
  assert.ok($("galerie-fonds").children.length > 0);
  assert.equal($("galerie-orbes").children.length, 0, "la galerie des orbes s'est arrêtée");
  assert.equal(stockage.getItem("atlas.rubrique"), "fond");
  assert.equal($("panneau-parametres").dataset.vue, "rubrique");
  $("retour-parametres").declencher("click");
  assert.equal($("panneau-parametres").dataset.vue, "menu", "« ‹ Paramètres » revient à la liste");
});

test("la liste des rubriques dit la valeur de chacune, à jour", async () => {
  const stockage = fauxStockage({ "atlas.cle": "cle", "atlas.hey_atlas": "1", "atlas.rubrique": "voix" });
  const { $, web } = await ouvrirLesParametres(stockage);
  assert.equal($("page-connecteurs").hidden, true, "la rubrique Voix est affichée");
  assert.equal($("valeur-voix").textContent, "Hey Atlas");
  assert.equal($("valeur-orbe").textContent, orbes.choisi(stockage).nom);
  assert.equal($("valeur-fond").textContent, fonds.choisi(stockage).nom);
  const connecteur = { id: "a", nom: "A", origine: "atlas", etat: "actif", reglages: [] };
  const connecteurs = [connecteur, { ...connecteur, id: "b" }, { ...connecteur, id: "c", etat: "coupe" }];
  web.recevoir({ type: "liste_connecteurs", disponible: true, connecteurs });
  assert.equal($("valeur-connecteurs").textContent, "2 actifs");
  assert.equal($("liste-connecteurs").children[0].children.length, 3, "à jour, même cachée");
  web.recevoir({
    type: "etat_core",
    version: "ce65d2a",
    date: "2026-09-29",
    occupe: false,
    mise_a_jour_possible: true,
    raison: "",
  });
  assert.equal($("valeur-core").textContent, "ce65d2a");
  $("hey-atlas").checked = false;
  $("hey-atlas").declencher("change");
  assert.equal($("valeur-voix").textContent, "");
  const orbe = document.querySelectorAll("#menu-parametres [data-rubrique]")[2];
  orbe.declencher("click");
  const autre = orbes.tous.find((o) => o.nom !== $("valeur-orbe").textContent);
  $("galerie-orbes").children[orbes.tous.indexOf(autre)].declencher("click");
  assert.equal($("valeur-orbe").textContent, autre.nom);
});

test("remonter une rubrique au doigt ne ferme pas les Paramètres", async () => {
  const { $ } = await ouvrirLesParametres(fauxStockage({ "atlas.cle": "cle" }));
  const glisser = () => {
    document.declencher("touchstart", { touches: [{ clientY: 100 }] });
    document.declencher("touchend", { changedTouches: [{ clientY: 300 }] });
  };
  $("menu-parametres").scrollTop = 0;
  $("contenu-parametres").scrollTop = 300;
  glisser();
  assert.equal($("panneau-parametres").hidden, false, "la rubrique défile vers le haut");
  $("contenu-parametres").scrollTop = 0;
  $("menu-parametres").scrollTop = 120;
  glisser();
  assert.equal($("panneau-parametres").hidden, false, "la colonne aussi");
  $("menu-parametres").scrollTop = 0;
  glisser();
  assert.equal($("panneau-parametres").hidden, true, "tout en haut, le geste ferme");
  $("ouvrir-documents").declencher("click"); // un autre panneau défile, lui, tout entier
  $("panneau-documents").scrollTop = 200;
  glisser();
  assert.equal($("panneau-documents").hidden, false);
  $("panneau-documents").scrollTop = 0;
  glisser();
  assert.equal($("panneau-documents").hidden, true);
});

test("une fenêtre qui passe sous 720 px, puis au-dessus : la galerie s'arrête, puis revient", async () => {
  const stockage = fauxStockage({ "atlas.cle": "cle", "atlas.rubrique": "orbe" });
  const { $ } = await ouvrirLesParametres(stockage);
  const ecran = window.matchMedia("(max-width: 719px)");
  assert.ok($("galerie-orbes").children.length > 0);
  ecran.changer(true);
  assert.equal($("galerie-orbes").children.length, 0, "la liste seule : la galerie s'arrête");
  ecran.changer(false);
  assert.ok($("galerie-orbes").children.length > 0, "la rubrique revient à droite, sa galerie aussi");
  document.declencher("keydown", { key: "Escape" }); // les Paramètres se ferment
  ecran.changer(true);
  ecran.changer(false);
  assert.equal($("galerie-orbes").children.length, 0, "fermés, aucune galerie ne repart");
});

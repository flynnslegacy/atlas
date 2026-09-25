import assert from "node:assert/strict";
import { test } from "node:test";

import {
  Connexion,
  DELAIS_RECONNEXION_MS,
  FERMETURE_CLE_ABSENTE,
  FERMETURE_NON_AUTORISE,
  identifiantDePage,
} from "../../src/atlas_web/connexion.js";

class FauxWebSocket {
  static crees = [];

  constructor(url) {
    this.url = url;
    this.envoyes = [];
    this.readyState = 0;
    this.fermee = false;
    FauxWebSocket.crees.push(this);
  }

  send(donnees) {
    this.envoyes.push(typeof donnees === "string" ? JSON.parse(donnees) : donnees);
  }

  close() {
    this.fermee = true;
    this.readyState = 3;
  }

  // Ce que fait le serveur, simulé.
  ouvrir() {
    this.readyState = 1;
    this.onopen?.();
  }

  recevoir(message) {
    this.onmessage?.({ data: JSON.stringify(message) });
  }

  recevoirBinaire(donnees) {
    this.onmessage?.({ data: donnees });
  }

  couper(code) {
    this.readyState = 3;
    this.onclose?.({ code });
  }
}

function monter({ cle = "cle", entree } = {}) {
  FauxWebSocket.crees = [];
  const statuts = [];
  const messages = [];
  const binaires = [];
  const planifies = [];
  const connexion = new Connexion({
    url: "ws://atlas.local:8080/ws/web",
    lireCle: () => cle,
    entree,
    surMessage: (message) => messages.push(message),
    surBinaire: (donnees) => binaires.push(donnees),
    surStatut: (statut) => statuts.push(statut),
    FabriqueWebSocket: FauxWebSocket,
    planifier: (rappel, delai) => planifies.push({ rappel, delai }),
  });
  return { connexion, statuts, messages, binaires, planifies, derniere: () => FauxWebSocket.crees.at(-1) };
}

test("la clé part dans le premier message, puis la page est en ligne", () => {
  const m = monter();
  m.connexion.demarrer();
  const ws = m.derniere();
  ws.ouvrir();
  assert.equal(ws.url, "ws://atlas.local:8080/ws/web");
  assert.deepEqual(ws.envoyes, [{ type: "authentification", cle: "cle" }]);
  ws.recevoir({ type: "historique", echanges: [] });
  assert.deepEqual(m.statuts, ["connexion", "en_ligne"]);
  assert.deepEqual(m.messages, [{ type: "historique", echanges: [] }]);
});

test("sans clé mémorisée, rien ne part et la clé est demandée", () => {
  const m = monter({ cle: null });
  m.connexion.demarrer();
  assert.equal(FauxWebSocket.crees.length, 0);
  assert.deepEqual(m.statuts, ["cle_requise"]);
});

test("une clé refusée ou non configurée arrête les tentatives", () => {
  for (const [code, statut] of [
    [FERMETURE_NON_AUTORISE, "cle_refusee"],
    [FERMETURE_CLE_ABSENTE, "cle_absente"],
  ]) {
    const m = monter();
    m.connexion.demarrer();
    m.derniere().ouvrir();
    m.derniere().couper(code);
    assert.equal(m.statuts.at(-1), statut);
    assert.equal(m.planifies.length, 0);
  }
});

test("une coupure relance la connexion, de plus en plus espacée, jusqu'à 30 s", () => {
  const m = monter();
  m.connexion.demarrer();
  for (let i = 0; i < 8; i++) {
    m.derniere().couper(1006);
    m.planifies.at(-1).rappel();
  }
  assert.deepEqual(
    m.planifies.map((p) => p.delai),
    [1000, 2000, 4000, 8000, 16000, 30000, 30000, 30000],
  );
  assert.equal(m.statuts.filter((s) => s === "hors_ligne").length, 8);
});

test("une connexion réussie remet l'attente à une seconde", () => {
  const m = monter();
  m.connexion.demarrer();
  m.derniere().couper(1006);
  m.planifies.at(-1).rappel();
  m.derniere().couper(1006);
  m.planifies.at(-1).rappel();
  const ws = m.derniere();
  ws.ouvrir();
  ws.recevoir({ type: "muet", actif: false });
  ws.couper(1006);
  assert.equal(m.planifies.at(-1).delai, DELAIS_RECONNEXION_MS[0]);
});

test("envoyer ne part qu'une fois en ligne", () => {
  const m = monter();
  m.connexion.demarrer();
  const ws = m.derniere();
  assert.equal(m.connexion.envoyer({ type: "saisie", texte: "q" }), false);
  ws.ouvrir();
  assert.equal(m.connexion.envoyer({ type: "saisie", texte: "q" }), false);
  ws.recevoir({ type: "historique", echanges: [] });
  assert.equal(m.connexion.envoyer({ type: "saisie", texte: "q" }), true);
  assert.deepEqual(ws.envoyes.at(-1), { type: "saisie", texte: "q" });
});

test("arrêter empêche toute reconnexion", () => {
  const m = monter();
  m.connexion.demarrer();
  const ws = m.derniere();
  m.connexion.arreter();
  assert.equal(ws.fermee, true);
  ws.couper(1006);
  assert.equal(m.planifies.length, 0);
});

test("redémarrer abandonne l'ancienne connexion sans la relancer", () => {
  const m = monter();
  m.connexion.demarrer();
  const ancienne = m.derniere();
  m.connexion.demarrer();
  assert.equal(ancienne.fermee, true);
  ancienne.couper(1006);
  assert.equal(m.planifies.length, 0);
  assert.equal(FauxWebSocket.crees.length, 2);
});

test("un message illisible est ignoré", () => {
  const m = monter();
  m.connexion.demarrer();
  const ws = m.derniere();
  ws.ouvrir();
  ws.onmessage({ data: "pas du json" });
  assert.deepEqual(m.messages, []);
});

test("l'entrée porte aussi ce que la page y ajoute, relu à chaque connexion", () => {
  let heyAtlas = true;
  const m = monter({ entree: () => ({ page: "p1", hey_atlas: heyAtlas }) });
  m.connexion.demarrer();
  m.derniere().ouvrir();
  assert.deepEqual(m.derniere().envoyes, [{ type: "authentification", cle: "cle", page: "p1", hey_atlas: true }]);
  heyAtlas = false;
  m.derniere().couper(1006);
  m.planifies.at(-1).rappel();
  m.derniere().ouvrir();
  assert.equal(m.derniere().envoyes[0].hey_atlas, false);
});

test("le son reçu va à surBinaire, une fois en ligne seulement", () => {
  const m = monter();
  m.connexion.demarrer();
  const ws = m.derniere();
  assert.equal(ws.binaryType, "arraybuffer");
  ws.ouvrir();
  const avant = new ArrayBuffer(640);
  ws.recevoirBinaire(avant);
  ws.recevoir({ type: "pret" });
  const apres = new ArrayBuffer(640);
  ws.recevoirBinaire(apres);
  assert.deepEqual(m.binaires, [apres]);
  assert.deepEqual(m.messages, [{ type: "pret" }]);
});

test("envoyerBinaire ne part qu'une fois en ligne", () => {
  const m = monter();
  m.connexion.demarrer();
  const ws = m.derniere();
  const bloc = new ArrayBuffer(640);
  ws.ouvrir();
  assert.equal(m.connexion.envoyerBinaire(bloc), false);
  ws.recevoir({ type: "pret" });
  assert.equal(m.connexion.envoyerBinaire(bloc), true);
  assert.equal(ws.envoyes.at(-1), bloc);
});

test("l'identifiant de page est tiré au hasard, dans le format que le Core accepte", () => {
  const a = identifiantDePage();
  assert.match(a, /^[0-9a-f]{24}$/);
  assert.notEqual(identifiantDePage(), a);
  const fixe = { getRandomValues: (octets) => octets.fill(0xab) };
  assert.equal(identifiantDePage(fixe), "ab".repeat(12));
});

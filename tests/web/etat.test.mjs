import assert from "node:assert/strict";
import { test } from "node:test";

import {
  COULEURS,
  COULEUR_HORS_LIGNE,
  DELAI_SOUS_TITRES_MS,
  TAILLE_HISTORIQUE,
  appliquerMessage,
  avancer,
  creerEtat,
  heureDe,
  sceneDe,
  sousTitresVisibles,
} from "../../src/atlas_web/etat.js";

const T0 = Date.UTC(2026, 8, 24, 12, 0, 0);

function proche(a, b, tolerance = 1) {
  a.forEach((x, i) => assert.ok(Math.abs(x - b[i]) <= tolerance, `${a} ≉ ${b}`));
}

function avancerLongtemps(etat, secondes, dt = 1 / 60) {
  for (let t = 0; t < secondes; t += dt) avancer(etat, dt);
}

test("un état neuf est hors ligne, au repos et gris", () => {
  const e = creerEtat();
  assert.equal(e.enLigne, false);
  assert.equal(e.etat, "repos");
  assert.deepEqual(e.couleur, COULEUR_HORS_LIGNE);
  assert.deepEqual(e.historique, []);
});

test("les messages etat et niveau pilotent l'orbe", () => {
  const e = creerEtat();
  appliquerMessage(e, { type: "etat", valeur: "ecoute" }, T0);
  appliquerMessage(e, { type: "niveau", valeur: 0.8 }, T0);
  assert.equal(e.etat, "ecoute");
  assert.equal(e.volumeCible, 0.8);
  appliquerMessage(e, { type: "etat", valeur: "reflexion" }, T0);
  assert.equal(e.volumeCible, 0);
});

test("le volume rejoint sa cible en douceur", () => {
  const e = creerEtat();
  e.enLigne = true;
  e.etat = "parole";
  e.volumeCible = 1;
  avancer(e, 1 / 60);
  assert.ok(e.volume > 0 && e.volume < 0.5);
  avancerLongtemps(e, 1);
  assert.ok(e.volume > 0.99);
});

test("au repos, la cible du volume retombe d'elle-même", () => {
  const e = creerEtat();
  e.enLigne = true;
  e.volumeCible = 1;
  avancerLongtemps(e, 3);
  assert.ok(e.volumeCible < 0.01 && e.volume < 0.05);
});

test("la couleur glisse vers celle de l'état, puis vers le gris hors ligne", () => {
  const e = creerEtat();
  e.enLigne = true;
  e.etat = "parole";
  avancer(e, 1 / 60);
  assert.notDeepEqual(e.couleur, COULEURS.parole);
  avancerLongtemps(e, 3);
  proche(e.couleur, COULEURS.parole);
  e.enLigne = false;
  avancerLongtemps(e, 3);
  proche(e.couleur, COULEUR_HORS_LIGNE);
});

test("une syllabe est signalée une fois par montée du volume", () => {
  const e = creerEtat();
  e.enLigne = true;
  e.etat = "ecoute";
  const syllabes = [];
  for (const cible of [0.9, 0.1, 0.9]) {
    e.volumeCible = cible;
    for (let i = 0; i < 30; i++) {
      avancer(e, 1 / 60);
      syllabes.push(e.syllabe);
    }
  }
  assert.equal(syllabes.filter(Boolean).length, 2);
});

test("question puis réponses : sous-titres et historique", () => {
  const e = creerEtat();
  appliquerMessage(e, { type: "question", texte: "Quelle heure ?", source: "clavier" }, T0);
  appliquerMessage(e, { type: "reponse", texte: "Il est midi." }, T0);
  appliquerMessage(e, { type: "reponse", texte: "Tu déjeunes ?" }, T0);
  assert.equal(e.question, "Quelle heure ?");
  assert.equal(e.reponse, "Il est midi. Tu déjeunes ?");
  const [echange] = e.historique;
  assert.equal(echange.source, "clavier");
  assert.equal(echange.reponse, "Il est midi. Tu déjeunes ?");
  assert.match(echange.heure, /^\d\d:\d\d$/);
});

test("une erreur pendant un tour s'attache à l'échange, sinon elle en crée un", () => {
  const e = creerEtat();
  appliquerMessage(e, { type: "etat", valeur: "reflexion" }, T0);
  appliquerMessage(e, { type: "question", texte: "Bonjour", source: "voix" }, T0);
  appliquerMessage(e, { type: "erreur", code: "tour", message: "Je n'ai pas pu répondre : panne" }, T0);
  appliquerMessage(e, { type: "etat", valeur: "repos" }, T0);
  appliquerMessage(e, { type: "erreur", code: "tour", message: "Je n'ai pas pu répondre : délai" }, T0);
  assert.equal(e.historique.length, 2);
  assert.equal(e.historique[0].erreur, "Je n'ai pas pu répondre : panne");
  assert.equal(e.historique[1].question, "");
  assert.equal(e.erreur, "Je n'ai pas pu répondre : délai");
});

test("l'erreur de clé absente ne va pas dans l'historique", () => {
  const e = creerEtat();
  appliquerMessage(e, { type: "erreur", code: "cle_absente", message: "ATLAS_WEB_CLE…" }, T0);
  assert.deepEqual(e.historique, []);
});

test("A : une erreur après l'écoute ne touche pas l'échange terminé", () => {
  const e = creerEtat();
  appliquerMessage(e, { type: "question", texte: "quelle heure est-il", source: "voix" }, T0);
  appliquerMessage(e, { type: "reponse", texte: "Il est midi." }, T0);
  appliquerMessage(
    e,
    { type: "latences", transcription_ms: 420, reflexion_ms: 12, premiere_voix_ms: 900 },
    T0,
  );
  appliquerMessage(e, { type: "etat", valeur: "repos" }, T0);
  appliquerMessage(e, { type: "etat", valeur: "ecoute" }, T0);
  appliquerMessage(e, { type: "etat", valeur: "reflexion" }, T0);
  appliquerMessage(e, { type: "erreur", code: "tour", message: "Je n'ai pas pu répondre : ConnectError" }, T0);
  assert.equal(e.historique.length, 2);
  const [premier, second] = e.historique;
  assert.equal(premier.question, "quelle heure est-il");
  assert.equal(premier.reponse, "Il est midi.");
  assert.equal(premier.erreur, null);
  assert.equal(second.question, "");
  assert.equal(second.erreur, "Je n'ai pas pu répondre : ConnectError");
});

test("B : une coupure pendant la réponse n'empêche pas une nouvelle erreur", () => {
  const e = creerEtat();
  appliquerMessage(e, { type: "question", texte: "quelle heure est-il", source: "voix" }, T0);
  appliquerMessage(e, { type: "etat", valeur: "parole" }, T0);
  appliquerMessage(e, { type: "reponse", texte: "Il est" }, T0);
  appliquerMessage(e, { type: "etat", valeur: "ecoute" }, T0); // coupure : l'échange n'est plus en cours
  appliquerMessage(e, { type: "etat", valeur: "reflexion" }, T0);
  appliquerMessage(e, { type: "erreur", code: "tour", message: "Je n'ai pas pu répondre : ConnectError" }, T0);
  assert.equal(e.historique.length, 2);
  const [premier, second] = e.historique;
  assert.equal(premier.question, "quelle heure est-il");
  assert.equal(premier.reponse, "Il est");
  assert.equal(premier.erreur, null);
  assert.equal(second.question, "");
  assert.equal(second.erreur, "Je n'ai pas pu répondre : ConnectError");
});

test("C : une saisie refusée pendant la réponse s'affiche sans toucher l'historique", () => {
  const e = creerEtat();
  appliquerMessage(e, { type: "question", texte: "quelle heure est-il", source: "voix" }, T0);
  appliquerMessage(e, { type: "etat", valeur: "parole" }, T0);
  appliquerMessage(e, { type: "reponse", texte: "Il est midi." }, T0);
  appliquerMessage(e, { type: "erreur", code: "message_invalide", message: "Texte invalide" }, T0);
  assert.equal(e.historique.length, 1);
  assert.equal(e.historique[0].erreur, null);
  assert.equal(e.historique[0].reponse, "Il est midi.");
  assert.equal(e.erreur, "Texte invalide");
});

test("les latences s'attachent au dernier échange, le muet est suivi", () => {
  const e = creerEtat();
  appliquerMessage(e, { type: "question", texte: "q", source: "voix" }, T0);
  appliquerMessage(
    e,
    { type: "latences", transcription_ms: 420, reflexion_ms: 12, premiere_voix_ms: null },
    T0,
  );
  appliquerMessage(e, { type: "muet", actif: true }, T0);
  assert.deepEqual(e.historique[0].latences, {
    transcription_ms: 420,
    reflexion_ms: 12,
    premiere_voix_ms: null,
  });
  assert.equal(e.muet, true);
});

test("l'historique du Core remplace celui de la page", () => {
  const e = creerEtat();
  appliquerMessage(e, { type: "question", texte: "ancienne", source: "voix" }, T0);
  const echange = { heure: "09:00", source: "clavier", question: "q", reponse: "r", erreur: null, latences: null };
  appliquerMessage(e, { type: "historique", echanges: [echange] }, T0);
  assert.deepEqual(e.historique, [echange]);
});

test("l'historique de la page est limité", () => {
  const e = creerEtat();
  for (let i = 0; i < TAILLE_HISTORIQUE + 5; i++) {
    appliquerMessage(e, { type: "question", texte: `q${i}`, source: "voix" }, T0);
  }
  assert.equal(e.historique.length, TAILLE_HISTORIQUE);
  assert.equal(e.historique[0].question, "q5");
});

test("les sous-titres s'effacent après 10 s de repos", () => {
  const e = creerEtat();
  appliquerMessage(e, { type: "etat", valeur: "parole" }, T0);
  assert.equal(sousTitresVisibles(e, T0 + 60000), true);
  appliquerMessage(e, { type: "etat", valeur: "repos" }, T0);
  assert.equal(sousTitresVisibles(e, T0 + DELAI_SOUS_TITRES_MS - 1), true);
  assert.equal(sousTitresVisibles(e, T0 + DELAI_SOUS_TITRES_MS + 1), false);
});

test("une erreur au repos reste affichée 10 s", () => {
  const e = creerEtat();
  appliquerMessage(e, { type: "etat", valeur: "repos" }, T0);
  appliquerMessage(e, { type: "erreur", code: "tour", message: "panne" }, T0 + 60000);
  assert.equal(sousTitresVisibles(e, T0 + 65000), true);
});

test("les sous-titres effacés ne reviennent pas au réveil suivant", () => {
  const e = creerEtat();
  appliquerMessage(e, { type: "etat", valeur: "reflexion" }, T0);
  appliquerMessage(e, { type: "question", texte: "Quelle heure ?", source: "voix" }, T0);
  appliquerMessage(e, { type: "reponse", texte: "Il est midi." }, T0);
  appliquerMessage(e, { type: "erreur", code: "tour", message: "Je n'ai pas pu répondre : panne" }, T0);
  appliquerMessage(e, { type: "etat", valeur: "repos" }, T0);
  // 60 s de repos, puis un réveil : les sous-titres n'étaient plus visibles avant ce message.
  appliquerMessage(e, { type: "etat", valeur: "ecoute" }, T0 + 60000);
  assert.equal(e.question, "");
  assert.equal(e.reponse, "");
  assert.equal(e.erreur, "");
});

test("la scène d'une page hors ligne est au repos, et réduite si demandé", () => {
  const e = creerEtat();
  e.etat = "parole";
  e.volume = 1;
  assert.equal(sceneDe(e, 0.016).etat, "repos");
  e.enLigne = true;
  const scene = sceneDe(e, 0.016, true);
  assert.equal(scene.etat, "parole");
  assert.equal(scene.volume, 0.6);
  assert.equal(scene.dt, 0.016);
  assert.equal(scene.couleur, e.couleur);
});

test("heureDe écrit l'heure locale sur deux chiffres", () => {
  assert.match(heureDe(T0), /^\d\d:\d\d$/);
});

import assert from "node:assert/strict";
import { test } from "node:test";

import {
  CONFIRMATIONS,
  DELAI_RETOUR_MS,
  NE_REVIENT_PAS,
  NE_REVIENT_PAS_DETAIL,
  REDEMARRAGE,
  SuiviCore,
  rendreCore,
} from "../../src/atlas_web/core.js";
import { fauxDocument } from "./faux_dom.mjs";

const VERSION = {
  type: "etat_core",
  version: "ce65d2a",
  date: "2026-09-29",
  occupe: false,
  mise_a_jour_possible: true,
  raison: "",
};

function rendre(etat) {
  const document = fauxDocument();
  const conteneur = document.createElement("div");
  const actions = [];
  rendreCore(document, conteneur, etat, (type) => actions.push(type));
  const par = (classe) => conteneur.children.find((e) => e.className === classe);
  const [redemarrer, mettreAJour] = par("boutons").children;
  return { conteneur, par, redemarrer, mettreAJour, actions };
}

test("la version qui tourne, et deux boutons qui demandent confirmation", () => {
  const { par, redemarrer, mettreAJour, actions } = rendre({ version: VERSION, enCours: null, fin: null });
  assert.equal(par("version").textContent, "Version ce65d2a, du 2026-09-29");
  assert.deepEqual([redemarrer.disabled, mettreAJour.disabled], [false, false]);
  const confirmation = par("confirmation-core");
  assert.equal(confirmation.hidden, true);
  mettreAJour.declencher("click");
  assert.deepEqual([confirmation.hidden, confirmation.children[0].textContent], [false, CONFIRMATIONS.mettre_a_jour_core]);
  confirmation.children[2].declencher("click"); // Annuler
  assert.deepEqual([confirmation.hidden, actions], [true, []]);
  redemarrer.declencher("click");
  assert.equal(confirmation.children[0].textContent, CONFIRMATIONS.redemarrer_core);
  confirmation.children[1].declencher("click"); // Confirmer
  assert.deepEqual([confirmation.hidden, actions], [true, ["redemarrer_core"]]);
});

test("la mise à jour impossible est grisée, avec sa raison", () => {
  const raison = "Le dépôt du Core est sur la branche essai, pas sur main : mets-le à jour au Terminal.";
  const version = { ...VERSION, mise_a_jour_possible: false, raison };
  const { par, redemarrer, mettreAJour } = rendre({ version, enCours: null, fin: null });
  assert.deepEqual([redemarrer.disabled, mettreAJour.disabled], [false, true]);
  assert.equal(par("raison").textContent, raison);
});

test("avant la version, ou pendant une étape, les boutons attendent", () => {
  let { par, redemarrer, mettreAJour } = rendre({ version: null, enCours: null, fin: null });
  assert.equal(par("version").textContent, "Version…");
  assert.deepEqual([redemarrer.disabled, mettreAJour.disabled], [true, true]);
  const enCours = { etape: "installation", texte: "Installation…", nouveautes: ["Deux", "Un"] };
  ({ par, redemarrer, mettreAJour } = rendre({ version: VERSION, enCours, fin: null }));
  assert.deepEqual([redemarrer.disabled, mettreAJour.disabled], [true, true]);
  assert.equal(par("etape").textContent, "Installation…");
  assert.deepEqual(par("nouveautes").children.map((li) => li.textContent), ["Deux", "Un"]);
  ({ redemarrer } = rendre({ version: { ...VERSION, occupe: true }, enCours: null, fin: null }));
  assert.equal(redemarrer.disabled, true, "occupé par une autre page");
});

test("la fin : le texte, et les dernières lignes d'une erreur, comme du texte", () => {
  const fin = { ok: false, texte: "La récupération a échoué : rien n'a changé.", details: ["fatal: <b>", "x"] };
  const { par } = rendre({ version: VERSION, enCours: null, fin });
  assert.equal(par("fin refus").textContent, fin.texte);
  assert.equal(par("details").textContent, "fatal: <b>\nx");
  const ok = rendre({ version: VERSION, enCours: null, fin: { ok: true, texte: "Atlas est déjà à jour.", details: [] } });
  assert.equal(ok.par("fin ok").textContent, "Atlas est déjà à jour.");
  assert.equal(ok.par("details"), undefined);
});

function suivi() {
  const envois = [];
  const minuteurs = [];
  let changements = 0;
  const s = new SuiviCore({
    envoyer: (message) => envois.push(message),
    surChangement: () => (changements += 1),
    planifier: (rappel, delai) => minuteurs.push({ rappel, delai, annule: false }) - 1,
    annuler: (n) => {
      if (n !== null && n !== undefined) minuteurs[n].annule = true;
    },
  });
  return { s, envois, minuteurs, changements: () => changements };
}

test("le suivi range la version, les étapes et la fin ; une fin redemande la version", () => {
  const { s, envois, changements } = suivi();
  s.recevoir({ type: "question", texte: "Bonjour", source: "clavier" });
  assert.equal(changements(), 0, "pas un message du Core");
  s.recevoir(VERSION);
  assert.equal(s.etat.version, VERSION);
  const enCours = { type: "core_en_cours", etape: "recuperation", texte: "Récupération…", nouveautes: [] };
  s.recevoir(enCours);
  assert.equal(s.etat.enCours, enCours);
  const fin = { type: "fin_core", ok: true, texte: "Atlas est déjà à jour.", details: [] };
  s.recevoir(fin);
  assert.deepEqual([s.etat.enCours, s.etat.fin], [null, fin]);
  assert.deepEqual(envois, [{ type: "demande_core" }]);
  assert.equal(changements(), 3);
  assert.equal(s.libelle(), null, "aucun redémarrage : la barre dit son statut habituel");
  s.recevoir(enCours); // une autre mise à jour : l'ancienne fin s'efface
  assert.deepEqual([s.etat.enCours, s.etat.fin], [enCours, null]);
});

test("pendant un redémarrage, la barre le dit ; le Core revenu, la version se redemande", () => {
  const { s, envois, minuteurs } = suivi();
  s.recevoir({ type: "core_en_cours", etape: "redemarrage", texte: REDEMARRAGE, nouveautes: [] });
  assert.equal(minuteurs[0].delai, DELAI_RETOUR_MS);
  assert.equal(s.libelle(), REDEMARRAGE);
  s.surStatut("en_ligne"); // encore l'ancienne connexion : pas un retour
  assert.equal(s.libelle(), REDEMARRAGE);
  s.surStatut("hors_ligne");
  s.surStatut("connexion");
  s.surStatut("en_ligne");
  assert.equal(s.libelle(), null);
  assert.equal(minuteurs[0].annule, true);
  assert.deepEqual([s.etat.enCours, s.etat.fin, envois], [null, null, [{ type: "demande_core" }]]);
});

test("un Core qui ne revient pas au bout d'une minute, la page le dit", () => {
  const { s, minuteurs } = suivi();
  s.recevoir({ type: "core_en_cours", etape: "redemarrage", texte: REDEMARRAGE, nouveautes: [] });
  s.surStatut("hors_ligne");
  minuteurs[0].rappel();
  assert.equal(s.libelle(), NE_REVIENT_PAS);
  assert.deepEqual(s.etat.fin, { ok: false, texte: NE_REVIENT_PAS_DETAIL, details: [] });
  s.surStatut("en_ligne"); // il finit par revenir
  assert.deepEqual([s.libelle(), s.etat.fin], [null, null]);
});

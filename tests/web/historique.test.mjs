import assert from "node:assert/strict";
import { test } from "node:test";

import { formaterDuree, formaterLatences, rendreHistorique } from "../../src/atlas_web/historique.js";
import { fauxDocument } from "./faux_dom.mjs";

test("les durées s'écrivent en ms sous la seconde, en secondes au-delà", () => {
  assert.equal(formaterDuree(420), "420 ms");
  assert.equal(formaterDuree(1234), "1,2 s");
  assert.equal(formaterDuree(null), null);
  assert.equal(formaterDuree(undefined), null);
});

test("les délais d'un échange se lisent d'une traite", () => {
  assert.equal(
    formaterLatences({ transcription_ms: 420, reflexion_ms: 1234, premiere_voix_ms: null }),
    "transcription 420 ms · réflexion 1,2 s",
  );
  assert.equal(formaterLatences(null), "");
});

test("l'historique se rend en texte brut, un élément par échange", () => {
  const document = fauxDocument();
  const liste = document.createElement("ol");
  rendreHistorique(document, liste, [
    {
      heure: "14:31",
      source: "clavier",
      question: "<b>q</b>",
      reponse: "r",
      erreur: null,
      latences: { transcription_ms: null, reflexion_ms: 12, premiere_voix_ms: 900 },
    },
    { heure: "14:32", source: "voix", question: "", reponse: "", erreur: "panne", latences: null },
  ]);
  assert.equal(liste.children.length, 2);
  const [premier, second] = liste.children;
  assert.deepEqual(
    premier.children.map((p) => [p.className, p.textContent]),
    [
      ["entete", "14:31 ⌨"],
      ["question", "<b>q</b>"],
      ["reponse", "r"],
      ["latences", "réflexion 12 ms · voix 900 ms"],
    ],
  );
  assert.deepEqual(second.children.map((p) => p.className), ["entete", "question", "erreur"]);
  assert.equal(second.children[0].textContent, "14:32 🎙");
  assert.equal(second.children[1].textContent, "(rien d'entendu)");
});

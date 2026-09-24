import assert from "node:assert/strict";
import { test } from "node:test";

import { orbes } from "../../src/atlas_web/orbes/index.js";
import { animer, fauxCanevas } from "./faux_canevas.mjs";

const ORDRE = [
  "particules",
  "liquide",
  "anneaux",
  "armillaire",
  "relief",
  "cymatique",
  "oscilloscope",
  "plasma",
  "constellations",
  "aurore",
  "galaxie",
  "mandala",
];

test("les douze orbes sont enregistrées, l'aurore par défaut", () => {
  assert.deepEqual(
    orbes.tous.map((o) => o.id),
    ORDRE,
  );
  assert.equal(orbes.parDefaut.id, "aurore");
});

for (const module of orbes.tous) {
  test(`l'orbe ${module.id} s'anime dans les quatre états sans cacher le fond`, () => {
    assert.ok(module.nom.length > 0 && module.idee.length > 0);
    for (const [largeur, hauteur] of [
      [400, 400],
      [640, 400],
    ]) {
      const canevas = fauxCanevas(largeur, hauteur);
      const parImage = animer(module, canevas);
      assert.ok(Math.min(...parImage) >= 2, `${module.id} ne dessine pas son corps à chaque image`);
      assert.equal(canevas.bilan.peinturesOpaquesPleines, 0, `${module.id} cache le fond`);
    }
  });
}

import assert from "node:assert/strict";
import { test } from "node:test";

import anneaux from "../../src/atlas_web/orbes/anneaux.js";
import armillaire from "../../src/atlas_web/orbes/armillaire.js";
import cymatique from "../../src/atlas_web/orbes/cymatique.js";
import liquide from "../../src/atlas_web/orbes/liquide.js";
import particules from "../../src/atlas_web/orbes/particules.js";
import relief from "../../src/atlas_web/orbes/relief.js";
import { animer, fauxCanevas } from "./faux_canevas.mjs";

function verifierOrbe(module) {
  assert.match(module.id, /^[a-z]+$/);
  assert.ok(module.nom.length > 0 && module.idee.length > 0);
  for (const [largeur, hauteur] of [[400, 400], [640, 400]]) {
    const canevas = fauxCanevas(largeur, hauteur);
    const parImage = animer(module, canevas);
    assert.ok(Math.min(...parImage) >= 2, `${module.id} ne dessine pas son corps à chaque image`);
    assert.equal(canevas.bilan.peinturesOpaquesPleines, 0, `${module.id} cache le fond`);
  }
}

for (const module of [particules, liquide, anneaux, armillaire, relief, cymatique]) {
  test(`l'orbe ${module.id} s'anime dans les quatre états sans cacher le fond`, () => verifierOrbe(module));
}

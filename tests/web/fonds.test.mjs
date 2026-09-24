import assert from "node:assert/strict";
import { test } from "node:test";

import { fonds } from "../../src/atlas_web/fonds/index.js";
import { animer, fauxCanevas } from "./faux_canevas.mjs";

test("les six fonds sont enregistrés, le bokeh par défaut", () => {
  assert.deepEqual(
    fonds.tous.map((f) => f.id),
    ["nuit", "etoiles", "nebuleuse", "horizon", "bokeh", "tunnel"],
  );
  assert.equal(fonds.parDefaut.id, "bokeh");
});

for (const module of fonds.tous) {
  test(`le fond ${module.id} s'anime dans les quatre états, en paysage comme en portrait`, () => {
    assert.ok(module.nom.length > 0 && module.idee.length > 0);
    for (const [largeur, hauteur] of [
      [1280, 800],
      [390, 844],
    ]) {
      const canevas = fauxCanevas(largeur, hauteur);
      const parImage = animer(module, canevas);
      assert.ok(Math.min(...parImage) >= 1, `${module.id} ne dessine pas à chaque image`);
    }
  });
}

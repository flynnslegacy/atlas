import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const RACINE = fileURLToPath(new URL("../../src/atlas_web/", import.meta.url));

function fichiers(dossier = RACINE) {
  return readdirSync(dossier, { withFileTypes: true }).flatMap((entree) => {
    const chemin = join(dossier, entree.name);
    if (entree.isDirectory()) return fichiers(chemin);
    return /\.(js|html|css)$/.test(entree.name) ? [chemin] : [];
  });
}

const lire = (chemin) => readFileSync(chemin, "utf8");
const INDEX = lire(join(RACINE, "index.html"));

test("aucun script n'insère de HTML ni n'évalue de texte", () => {
  const interdits = [/innerHTML/, /outerHTML/, /insertAdjacentHTML/, /document\.write/, /\beval\(/, /new Function/];
  for (const chemin of fichiers().filter((c) => c.endsWith(".js"))) {
    for (const motif of interdits) assert.doesNotMatch(lire(chemin), motif, chemin);
  }
});

test("la page ne charge rien de l'extérieur", () => {
  for (const chemin of fichiers()) assert.doesNotMatch(lire(chemin), /https?:\/\//, chemin);
});

test("index.html n'a ni script, ni style, ni gestionnaire d'événement en ligne", () => {
  assert.doesNotMatch(INDEX, /<script(?![^>]*\bsrc=)[^>]*>/);
  assert.doesNotMatch(INDEX, /<style/);
  assert.doesNotMatch(INDEX, /\sstyle=/);
  assert.doesNotMatch(INDEX, /\son[a-z]+=/);
});

test("chaque élément cherché par app.js existe dans index.html", () => {
  const ids = new Set([...lire(join(RACINE, "app.js")).matchAll(/\$\("([^"]+)"\)/g)].map((m) => m[1]));
  assert.ok(ids.size >= 15);
  for (const id of ids) assert.match(INDEX, new RegExp(`id="${id}"`), id);
});

test("app.js est un module valide", () => {
  const verification = spawnSync(process.execPath, ["--check", join(RACINE, "app.js")], { encoding: "utf8" });
  assert.equal(verification.status, 0, verification.stderr);
});

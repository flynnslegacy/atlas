import assert from "node:assert/strict";
import { test } from "node:test";

import { rendreMarkdown } from "../../src/atlas_web/markdown.js";
import { fauxDocument } from "./faux_dom.mjs";

// Le rendu en texte, pour comparer : un élément devient <tag attr="…">…</tag>, une chaîne
// reste du texte (le vrai navigateur en fait un nœud texte, jamais du HTML).
function rendu(noeud) {
  if (typeof noeud === "string") return noeud;
  const tag = noeud.tagName.toLowerCase();
  const attributs = Object.entries(noeud.attributs)
    .map(([nom, valeur]) => ` ${nom}="${valeur}"`)
    .join("");
  const dedans = noeud.children.length ? noeud.children.map(rendu).join("") : noeud.textContent;
  return `<${tag}${attributs}>${dedans}</${tag}>`;
}

function html(texte) {
  return rendreMarkdown(fauxDocument(), texte).map(rendu).join("");
}

function elements(noeuds) {
  return noeuds.flatMap((n) => (typeof n === "string" ? [] : [n, ...elements(n.children)]));
}

test("les titres ont trois niveaux ; au-delà, c'est du texte", () => {
  assert.equal(html("# Offre\n\n## Formules\n\n### Prix\n\n#### Détail"), "<h1>Offre</h1><h2>Formules</h2><h3>Prix</h3><p>#### Détail</p>");
});

test("un paragraphe réunit ses lignes, une ligne vide les sépare", () => {
  assert.equal(html("Une ligne\nqui continue.\n\nAutre paragraphe."), "<p>Une ligne qui continue.</p><p>Autre paragraphe.</p>");
});

test("les listes à puces et numérotées", () => {
  assert.equal(
    html("- un\n* **deux**\n\n1. premier\n2) second"),
    "<ul><li>un</li><li><strong>deux</strong></li></ul><ol><li>premier</li><li>second</li></ol>",
  );
});

test("une citation réunit ses lignes", () => {
  assert.equal(html("> À valider\n> avec Paul."), "<blockquote><p>À valider avec Paul.</p></blockquote>");
});

test("un tableau, avec ou sans ligne d'en-tête", () => {
  assert.equal(
    html("| Formule | Prix |\n| --- | ---: |\n| Diagnostic | 900 € |"),
    "<table><thead><tr><th>Formule</th><th>Prix</th></tr></thead>" +
      "<tbody><tr><td>Diagnostic</td><td>900 €</td></tr></tbody></table>",
  );
  assert.equal(html("| a | b |\n| c | d |"), "<table><tbody><tr><td>a</td><td>b</td></tr><tr><td>c</td><td>d</td></tr></tbody></table>");
});

test("le gras, l'italique, le code et les liens https", () => {
  assert.equal(
    html("**gras**, *italique*, `code` et [le site](https://example.com/offre)."),
    '<p><strong>gras</strong>, <em>italique</em>, <code>code</code> et <a href="https://example.com/offre" ' +
      'target="_blank" rel="noopener noreferrer">le site</a>.</p>',
  );
});

test("le gras garde sa mise en forme intérieure", () => {
  assert.equal(html("**voir `offre.md`**"), "<p><strong>voir <code>offre.md</code></strong></p>");
});

test("un bloc peut suivre un paragraphe sans ligne vide", () => {
  assert.equal(
    html("Les formules :\n- une\n- deux\nEt la suite.\n## Prix\n> Note"),
    "<p>Les formules :</p><ul><li>une</li><li>deux</li></ul><p>Et la suite.</p><h2>Prix</h2>" +
      "<blockquote><p>Note</p></blockquote>",
  );
});

test("un lien qui n'est pas en http(s) reste du texte", () => {
  for (const adresse of ["javascript:alert", "file:///etc/passwd", "data:text/html,x", "//exemple.fr"]) {
    const [p] = rendreMarkdown(fauxDocument(), `Voir [ici](${adresse}).`);
    assert.deepEqual(p.children, ["Voir ", "ici", "."], adresse);
  }
});

test("le HTML d'un document n'est jamais interprété", () => {
  const blocs = rendreMarkdown(fauxDocument(), "<script>alert(1)</script> **<img src=x onerror=y>**\n\n```\n<b>x</b>\n```");
  const tags = elements(blocs).map((e) => e.tagName);
  assert.deepEqual(tags, ["P", "STRONG", "PRE", "CODE"]);
  assert.deepEqual(blocs[0].children[0], "<script>alert(1)</script> ");
  assert.deepEqual(blocs[0].children[1].children, ["<img src=x onerror=y>"]);
  assert.equal(blocs[1].children[0].textContent, "<b>x</b>");
});

test("un document entier, avec des fins de ligne Windows", () => {
  const offre = [
    "# Offre de lancement",
    "",
    "Trois formules pour les premiers clients.",
    "",
    "## Les formules",
    "",
    "- **Diagnostic** : une journée.",
    "- *Mise en place* : quatre semaines.",
    "",
    "| Formule | Prix |",
    "| --- | --- |",
    "| Diagnostic | 900 € |",
    "",
    "> À valider avec Paul Durand.",
  ].join("\r\n");
  const blocs = rendreMarkdown(fauxDocument(), offre);
  assert.deepEqual(
    blocs.map((b) => b.tagName),
    ["H1", "P", "H2", "UL", "TABLE", "BLOCKQUOTE"],
  );
  assert.equal(rendu(blocs[0]), "<h1>Offre de lancement</h1>");
});

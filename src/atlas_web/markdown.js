// La mise en forme d'un document dans la page (spec 2c §5 et §7) : la syntaxe permise à
// Claude, et rien d'autre. Tout passe par des éléments et du texte, jamais par du HTML : un
// document ne peut pas injecter de code dans la page.

const TITRE = /^(#{1,3}) (.*)$/;
const PUCE = /^[-*] (.*)$/;
const NUMERO = /^\d+[.)] (.*)$/;
const CITATION = /^> ?(.*)$/;
const LIGNE_DE_TABLEAU = /^\s*(\|.*)$/;
const SEPARATEUR = /^\|?(\s*:?-{3,}:?\s*\|)*\s*:?-{3,}:?\s*\|?\s*$/;
const CLOTURE = /^```/;
const LIEN_PERMIS = /^https?:\/\//i;
const EN_LIGNE = /(`[^`]+`)|(\*\*[^*]+\*\*)|(\*[^*\s](?:[^*]*[^*\s])?\*)|(\[[^\]]+\]\([^)\s]+\))/g;

function element(document, tag, enfants = []) {
  const el = document.createElement(tag);
  el.append(...enfants);
  return el;
}

// Le texte d'une ligne : chaînes et éléments, dans l'ordre.
function enLigne(document, texte) {
  const morceaux = [];
  let dernier = 0;
  for (const trouve of texte.matchAll(EN_LIGNE)) {
    if (trouve.index > dernier) morceaux.push(texte.slice(dernier, trouve.index));
    const [tout, code, gras, italique, lien] = trouve;
    if (code) {
      const el = document.createElement("code");
      el.textContent = code.slice(1, -1);
      morceaux.push(el);
    } else if (gras) {
      morceaux.push(element(document, "strong", enLigne(document, gras.slice(2, -2))));
    } else if (italique) {
      morceaux.push(element(document, "em", enLigne(document, italique.slice(1, -1))));
    } else {
      const [, libelle, adresse] = lien.match(/^\[([^\]]+)\]\(([^)\s]+)\)$/);
      if (LIEN_PERMIS.test(adresse)) {
        const a = element(document, "a", [libelle]);
        a.setAttribute("href", adresse);
        a.setAttribute("target", "_blank");
        a.setAttribute("rel", "noopener noreferrer");
        morceaux.push(a);
      } else {
        morceaux.push(libelle); // un lien qui n'est pas en http(s) reste du texte
      }
    }
    dernier = trouve.index + tout.length;
  }
  if (dernier < texte.length) morceaux.push(texte.slice(dernier));
  return morceaux;
}

function cellules(ligne) {
  return ligne
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cellule) => cellule.trim());
}

function rangee(document, tag, textes) {
  return element(
    document,
    "tr",
    textes.map((texte) => element(document, tag, enLigne(document, texte))),
  );
}

function tableau(document, lignes) {
  const table = document.createElement("table");
  let corps = lignes;
  if (lignes.length > 1 && SEPARATEUR.test(lignes[1].trim())) {
    table.append(element(document, "thead", [rangee(document, "th", cellules(lignes[0]))]));
    corps = lignes.slice(2);
  }
  table.append(element(document, "tbody", corps.map((l) => rangee(document, "td", cellules(l)))));
  return table;
}

function debutDeBloc(ligne) {
  return [TITRE, PUCE, NUMERO, CITATION, LIGNE_DE_TABLEAU, CLOTURE].some((m) => m.test(ligne));
}

// Les blocs du document, prêts à mettre dans la page : `conteneur.replaceChildren(...blocs)`.
export function rendreMarkdown(document, texte) {
  const lignes = texte.replace(/\r\n?/g, "\n").split("\n");
  const blocs = [];
  let i = 0;
  // Les lignes qui suivent le même motif, réduites à ce qu'il capture.
  const suite = (motif) => {
    const prises = [];
    while (i < lignes.length && motif.test(lignes[i])) prises.push(lignes[i++].match(motif)[1]);
    return prises;
  };
  while (i < lignes.length) {
    const ligne = lignes[i];
    if (!ligne.trim()) {
      i += 1;
    } else if (CLOTURE.test(ligne)) {
      i += 1;
      const code = [];
      while (i < lignes.length && !CLOTURE.test(lignes[i])) code.push(lignes[i++]);
      i += 1;
      const el = document.createElement("code");
      el.textContent = code.join("\n");
      blocs.push(element(document, "pre", [el]));
    } else if (TITRE.test(ligne)) {
      const [, dieses, titre] = ligne.match(TITRE);
      blocs.push(element(document, `h${dieses.length}`, enLigne(document, titre.trim())));
      i += 1;
    } else if (PUCE.test(ligne)) {
      const items = suite(PUCE).map((t) => element(document, "li", enLigne(document, t)));
      blocs.push(element(document, "ul", items));
    } else if (NUMERO.test(ligne)) {
      const items = suite(NUMERO).map((t) => element(document, "li", enLigne(document, t)));
      blocs.push(element(document, "ol", items));
    } else if (CITATION.test(ligne)) {
      const paragraphe = element(document, "p", enLigne(document, suite(CITATION).join(" ").trim()));
      blocs.push(element(document, "blockquote", [paragraphe]));
    } else if (LIGNE_DE_TABLEAU.test(ligne)) {
      blocs.push(tableau(document, suite(LIGNE_DE_TABLEAU)));
    } else {
      const morceaux = [];
      while (i < lignes.length && lignes[i].trim() && !debutDeBloc(lignes[i])) {
        morceaux.push(lignes[i++].trim());
      }
      blocs.push(element(document, "p", enLigne(document, morceaux.join(" "))));
    }
  }
  return blocs;
}

// Le panneau « Documents » : la liste des documents d'Atlas, puis l'un d'eux mis en forme
// (spec 2c §7). Texte brut, et la mise en forme de markdown.js : jamais de HTML.

import { rendreMarkdown } from "./markdown.js";

export const MEMOIRE_ABSENTE = "La mémoire n'est pas disponible.";
export const AUCUN_DOCUMENT = "Pas encore de document : demande à Atlas d'en faire un.";

function paragraphe(document, classe, texte) {
  const p = document.createElement("p");
  p.className = classe;
  p.textContent = texte;
  return p;
}

// La liste (message `liste_documents`) : un bouton par document ; `surChoix(chemin)` l'ouvre.
export function rendreListeDocuments(document, conteneur, message, surChoix) {
  if (!message.disponible) {
    conteneur.replaceChildren(paragraphe(document, "vide", MEMOIRE_ABSENTE));
    return;
  }
  if (message.documents.length === 0) {
    conteneur.replaceChildren(paragraphe(document, "vide", AUCUN_DOCUMENT));
    return;
  }
  const liste = document.createElement("ol");
  liste.className = "documents";
  liste.append(
    ...message.documents.map((doc) => {
      const bouton = document.createElement("button");
      bouton.type = "button";
      bouton.className = "document";
      bouton.append(paragraphe(document, "titre", doc.titre));
      if (doc.resume) bouton.append(paragraphe(document, "resume", doc.resume));
      bouton.append(paragraphe(document, "date", doc.modifie));
      bouton.addEventListener("click", () => surChoix(doc.chemin));
      const element = document.createElement("li");
      element.append(bouton);
      return element;
    }),
  );
  conteneur.replaceChildren(liste);
}

// Un document (message `document`) : sa mise en forme, ou l'erreur que le Core a rendue.
export function rendreDocument(document, conteneur, message) {
  if (message.erreur) {
    conteneur.replaceChildren(paragraphe(document, "erreur", message.erreur));
    return;
  }
  conteneur.replaceChildren(...rendreMarkdown(document, message.contenu));
}

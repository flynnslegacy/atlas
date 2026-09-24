import { sousTitresVisibles } from "./etat.js";

// Les sous-titres : la question en petit, la réponse (ou l'erreur, en rouge) en grand.
// Appelée à chaque image : le DOM n'est touché que si le texte change.
export function afficherSousTitres({ conteneur, question, reponse }, etat, maintenantMs) {
  const texte = etat.erreur || etat.reponse;
  if (question.textContent !== etat.question) question.textContent = etat.question;
  if (reponse.textContent !== texte) reponse.textContent = texte;
  reponse.classList.toggle("erreur", Boolean(etat.erreur));
  conteneur.classList.toggle("efface", !sousTitresVisibles(etat, maintenantMs));
}

// La rubrique « Connecteurs » des Paramètres (spec des connecteurs, §6) : chaque connecteur,
// son état, son interrupteur et ses réglages. Les textes d'un manifeste viennent d'un tiers :
// ils ne sont jamais que du texte.

import { REGLAGES, rendreReglages } from "./reglages.js";

export const MEMOIRE_ABSENTE = "La mémoire n'est pas disponible : pas de connecteurs.";
export const AUCUN_CONNECTEUR = "Aucun connecteur trouvé.";
export const EN_ATTENTE = "Prend effet à ta prochaine question.";
export const AVERTISSEMENT =
  "Ce connecteur ne vient pas d'Atlas : son code tournera dans Atlas, avec accès à tes réglages et à ta mémoire.";
export const ETATS = {
  actif: "Actif",
  coupe: "Coupé",
  a_configurer: "À configurer",
  a_installer: "À installer",
  en_erreur: "En erreur",
};
const ORIGINES = { atlas: "Atlas", communaute: "Communauté" };

function texte(document, balise, classe, contenu) {
  const element = document.createElement(balise);
  element.className = classe;
  element.textContent = contenu;
  return element;
}

function bouton(document, classe, contenu) {
  const element = texte(document, "button", classe, contenu);
  element.type = "button";
  return element;
}

// La valeur de « Connecteurs » dans la liste des rubriques (écran étroit) : combien sont actifs.
export function resumeConnecteurs(message) {
  if (!message?.disponible) return "";
  const actifs = message.connecteurs.filter((connecteur) => connecteur.etat === "actif").length;
  if (actifs === 0) return "Aucun actif";
  return actifs === 1 ? "1 actif" : `${actifs} actifs`;
}

// La liste (message `liste_connecteurs`) ; `surBascule(id, actif)` envoie l'interrupteur au Core.
// `reglages` : `surRegler(id, valeurs, effacer)`, et ce qui survit à un nouveau rendu de la
// liste : les réglages ouverts (`ouverts`, des identifiants) et les dernières réponses du Core
// (`resultats`, par identifiant).
export function rendreConnecteurs(document, conteneur, message, surBascule, reglages = {}) {
  const { surRegler = () => {}, ouverts = new Set(), resultats = new Map() } = reglages;
  if (!message.disponible) {
    conteneur.replaceChildren(texte(document, "p", "vide", MEMOIRE_ABSENTE));
    return;
  }
  if (message.connecteurs.length === 0) {
    conteneur.replaceChildren(texte(document, "p", "vide", AUCUN_CONNECTEUR));
    return;
  }
  const liste = document.createElement("ul");
  liste.className = "connecteurs";
  for (const connecteur of message.connecteurs) {
    liste.append(carte(document, connecteur, surBascule, surRegler, ouverts, resultats));
  }
  conteneur.replaceChildren(liste);
}

// Une carte : l'entête (le texte à gauche ; « Réglages… » et l'interrupteur à droite),
// l'avertissement « Communauté », puis les réglages, sous une ligne de séparation.
function carte(document, connecteur, surBascule, surRegler, ouverts, resultats) {
  const element = document.createElement("li");
  element.className = "connecteur";
  const { bascule, interrupteur } = lInterrupteur(document, connecteur);
  const actions = document.createElement("div");
  actions.className = "actions";
  const entete = document.createElement("div");
  entete.className = "entete";
  entete.append(leTexte(document, connecteur), actions);
  element.append(entete, lAvertissement(document, connecteur, interrupteur, surBascule));
  if (connecteur.reglages?.length) {
    const [ouvrir, formulaire] = lesReglages(document, connecteur, surRegler, ouverts, resultats);
    actions.append(ouvrir);
    element.append(formulaire);
  }
  actions.append(bascule);
  return element;
}

function leTexte(document, connecteur) {
  const titre = document.createElement("div");
  titre.className = "titre";
  titre.append(
    texte(document, "span", "nom", connecteur.nom),
    texte(document, "span", `badge ${connecteur.origine}`, ORIGINES[connecteur.origine]),
  );
  const element = document.createElement("div");
  element.className = "texte";
  element.append(titre);
  if (connecteur.description) element.append(texte(document, "p", "description", connecteur.description));
  const signature = [connecteur.version && `version ${connecteur.version}`, connecteur.auteur];
  const quoi = signature.filter(Boolean).join(" · ");
  if (quoi) element.append(texte(document, "p", "signature", quoi));
  const etat = [ETATS[connecteur.etat], connecteur.detail].filter(Boolean).join(" : ");
  element.append(texte(document, "p", `etat ${connecteur.etat}`, etat));
  if (connecteur.en_attente) element.append(texte(document, "p", "attente", EN_ATTENTE));
  return element;
}

function lInterrupteur(document, connecteur) {
  const interrupteur = document.createElement("input");
  interrupteur.type = "checkbox";
  interrupteur.checked = connecteur.etat === "actif";
  interrupteur.disabled = connecteur.etat !== "actif" && connecteur.etat !== "coupe";
  interrupteur.setAttribute("aria-label", `Activer ${connecteur.nom}`);
  // Habillé comme « Muet » et « Hey Atlas » : une glissière, pas une case.
  const bascule = document.createElement("label");
  bascule.className = "interrupteur";
  bascule.append(interrupteur);
  return { bascule, interrupteur };
}

// Un connecteur de la communauté : l'avertissement d'abord, l'activation ensuite.
function lAvertissement(document, connecteur, interrupteur, surBascule) {
  const avertissement = document.createElement("div");
  avertissement.className = "avertissement";
  avertissement.hidden = true;
  const activer = bouton(document, "activer", "Activer quand même");
  const annuler = bouton(document, "annuler", "Annuler");
  avertissement.append(texte(document, "p", "", AVERTISSEMENT), activer, annuler);
  interrupteur.addEventListener("change", () => {
    if (interrupteur.checked && connecteur.origine === "communaute") {
      interrupteur.checked = false;
      avertissement.hidden = false;
      return;
    }
    surBascule(connecteur.id, interrupteur.checked);
  });
  activer.addEventListener("click", () => {
    avertissement.hidden = true;
    surBascule(connecteur.id, true);
  });
  annuler.addEventListener("click", () => {
    avertissement.hidden = true;
  });
  return avertissement;
}

// Le bouton « Réglages… » et son formulaire, ouvert ou fermé comme avant le nouveau rendu.
function lesReglages(document, connecteur, surRegler, ouverts, resultats) {
  const ouvrir = bouton(document, "ouvrir-reglages", REGLAGES);
  const formulaire = rendreReglages(document, connecteur, surRegler, resultats.get(connecteur.id));
  const montrer = (ouvert) => {
    formulaire.hidden = !ouvert;
    ouvrir.setAttribute("aria-expanded", String(ouvert));
    if (ouvert) ouverts.add(connecteur.id);
    else ouverts.delete(connecteur.id);
  };
  montrer(ouverts.has(connecteur.id));
  ouvrir.addEventListener("click", () => montrer(formulaire.hidden));
  return [ouvrir, formulaire];
}

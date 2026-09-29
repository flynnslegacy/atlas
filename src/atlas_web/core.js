// La rubrique « Le Core » des Paramètres (spec des réglages et du Core, §5 et §6) : la version
// qui tourne, « Redémarrer » et « Mettre à jour et redémarrer », chacun confirmé ; les étapes et
// la fin, que toutes les pages voient ; et, pendant un redémarrage, le retour du Core attendu.

export const REDEMARRER = "Redémarrer";
export const METTRE_A_JOUR = "Mettre à jour et redémarrer";
export const CONFIRMATIONS = {
  redemarrer_core:
    "Redémarrer le Core ? La conversation en cours se clôt, avec son résumé au journal. Atlas revient dans une dizaine de secondes.",
  mettre_a_jour_core:
    "Mettre Atlas à jour ? Le Core récupère la dernière version, installe ce qui manque, puis redémarre. La conversation en cours se clôt.",
};
export const REDEMARRAGE = "Redémarrage du Core…";
export const NE_REVIENT_PAS = "Le Core ne revient pas";
export const NE_REVIENT_PAS_DETAIL =
  "Le Core ne revient pas : regarde son journal (donnees/logs/core.log sur le néo).";
export const DELAI_RETOUR_MS = 60000;

// Ce que la page sait du Core : `etat` (la dernière version reçue, l'étape en cours, la fin),
// et le retour attendu après un redémarrage. `envoyer` parle au Core ; `surChangement`
// redessine la rubrique.
export class SuiviCore {
  constructor({
    envoyer,
    surChangement,
    planifier = (rappel, delai) => setTimeout(rappel, delai),
    annuler = (minuteur) => clearTimeout(minuteur),
  }) {
    this._envoyer = envoyer;
    this._surChangement = surChangement;
    this._planifier = planifier;
    this._annuler = annuler;
    this.etat = { version: null, enCours: null, fin: null };
    this._retour = null; // { parti, perdu, minuteur } pendant un redémarrage
  }

  demander() {
    this._envoyer({ type: "demande_core" });
  }

  recevoir(message) {
    if (message.type === "etat_core") {
      this.etat.version = message;
    } else if (message.type === "core_en_cours") {
      this.etat.enCours = message;
      this.etat.fin = null;
      if (message.etape === "redemarrage") this._attendreLeRetour();
    } else if (message.type === "fin_core") {
      this.etat.fin = message;
      this.etat.enCours = null;
      this.demander(); // le Core n'est plus occupé : la version et les boutons à jour
    } else {
      return;
    }
    this._surChangement();
  }

  // Le statut de la connexion : le Core est revenu quand elle revient en ligne après
  // s'être coupée.
  surStatut(statut) {
    if (!this._retour) return;
    if (statut !== "en_ligne") {
      this._retour.parti = true;
    } else if (this._retour.parti) {
      this._annuler(this._retour.minuteur);
      this._retour = null;
      this.etat.enCours = null;
      this.etat.fin = null;
      this.demander();
      this._surChangement();
    }
  }

  // Le libellé de la barre du haut, hors ligne, pendant un redémarrage ; sinon null.
  libelle() {
    if (!this._retour) return null;
    return this._retour.perdu ? NE_REVIENT_PAS : REDEMARRAGE;
  }

  _attendreLeRetour() {
    if (this._retour) this._annuler(this._retour.minuteur);
    const retour = { parti: false, perdu: false, minuteur: null };
    retour.minuteur = this._planifier(() => {
      retour.perdu = true;
      this.etat.fin = { ok: false, texte: NE_REVIENT_PAS_DETAIL, details: [] };
      this._surChangement();
    }, DELAI_RETOUR_MS);
    this._retour = retour;
  }
}

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

// La rubrique ; `surAction(type)` envoie « redemarrer_core » ou « mettre_a_jour_core », une
// fois confirmé.
export function rendreCore(document, conteneur, etat, surAction) {
  const { version, enCours, fin } = etat;
  const elements = [];
  const quand = version?.date ? `, du ${version.date}` : "";
  elements.push(texte(document, "p", "version", version ? `Version ${version.version}${quand}` : "Version…"));

  const occupe = Boolean(enCours) || Boolean(version?.occupe);
  const redemarrer = bouton(document, "redemarrer", REDEMARRER);
  const mettreAJour = bouton(document, "mettre-a-jour", METTRE_A_JOUR);
  redemarrer.disabled = !version || occupe;
  mettreAJour.disabled = !version || occupe || !version.mise_a_jour_possible;
  const boutons = document.createElement("div");
  boutons.className = "boutons";
  boutons.append(redemarrer, mettreAJour);
  elements.push(boutons);
  if (version && !version.mise_a_jour_possible && version.raison) {
    elements.push(texte(document, "p", "raison", version.raison));
  }

  const confirmation = document.createElement("div");
  confirmation.className = "confirmation-core";
  confirmation.hidden = true;
  const question = texte(document, "p", "", "");
  const confirmer = bouton(document, "confirmer", "Confirmer");
  const annuler = bouton(document, "annuler", "Annuler");
  confirmation.append(question, confirmer, annuler);
  elements.push(confirmation);
  let demande = null;
  for (const [element, type] of [
    [redemarrer, "redemarrer_core"],
    [mettreAJour, "mettre_a_jour_core"],
  ]) {
    element.addEventListener("click", () => {
      demande = type;
      question.textContent = CONFIRMATIONS[type];
      confirmation.hidden = false;
    });
  }
  confirmer.addEventListener("click", () => {
    confirmation.hidden = true;
    if (demande) surAction(demande);
  });
  annuler.addEventListener("click", () => {
    confirmation.hidden = true;
  });

  if (enCours) {
    elements.push(texte(document, "p", "etape", enCours.texte));
    if (enCours.nouveautes.length) {
      const liste = document.createElement("ul");
      liste.className = "nouveautes";
      liste.append(...enCours.nouveautes.map((titre) => texte(document, "li", "", titre)));
      elements.push(liste);
    }
  }
  if (fin) {
    elements.push(texte(document, "p", `fin ${fin.ok ? "ok" : "refus"}`, fin.texte));
    if (fin.details.length) elements.push(texte(document, "pre", "details", fin.details.join("\n")));
  }
  conteneur.replaceChildren(...elements);
}

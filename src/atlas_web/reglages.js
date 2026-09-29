// Les réglages d'un connecteur, dans sa ligne des Paramètres (spec des réglages et du Core, §4) :
// un champ par réglage. La valeur d'un secret n'arrive jamais dans la page : elle dit seulement
// s'il est défini, et un champ masqué le remplace. Le Core vérifie tout.

export const REGLAGES = "Réglages…";
export const ENREGISTRER = "Enregistrer";
export const EFFACER = "Effacer";
export const DEFINI = "Défini";
export const A_DEFINIR = "À définir";
export const AU_TERMINAL = "se change au Terminal";
export const GARDER = "Défini — laisse vide pour le garder";

function texte(document, balise, classe, contenu) {
  const element = document.createElement(balise);
  element.className = classe;
  element.textContent = contenu;
  return element;
}

// Le formulaire ; `surRegler(id, valeurs, effacer)` envoie au Core ce qui a changé ;
// `resultat` : la réponse du Core au dernier envoi pour ce connecteur ({ ok, message }).
export function rendreReglages(document, connecteur, surRegler, resultat = null) {
  const formulaire = document.createElement("form");
  formulaire.className = "reglages";
  const champs = [];
  for (const reglage of connecteur.reglages) {
    const ligne = document.createElement("div");
    ligne.className = "reglage";
    const etiquette = document.createElement("label");
    etiquette.append(
      texte(document, "span", "description", reglage.description),
      texte(document, "span", "variable", reglage.variable),
    );
    ligne.append(etiquette);
    formulaire.append(ligne);
    if (!reglage.modifiable) {
      // Une clé d'Atlas : jamais de champ, quoi que dise le manifeste.
      const statut = `${reglage.defini ? DEFINI : A_DEFINIR}, ${AU_TERMINAL}`;
      ligne.append(texte(document, "p", "statut", statut));
      continue;
    }
    const champ = document.createElement("input");
    champ.type = reglage.secret ? "password" : "text";
    champ.value = reglage.secret ? "" : reglage.valeur;
    // « new-password » : un navigateur n'y remplit jamais un mot de passe enregistré (la clé de
    // la page), qui partirait vers le connecteur.
    champ.setAttribute("autocomplete", reglage.secret ? "new-password" : "off");
    champ.setAttribute("spellcheck", "false");
    if (reglage.secret) champ.setAttribute("placeholder", reglage.defini ? GARDER : A_DEFINIR);
    etiquette.append(champ);
    champs.push({ reglage, champ });
    if (reglage.secret && reglage.defini) {
      const effacer = texte(document, "button", "effacer", EFFACER);
      effacer.type = "button";
      effacer.addEventListener("click", () => surRegler(connecteur.id, {}, [reglage.variable]));
      ligne.append(effacer);
    }
  }
  if (champs.length) {
    const enregistrer = texte(document, "button", "enregistrer", ENREGISTRER);
    enregistrer.type = "submit";
    formulaire.append(enregistrer);
  }
  if (resultat) {
    formulaire.append(texte(document, "p", `resultat ${resultat.ok ? "ok" : "refus"}`, resultat.message));
  }
  formulaire.addEventListener("submit", (evenement) => {
    evenement.preventDefault();
    const valeurs = {};
    const effacer = [];
    for (const { reglage, champ } of champs) {
      if (reglage.secret) {
        if (champ.value !== "") valeurs[reglage.variable] = champ.value; // vide : on garde
      } else if (champ.value === "") {
        if (reglage.defini) effacer.push(reglage.variable);
      } else if (champ.value !== reglage.valeur) {
        valeurs[reglage.variable] = champ.value;
      }
    }
    if (Object.keys(valeurs).length || effacer.length) surRegler(connecteur.id, valeurs, effacer);
  });
  return formulaire;
}

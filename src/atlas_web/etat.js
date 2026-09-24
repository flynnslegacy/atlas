// L'état de la page, reconstruit à partir des messages du Core. Aucun accès au DOM :
// tout ici se teste avec node --test.

export const COULEURS = {
  repos: [100, 130, 170],
  ecoute: [34, 211, 238],
  reflexion: [167, 139, 250],
  parole: [251, 191, 36],
};
export const COULEUR_HORS_LIGNE = [90, 96, 110];
export const LIBELLES = { repos: "Repos", ecoute: "Écoute", reflexion: "Réflexion", parole: "Parole" };
export const DELAI_SOUS_TITRES_MS = 10000;
export const TAILLE_HISTORIQUE = 50;
export const SEUIL_SYLLABE = 0.55;
export const REFRACTAIRE_SYLLABE_S = 0.18;

export function creerEtat() {
  return {
    enLigne: false,
    etat: "repos",
    reposDepuis: null,
    volumeCible: 0,
    volume: 0,
    couleur: COULEUR_HORS_LIGNE.slice(),
    syllabe: false,
    auDessusSeuil: false,
    depuisSyllabe: Infinity,
    question: "",
    reponse: "",
    erreur: "",
    historique: [],
    muet: false,
  };
}

export function heureDe(ms) {
  const d = new Date(ms);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function joindre(avant, texte) {
  return avant ? `${avant} ${texte}` : texte;
}

function ajouterEchange(e, echange) {
  e.historique.push(echange);
  if (e.historique.length > TAILLE_HISTORIQUE) e.historique.shift();
}

export function appliquerMessage(e, message, maintenantMs) {
  const dernier = e.historique[e.historique.length - 1];
  switch (message.type) {
    case "etat":
      e.etat = message.valeur;
      e.reposDepuis = message.valeur === "repos" ? maintenantMs : null;
      if (message.valeur === "repos" || message.valeur === "reflexion") e.volumeCible = 0;
      break;
    case "niveau":
      e.volumeCible = message.valeur;
      break;
    case "question":
      e.question = message.texte;
      e.reponse = "";
      e.erreur = "";
      ajouterEchange(e, {
        heure: heureDe(maintenantMs),
        source: message.source,
        question: message.texte,
        reponse: "",
        erreur: null,
        latences: null,
      });
      break;
    case "reponse":
      e.reponse = joindre(e.reponse, message.texte);
      if (dernier) dernier.reponse = joindre(dernier.reponse, message.texte);
      break;
    case "erreur":
      e.erreur = message.message;
      if (e.etat === "repos") e.reposDepuis = maintenantMs; // l'erreur reste 10 s à l'écran
      if (message.code === "cle_absente") break;
      if (dernier && e.etat !== "repos") {
        dernier.erreur = message.message;
      } else {
        e.question = "";
        ajouterEchange(e, {
          heure: heureDe(maintenantMs),
          source: "voix",
          question: "",
          reponse: "",
          erreur: message.message,
          latences: null,
        });
      }
      break;
    case "latences":
      if (dernier) {
        dernier.latences = {
          transcription_ms: message.transcription_ms ?? null,
          reflexion_ms: message.reflexion_ms ?? null,
          premiere_voix_ms: message.premiere_voix_ms ?? null,
        };
      }
      break;
    case "muet":
      e.muet = message.actif;
      break;
    case "historique":
      e.historique = message.echanges.map((x) => ({
        heure: x.heure,
        source: x.source,
        question: x.question,
        reponse: x.reponse ?? "",
        erreur: x.erreur ?? null,
        latences: x.latences ?? null,
      }));
      break;
    default:
      break;
  }
  return e;
}

export function avancer(e, dt) {
  // Hors écoute et parole, le Core n'envoie plus de niveaux : la cible retombe seule.
  if (!e.enLigne || e.etat === "repos" || e.etat === "reflexion") {
    e.volumeCible *= Math.exp(-dt * 3);
  }
  e.volume += (e.volumeCible - e.volume) * (1 - Math.exp(-dt * 14));
  const cible = e.enLigne ? (COULEURS[e.etat] ?? COULEURS.repos) : COULEUR_HORS_LIGNE;
  const k = 1 - Math.exp(-dt * 4);
  for (let i = 0; i < 3; i++) e.couleur[i] += (cible[i] - e.couleur[i]) * k;
  // Une syllabe : le volume franchit le seuil vers le haut, pas plus d'une fois par
  // montée, et jamais à moins de 180 ms de la précédente.
  e.depuisSyllabe += dt;
  e.syllabe = false;
  if (e.volume >= SEUIL_SYLLABE) {
    if (!e.auDessusSeuil && e.depuisSyllabe >= REFRACTAIRE_SYLLABE_S) {
      e.syllabe = true;
      e.depuisSyllabe = 0;
    }
    e.auDessusSeuil = true;
  } else if (e.volume < SEUIL_SYLLABE * 0.7) {
    e.auDessusSeuil = false;
  }
  return e;
}

export function sousTitresVisibles(e, maintenantMs) {
  return !(e.etat === "repos" && e.reposDepuis !== null && maintenantMs - e.reposDepuis > DELAI_SOUS_TITRES_MS);
}

export function sceneDe(e, dt, reduire = false) {
  return {
    etat: e.enLigne ? e.etat : "repos",
    volume: e.volume * (reduire ? 0.6 : 1),
    couleur: e.couleur,
    syllabe: e.syllabe,
    dt,
  };
}

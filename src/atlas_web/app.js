// Le démarrage de la page : relie la connexion, la voix, l'état, l'orbe, le fond et les panneaux.

import { Connexion, identifiantDePage } from "./connexion.js";
import { dimensionner, rgba } from "./dessin.js";
import { LIBELLES, appliquerMessage, avancer, creerEtat, sceneDe } from "./etat.js";
import { fonds } from "./fonds/index.js";
import { rendreHistorique } from "./historique.js";
import { orbes } from "./orbes/index.js";
import { ouvrirGalerie } from "./parametres.js";
import { ecrireStockage, lireStockage } from "./registre.js";
import { afficherSousTitres } from "./sous_titres.js";
import { Voix } from "./voix.js";

const $ = (id) => document.getElementById(id);
const CLE_STOCKAGE = "atlas.cle";
const CLE_HEY_ATLAS = "atlas.hey_atlas";
const SEUIL_GLISSEMENT_PX = 60;
const TOUCHENT_HISTORIQUE = new Set(["question", "reponse", "erreur", "latences", "historique"]);
const STATUTS = {
  connexion: "Connexion…",
  hors_ligne: "Hors ligne — nouvelle tentative…",
  cle_requise: "Clé requise",
  cle_refusee: "Clé refusée",
  cle_absente: "Clé non configurée",
};
const MESSAGES_CLE = {
  cle_requise: "Entre la clé d'accès d'Atlas : la valeur de ATLAS_WEB_CLE dans le .env du Core.",
  cle_refusee: "Le Core a refusé cette clé. Vérifie ATLAS_WEB_CLE dans son .env.",
  cle_absente: "Le Core n'a pas de clé : ajoute ATLAS_WEB_CLE dans son .env, redémarre-le, puis entre-la ici.",
};
const MESSAGES_VOIX = {
  ouverture: "Ouverture du micro…",
  https_requis: "Le micro ne s'ouvre qu'à l'adresse HTTPS d'Atlas.",
  connexion: "Connexion de la voix…",
  hors_ligne: "Voix hors ligne — nouvelle tentative…",
  cle_requise: "Entre d'abord la clé d'accès d'Atlas.",
  cle_refusee: "Le Core a refusé la clé.",
  interrompue: "Micro en pause : écran verrouillé ou autre app.",
  a_reactiver: "Touche ici pour réactiver le micro.",
};

let stockage = null;
try {
  stockage = window.localStorage;
} catch {
  stockage = null; // stockage interdit : les choix ne seront pas mémorisés, la page marche quand même
}
let cleEnMemoire = null;
const page = identifiantDePage();

const etat = creerEtat();
let statut = "connexion";
let orbe = orbes.choisi(stockage).creer($("orbe"));
let fond = fonds.choisi(stockage).creer($("fond"));
let sceneCourante = sceneDe(etat, 0);
let galeries = [];
const reduire = window.matchMedia("(prefers-reduced-motion: reduce)");
const sousTitres = { conteneur: $("sous-titres"), question: $("st-question"), reponse: $("st-reponse") };

// --- La connexion -----------------------------------------------------------------

const connexion = new Connexion({
  url: `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/web`,
  lireCle: () => cleEnMemoire ?? lireStockage(stockage, CLE_STOCKAGE),
  entree: () => ({ page }),
  surMessage(message) {
    appliquerMessage(etat, message, Date.now());
    if (message.type === "muet") $("muet").checked = message.actif;
    if (TOUCHENT_HISTORIQUE.has(message.type) && !$("panneau-historique").hidden) {
      rendreHistorique(document, $("liste-historique"), etat.historique);
    }
  },
  surStatut(nouveau) {
    statut = nouveau;
    etat.enLigne = nouveau === "en_ligne";
    if (nouveau in MESSAGES_CLE) demanderCle(MESSAGES_CLE[nouveau]);
  },
});

// --- La voix ----------------------------------------------------------------------

const voix = new Voix({
  url: `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/voix`,
  lireCle: () => cleEnMemoire ?? lireStockage(stockage, CLE_STOCKAGE),
  page,
  heyAtlas: () => $("hey-atlas").checked,
  surStatut: afficherVoix,
});

function messageVoix(statut) {
  if (statut === "micro_refuse") {
    return `Micro indisponible (${voix.derniereErreur}) : autorise-le pour ce site dans les réglages du navigateur.`;
  }
  // 4000 : la clé ou les modèles manquent sur le Core, qui l'a dit juste avant de fermer.
  if (statut === "cle_absente") return voix.derniereErreur ?? "Le Core n'a pas de clé.";
  return MESSAGES_VOIX[statut] ?? "";
}

function afficherVoix(statut) {
  $("micro").setAttribute("aria-pressed", String(voix.allumee));
  $("micro").classList.toggle("allume", voix.allumee);
  $("parler").hidden = !voix.allumee;
  const message = messageVoix(statut);
  $("message-voix").textContent = message;
  $("message-voix").hidden = !message;
}

$("micro").addEventListener("click", () => {
  if (voix.allumee) voix.eteindre();
  else voix.allumer();
});
$("parler").addEventListener("click", () => voix.toucherOrbe());
$("message-voix").addEventListener("click", () => {
  if (voix.statut === "a_reactiver") voix.reactiver();
});
$("hey-atlas").checked = lireStockage(stockage, CLE_HEY_ATLAS) === "1";
$("hey-atlas").addEventListener("change", () => {
  ecrireStockage(stockage, CLE_HEY_ATLAS, $("hey-atlas").checked ? "1" : "0");
  voix.changerHeyAtlas($("hey-atlas").checked);
});

function demanderCle(message) {
  fermerPanneaux();
  $("message-cle").textContent = message;
  $("champ-cle").value = "";
  $("panneau-cle").hidden = false;
  $("champ-cle").focus();
}

$("formulaire-cle").addEventListener("submit", (evenement) => {
  evenement.preventDefault();
  const cle = $("champ-cle").value.trim();
  if (!cle) return;
  cleEnMemoire = cle;
  ecrireStockage(stockage, CLE_STOCKAGE, cle);
  $("panneau-cle").hidden = true;
  connexion.demarrer();
});

// --- La saisie et le muet ---------------------------------------------------------

$("saisie").addEventListener("submit", (evenement) => {
  evenement.preventDefault();
  const texte = $("champ").value.trim();
  if (texte && connexion.envoyer({ type: "saisie", texte })) $("champ").value = "";
});

$("muet").addEventListener("change", () => {
  // Le Core confirme à toutes les pages ; hors ligne, l'interrupteur revient à sa place.
  if (!connexion.envoyer({ type: "muet", actif: $("muet").checked })) $("muet").checked = etat.muet;
});

// --- Les panneaux -----------------------------------------------------------------

function ouvrirParametres() {
  const commun = { document, stockage, scene: () => sceneCourante };
  galeries = [
    ouvrirGalerie({
      ...commun,
      conteneur: $("galerie-orbes"),
      registre: orbes,
      surChoix: (choix) => {
        orbe = choix.creer($("orbe"));
      },
    }),
    ouvrirGalerie({
      ...commun,
      conteneur: $("galerie-fonds"),
      registre: fonds,
      surChoix: (choix) => {
        fond = choix.creer($("fond"));
      },
    }),
  ];
}

function ouvrirPanneau(panneau) {
  const dejaOuvert = !panneau.hidden;
  fermerPanneaux();
  if (dejaOuvert) return; // le même bouton ouvre et ferme
  panneau.hidden = false;
  panneau.scrollTop = 0;
  if (panneau === $("panneau-historique")) rendreHistorique(document, $("liste-historique"), etat.historique);
  else ouvrirParametres();
}

function fermerPanneaux() {
  for (const galerie of galeries) galerie.fermer();
  galeries = [];
  $("panneau-historique").hidden = true;
  $("panneau-parametres").hidden = true;
}

$("ouvrir-historique").addEventListener("click", () => ouvrirPanneau($("panneau-historique")));
$("ouvrir-parametres").addEventListener("click", () => ouvrirPanneau($("panneau-parametres")));
for (const bouton of document.querySelectorAll(".panneau .fermer")) {
  bouton.addEventListener("click", fermerPanneaux);
}
document.addEventListener("keydown", (evenement) => {
  if (evenement.key === "Escape") fermerPanneaux();
});

// Glisser vers le haut ouvre l'historique ; vers le bas, depuis le haut d'un panneau, le ferme.
let depart = null;
document.addEventListener(
  "touchstart",
  (evenement) => {
    if (evenement.touches.length !== 1) {
      depart = null;
      return;
    }
    const ouvert = document.querySelector(".panneau:not([hidden])");
    depart = { y: evenement.touches[0].clientY, ouvert, enHaut: !ouvert || ouvert.scrollTop === 0 };
  },
  { passive: true },
);
document.addEventListener(
  "touchend",
  (evenement) => {
    if (!depart || !$("panneau-cle").hidden) return;
    const dy = evenement.changedTouches[0].clientY - depart.y;
    if (!depart.ouvert && dy < -SEUIL_GLISSEMENT_PX) ouvrirPanneau($("panneau-historique"));
    else if (depart.ouvert && depart.enHaut && dy > SEUIL_GLISSEMENT_PX) fermerPanneaux();
    depart = null;
  },
  { passive: true },
);

// --- L'animation ------------------------------------------------------------------

let t = 0;
let precedent = null;
let idImage = null;
let erreurDessinSignalee = false;

function image(ms) {
  // L'image suivante d'abord : une exception plus bas ne doit jamais figer la boucle
  // (visibilitychange ne pourrait pas la relancer, idImage restant non nul).
  idImage = requestAnimationFrame(image);
  try {
    const dt = precedent === null ? 0 : Math.min(0.1, (ms - precedent) / 1000);
    precedent = ms;
    // Hors ligne, l'orbe se fige : son temps s'arrête, seule sa couleur glisse vers le gris.
    const pas = etat.enLigne ? dt * (reduire.matches ? 0.5 : 1) : 0;
    t += pas;
    avancer(etat, dt);
    sceneCourante = sceneDe(etat, pas, reduire.matches);
    dimensionner($("fond"));
    dimensionner($("orbe"));
    fond.dessiner(t, sceneCourante);
    orbe.dessiner(t, sceneCourante);
    $("pastille").style.backgroundColor = rgba(etat.couleur, 1);
    const libelle = etat.enLigne ? LIBELLES[etat.etat] : (STATUTS[statut] ?? "");
    if ($("libelle-etat").textContent !== libelle) $("libelle-etat").textContent = libelle;
    afficherSousTitres(sousTitres, etat, Date.now());
  } catch (e) {
    if (!erreurDessinSignalee) {
      erreurDessinSignalee = true; // une seule ligne, pas une par image, à 60 par seconde
      console.error("dessin interrompu :", e);
    }
  }
}

// Onglet caché : plus aucune image, ni de l'orbe ni du fond.
document.addEventListener("visibilitychange", () => {
  voix.surVisibilite(!document.hidden);
  if (document.hidden) {
    cancelAnimationFrame(idImage);
    idImage = null;
  } else if (idImage === null) {
    precedent = null;
    idImage = requestAnimationFrame(image);
  }
});

connexion.demarrer();
idImage = requestAnimationFrame(image);

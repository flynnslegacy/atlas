// Les rubriques des Paramètres (spec des Paramètres, §3) : une colonne à gauche, la rubrique
// choisie à droite ; sur un écran étroit, la liste d'abord, puis la rubrique, avec un retour.
// La page ne dit que « la liste » ou « la rubrique » (`data-vue`) : la largeur est une règle CSS,
// et un écran large montre les deux.

import { ecrireStockage, lireStockage } from "./registre.js";

export const RUBRIQUES = ["connecteurs", "voix", "orbe", "fond", "core"];
export const PAR_DEFAUT = "connecteurs";
export const CLE_RUBRIQUE = "atlas.rubrique";

// `boutons` : ceux de la colonne, chacun avec `data-rubrique` ; `pages` : la section de chaque
// rubrique ; `contenu` et `menu` : ce qui défile ; `boutonRetour` : « ‹ Paramètres » ; `estEtroit()` :
// l'écran montre-t-il une seule colonne ? `surChoix(id)` : la rubrique affichée (null : aucune,
// la liste seule).
export class Rubriques {
  constructor({
    boutons,
    pages,
    panneau,
    contenu,
    menu = null,
    boutonRetour = null,
    stockage,
    estEtroit = () => false,
    surChoix = () => {},
  }) {
    this._boutons = boutons;
    this._pages = pages;
    this._panneau = panneau;
    this._contenu = contenu;
    this._menu = menu;
    this._boutonRetour = boutonRetour;
    this._stockage = stockage;
    this._estEtroit = estEtroit;
    this._surChoix = surChoix;
    this.courante = null;
    for (const bouton of boutons) {
      bouton.addEventListener("click", () => this.choisir(bouton.dataset.rubrique));
    }
  }

  // À l'ouverture des Paramètres : la dernière rubrique choisie sur cet appareil ; sur un
  // écran étroit, la liste d'abord.
  ouvrir() {
    const retenue = lireStockage(this._stockage, CLE_RUBRIQUE);
    this._afficher(RUBRIQUES.includes(retenue) ? retenue : PAR_DEFAUT);
    this._panneau.dataset.vue = "menu";
    this._contenu.scrollTop = 0; // rouverts, ils repartent en haut, comme avant
    if (this._menu) this._menu.scrollTop = 0;
    this._surChoix(this._estEtroit() ? null : this.courante);
    this._boutonCourant()?.focus(); // le focus entre dans les Paramètres
  }

  choisir(id) {
    if (!RUBRIQUES.includes(id)) return;
    ecrireStockage(this._stockage, CLE_RUBRIQUE, id);
    this._afficher(id);
    this._panneau.dataset.vue = "rubrique";
    this._contenu.scrollTop = 0;
    this._surChoix(id);
    // Sur un écran étroit, la colonne se cache : le focus passe dans la rubrique.
    if (this._estEtroit()) this._boutonRetour?.focus();
  }

  // « ‹ Paramètres » : la liste ; sur un écran large, la rubrique reste à côté.
  retour() {
    this._panneau.dataset.vue = "menu";
    if (!this._estEtroit()) return;
    this._surChoix(null);
    this._boutonCourant()?.focus(); // la rubrique qu'on vient de quitter
  }

  _boutonCourant() {
    return this._boutons.find((bouton) => bouton.dataset.rubrique === this.courante);
  }

  // La largeur a changé, les Paramètres ouverts (une fenêtre redimensionnée, un iPad en Split
  // View) : une rubrique apparaît ou disparaît, et sa galerie avec elle.
  surLargeur() {
    const affichee = this._estEtroit() && this._panneau.dataset.vue === "menu" ? null : this.courante;
    this._surChoix(affichee);
  }

  _afficher(id) {
    this.courante = id;
    for (const bouton of this._boutons) {
      bouton.setAttribute("aria-current", bouton.dataset.rubrique === id ? "page" : "false");
    }
    for (const [cle, page] of Object.entries(this._pages)) page.hidden = cle !== id;
  }
}

// Doublures minimales du DOM et du stockage du navigateur, pour node --test.

import { fauxCanevas } from "./faux_canevas.mjs";

export function fauxElement(tag) {
  const classes = new Set();
  const ecouteurs = {};
  return {
    tagName: tag.toUpperCase(),
    children: [],
    className: "",
    textContent: "",
    type: "",
    hidden: false,
    attributs: {},
    setAttribute(nom, valeur) {
      this.attributs[nom] = String(valeur);
    },
    classList: {
      add: (nom) => classes.add(nom),
      remove: (nom) => classes.delete(nom),
      contains: (nom) => classes.has(nom),
      toggle(nom, force) {
        const actif = force ?? !classes.has(nom);
        if (actif) classes.add(nom);
        else classes.delete(nom);
        return actif;
      },
    },
    append(...enfants) {
      this.children.push(...enfants);
    },
    replaceChildren(...enfants) {
      this.children = enfants;
    },
    addEventListener(type, rappel) {
      (ecouteurs[type] ??= []).push(rappel);
    },
    declencher(type, evenement = {}) {
      for (const rappel of ecouteurs[type] ?? []) rappel(evenement);
    },
  };
}

export function fauxDocument() {
  const canevas = [];
  return {
    canevas,
    createElement(tag) {
      const element = fauxElement(tag);
      if (tag !== "canvas") return element;
      const faux = fauxCanevas(160, 160);
      canevas.push(faux);
      return Object.assign(element, faux.canvas);
    },
  };
}

export function fauxStockage(initial = {}) {
  const valeurs = new Map(Object.entries(initial));
  return {
    getItem: (cle) => valeurs.get(cle) ?? null,
    setItem: (cle, valeur) => valeurs.set(cle, String(valeur)),
  };
}

export const stockageCasse = {
  getItem() {
    throw new Error("stockage interdit");
  },
  setItem() {
    throw new Error("stockage interdit");
  },
};

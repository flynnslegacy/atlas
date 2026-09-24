// Un registre d'éléments interchangeables (orbes, fonds), avec le choix mémorisé par
// ce navigateur. Le stockage peut manquer ou refuser (navigation privée) : rien ne casse.

export function lireStockage(stockage, cle) {
  try {
    return stockage?.getItem(cle) ?? null;
  } catch {
    return null;
  }
}

export function ecrireStockage(stockage, cle, valeur) {
  try {
    stockage?.setItem(cle, valeur);
    return Boolean(stockage);
  } catch {
    return false;
  }
}

export function creerRegistre(elements, idParDefaut, cle) {
  const vus = new Set();
  for (const element of elements) {
    if (vus.has(element.id)) throw new Error(`identifiant en double : ${element.id}`);
    vus.add(element.id);
  }
  const parDefaut = elements.find((element) => element.id === idParDefaut);
  if (!parDefaut) throw new Error(`élément par défaut introuvable : ${idParDefaut}`);
  return {
    tous: elements,
    parDefaut,
    choisi(stockage) {
      const id = lireStockage(stockage, cle);
      return elements.find((element) => element.id === id) ?? parDefaut;
    },
    choisir(stockage, id) {
      const element = elements.find((candidat) => candidat.id === id);
      if (!element) throw new Error(`élément inconnu : ${id}`);
      ecrireStockage(stockage, cle, id);
      return element;
    },
  };
}

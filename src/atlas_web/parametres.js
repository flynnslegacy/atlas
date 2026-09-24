import { dimensionner } from "./dessin.js";

// Une galerie d'aperçus animés (orbes ou fonds). Un clic applique et mémorise le choix.
// Les aperçus ne tournent que tant que la galerie est ouverte.
export function ouvrirGalerie({
  document,
  conteneur,
  registre,
  stockage,
  scene,
  surChoix,
  planifier = (rappel) => requestAnimationFrame(rappel),
  annuler = (id) => cancelAnimationFrame(id),
}) {
  const choisi = registre.choisi(stockage).id;
  const cartes = registre.tous.map((element) => {
    const carte = document.createElement("button");
    carte.type = "button";
    carte.title = element.idee;
    carte.classList.add("carte");
    carte.classList.toggle("choisie", element.id === choisi);
    const canvas = document.createElement("canvas");
    const nom = document.createElement("span");
    nom.textContent = element.nom;
    carte.append(canvas, nom);
    return { carte, canvas, element, dessin: null };
  });
  for (const { carte, element } of cartes) {
    carte.addEventListener("click", () => {
      registre.choisir(stockage, element.id);
      for (const autre of cartes) autre.carte.classList.toggle("choisie", autre.element === element);
      surChoix(element);
    });
  }
  conteneur.replaceChildren(...cartes.map((c) => c.carte));

  let ouverte = true;
  let debut = null;
  let id = null;
  function image(ms) {
    if (!ouverte) return;
    debut ??= ms;
    const s = scene();
    for (const c of cartes) {
      dimensionner(c.canvas, 1);
      c.dessin ??= c.element.creer(c.canvas);
      c.dessin.dessiner((ms - debut) / 1000, s);
    }
    id = planifier(image);
  }
  id = planifier(image);

  return {
    fermer() {
      ouverte = false;
      if (id !== null) annuler(id);
      id = null;
      conteneur.replaceChildren();
    },
  };
}

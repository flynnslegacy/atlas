import { creerRegistre } from "../registre.js";
import anneaux from "./anneaux.js";
import armillaire from "./armillaire.js";
import aurore from "./aurore.js";
import constellations from "./constellations.js";
import cymatique from "./cymatique.js";
import galaxie from "./galaxie.js";
import liquide from "./liquide.js";
import mandala from "./mandala.js";
import oscilloscope from "./oscilloscope.js";
import particules from "./particules.js";
import plasma from "./plasma.js";
import relief from "./relief.js";

// L'ordre est celui de la galerie des paramètres.
export const orbes = creerRegistre(
  [
    particules,
    liquide,
    anneaux,
    armillaire,
    relief,
    cymatique,
    oscilloscope,
    plasma,
    constellations,
    aurore,
    galaxie,
    mandala,
  ],
  "aurore",
  "atlas.orbe",
);

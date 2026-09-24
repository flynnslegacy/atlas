import { creerRegistre } from "../registre.js";
import bokeh from "./bokeh.js";
import etoiles from "./etoiles.js";
import horizon from "./horizon.js";
import nebuleuse from "./nebuleuse.js";
import nuit from "./nuit.js";
import tunnel from "./tunnel.js";

// L'ordre est celui de la galerie des paramètres.
export const fonds = creerRegistre([nuit, etoiles, nebuleuse, horizon, bokeh, tunnel], "bokeh", "atlas.fond");

// Une doublure du contexte 2D : elle accepte tout appel, refuse les nombres invalides
// et les rayons négatifs (un vrai navigateur lèverait une erreur), compte ce qui est
// dessiné et relève toute peinture opaque de tout le canevas.

export const ETATS = ["repos", "ecoute", "reflexion", "parole"];
export const IMAGES_PAR_ETAT = 75;

const RAYONS = { arc: [2], ellipse: [2, 3], createRadialGradient: [2, 5] };
const DESSINS = new Set(["fill", "stroke", "fillRect", "strokeRect"]);

function estOpaque(style) {
  if (typeof style !== "string") return false; // un dégradé
  const alpha = style.match(/^rgba\((?:[^,]+,){3}\s*([\d.]+)\)$/i);
  if (alpha) return Number(alpha[1]) >= 0.99;
  return /^(#|rgb\()/i.test(style);
}

export function fauxCanevas(largeur = 400, hauteur = 400) {
  const bilan = { dessins: 0, peinturesOpaquesPleines: 0 };
  const canvas = { width: largeur, height: hauteur, clientWidth: largeur, clientHeight: hauteur };
  const etat = {
    fillStyle: "#000000",
    strokeStyle: "#000000",
    lineWidth: 1,
    globalCompositeOperation: "source-over",
    globalAlpha: 1,
  };
  const ctx = new Proxy(etat, {
    get(cible, nom) {
      if (nom in cible) return cible[nom];
      return (...args) => {
        args.forEach((valeur, i) => {
          if (typeof valeur === "number" && !Number.isFinite(valeur)) {
            throw new Error(`${String(nom)} : argument ${i} = ${valeur}`);
          }
        });
        for (const i of RAYONS[nom] ?? []) {
          if (args[i] < 0) throw new Error(`${String(nom)} : rayon négatif (${args[i]})`);
        }
        if (nom === "createRadialGradient" || nom === "createLinearGradient") {
          return {
            addColorStop(position, couleur) {
              if (!(position >= 0 && position <= 1)) throw new Error(`addColorStop : ${position}`);
              if (String(couleur).includes("NaN")) throw new Error(`addColorStop : ${couleur}`);
            },
          };
        }
        if (DESSINS.has(nom)) bilan.dessins += 1;
        const plein =
          nom === "fillRect" &&
          args[0] <= 0 &&
          args[1] <= 0 &&
          args[0] + args[2] >= canvas.width &&
          args[1] + args[3] >= canvas.height;
        if (plein && estOpaque(cible.fillStyle)) bilan.peinturesOpaquesPleines += 1;
        return undefined;
      };
    },
    set(cible, nom, valeur) {
      if (typeof valeur === "string" && valeur.includes("NaN")) throw new Error(`${String(nom)} = ${valeur}`);
      if (typeof valeur === "number" && !Number.isFinite(valeur)) throw new Error(`${String(nom)} = ${valeur}`);
      cible[nom] = valeur;
      return true;
    },
  });
  canvas.getContext = () => ctx;
  return { canvas, bilan };
}

export function animer(module, canevas, couleur = [34, 211, 238]) {
  const dessin = module.creer(canevas.canvas);
  let t = 0;
  for (const etat of ETATS) {
    for (let i = 0; i < IMAGES_PAR_ETAT; i++) {
      t += 1 / 60;
      const parle = etat === "ecoute" || etat === "parole";
      const volume = parle ? 0.5 + 0.5 * Math.sin(i / 3) : 0.05;
      dessin.dessiner(t, { etat, volume, couleur, syllabe: i % 12 === 0, dt: 1 / 60 });
    }
  }
}

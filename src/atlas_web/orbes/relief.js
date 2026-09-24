import { geo, preparerOrbe, rgba, trace } from "../dessin.js";

const LIGNES = 30;

function relief(x, y, largeur, t, scene) {
  const u = x / largeur;
  const bord = Math.max(0, 1 - u * u);
  let h = 0.015 * Math.sin(9 * x + t * 1.3 + y * 7);
  const force = scene.etat === "repos" ? 0.08 : scene.etat === "reflexion" ? 0.25 : scene.volume;
  for (let k = 0; k < 4; k++) {
    const centre = Math.sin(t * 0.35 + k * 1.9 + y * 1.3) * 0.65 * largeur;
    const haut = force * (0.45 + 0.55 * Math.sin(t * (4 + k) + k * 1.7 + y * 3)) * (0.6 + 0.4 * Math.cos(y * 2 + k));
    h += Math.max(0, haut) * Math.exp(-(((x - centre) / 0.16) ** 2));
  }
  if (scene.etat === "reflexion") {
    const front = ((t * 0.7) % 2.4) - 1.2;
    h += 0.35 * Math.exp(-(((y - front) / 0.1) ** 2)) * (0.5 + 0.5 * Math.sin(20 * x - t * 6));
  }
  return h * bord;
}

export default {
  id: "relief",
  nom: "Globe en lignes de relief",
  idee: "Un globe en courbes de niveau : un atlas, ce sont des cartes.",
  creer(canvas) {
    const ctx = canvas.getContext("2d");
    return {
      dessiner(t, scene) {
        const g = geo(canvas);
        const R = g.m * 0.33;
        preparerOrbe(ctx, g, scene);
        for (let i = 0; i < LIGNES; i++) {
          const y = -0.94 + (1.88 * i) / (LIGNES - 1);
          const largeur = Math.sqrt(1 - y * y);
          const points = [];
          for (let j = 0; j <= 60; j++) {
            const x = -largeur + (2 * largeur * j) / 60;
            points.push([g.cx + x * R, g.cy + y * R - relief(x, y, largeur, t, scene) * R * 0.45]);
          }
          // Chaque ligne masque celles de derrière : le globe a un corps sombre.
          trace(ctx, points);
          ctx.lineTo(points[points.length - 1][0], g.cy + y * R + 2 * g.k);
          ctx.lineTo(points[0][0], g.cy + y * R + 2 * g.k);
          ctx.closePath();
          ctx.fillStyle = "rgba(5,7,13,0.92)";
          ctx.fill();
          trace(ctx, points);
          ctx.strokeStyle = rgba(scene.couleur, 0.35 + 0.6 * (0.45 + 0.55 * (i / (LIGNES - 1))), 0.15);
          ctx.lineWidth = 1.4 * g.k;
          ctx.stroke();
        }
      },
    };
  },
};

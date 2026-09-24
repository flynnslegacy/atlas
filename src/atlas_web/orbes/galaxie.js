import { geo, lueur, preparerOrbe, rgba, TOUR } from "../dessin.js";

const BRAS = 3;
const INCLINAISON = -0.35;

export default {
  id: "galaxie",
  nom: "Galaxie spirale",
  idee: "Des bras d'étoiles qui tournent ; la voix y lance des ondes.",
  creer(canvas) {
    const ctx = canvas.getContext("2d");
    const etoiles = [];
    for (let i = 0; i < 1300; i++) {
      const bras = i % BRAS;
      const r = Math.random() ** 0.7;
      etoiles.push([r, (bras * TOUR) / BRAS + r * 4.2 + (Math.random() - 0.5) * 0.5]);
    }
    const cos = Math.cos(INCLINAISON);
    const sin = Math.sin(INCLINAISON);
    return {
      dessiner(t, scene) {
        const g = geo(canvas);
        const R = g.m * 0.42;
        const taille = 1.3 * g.k;
        const c = scene.couleur;
        const v = scene.volume;
        const vitesse = scene.etat === "reflexion" ? 1.2 : 0.25;
        const parle = scene.etat === "parole" || scene.etat === "ecoute";
        preparerOrbe(ctx, g, scene);
        ctx.globalCompositeOperation = "lighter";
        for (const [r, angleDepart] of etoiles) {
          const angle = angleDepart + (t * vitesse * 0.35) / (0.25 + r); // le centre tourne plus vite
          const x0 = Math.cos(angle) * r;
          const y0 = Math.sin(angle) * r * 0.5;
          const onde = parle ? Math.max(0, Math.sin(r * 10 - t * 6)) * v : 0;
          ctx.fillStyle = rgba(c, 0.2 + 0.5 * (1 - r) + onde * 0.6, 0.3 * (1 - r));
          ctx.fillRect(g.cx + (x0 * cos - y0 * sin) * R, g.cy + (x0 * sin + y0 * cos) * R, taille, taille);
        }
        lueur(ctx, g.cx, g.cy, R * (0.16 + v * 0.08), c, 1, 0.8);
      },
    };
  },
};

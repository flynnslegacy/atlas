import { geo, lueur, preparerOrbe, rgba, TOUR } from "../dessin.js";

const ANNEAUX = [
  { r: 0.4, n: 18, l: 5, v: 0.35 },
  { r: 0.55, n: 64, l: 2, v: -0.22 },
  { r: 0.7, n: 10, l: 7, v: 0.12 },
  { r: 0.84, n: 96, l: 1.5, v: -0.06 },
];

// Chaque anneau a des segments manquants, tirés une fois pour toutes.
function present(segment, anneau) {
  const x = Math.sin(segment * 12.9898 + anneau * 78.233) * 43758.5453;
  return x - Math.floor(x) >= 0.3;
}

export default {
  id: "anneaux",
  nom: "Anneaux « réacteur »",
  idee: "Des anneaux en segments autour d'un cœur, façon cockpit.",
  creer(canvas) {
    const ctx = canvas.getContext("2d");
    return {
      dessiner(t, scene) {
        const g = geo(canvas);
        const R = g.m * 0.36;
        const v = scene.volume;
        const acceleration = scene.etat === "reflexion" ? 4 : 1;
        preparerOrbe(ctx, g, scene);
        ctx.globalCompositeOperation = "lighter";
        lueur(ctx, g.cx, g.cy, R * (0.28 + v * 0.12), scene.couleur, 0.95, 0.7);
        ANNEAUX.forEach((anneau, j) => {
          ctx.lineWidth = anneau.l * g.k;
          const pas = TOUR / anneau.n;
          for (let s = 0; s < anneau.n; s++) {
            if (!present(s, j)) continue;
            const debut = s * pas + t * anneau.v * acceleration;
            ctx.strokeStyle = rgba(scene.couleur, 0.35 + 0.55 * v * (j % 2 ? 1 : 0.6));
            ctx.beginPath();
            ctx.arc(g.cx, g.cy, R * anneau.r, debut, debut + pas * 0.7);
            ctx.stroke();
          }
        });
        if (scene.etat === "parole" || scene.etat === "ecoute") {
          ctx.lineWidth = 1.5 * g.k;
          ctx.strokeStyle = rgba(scene.couleur, 0.7, 0.3);
          ctx.beginPath();
          for (let i = 0; i <= 180; i++) {
            const th = (i / 180) * TOUR;
            const r = R * (0.95 + v * 0.06 * Math.sin(24 * th + t * 12));
            const x = g.cx + r * Math.cos(th);
            const y = g.cy + r * Math.sin(th);
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
          }
          ctx.stroke();
        }
      },
    };
  },
};

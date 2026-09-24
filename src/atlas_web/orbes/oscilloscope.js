import { geo, melanger, preparerOrbe, rgba, trace, TOUR } from "../dessin.js";

const PHOSPHORE = [124, 255, 140];
const RAPPORTS = { repos: [1, 1], ecoute: [1, 2], reflexion: [3, 4], parole: [2, 3] };

export default {
  id: "oscilloscope",
  nom: "Oscilloscope",
  idee: "Des courbes de Lissajous en phosphore vert, façon labo rétro.",
  creer(canvas) {
    const ctx = canvas.getContext("2d");
    let a = 1;
    let b = 2;
    return {
      dessiner(t, scene) {
        const g = geo(canvas);
        const R = g.m * 0.36;
        const v = scene.volume;
        preparerOrbe(ctx, g, scene);
        ctx.fillStyle = "rgba(2,8,5,0.85)"; // l'écran du tube
        ctx.beginPath();
        ctx.arc(g.cx, g.cy, R * 1.04, 0, TOUR);
        ctx.fill();
        ctx.strokeStyle = "rgba(124,255,140,0.10)";
        ctx.lineWidth = g.k;
        for (let i = -4; i <= 4; i++) {
          const d = (i * R) / 4;
          const l = Math.sqrt(Math.max(0, R * R - d * d));
          ctx.beginPath();
          ctx.moveTo(g.cx - l, g.cy + d);
          ctx.lineTo(g.cx + l, g.cy + d);
          ctx.stroke();
          ctx.beginPath();
          ctx.moveTo(g.cx + d, g.cy - l);
          ctx.lineTo(g.cx + d, g.cy + l);
          ctx.stroke();
        }
        ctx.strokeStyle = "rgba(124,255,140,0.25)";
        ctx.lineWidth = 2 * g.k;
        ctx.beginPath();
        ctx.arc(g.cx, g.cy, R * 1.04, 0, TOUR);
        ctx.stroke();
        const cible = RAPPORTS[scene.etat] ?? RAPPORTS.repos;
        const k = 1 - Math.exp(-scene.dt * 1.2); // la figure glisse d'un rapport à l'autre
        a += (cible[0] - a) * k;
        b += (cible[1] - b) * k;
        const phase = t * (scene.etat === "reflexion" ? 1.5 : 0.4);
        const amplitude = R * (0.45 + 0.5 * v);
        const points = [];
        for (let i = 0; i <= 500; i++) {
          const tau = (i / 500) * TOUR;
          let y = Math.sin(b * tau);
          if (scene.etat === "parole" || scene.etat === "ecoute") y += v * 0.08 * Math.sin(37 * tau + t * 25);
          points.push([g.cx + Math.sin(a * tau + phase) * amplitude, g.cy + y * amplitude]);
        }
        const teinte = melanger(PHOSPHORE, scene.couleur, 0.35);
        ctx.globalCompositeOperation = "lighter";
        ctx.strokeStyle = rgba(teinte, 0.22);
        ctx.lineWidth = 6 * g.k;
        trace(ctx, points);
        ctx.stroke();
        ctx.strokeStyle = rgba(teinte, 0.95, 0.4);
        ctx.lineWidth = 1.6 * g.k;
        trace(ctx, points);
        ctx.stroke();
      },
    };
  },
};

import { geo, lueur, preparerOrbe, rgba, TOUR } from "../dessin.js";

export default {
  id: "mandala",
  nom: "Mandala",
  idee: "Un kaléidoscope à 12 branches qui respire avec la voix.",
  creer(canvas) {
    const ctx = canvas.getContext("2d");
    return {
      dessiner(t, scene) {
        const g = geo(canvas);
        const R = g.m * 0.38;
        const c = scene.couleur;
        const v = scene.volume;
        const rotation = t * (scene.etat === "reflexion" ? 0.6 : 0.08);
        const souffle = 1 + v * 0.22;
        preparerOrbe(ctx, g, scene);
        ctx.globalCompositeOperation = "lighter";
        ctx.save();
        ctx.translate(g.cx, g.cy);
        ctx.rotate(rotation);
        for (let s = 0; s < 12; s++) {
          ctx.save();
          ctx.rotate((s * Math.PI) / 6);
          if (s % 2) ctx.scale(1, -1); // une branche sur deux en miroir : le kaléidoscope
          for (let k = 0; k < 3; k++) {
            const r1 = R * (0.12 + 0.26 * k) * souffle;
            const r2 = R * (0.34 + 0.26 * k) * souffle;
            const bosse = R * (0.1 + 0.07 * Math.sin(t * 1.5 + k * 1.3 + (scene.etat === "parole" ? v * 4 : 0)));
            ctx.strokeStyle = rgba(c, 0.45 + 0.4 * v - k * 0.1, k * 0.15);
            ctx.lineWidth = (1.6 - k * 0.35) * g.k;
            ctx.beginPath();
            ctx.moveTo(r1, 0);
            ctx.quadraticCurveTo((r1 + r2) / 2, bosse, r2, 0);
            ctx.quadraticCurveTo((r1 + r2) / 2, -bosse * 0.35, r1, 0);
            ctx.stroke();
            ctx.fillStyle = rgba(c, 0.8, 0.5);
            ctx.beginPath();
            ctx.arc(r2, 0, (1.6 - k * 0.3) * g.k * (1 + v), 0, TOUR);
            ctx.fill();
          }
          ctx.restore();
        }
        ctx.restore();
        lueur(ctx, g.cx, g.cy, R * (0.14 + v * 0.1), c, 1, 0.8);
      },
    };
  },
};

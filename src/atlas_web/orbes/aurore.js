import { geo, preparerOrbe, rgba, TOUR } from "../dessin.js";

export default {
  id: "aurore",
  nom: "Aurore boréale",
  idee: "Des rideaux de lumière qui ondulent dans un hublot.",
  creer(canvas) {
    const ctx = canvas.getContext("2d");
    return {
      dessiner(t, scene) {
        const g = geo(canvas);
        const R = g.m * 0.38;
        const c = scene.couleur;
        preparerOrbe(ctx, g, scene);
        ctx.save();
        ctx.beginPath();
        ctx.arc(g.cx, g.cy, R, 0, TOUR);
        ctx.clip();
        const ciel = ctx.createLinearGradient(0, g.cy - R, 0, g.cy + R);
        ciel.addColorStop(0, "rgba(4,6,12,0.92)");
        ciel.addColorStop(1, "rgba(11,20,36,0.92)");
        ctx.fillStyle = ciel;
        ctx.fillRect(g.cx - R, g.cy - R, 2 * R, 2 * R);
        ctx.globalCompositeOperation = "lighter";
        const force = scene.etat === "repos" ? 0.25 : scene.etat === "reflexion" ? 0.55 : 0.35 + 0.65 * scene.volume;
        const vitesse = scene.etat === "reflexion" ? 2.5 : 1;
        const pas = 3 * g.k;
        for (let n = 0; n < 3; n++) {
          for (let x = g.cx - R; x < g.cx + R; x += pas) {
            const u = (x - g.cx) / R;
            const base = g.cy + R * (0.22 + 0.16 * Math.sin(u * 2.2 + t * 0.5 * vitesse + n * 1.3) + n * 0.09);
            const haut = R * (0.2 + 0.45 * force * (0.55 + 0.45 * Math.sin(u * 6 + t * (2 + n) * vitesse + n)));
            for (let s = 0; s < 6; s++) {
              ctx.fillStyle = rgba(c, (0.12 + force * 0.22) * (1 - s / 6) ** 1.3, 0.25 + 0.2 * n);
              ctx.fillRect(x, base - (haut * (s + 1)) / 6, pas, haut / 6);
            }
            ctx.fillStyle = rgba(c, 0.25 + force * 0.4, 0.6); // le liseré lumineux au pied du rideau
            ctx.fillRect(x, base - 1.5 * g.k, pas, 1.5 * g.k);
          }
        }
        ctx.restore();
        ctx.globalCompositeOperation = "source-over";
        ctx.strokeStyle = rgba(c, 0.35);
        ctx.lineWidth = 2 * g.k;
        ctx.beginPath();
        ctx.arc(g.cx, g.cy, R, 0, TOUR);
        ctx.stroke();
      },
    };
  },
};

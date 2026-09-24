import { geo, preparerOrbe, rgba, trace, TOUR } from "../dessin.js";

export default {
  id: "liquide",
  nom: "Orbe liquide",
  idee: "Une goutte de lumière aux contours mouvants.",
  creer(canvas) {
    const ctx = canvas.getContext("2d");
    return {
      dessiner(t, scene) {
        const g = geo(canvas);
        const R = g.m * 0.27;
        const lent = scene.etat === "reflexion" ? 2.2 : 1;
        const v = scene.volume;
        preparerOrbe(ctx, g, scene);
        ctx.globalCompositeOperation = "lighter";
        for (let k = 0; k < 3; k++) {
          const points = [];
          for (let i = 0; i <= 100; i++) {
            const th = (i / 100) * TOUR;
            const r =
              R *
              (0.82 + 0.09 * k) *
              (1 +
                (0.04 + v * 0.2) * Math.sin(3 * th + t * 2.1 * lent + k * 1.7) +
                0.05 * Math.sin(5 * th - t * 1.6 * lent + k * 2.3) +
                (0.02 + v * 0.08) * Math.sin(2 * th + t * 1.3 * lent * (k + 1)));
            points.push([g.cx + r * Math.cos(th), g.cy + r * Math.sin(th)]);
          }
          trace(ctx, points);
          const degrade = ctx.createRadialGradient(g.cx, g.cy - R * 0.2, R * 0.05, g.cx, g.cy, R * 1.2);
          degrade.addColorStop(0, rgba(scene.couleur, 0.55, 0.6));
          degrade.addColorStop(0.6, rgba(scene.couleur, 0.35));
          degrade.addColorStop(1, rgba(scene.couleur, 0));
          ctx.fillStyle = degrade;
          ctx.fill();
        }
      },
    };
  },
};

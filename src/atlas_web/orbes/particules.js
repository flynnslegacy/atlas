import { geo, preparerOrbe, rgba, tourner, TOUR } from "../dessin.js";

export default {
  id: "particules",
  nom: "Sphère de particules",
  idee: "Un nuage de points en 3D qui se gonfle avec la voix.",
  creer(canvas) {
    const ctx = canvas.getContext("2d");
    const points = [];
    const nombre = 500;
    const angleOr = Math.PI * (3 - Math.sqrt(5));
    for (let i = 0; i < nombre; i++) {
      const y = 1 - (i / (nombre - 1)) * 2;
      const r = Math.sqrt(1 - y * y);
      const phi = i * angleOr;
      points.push([Math.cos(phi) * r, y, Math.sin(phi) * r, Math.random() * TOUR]);
    }
    return {
      dessiner(t, scene) {
        const g = geo(canvas);
        const R = g.m * 0.3;
        const ay = t * (scene.etat === "reflexion" ? 0.9 : 0.18);
        const bande = Math.sin(t * 2.2);
        preparerOrbe(ctx, g, scene);
        ctx.globalCompositeOperation = "lighter";
        for (const p of points) {
          const q = tourner(p, ay, 0.35);
          const d = 1 + scene.volume * 0.32 * Math.sin(3 * p[1] + t * 5 + p[3]);
          const profondeur = (q[2] + 1) / 2;
          let alpha = 0.18 + 0.7 * profondeur;
          if (scene.etat === "reflexion" && Math.abs(p[1] - bande) < 0.12) alpha = 1;
          ctx.fillStyle = rgba(scene.couleur, alpha, 0.25 * profondeur);
          ctx.beginPath();
          ctx.arc(g.cx + q[0] * R * d, g.cy + q[1] * R * d, (0.6 + 1.6 * profondeur) * g.k, 0, TOUR);
          ctx.fill();
        }
      },
    };
  },
};

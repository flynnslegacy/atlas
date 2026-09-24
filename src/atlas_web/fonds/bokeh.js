import { haloFond, melanger, rgba, TOUR, vignette } from "../dessin.js";

export default {
  id: "bokeh",
  nom: "Bokeh",
  idee: "Des halos de lumière flous qui dérivent à plusieurs profondeurs.",
  creer(canvas) {
    const ctx = canvas.getContext("2d");
    const halos = [];
    for (let i = 0; i < 38; i++) {
      halos.push({
        x: Math.random(),
        y: Math.random(),
        profondeur: 0.3 + Math.random() * 0.7,
        phase: Math.random() * TOUR,
        teinte: Math.random() > 0.5 ? [255, 180, 120] : [120, 170, 255],
      });
    }
    return {
      dessiner(t, scene) {
        const w = canvas.width;
        const h = canvas.height;
        const base = Math.max(w, h);
        ctx.globalCompositeOperation = "source-over";
        ctx.fillStyle = "#04050c";
        ctx.fillRect(0, 0, w, h);
        haloFond(ctx, w, h, scene, 0.06);
        ctx.globalCompositeOperation = "lighter";
        for (const halo of halos) {
          halo.y -= scene.dt * 0.012 * halo.profondeur;
          if (halo.y < -0.2) {
            halo.y = 1.2;
            halo.x = Math.random();
          }
          const x = (halo.x + 0.02 * Math.sin(t * 0.3 + halo.phase)) * w;
          const y = halo.y * h;
          const r = (0.02 + 0.07 * (1 - halo.profondeur)) * base; // les plus proches sont les plus flous
          const alpha = (0.05 + 0.1 * halo.profondeur) * (0.8 + 0.2 * Math.sin(t + halo.phase));
          const teinte = melanger(halo.teinte, scene.couleur, 0.4);
          const degrade = ctx.createRadialGradient(x, y, r * 0.6, x, y, r);
          degrade.addColorStop(0, rgba(teinte, alpha));
          degrade.addColorStop(1, rgba(teinte, 0));
          ctx.fillStyle = degrade;
          ctx.beginPath();
          ctx.arc(x, y, r, 0, TOUR);
          ctx.fill();
        }
        vignette(ctx, w, h);
      },
    };
  },
};

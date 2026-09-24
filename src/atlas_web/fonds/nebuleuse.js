import { melanger, rgba, vignette } from "../dessin.js";

const TEINTES = [
  [60, 40, 120],
  [20, 60, 120],
  [120, 40, 90],
  [30, 90, 110],
];

export default {
  id: "nebuleuse",
  nom: "Nébuleuse",
  idee: "Des nuages colorés qui dérivent lentement, teintés par l'état.",
  creer(canvas) {
    const ctx = canvas.getContext("2d");
    const nuages = [];
    for (let i = 0; i < 7; i++) {
      nuages.push({
        x: Math.random(),
        y: Math.random(),
        r: 0.25 + Math.random() * 0.3,
        phase: Math.random() * 6.28,
        teinte: TEINTES[i % TEINTES.length],
      });
    }
    const poussiere = [];
    for (let i = 0; i < 90; i++) poussiere.push([Math.random(), Math.random(), Math.random() * 6.28]);
    return {
      dessiner(t, scene) {
        const w = canvas.width;
        const h = canvas.height;
        ctx.globalCompositeOperation = "source-over";
        ctx.fillStyle = "#03040a";
        ctx.fillRect(0, 0, w, h);
        ctx.globalCompositeOperation = "lighter";
        for (const nuage of nuages) {
          const x = (nuage.x + 0.06 * Math.sin(t * 0.05 + nuage.phase)) * w;
          const y = (nuage.y + 0.05 * Math.cos(t * 0.04 + nuage.phase)) * h;
          const r = nuage.r * Math.max(w, h);
          const teinte = melanger(nuage.teinte, scene.couleur, 0.35);
          const degrade = ctx.createRadialGradient(x, y, 0, x, y, r);
          degrade.addColorStop(0, rgba(teinte, 0.22));
          degrade.addColorStop(1, rgba(teinte, 0));
          ctx.fillStyle = degrade;
          ctx.fillRect(0, 0, w, h);
        }
        const taille = Math.max(1, Math.min(w, h) / 900);
        for (const [px, py, phase] of poussiere) {
          ctx.fillStyle = rgba([230, 235, 255], 0.3 + 0.3 * Math.sin(t * 2 + phase));
          ctx.fillRect(px * w, py * h, taille, taille);
        }
        vignette(ctx, w, h);
      },
    };
  },
};

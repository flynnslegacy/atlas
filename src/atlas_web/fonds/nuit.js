import { haloFond, vignette } from "../dessin.js";

export default {
  id: "nuit",
  nom: "Nuit",
  idee: "Un dégradé bleu nuit et un vignettage : la référence sobre.",
  creer(canvas) {
    const ctx = canvas.getContext("2d");
    return {
      dessiner(t, scene) {
        const w = canvas.width;
        const h = canvas.height;
        const degrade = ctx.createLinearGradient(0, 0, 0, h);
        degrade.addColorStop(0, "#0a1020");
        degrade.addColorStop(1, "#020308");
        ctx.globalCompositeOperation = "source-over";
        ctx.fillStyle = degrade;
        ctx.fillRect(0, 0, w, h);
        haloFond(ctx, w, h, scene, 0.1);
        vignette(ctx, w, h);
      },
    };
  },
};

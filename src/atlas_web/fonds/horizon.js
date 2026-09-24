import { melanger, rgba, vignette } from "../dessin.js";

export default {
  id: "horizon",
  nom: "Horizon quadrillé",
  idee: "Un sol en perspective qui défile ; l'orbe flotte au-dessus de l'horizon.",
  creer(canvas) {
    const ctx = canvas.getContext("2d");
    let defilement = 0;
    let eclat = 0;
    return {
      dessiner(t, scene) {
        const w = canvas.width;
        const h = canvas.height;
        const horizon = h * 0.66;
        const c = scene.couleur;
        const ciel = ctx.createLinearGradient(0, 0, 0, horizon);
        ciel.addColorStop(0, "#02030a");
        ciel.addColorStop(1, rgba(melanger([20, 16, 40], c, 0.3), 1));
        ctx.globalCompositeOperation = "source-over";
        ctx.fillStyle = ciel;
        ctx.fillRect(0, 0, w, horizon);
        ctx.fillStyle = "#020309";
        ctx.fillRect(0, horizon, w, h - horizon);
        defilement = (defilement + scene.dt * (scene.etat === "reflexion" ? 0.9 : 0.35)) % 1;
        if (scene.syllabe) eclat = 1; // le sol pulse sur chaque syllabe
        eclat *= Math.exp(-scene.dt * 6);
        ctx.globalCompositeOperation = "lighter";
        ctx.lineWidth = Math.max(1, w / 700);
        for (let i = 0; i < 18; i++) {
          const z = (i + defilement) / 18;
          const y = horizon + (h - horizon) * z ** 2.2;
          ctx.strokeStyle = rgba(c, 0.08 + 0.35 * z + eclat * 0.2 * z);
          ctx.beginPath();
          ctx.moveTo(0, y);
          ctx.lineTo(w, y);
          ctx.stroke();
        }
        ctx.strokeStyle = rgba(c, 0.18 + eclat * 0.15);
        for (let i = -16; i <= 16; i++) {
          ctx.beginPath();
          ctx.moveTo(w / 2 + i * w * 0.012, horizon);
          ctx.lineTo(w / 2 + i * w * 0.16, h);
          ctx.stroke();
        }
        const lueur = ctx.createLinearGradient(0, horizon - h * 0.08, 0, horizon + h * 0.02);
        lueur.addColorStop(0, "rgba(0,0,0,0)");
        lueur.addColorStop(1, rgba(c, 0.25 + scene.volume * 0.15));
        ctx.fillStyle = lueur;
        ctx.fillRect(0, horizon - h * 0.08, w, h * 0.1);
        vignette(ctx, w, h);
      },
    };
  },
};

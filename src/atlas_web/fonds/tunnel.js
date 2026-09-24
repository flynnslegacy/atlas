import { rgba, TOUR, vignette } from "../dessin.js";

export default {
  id: "tunnel",
  nom: "Tunnel",
  idee: "Des anneaux en perspective qui viennent vers toi, plus vite quand il réfléchit.",
  creer(canvas) {
    const ctx = canvas.getContext("2d");
    let avance = 0;
    return {
      dessiner(t, scene) {
        const w = canvas.width;
        const h = canvas.height;
        const cy = h * 0.42; // le point de fuite, derrière l'orbe
        const c = scene.couleur;
        ctx.globalCompositeOperation = "source-over";
        ctx.fillStyle = "#02030a";
        ctx.fillRect(0, 0, w, h);
        avance = (avance + scene.dt * (scene.etat === "reflexion" ? 0.6 : 0.15)) % 1;
        ctx.globalCompositeOperation = "lighter";
        ctx.lineWidth = Math.max(1, w / 800);
        for (let i = 0; i < 14; i++) {
          const z = (i + avance) / 14;
          const e = z ** 2.4;
          ctx.strokeStyle = rgba(c, 0.04 + 0.22 * z * (1 - z * 0.3));
          ctx.beginPath();
          ctx.ellipse(w / 2, cy, w * 0.08 + e * w * 0.75, h * 0.08 + e * h * 0.75, 0, 0, TOUR);
          ctx.stroke();
        }
        ctx.strokeStyle = rgba(c, 0.06);
        for (let k = 0; k < 12; k++) {
          const a = (k / 12) * TOUR + t * 0.02;
          ctx.beginPath();
          ctx.moveTo(w / 2 + Math.cos(a) * w * 0.08, cy + Math.sin(a) * h * 0.08);
          ctx.lineTo(w / 2 + Math.cos(a) * w * 0.9, cy + Math.sin(a) * h * 0.9);
          ctx.stroke();
        }
        vignette(ctx, w, h);
      },
    };
  },
};

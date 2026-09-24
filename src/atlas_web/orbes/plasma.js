import { geo, lueur, preparerOrbe, rgba, trace, TOUR } from "../dessin.js";

export default {
  id: "plasma",
  nom: "Boule plasma",
  idee: "Des filaments électriques qui cherchent le verre au son de la voix.",
  creer(canvas) {
    const ctx = canvas.getContext("2d");
    const filaments = [];
    for (let i = 0; i < 9; i++) {
      filaments.push({ angle: (i / 9) * TOUR, derive: (Math.random() - 0.5) * 0.6, graine: Math.random() * 100 });
    }
    return {
      dessiner(t, scene) {
        const g = geo(canvas);
        const R = g.m * 0.37;
        const v = scene.volume;
        const c = scene.couleur;
        const f = Math.min(3, Math.max(0, scene.dt * 60));
        preparerOrbe(ctx, g, scene);
        const verre = ctx.createRadialGradient(g.cx, g.cy, 0, g.cx, g.cy, R);
        verre.addColorStop(0, rgba(c, 0.1));
        verre.addColorStop(1, "rgba(10,14,25,0.9)");
        ctx.fillStyle = verre;
        ctx.beginPath();
        ctx.arc(g.cx, g.cy, R, 0, TOUR);
        ctx.fill();
        ctx.globalCompositeOperation = "lighter";
        const actifs = scene.etat === "repos" ? 4 : scene.etat === "reflexion" ? 9 : 5 + Math.round(v * 4);
        const vers = t * 0.5;
        for (let i = 0; i < actifs; i++) {
          const filament = filaments[i];
          const deriveEtat = filament.derive * 0.01 * (scene.etat === "reflexion" ? 4 : 1);
          filament.angle += (deriveEtat + (Math.random() - 0.5) * 0.02) * f;
          let angle = filament.angle;
          // Quand Atlas parle, les filaments convergent, comme vers une main posée sur le verre.
          if (scene.etat === "parole") angle += Math.atan2(Math.sin(vers - angle), Math.cos(vers - angle)) * 0.35 * v;
          const points = [];
          for (let j = 0; j <= 16; j++) {
            const s = j / 16;
            const ondulation =
              Math.sin(filament.graine + j * 1.7 + t * 9) + 0.5 * Math.sin(filament.graine * 2 + j * 3.1 - t * 13);
            const ecart = ondulation * s * R * 0.12 * (0.6 + v);
            const r = s * R * 0.97;
            points.push([
              g.cx + Math.cos(angle) * r - Math.sin(angle) * ecart,
              g.cy + Math.sin(angle) * r + Math.cos(angle) * ecart,
            ]);
          }
          ctx.strokeStyle = rgba(c, 0.18);
          ctx.lineWidth = 5 * g.k * (0.7 + v * 0.6);
          trace(ctx, points);
          ctx.stroke();
          ctx.strokeStyle = rgba(c, 0.85, 0.6);
          ctx.lineWidth = 1.2 * g.k;
          trace(ctx, points);
          ctx.stroke();
          const bout = points[points.length - 1];
          lueur(ctx, bout[0], bout[1], 10 * g.k, c, 0.8, 0.5);
        }
        lueur(ctx, g.cx, g.cy, R * 0.22 * (1 + v * 0.5), c, 1, 0.8);
        ctx.globalCompositeOperation = "source-over";
        ctx.strokeStyle = "rgba(200,220,255,0.18)";
        ctx.lineWidth = 2 * g.k;
        ctx.beginPath();
        ctx.arc(g.cx, g.cy, R, 0, TOUR);
        ctx.stroke();
        const rx = g.cx - R * 0.35;
        const ry = g.cy - R * 0.4;
        const reflet = ctx.createRadialGradient(rx, ry, 0, rx, ry, R * 0.45);
        reflet.addColorStop(0, "rgba(255,255,255,0.10)");
        reflet.addColorStop(1, "rgba(255,255,255,0)");
        ctx.fillStyle = reflet;
        ctx.beginPath();
        ctx.arc(g.cx, g.cy, R, 0, TOUR);
        ctx.fill();
      },
    };
  },
};

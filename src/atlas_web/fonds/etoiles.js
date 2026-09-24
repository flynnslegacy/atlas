import { haloFond, melanger, rgba, TOUR, vignette } from "../dessin.js";

const COUCHES = [
  { nombre: 140, vitesse: 0.01 },
  { nombre: 70, vitesse: 0.022 },
  { nombre: 30, vitesse: 0.045 },
];

export default {
  id: "etoiles",
  nom: "Champ d'étoiles",
  idee: "Trois couches d'étoiles qui s'écartent du centre : on avance dans l'espace.",
  creer(canvas) {
    const ctx = canvas.getContext("2d");
    const etoiles = [];
    COUCHES.forEach((couche, c) => {
      for (let i = 0; i < couche.nombre; i++) {
        etoiles.push({ couche: c, angle: Math.random() * TOUR, distance: Math.random(), phase: Math.random() * TOUR });
      }
    });
    return {
      dessiner(t, scene) {
        const w = canvas.width;
        const h = canvas.height;
        const rayon = Math.hypot(w, h) / 2;
        const echelle = Math.max(0.5, Math.min(w, h) / 700);
        ctx.globalCompositeOperation = "source-over";
        ctx.fillStyle = "#03050b";
        ctx.fillRect(0, 0, w, h);
        haloFond(ctx, w, h, scene, 0.07);
        const acceleration = scene.etat === "reflexion" ? 3 : 1;
        const teinte = melanger([220, 230, 255], scene.couleur, 0.25);
        ctx.globalCompositeOperation = "lighter";
        for (const e of etoiles) {
          e.distance += scene.dt * acceleration * COUCHES[e.couche].vitesse * (0.3 + e.distance);
          if (e.distance > 1) {
            e.distance = 0.02 + Math.random() * 0.1;
            e.angle = Math.random() * TOUR;
          }
          const x = w / 2 + Math.cos(e.angle) * e.distance * rayon;
          const y = h / 2 + Math.sin(e.angle) * e.distance * rayon;
          ctx.fillStyle = rgba(teinte, (0.25 + 0.6 * e.distance) * (0.7 + 0.3 * Math.sin(t * 3 + e.phase)));
          ctx.beginPath();
          ctx.arc(x, y, (0.5 + e.couche * 0.6 + e.distance * 1.2) * echelle, 0, TOUR);
          ctx.fill();
        }
        vignette(ctx, w, h);
      },
    };
  },
};

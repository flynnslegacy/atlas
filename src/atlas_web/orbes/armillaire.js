import { geo, lueur, melanger, preparerOrbe, rgba, tourner, TOUR } from "../dessin.js";

const LAITON = [201, 168, 106];
const EPS = (23.4 * Math.PI) / 180;
const ANNEAUX = [
  { c: [0, 0, 0], u: [1, 0, 0], v: [0, 0, 1], r: 1, vitesse: 0, epaisseur: 2.2 }, // équateur
  { c: [0, 0.4, 0], u: [1, 0, 0], v: [0, 0, 1], r: Math.sqrt(0.84), vitesse: 0, epaisseur: 1 }, // tropiques
  { c: [0, -0.4, 0], u: [1, 0, 0], v: [0, 0, 1], r: Math.sqrt(0.84), vitesse: 0, epaisseur: 1 },
  { c: [0, 0, 0], u: [0, 1, 0], v: [1, 0, 0], r: 1, vitesse: 0.9, epaisseur: 1.6 }, // méridiens
  { c: [0, 0, 0], u: [0, 1, 0], v: [0, 0, 1], r: 1, vitesse: -0.6, epaisseur: 1.6 },
  {
    c: [0, 0, 0],
    u: [1, 0, 0],
    v: [0, Math.sin(EPS), Math.cos(EPS)],
    r: 1.02,
    vitesse: 0.35,
    epaisseur: 3.2,
    ecliptique: true,
  },
];

function point(anneau, r, th) {
  return [0, 1, 2].map((d) => anneau.c[d] + r * (Math.cos(th) * anneau.u[d] + Math.sin(th) * anneau.v[d]));
}

export default {
  id: "armillaire",
  nom: "Sphère armillaire",
  idee: "L'astrolabe de laiton : Atlas porte la voûte céleste.",
  creer(canvas) {
    const ctx = canvas.getContext("2d");
    const etoiles = [];
    for (let i = 0; i < 120; i++) {
      const u = Math.random() * 2 - 1;
      const th = Math.random() * TOUR;
      const rayon = 0.25 + 0.6 * Math.random();
      const s = Math.sqrt(1 - u * u);
      etoiles.push([Math.cos(th) * s * rayon, u * rayon, Math.sin(th) * s * rayon, Math.random() * TOUR]);
    }
    return {
      dessiner(t, scene) {
        const g = geo(canvas);
        const c = scene.couleur;
        const v = scene.volume;
        const R = g.m * 0.33;
        const gyroscope = scene.etat === "reflexion" ? 1 : 0.08;
        const echelle = 1 + (scene.etat === "ecoute" ? v * 0.05 : 0);
        preparerOrbe(ctx, g, scene);
        ctx.globalCompositeOperation = "lighter";
        lueur(ctx, g.cx, g.cy, R * (0.2 + v * 0.14), c, 1, 0.75);
        const rotation = t * 0.12;
        for (const e of etoiles) {
          const p = tourner(e, rotation, 0.35);
          const alpha = (0.25 + 0.25 * (p[2] + 1)) * (0.6 + 0.4 * Math.sin(t * 2 + e[3]));
          ctx.fillStyle = rgba(melanger(LAITON, c, 0.2), alpha, 0.5);
          ctx.fillRect(g.cx + p[0] * R * echelle, g.cy + p[1] * R * echelle, 1.2 * g.k, 1.2 * g.k);
        }
        for (const anneau of ANNEAUX) {
          const ay = rotation + t * anneau.vitesse * gyroscope;
          let precedent = null;
          for (let i = 0; i <= 120; i++) {
            const th = (i / 120) * TOUR;
            let r = anneau.r;
            if (anneau.ecliptique && scene.etat === "parole") r *= 1 + v * 0.07 * Math.sin(14 * th + t * 11);
            const p = tourner(point(anneau, r, th), ay, 0.35);
            const courant = [g.cx + p[0] * R * echelle, g.cy + p[1] * R * echelle, p[2]];
            if (precedent) {
              const profondeur = ((courant[2] + precedent[2]) / 2 + 1) / 2;
              const teinte = melanger(LAITON, c, anneau.ecliptique ? 0.55 : 0.15);
              ctx.strokeStyle = rgba(teinte, 0.15 + 0.75 * profondeur, anneau.ecliptique ? 0.2 * v : 0);
              ctx.lineWidth = anneau.epaisseur * g.k * (0.6 + 0.6 * profondeur);
              ctx.beginPath();
              ctx.moveTo(precedent[0], precedent[1]);
              ctx.lineTo(courant[0], courant[1]);
              ctx.stroke();
            }
            precedent = courant;
          }
          if (anneau.ecliptique) {
            for (let j = 0; j < 3; j++) {
              const th = t * (scene.etat === "parole" ? 1.6 : 0.4) + j * 2.1;
              const p = tourner(point(anneau, anneau.r, th), ay, 0.35);
              lueur(ctx, g.cx + p[0] * R, g.cy + p[1] * R, 7 * g.k, c, 1, 0.6);
            }
          }
        }
        ctx.globalCompositeOperation = "source-over";
        ctx.strokeStyle = rgba(LAITON, 0.55);
        ctx.lineWidth = 3 * g.k;
        ctx.beginPath();
        ctx.ellipse(g.cx, g.cy + R * 0.02, R * 1.16, R * 0.34, 0, 0, TOUR);
        ctx.stroke();
      },
    };
  },
};

import { geo, lueur, preparerOrbe, rgba, TOUR } from "../dessin.js";

function placerEtoiles() {
  const etoiles = [];
  for (let essai = 0; essai < 3000 && etoiles.length < 36; essai++) {
    const r = Math.sqrt(Math.random()) * 0.92;
    const th = Math.random() * TOUR;
    const p = [r * Math.cos(th), r * Math.sin(th), Math.random() * TOUR];
    if (etoiles.every((q) => Math.hypot(q[0] - p[0], q[1] - p[1]) > 0.17)) etoiles.push(p);
  }
  return etoiles;
}

function relier(etoiles) {
  const aretes = [];
  etoiles.forEach((p, i) => {
    const voisins = etoiles
      .map((q, j) => [Math.hypot(q[0] - p[0], q[1] - p[1]), j])
      .sort((x, y) => x[0] - y[0]);
    for (let k = 1; k <= 2 && k < voisins.length; k++) {
      const j = voisins[k][1];
      if (!aretes.some(([a, b]) => (a === i && b === j) || (a === j && b === i))) aretes.push([i, j]);
    }
  });
  return aretes;
}

export default {
  id: "constellations",
  nom: "Constellations",
  idee: "Des étoiles qui se relient ; des éclairs y courent quand il réfléchit.",
  creer(canvas) {
    const ctx = canvas.getContext("2d");
    const etoiles = placerEtoiles();
    const aretes = relier(etoiles);
    const impulsions = [];
    let prochaine = 0;
    function lancer() {
      if (aretes.length) {
        impulsions.push({ arete: Math.floor(Math.random() * aretes.length), p: 0, sens: Math.random() > 0.5 });
      }
    }
    return {
      dessiner(t, scene) {
        const g = geo(canvas);
        const R = g.m * 0.38;
        const rotation = t * 0.05;
        const c = scene.couleur;
        const v = scene.volume;
        const P = etoiles.map((e) => [
          g.cx + (e[0] * Math.cos(rotation) - e[1] * Math.sin(rotation)) * R,
          g.cy + (e[0] * Math.sin(rotation) + e[1] * Math.cos(rotation)) * R,
          e[2],
        ]);
        if ((scene.etat === "ecoute" || scene.etat === "parole") && scene.syllabe) {
          lancer();
          lancer();
          lancer();
        } else if (scene.etat === "reflexion" && t > prochaine) {
          lancer();
          prochaine = t + 0.12;
        }
        preparerOrbe(ctx, g, scene);
        ctx.globalCompositeOperation = "lighter";
        const alphaLigne = scene.etat === "repos" ? 0.06 : scene.etat === "reflexion" ? 0.28 : 0.12 + 0.3 * v;
        ctx.lineWidth = g.k;
        ctx.strokeStyle = rgba(c, alphaLigne, 0.2);
        for (const [a, b] of aretes) {
          ctx.beginPath();
          ctx.moveTo(P[a][0], P[a][1]);
          ctx.lineTo(P[b][0], P[b][1]);
          ctx.stroke();
        }
        for (let i = impulsions.length - 1; i >= 0; i--) {
          const impulsion = impulsions[i];
          impulsion.p += scene.dt * 1.5;
          if (impulsion.p >= 1) {
            impulsions.splice(i, 1);
            continue;
          }
          const [a, b] = aretes[impulsion.arete];
          const depart = P[impulsion.sens ? a : b];
          const arrivee = P[impulsion.sens ? b : a];
          const x = depart[0] + (arrivee[0] - depart[0]) * impulsion.p;
          const y = depart[1] + (arrivee[1] - depart[1]) * impulsion.p;
          lueur(ctx, x, y, 6 * g.k, c, 1, 0.6);
        }
        for (const p of P) {
          const scintillement = 0.5 + 0.5 * Math.sin(t * 2.5 + p[2]);
          lueur(ctx, p[0], p[1], (3 + 3 * v + 2 * scintillement) * g.k, c, 0.5 + 0.4 * scintillement, 0.6);
        }
      },
    };
  },
};

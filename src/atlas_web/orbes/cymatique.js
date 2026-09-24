import { geo, preparerOrbe, rgba, TOUR } from "../dessin.js";

const GRAINS = 3000;
const MODES = [[1, 2], [2, 3], [1, 4], [3, 4], [2, 5], [3, 5], [1, 6], [4, 5], [2, 7], [3, 7], [5, 6]];

export default {
  id: "cymatique",
  nom: "Cymatique",
  idee: "Du sable qui dessine les figures de la voix sur une plaque.",
  creer(canvas) {
    const ctx = canvas.getContext("2d");
    const X = new Float32Array(GRAINS);
    const Y = new Float32Array(GRAINS);
    for (let i = 0; i < GRAINS; i++) {
      const r = Math.sqrt(Math.random());
      const th = Math.random() * TOUR;
      X[i] = r * Math.cos(th);
      Y[i] = r * Math.sin(th);
    }
    let mode = 1;
    let secousse = 1;
    let prochain = 0;
    function changerDeFigure(t, attente) {
      mode = (mode + 1 + Math.floor(Math.random() * 3)) % MODES.length;
      secousse = 1;
      prochain = t + attente;
    }
    return {
      dessiner(t, scene) {
        const parle = scene.etat === "ecoute" || scene.etat === "parole";
        if (parle && scene.syllabe && t > prochain) changerDeFigure(t, 0.45);
        else if (scene.etat === "reflexion" && t > prochain) changerDeFigure(t, 1.3);
        const f = Math.min(3, Math.max(0, scene.dt * 60)); // en images de 1/60 s
        secousse *= 0.94 ** f;
        const [n, m] = MODES[mode];
        const pi = Math.PI;
        const agitation = (scene.etat === "repos" ? 0.0015 : 0.003 + 0.035 * secousse + 0.008 * scene.volume) * f;
        for (let i = 0; i < GRAINS; i++) {
          const x = X[i];
          const y = Y[i];
          const cnx = Math.cos(n * pi * x);
          const cmy = Math.cos(m * pi * y);
          const cmx = Math.cos(m * pi * x);
          const cny = Math.cos(n * pi * y);
          // Figure de Chladni : le sable fuit les ventres et s'amasse sur les lignes immobiles.
          const valeur = cnx * cmy - cmx * cny;
          const gx = -n * pi * Math.sin(n * pi * x) * cmy + m * pi * Math.sin(m * pi * x) * cny;
          const gy = -m * pi * cnx * Math.sin(m * pi * y) + n * pi * cmx * Math.sin(n * pi * y);
          const pas = (0.0012 * f * valeur) / (n + m);
          const bruit = agitation * (0.3 + Math.abs(valeur));
          let nx = x - pas * gx + (Math.random() - 0.5) * bruit;
          let ny = y - pas * gy + (Math.random() - 0.5) * bruit;
          const d2 = nx * nx + ny * ny;
          if (d2 > 0.98) {
            const s = 0.97 / Math.sqrt(d2);
            nx *= s;
            ny *= s;
          }
          X[i] = nx;
          Y[i] = ny;
        }
        const g = geo(canvas);
        const R = g.m * 0.36;
        preparerOrbe(ctx, g, scene);
        ctx.globalCompositeOperation = "lighter";
        ctx.fillStyle = rgba(scene.couleur, scene.etat === "repos" ? 0.35 : 0.6, 0.35);
        const taille = 1.4 * g.k;
        for (let i = 0; i < GRAINS; i++) ctx.fillRect(g.cx + X[i] * R, g.cy + Y[i] * R, taille, taille);
        ctx.globalCompositeOperation = "source-over";
        ctx.strokeStyle = rgba(scene.couleur, 0.25);
        ctx.lineWidth = 1.2 * g.k;
        ctx.beginPath();
        ctx.arc(g.cx, g.cy, R * 1.01, 0, TOUR);
        ctx.stroke();
      },
    };
  },
};

// Outils de dessin partagés par les orbes et les fonds.

export const TOUR = Math.PI * 2;

export function melanger(base, couleur, part) {
  return [0, 1, 2].map((i) => base[i] * (1 - part) + couleur[i] * part);
}

export function rgba(couleur, alpha, eclaircir = 0) {
  const [r, g, b] = couleur.map((x) => Math.round(x + (255 - x) * eclaircir));
  return `rgba(${r},${g},${b},${Math.max(0, Math.min(1, alpha))})`;
}

export function geo(canvas) {
  const w = canvas.width;
  const h = canvas.height;
  const m = Math.min(w, h);
  return { w, h, m, cx: w / 2, cy: h / 2, k: m / 400 };
}

export function lueur(ctx, x, y, r, couleur, alpha, eclaircir = 0) {
  if (!(r > 0)) return;
  const degrade = ctx.createRadialGradient(x, y, 0, x, y, r);
  degrade.addColorStop(0, rgba(couleur, alpha, eclaircir));
  degrade.addColorStop(1, rgba(couleur, 0));
  ctx.fillStyle = degrade;
  ctx.beginPath();
  ctx.arc(x, y, r, 0, TOUR);
  ctx.fill();
}

// Le calque de l'orbe reste transparent : on l'efface, puis un halo doux l'entoure.
export function preparerOrbe(ctx, g, scene) {
  ctx.globalCompositeOperation = "source-over";
  ctx.clearRect(0, 0, g.w, g.h);
  lueur(ctx, g.cx, g.cy, g.m * 0.5, scene.couleur, 0.08 + scene.volume * 0.1);
}

export function tourner(p, ay, ax) {
  const x = p[0] * Math.cos(ay) + p[2] * Math.sin(ay);
  const z0 = -p[0] * Math.sin(ay) + p[2] * Math.cos(ay);
  return [x, p[1] * Math.cos(ax) - z0 * Math.sin(ax), p[1] * Math.sin(ax) + z0 * Math.cos(ax)];
}

export function trace(ctx, points) {
  ctx.beginPath();
  points.forEach((p, i) => (i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])));
}

export function vignette(ctx, w, h) {
  const v = ctx.createRadialGradient(w / 2, h / 2, Math.min(w, h) * 0.35, w / 2, h / 2, Math.max(w, h) * 0.75);
  v.addColorStop(0, "rgba(0,0,0,0)");
  v.addColorStop(1, "rgba(0,0,0,0.65)");
  ctx.globalCompositeOperation = "source-over";
  ctx.fillStyle = v;
  ctx.fillRect(0, 0, w, h);
}

// Le halo d'un fond, centré là où flotte l'orbe (42 % de la hauteur).
export function haloFond(ctx, w, h, scene, alpha) {
  const g = ctx.createRadialGradient(w / 2, h * 0.42, 0, w / 2, h * 0.42, h * 0.6);
  g.addColorStop(0, rgba(scene.couleur, alpha + scene.volume * 0.08));
  g.addColorStop(1, "rgba(0,0,0,0)");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, w, h);
}

export function dimensionner(canvas, dprMax = 2) {
  const dpr = Math.min(dprMax, globalThis.devicePixelRatio || 1);
  const w = Math.max(1, Math.round(canvas.clientWidth * dpr));
  const h = Math.max(1, Math.round(canvas.clientHeight * dpr));
  if (canvas.width !== w || canvas.height !== h) {
    canvas.width = w;
    canvas.height = h;
  }
}

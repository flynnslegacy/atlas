import assert from "node:assert/strict";
import { test } from "node:test";

import { Decimateur, TAILLE_BLOC, TamponLecture } from "../../src/atlas_web/voix_worklet.js";

// Une seconde de sinusoïde, découpée comme le navigateur la livre au processeur (128).
function sinusoide(frequence, hz, amplitude, secondes = 1) {
  const n = Math.round(frequence * secondes);
  const tout = Float32Array.from({ length: n }, (_, i) => amplitude * Math.sin((2 * Math.PI * hz * i) / frequence));
  const morceaux = [];
  for (let i = 0; i < n; i += 128) morceaux.push(tout.subarray(i, i + 128));
  return morceaux;
}

function decimer(frequence, morceaux) {
  const decimateur = new Decimateur(frequence);
  const blocs = morceaux.flatMap((morceau) => decimateur.ajouter(morceau));
  const tout = new Int16Array(blocs.length * TAILLE_BLOC);
  blocs.forEach((bloc, i) => tout.set(bloc, i * TAILLE_BLOC));
  return { blocs, tout };
}

const efficace = (x) => Math.sqrt(x.reduce((s, v) => s + v * v, 0) / x.length);
const passagesParZero = (x) => x.slice(1).filter((v, i) => (x[i] < 0) !== (v < 0)).length;

// 48 et 44,1 kHz d'ordinaire ; 24 et 16 kHz derrière certains casques Bluetooth.
for (const frequence of [48000, 44100, 24000, 16000]) {
  test(`à ${frequence} Hz, une voix à 1 kHz sort à 16 kHz, en blocs de 20 ms, intacte`, () => {
    const { blocs, tout } = decimer(frequence, sinusoide(frequence, 1000, 0.5));
    assert.ok(blocs.length >= 49 && blocs.length <= 50, `${blocs.length} blocs`);
    assert.ok(blocs.every((bloc) => bloc instanceof Int16Array && bloc.length === TAILLE_BLOC));
    const passages = passagesParZero(tout);
    assert.ok(Math.abs(passages - 2 * 1000 * (tout.length / 16000)) <= 4, `${passages} passages par zéro`);
    const attendu = (0.5 / Math.SQRT2) * 32767;
    assert.ok(Math.abs(efficace(tout.subarray(320)) / attendu - 1) < 0.02);
  });
}

test("les aigus au-dessus de 8 kHz ne se replient pas dans la voix", () => {
  const { tout } = decimer(48000, sinusoide(48000, 12000, 0.5));
  const attenuation = 20 * Math.log10(efficace(tout.subarray(320)) / ((0.5 / Math.SQRT2) * 32767));
  assert.ok(attenuation < -40, `${attenuation.toFixed(1)} dB`);
});

test("la capture oublie ce qu'elle a décimé", () => {
  const decimateur = new Decimateur(48000);
  for (const morceau of sinusoide(48000, 1000, 0.5, 2)) decimateur.ajouter(morceau);
  assert.ok(decimateur._entree.length < 200, `${decimateur._entree.length} gardés`);
});

test("un son trop fort est écrêté, jamais retourné", () => {
  const { tout } = decimer(48000, [new Float32Array(48000).fill(1.5)]);
  assert.equal(Math.min(...tout.subarray(320)), 32767);
});

function trame(valeur, n = TAILLE_BLOC) {
  return new Int16Array(n).fill(valeur).buffer;
}

for (const frequence of [48000, 44100, 24000, 16000]) {
  test(`à ${frequence} Hz, une trame de 20 ms se joue en 20 ms`, () => {
    const tampon = new TamponLecture(frequence);
    tampon.ajouter(trame(16384));
    let joues = 0;
    const sortie = new Float32Array(128);
    for (let i = 0; i < 10; i++) {
      joues += tampon.remplir(sortie);
      if (i === 0) assert.ok(sortie.every((v) => Math.abs(v - 0.5) < 1e-6));
    }
    // Le dernier échantillon attend le suivant pour s'interpoler.
    const pas = frequence / 16000;
    assert.ok(joues >= (TAILLE_BLOC - 1) * pas && joues <= TAILLE_BLOC * pas, `${joues} joués`);
  });
}

test("sans rien à jouer, la sortie est du silence", () => {
  const tampon = new TamponLecture(48000);
  const sortie = new Float32Array(128).fill(0.9);
  assert.equal(tampon.remplir(sortie), 0);
  assert.ok(sortie.every((v) => v === 0));
});

test("vider coupe le son d'un coup", () => {
  const tampon = new TamponLecture(48000);
  for (let i = 0; i < 50; i++) tampon.ajouter(trame(8000));
  const sortie = new Float32Array(128);
  assert.equal(tampon.remplir(sortie), 128);
  tampon.vider();
  assert.equal(tampon.remplir(sortie), 0);
  assert.ok(sortie.every((v) => v === 0));
  tampon.ajouter(trame(8000));
  assert.equal(tampon.remplir(sortie), 128);
});

test("la lecture oublie ce qu'elle a joué", () => {
  const tampon = new TamponLecture(48000);
  for (let i = 0; i < 100; i++) tampon.ajouter(trame(1000)); // 2 s de voix
  const sortie = new Float32Array(128);
  for (let i = 0; i < 300; i++) tampon.remplir(sortie); // 0,8 s jouées
  assert.ok(tampon._echantillons.length < 32000 - 12000, `${tampon._echantillons.length} gardés`);
});

test("le module se charge hors du navigateur sans déclarer de processeur", async () => {
  assert.equal(typeof globalThis.registerProcessor, "undefined");
  await import("../../src/atlas_web/voix_worklet.js");
});

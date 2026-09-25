// Les deux processeurs AudioWorklet de la voix (validés par le spike S4) : la capture
// ramène le micro à 16 kHz mono, en blocs de 20 ms ; la lecture joue les trames 16 kHz du
// Core à la fréquence du contexte, et se vide d'un coup. Leurs calculs sont des classes
// pures, testées avec node --test ; les processeurs ne se déclarent que dans le navigateur.

export const FREQUENCE_CORE = 16000;
export const TAILLE_BLOC = 320; // 20 ms à 16 kHz

// Filtre passe-bas (sinus cardinal fenêtré) : coupe au-dessus de 7,2 kHz avant de décimer,
// pour que les aigus du micro ne se replient pas dans la bande de la voix.
export function noyauPasseBas(taps, coupure) {
  const h = new Float32Array(taps);
  const m = (taps - 1) / 2;
  let somme = 0;
  for (let i = 0; i < taps; i++) {
    const x = i - m;
    const sinc = x === 0 ? 2 * coupure : Math.sin(2 * Math.PI * coupure * x) / (Math.PI * x);
    const fenetre = 0.54 - 0.46 * Math.cos((2 * Math.PI * i) / (taps - 1));
    h[i] = sinc * fenetre;
    somme += h[i];
  }
  for (let i = 0; i < taps; i++) h[i] /= somme;
  return h;
}

// Le micro, de la fréquence du contexte (44,1 ou 48 kHz) à des blocs de 320 échantillons
// 16 bits à 16 kHz.
export class Decimateur {
  constructor(frequence) {
    this._pas = frequence / FREQUENCE_CORE;
    this._h = noyauPasseBas(63, 7200 / frequence);
    this._demi = (this._h.length - 1) / 2;
    this._entree = new Float32Array(0);
    this._origine = 0; // indice absolu de _entree[0]
    this._prochain = this._demi; // position absolue (fractionnaire) du prochain échantillon
    this._bloc = new Int16Array(TAILLE_BLOC);
    this._n = 0;
  }

  _filtrer(i) {
    let s = 0;
    const base = i - this._demi - this._origine;
    for (let k = 0; k < this._h.length; k++) s += this._h[k] * this._entree[base + k];
    return s;
  }

  // Ajoute des échantillons du micro ; rend les blocs complétés (Int16Array de 320).
  ajouter(echantillons) {
    const suite = new Float32Array(this._entree.length + echantillons.length);
    suite.set(this._entree);
    suite.set(echantillons, this._entree.length);
    this._entree = suite;
    const blocs = [];
    const fin = this._origine + this._entree.length;
    while (Math.floor(this._prochain) + 1 + this._demi < fin) {
      const i = Math.floor(this._prochain);
      const f = this._prochain - i;
      const v = (1 - f) * this._filtrer(i) + f * this._filtrer(i + 1);
      this._bloc[this._n++] = Math.max(-32768, Math.min(32767, Math.round(v * 32767)));
      if (this._n === TAILLE_BLOC) {
        blocs.push(this._bloc);
        this._bloc = new Int16Array(TAILLE_BLOC);
        this._n = 0;
      }
      this._prochain += this._pas;
    }
    const consommes = Math.floor(this._prochain) - this._demi - this._origine;
    if (consommes > 0) {
      this._entree = this._entree.slice(consommes);
      this._origine += consommes;
    }
    return blocs;
  }
}

// Le son du Core : des trames 16 bits à 16 kHz, jouées à la fréquence du contexte.
export class TamponLecture {
  constructor(frequence) {
    this._pas = FREQUENCE_CORE / frequence; // échantillons 16 kHz lus par échantillon joué
    this._echantillons = new Float32Array(0);
    this._position = 0;
  }

  ajouter(pcm) {
    const i16 = new Int16Array(pcm);
    const suite = new Float32Array(this._echantillons.length + i16.length);
    suite.set(this._echantillons);
    for (let k = 0; k < i16.length; k++) suite[this._echantillons.length + k] = i16[k] / 32768;
    this._echantillons = suite;
  }

  vider() {
    this._echantillons = new Float32Array(0);
    this._position = 0;
  }

  // Remplit la sortie ; du silence quand il n'y a plus rien à jouer. Rend le nombre
  // d'échantillons joués.
  remplir(sortie) {
    let ecrits = 0;
    for (let k = 0; k < sortie.length; k++) {
      const i = Math.floor(this._position);
      if (i + 1 >= this._echantillons.length) break;
      const f = this._position - i;
      sortie[k] = (1 - f) * this._echantillons[i] + f * this._echantillons[i + 1];
      this._position += this._pas;
      ecrits++;
    }
    sortie.fill(0, ecrits);
    const joues = Math.floor(this._position);
    if (joues > 4096) {
      // Ce qui est joué s'oublie : le tampon ne garde que ce qui reste à jouer.
      this._echantillons = this._echantillons.slice(joues);
      this._position -= joues;
    }
    return ecrits;
  }
}

if (typeof registerProcessor === "function") {
  class Capture16k extends AudioWorkletProcessor {
    constructor() {
      super();
      this.decimateur = new Decimateur(sampleRate);
    }

    process(inputs) {
      const canal = inputs[0]?.[0];
      if (canal) {
        for (const bloc of this.decimateur.ajouter(canal)) this.port.postMessage(bloc.buffer, [bloc.buffer]);
      }
      return true;
    }
  }

  class Lecture16k extends AudioWorkletProcessor {
    constructor() {
      super();
      this.tampon = new TamponLecture(sampleRate);
      this.port.onmessage = (e) => {
        if (e.data === "vider") this.tampon.vider();
        else this.tampon.ajouter(e.data);
      };
    }

    process(_entrees, sorties) {
      this.tampon.remplir(sorties[0][0]);
      return true;
    }
  }

  registerProcessor("capture-16k", Capture16k);
  registerProcessor("lecture-16k", Lecture16k);
}

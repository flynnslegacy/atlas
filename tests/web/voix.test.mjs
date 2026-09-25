import assert from "node:assert/strict";
import { test } from "node:test";

import { DELAI_REPRISE_MS, VerrouEcran, Voix, ouvrirAudioNavigateur } from "../../src/atlas_web/voix.js";
import { fauxNavigateurAudio } from "./faux_audio.mjs";

class FauxWebSocket {
  static crees = [];

  constructor(url) {
    this.url = url;
    this.envoyes = [];
    this.readyState = 0;
    this.fermee = false;
    FauxWebSocket.crees.push(this);
  }

  send(donnees) {
    this.envoyes.push(typeof donnees === "string" ? JSON.parse(donnees) : donnees);
  }

  close() {
    this.fermee = true;
    this.readyState = 3;
  }

  ouvrir() {
    this.readyState = 1;
    this.onopen?.();
  }

  recevoir(message) {
    this.onmessage?.({ data: JSON.stringify(message) });
  }

  recevoirBinaire(donnees) {
    this.onmessage?.({ data: donnees });
  }

  couper(code) {
    this.readyState = 3;
    this.onclose?.({ code });
  }
}

class FauxAudio {
  constructor(rappels) {
    this.rappels = rappels;
    this.etat = "running";
    this.joues = [];
    this.vidages = 0;
    this.reprises = 0;
    this.fermee = false;
    this.microVivant = true;
  }

  jouer(pcm) {
    this.joues.push(pcm);
  }

  vider() {
    this.vidages += 1;
  }

  async reprendre() {
    this.reprises += 1;
    this.microVivant = true;
  }

  fermer() {
    this.fermee = true;
  }
}

class FauxVerrou {
  constructor() {
    this.appels = [];
  }

  demander() {
    this.appels.push("demander");
  }

  relacher() {
    this.appels.push("relacher");
  }

  surVisible() {
    this.appels.push("visible");
  }
}

function monter({ heyAtlas = true, ouvrirAudio } = {}) {
  FauxWebSocket.crees = [];
  const m = { statuts: [], planifies: [], audios: [], verrou: new FauxVerrou(), heyAtlas };
  m.voix = new Voix({
    url: "wss://atlas.example.com/ws/voix",
    lireCle: () => "cle",
    page: "p1",
    heyAtlas: () => m.heyAtlas,
    surStatut: (statut) => m.statuts.push(statut),
    ouvrirAudio:
      ouvrirAudio ??
      (async (rappels) => {
        m.audios.push(new FauxAudio(rappels));
        return m.audios.at(-1);
      }),
    verrou: m.verrou,
    FabriqueWebSocket: FauxWebSocket,
    planifier: (rappel, delai) => m.planifies.push({ rappel, delai }),
  });
  m.ws = () => FauxWebSocket.crees.at(-1);
  return m;
}

async function enLigne(m) {
  await m.voix.allumer();
  m.ws().ouvrir();
  m.ws().recevoir({ type: "pret" });
}

test("allumer ouvre le micro, puis /ws/voix avec la page et « Hey Atlas »", async () => {
  const m = monter({ heyAtlas: false });
  await m.voix.allumer();
  assert.equal(m.audios.length, 1);
  assert.equal(m.ws().url, "wss://atlas.example.com/ws/voix");
  m.ws().ouvrir();
  assert.deepEqual(m.ws().envoyes, [{ type: "authentification", cle: "cle", page: "p1", hey_atlas: false }]);
  m.ws().recevoir({ type: "pret" });
  assert.deepEqual(m.statuts, ["ouverture", "connexion", "active"]);
  assert.equal(m.voix.allumee, true);
});

test("un deuxième toucher pendant l'ouverture n'ouvre pas un deuxième micro", async () => {
  const m = monter();
  await Promise.all([m.voix.allumer(), m.voix.allumer()]);
  assert.equal(m.audios.length, 1);
  assert.equal(FauxWebSocket.crees.length, 1);
});

test("micro refusé : rien ne se connecte, et la page le dit", async () => {
  const refus = Object.assign(new Error("Permission refusée"), { name: "NotAllowedError" });
  const m = monter({ ouvrirAudio: async () => Promise.reject(refus) });
  await m.voix.allumer();
  assert.deepEqual(m.statuts, ["ouverture", "micro_refuse"]);
  assert.equal(FauxWebSocket.crees.length, 0);
  assert.equal(m.voix.allumee, false);
  assert.match(m.voix.derniereErreur, /NotAllowedError/);
});

test("éteint pendant l'ouverture, le micro à peine ouvert se referme", async () => {
  let ouvrir;
  const m = monter({ ouvrirAudio: () => new Promise((resoudre) => (ouvrir = resoudre)) });
  const allumage = m.voix.allumer();
  m.voix.eteindre();
  const audio = new FauxAudio({});
  ouvrir(audio);
  await allumage;
  assert.equal(audio.fermee, true);
  assert.equal(FauxWebSocket.crees.length, 0);
});

test("le micro ne part au Core qu'une fois la voix prête", async () => {
  const m = monter();
  await m.voix.allumer();
  const bloc = new ArrayBuffer(640);
  m.audios[0].rappels.surBloc(bloc);
  m.ws().ouvrir();
  m.audios[0].rappels.surBloc(bloc);
  m.ws().recevoir({ type: "pret" });
  m.audios[0].rappels.surBloc(bloc);
  assert.deepEqual(
    m.ws().envoyes.filter((envoi) => envoi instanceof ArrayBuffer),
    [bloc],
  );
});

test("le son du Core se joue, et « vider » le coupe net", async () => {
  const m = monter();
  await enLigne(m);
  const trame = new ArrayBuffer(640);
  m.ws().recevoirBinaire(trame);
  m.ws().recevoir({ type: "vider" });
  assert.deepEqual(m.audios[0].joues, [trame]);
  assert.equal(m.audios[0].vidages, 1);
});

test("toucher l'orbe et l'interrupteur « Hey Atlas » partent au Core", async () => {
  const m = monter();
  assert.equal(m.voix.toucherOrbe(), false); // éteinte : rien ne part
  await enLigne(m);
  assert.equal(m.voix.toucherOrbe(), true);
  m.voix.changerHeyAtlas(false);
  assert.deepEqual(m.ws().envoyes.slice(1), [{ type: "parler" }, { type: "hey_atlas", actif: false }]);
});

test("l'écran reste allumé tant que « Hey Atlas » écoute", async () => {
  const m = monter({ heyAtlas: true });
  m.voix.changerHeyAtlas(true); // micro éteint : l'écran peut s'éteindre
  assert.deepEqual(m.verrou.appels, ["relacher"]);
  m.verrou.appels = [];
  await enLigne(m);
  m.heyAtlas = false;
  m.voix.changerHeyAtlas(false);
  m.heyAtlas = true;
  m.voix.changerHeyAtlas(true);
  m.voix.eteindre();
  assert.deepEqual(m.verrou.appels, ["demander", "relacher", "demander", "relacher"]);
  const n = monter({ heyAtlas: false });
  await enLigne(n);
  assert.deepEqual(n.verrou.appels, []);
});

test("après une interruption d'iOS, la reprise du son est signalée au Core", async () => {
  const m = monter();
  await enLigne(m);
  const { surEtat } = m.audios[0].rappels;
  surEtat("running"); // pas d'interruption : rien à signaler
  surEtat("interrupted");
  assert.equal(m.voix.statut, "interrompue");
  surEtat("running");
  assert.equal(m.voix.statut, "active");
  assert.deepEqual(m.ws().envoyes.slice(1), [{ type: "reprise" }]);
});

test("rebranchée pendant une interruption, la voix reste en pause jusqu'à la reprise", async () => {
  const m = monter();
  await enLigne(m);
  m.audios[0].rappels.surEtat("interrupted");
  m.ws().couper(1006);
  m.planifies.at(-1).rappel();
  m.ws().ouvrir();
  m.ws().recevoir({ type: "pret" });
  assert.equal(m.voix.statut, "interrompue");
  m.audios[0].rappels.surEtat("running");
  assert.equal(m.voix.statut, "active");
  assert.deepEqual(m.ws().envoyes.at(-1), { type: "reprise" });
});

test("si le son ne repart pas au retour sur la page, un toucher le rouvre", async () => {
  const m = monter();
  await enLigne(m);
  m.audios[0].etat = "interrupted";
  m.voix.surVisibilite(true);
  assert.deepEqual(m.verrou.appels.at(-1), "visible");
  const { rappel, delai } = m.planifies.at(-1);
  assert.equal(delai, DELAI_REPRISE_MS);
  rappel();
  assert.equal(m.voix.statut, "a_reactiver");
  await m.voix.reactiver();
  assert.equal(m.audios[0].reprises, 1);
});

test("un micro coupé (appel, casque débranché) se rouvre d'un toucher", async () => {
  const m = monter();
  await enLigne(m);
  const { surEtat } = m.audios[0].rappels;
  m.audios[0].microVivant = false;
  surEtat("micro_coupe");
  assert.equal(m.voix.statut, "a_reactiver");
  await m.voix.reactiver();
  assert.equal(m.audios[0].reprises, 1);
  surEtat("running");
  assert.equal(m.voix.statut, "active");
  assert.deepEqual(m.ws().envoyes.at(-1), { type: "reprise" });
});

test("après un appel, un son reparti seul ne suffit pas : le micro mort demande un toucher", async () => {
  const m = monter();
  await enLigne(m);
  const audio = m.audios[0];
  const { surEtat } = audio.rappels;
  surEtat("interrupted"); // l'appel interrompt le son…
  audio.microVivant = false;
  surEtat("micro_coupe"); // … et termine la piste du micro
  surEtat("running"); // iOS relance le son tout seul
  assert.equal(m.voix.statut, "a_reactiver");
  assert.deepEqual(m.ws().envoyes.slice(1), []); // pas de reprise : le Core n'entendrait que du silence
  await m.voix.reactiver();
  surEtat("running");
  assert.equal(m.voix.statut, "active");
  assert.deepEqual(m.ws().envoyes.slice(1), [{ type: "reprise" }]);
});

test("rebranchée pendant que le micro est coupé, la page demande toujours un toucher", async () => {
  const m = monter();
  await enLigne(m);
  m.audios[0].microVivant = false;
  m.audios[0].rappels.surEtat("micro_coupe");
  m.ws().couper(1006);
  m.planifies.at(-1).rappel();
  m.ws().ouvrir();
  m.ws().recevoir({ type: "pret" });
  assert.equal(m.voix.statut, "a_reactiver");
});

test("au retour sur la page, un micro mort demande un toucher, même son contexte en marche", async () => {
  const m = monter();
  await enLigne(m);
  m.audios[0].microVivant = false; // sa fin n'a pas été signalée
  m.voix.surVisibilite(true);
  m.planifies.at(-1).rappel();
  assert.equal(m.voix.statut, "a_reactiver");
});

test("si le micro ne peut pas se rouvrir, la page le dit et s'éteint", async () => {
  const m = monter();
  await enLigne(m);
  const audio = m.audios[0];
  audio.microVivant = false;
  audio.rappels.surEtat("micro_coupe");
  audio.reprendre = async () => {
    throw Object.assign(new Error("Permission refusée"), { name: "NotAllowedError" });
  };
  await m.voix.reactiver();
  assert.equal(m.voix.statut, "micro_refuse");
  assert.match(m.voix.derniereErreur, /NotAllowedError/);
  assert.equal(m.voix.allumee, false);
  assert.equal(audio.fermee, true);
  assert.equal(m.ws().fermee, true);
});

test("au retour sur la page, un son reparti seul ne demande rien", async () => {
  const m = monter();
  await enLigne(m);
  m.voix.surVisibilite(true);
  m.planifies.at(-1).rappel();
  assert.equal(m.voix.statut, "active");
});

test("éteinte, la fermeture du son n'est pas prise pour une interruption", async () => {
  const m = monter();
  await enLigne(m);
  m.voix.eteindre();
  m.audios[0].rappels.surEtat("closed"); // le contexte fermé le signale après coup
  assert.equal(m.voix.statut, "eteinte");
});

test("micro refusé, son message reste malgré la fermeture du contexte", async () => {
  let rappels;
  const refus = Object.assign(new Error("Permission refusée"), { name: "NotAllowedError" });
  const m = monter({
    ouvrirAudio: async (r) => {
      rappels = r;
      throw refus;
    },
  });
  await m.voix.allumer();
  rappels.surEtat("closed");
  assert.equal(m.voix.statut, "micro_refuse");
});

test("éteindre ferme le micro et la connexion", async () => {
  const m = monter();
  await enLigne(m);
  m.voix.eteindre();
  assert.equal(m.audios[0].fermee, true);
  assert.equal(m.ws().fermee, true);
  assert.equal(m.voix.statut, "eteinte");
  assert.equal(m.voix.allumee, false);
});

test("une clé refusée éteint le micro ; une coupure le garde et se rebranche", async () => {
  const m = monter();
  await enLigne(m);
  m.ws().couper(1006);
  assert.equal(m.voix.statut, "hors_ligne");
  assert.equal(m.audios[0].fermee, false);
  m.planifies.at(-1).rappel();
  m.ws().couper(4401);
  assert.equal(m.voix.statut, "cle_refusee");
  assert.equal(m.audios[0].fermee, true);
  assert.equal(m.voix.allumee, false);
});

test("l'explication du Core est gardée quand il ferme la voix", async () => {
  const m = monter();
  await m.voix.allumer();
  m.ws().ouvrir();
  m.ws().recevoir({ type: "erreur", code: "modeles_absents", message: "Modèle Silero introuvable" });
  m.ws().couper(4000);
  assert.equal(m.voix.statut, "cle_absente");
  assert.equal(m.voix.derniereErreur, "Modèle Silero introuvable");
});

// --- le verrou d'écran ---------------------------------------------------------------

function fauxNavigateur({ refuse = false } = {}) {
  const nav = { demandes: 0, verrous: [] };
  nav.wakeLock = {
    async request(type) {
      assert.equal(type, "screen");
      nav.demandes += 1;
      if (refuse) throw new Error("refusé");
      const verrou = {
        released: false,
        async release() {
          verrou.released = true;
        },
      };
      nav.verrous.push(verrou);
      return verrou;
    },
  };
  return nav;
}

test("le verrou d'écran se demande une fois, et se redemande au retour s'il a été relâché", async () => {
  const nav = fauxNavigateur();
  const verrou = new VerrouEcran(nav);
  await verrou.demander();
  await verrou.demander();
  assert.equal(nav.demandes, 1);
  nav.verrous[0].released = true; // la page a été cachée
  await verrou.surVisible();
  assert.equal(nav.demandes, 2);
  verrou.relacher();
  assert.equal(nav.verrous[1].released, true);
  await verrou.surVisible();
  assert.equal(nav.demandes, 2);
});

test("relâché pendant sa demande, le verrou est rendu dès qu'il arrive", async () => {
  const nav = fauxNavigateur();
  const verrou = new VerrouEcran(nav);
  const demande = verrou.demander();
  verrou.relacher();
  await demande;
  assert.equal(nav.verrous[0].released, true);
});

test("sans API, ou refusé, le verrou d'écran ne casse rien", async () => {
  await new VerrouEcran({}).demander();
  await new VerrouEcran(undefined).demander();
  await new VerrouEcran(fauxNavigateur({ refuse: true })).demander();
});

// --- le micro et le haut-parleur du navigateur -----------------------------------------

test("le micro garde toujours l'annulation d'écho, et le son se joue et se vide", async () => {
  const { trace, nav } = fauxNavigateurAudio();
  const audio = await ouvrirAudioNavigateur({ surBloc() {}, surEtat() {} }, nav);
  assert.deepEqual(trace.contraintes, {
    audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
  });
  assert.match(trace.modules[0], /\/voix_worklet\.js$/);
  assert.equal(audio.etat, "running");
  const trame = new ArrayBuffer(640);
  audio.jouer(trame);
  audio.vider();
  assert.deepEqual(trace.postes, [
    { message: trame, transferts: [trame] },
    { message: "vider", transferts: undefined },
  ]);
  audio.fermer();
  assert.equal(trace.pistes[0].readyState, "ended");
  assert.equal(trace.contextes[0].fermee, true);
});

test("sans HTTPS, le micro n'est même pas demandé", async () => {
  const { trace, nav } = fauxNavigateurAudio({ securisee: false });
  await assert.rejects(ouvrirAudioNavigateur({ surBloc() {}, surEtat() {} }, nav), { name: "PageNonSecurisee" });
  assert.equal(trace.contextes.length, 0);
  assert.equal(trace.contraintes, null);
});

test("sans HTTPS, la voix dit pourquoi elle ne s'allume pas", async () => {
  const refus = Object.assign(new Error("HTTPS"), { name: "PageNonSecurisee" });
  const m = monter({ ouvrirAudio: async () => Promise.reject(refus) });
  await m.voix.allumer();
  assert.equal(m.voix.statut, "https_requis");
});

test("un micro qui se coupe le signale, et reprendre le rouvre", async () => {
  const { trace, nav } = fauxNavigateurAudio();
  const etats = [];
  const audio = await ouvrirAudioNavigateur({ surBloc() {}, surEtat: (etat) => etats.push(etat) }, nav);
  assert.equal(audio.microVivant, true);
  trace.pistes[0].terminer();
  assert.deepEqual(etats, ["running", "micro_coupe"]);
  assert.equal(audio.microVivant, false);
  await audio.reprendre();
  assert.equal(audio.microVivant, true);
  assert.equal(trace.pistes.length, 2);
  assert.deepEqual(etats, ["running", "micro_coupe", "running"]);
  await audio.reprendre();
  assert.equal(trace.pistes.length, 2); // micro vivant : rien à rouvrir
});

test("la fermeture du contexte par la page n'est pas signalée comme un état", async () => {
  const { nav } = fauxNavigateurAudio();
  const etats = [];
  const audio = await ouvrirAudioNavigateur({ surBloc() {}, surEtat: (etat) => etats.push(etat) }, nav);
  audio.fermer();
  await new Promise((resoudre) => setImmediate(resoudre)); // l'événement arrive après coup
  assert.deepEqual(etats, ["running"]);
});

test("micro refusé : le contexte audio se referme et l'erreur remonte", async () => {
  const { trace, nav } = fauxNavigateurAudio({ micro: "refuse" });
  await assert.rejects(ouvrirAudioNavigateur({ surBloc() {}, surEtat() {} }, nav), { name: "NotAllowedError" });
  assert.equal(trace.contextes[0].fermee, true);
});

// La voix de la page : le micro part au Core par /ws/voix, le son d'Atlas en revient. La
// page n'est qu'un terminal audio : le mot de réveil, la détection de voix et la coupure de
// parole tournent sur le Core (voix.py).

import { Connexion } from "./connexion.js";

// Au retour sur la page, le son d'iOS repart seul (spike S4) ; sinon, un toucher le rouvre.
export const DELAI_REPRISE_MS = 1500;
// Les fins de connexion qui ne se retentent pas : le micro n'a plus de raison de rester ouvert.
const FINS = new Set(["cle_requise", "cle_refusee", "cle_absente"]);

export class Voix {
  constructor({
    url,
    lireCle,
    page,
    heyAtlas,
    surStatut,
    ouvrirAudio = ouvrirAudioNavigateur,
    verrou = new VerrouEcran(),
    FabriqueWebSocket,
    planifier = (rappel, delai) => setTimeout(rappel, delai),
  }) {
    this._heyAtlas = heyAtlas;
    this._surStatut = surStatut;
    this._ouvrirAudio = ouvrirAudio;
    this._verrou = verrou;
    this._planifier = planifier;
    this._audio = null;
    this._voulue = false; // le bouton « Micro » est allumé
    this._interrompue = false; // iOS a coupé le son de la page
    this.statut = "eteinte";
    this.derniereErreur = null; // l'explication du Core avant qu'il ne ferme, s'il en donne une
    this._connexion = new Connexion({
      url,
      lireCle,
      entree: () => ({ page, hey_atlas: this._heyAtlas() }),
      surMessage: (message) => this._surMessage(message),
      surBinaire: (pcm) => this._audio?.jouer(pcm),
      surStatut: (statut) => this._surStatutConnexion(statut),
      FabriqueWebSocket,
      planifier,
    });
  }

  get allumee() {
    return this._voulue;
  }

  // À appeler depuis un geste de l'utilisateur : iOS n'ouvre le micro et le son qu'ainsi.
  async allumer() {
    if (this._voulue) return;
    this._voulue = true;
    this.derniereErreur = null;
    this._changer("ouverture");
    let audio;
    try {
      audio = await this._ouvrirAudio({
        surBloc: (bloc) => this._connexion.envoyerBinaire(bloc),
        surEtat: (etat) => this._surEtatAudio(etat),
      });
    } catch (e) {
      this._voulue = false;
      this.derniereErreur = `${e.name} : ${e.message}`;
      this._changer(e.name === "PageNonSecurisee" ? "https_requis" : "micro_refuse");
      return;
    }
    if (!this._voulue) {
      audio.fermer(); // éteinte pendant l'ouverture
      return;
    }
    this._audio = audio;
    this._interrompue = false;
    this._connexion.demarrer();
    if (this._heyAtlas()) this._verrou.demander();
  }

  eteindre() {
    this._arreter("eteinte");
  }

  toucherOrbe() {
    return this._connexion.envoyer({ type: "parler" });
  }

  changerHeyAtlas(actif) {
    // Hors ligne, rien ne part : la prochaine connexion lira l'état du moment.
    this._connexion.envoyer({ type: "hey_atlas", actif });
    if (actif && this._voulue) this._verrou.demander();
    else this._verrou.relacher();
  }

  surVisibilite(visible) {
    if (!visible || !this._audio) return;
    if (this._heyAtlas()) this._verrou.surVisible();
    this._planifier(() => {
      if (!this._audio || (this._audio.etat === "running" && this._audio.microVivant)) return;
      this._interrompue = true; // le toucher qui le rouvrira le signalera au Core
      this._changer("a_reactiver");
    }, DELAI_REPRISE_MS);
  }

  // Le toucher qui rouvre le son quand iOS ne l'a pas relancé seul.
  async reactiver() {
    if (!this._audio) return;
    try {
      await this._audio.reprendre();
    } catch (e) {
      // L'autorisation retirée, ou le micro pris par une autre app : la page le dit.
      this.derniereErreur = `${e.name} : ${e.message}`;
      this._arreter("micro_refuse");
    }
  }

  _surMessage(message) {
    if (message.type === "vider") this._audio?.vider();
    else if (message.type === "erreur") this.derniereErreur = message.message;
  }

  _surStatutConnexion(statut) {
    if (statut === "en_ligne") {
      this._changer(this._statutAudio());
      return;
    }
    if (FINS.has(statut)) {
      this._voulue = false;
      this._fermerAudio();
    }
    this._changer(statut);
  }

  _surEtatAudio(etat) {
    if (!this._audio) return; // son fermé par la page elle-même, ou pas encore ouvert
    if (etat !== "running" || !this._audio.microVivant) {
      this._interrompue = true;
      this._changer(this._statutAudio());
      return;
    }
    if (!this._interrompue) return;
    this._interrompue = false;
    // Le Core laisse à l'annuleur d'écho le temps de se réinstaller.
    this._connexion.envoyer({ type: "reprise" });
    this._changer("active");
  }

  _statutAudio() {
    // Un micro coupé (appel, casque débranché…) ne revient jamais seul, même quand le son
    // repart : un toucher le rouvre.
    if (!this._audio.microVivant) return "a_reactiver";
    return this._interrompue ? "interrompue" : "active";
  }

  _arreter(statut) {
    this._voulue = false;
    this._connexion.arreter();
    this._fermerAudio();
    this._changer(statut);
  }

  _fermerAudio() {
    this._audio?.fermer();
    this._audio = null;
    this._verrou.relacher();
  }

  _changer(statut) {
    this.statut = statut;
    this._surStatut(statut);
  }
}

// Garde l'écran allumé tant que « Hey Atlas » écoute. Le navigateur relâche le verrou
// quand la page est cachée : il se redemande à son retour.
export class VerrouEcran {
  constructor(navigateur = globalThis.navigator) {
    this._navigateur = navigateur;
    this._verrou = null;
    this._voulu = false;
  }

  async demander() {
    this._voulu = true;
    if (!this._navigateur?.wakeLock || (this._verrou && !this._verrou.released)) return;
    let verrou;
    try {
      verrou = await this._navigateur.wakeLock.request("screen");
    } catch {
      return; // refusé (économie d'énergie…) : la page marche quand même, écran compris
    }
    if (this._voulu) this._verrou = verrou;
    else verrou.release().catch(() => {}); // relâché pendant la demande
  }

  relacher() {
    this._voulu = false;
    this._verrou?.release().catch(() => {});
    this._verrou = null;
  }

  async surVisible() {
    if (this._voulu) await this.demander();
  }
}

// Le micro et le haut-parleur, dans le navigateur. Le micro garde les réglages par défaut
// (spike S4) : jamais sans annulation d'écho, sinon iOS baisse la voix d'Atlas.
export async function ouvrirAudioNavigateur({ surBloc, surEtat }, nav = globalThis) {
  if (!nav.isSecureContext) {
    // Page ouverte par l'ancienne adresse en HTTP : le navigateur n'y donne pas le micro.
    throw Object.assign(new Error("le micro ne s'ouvre que sur une page en HTTPS"), { name: "PageNonSecurisee" });
  }
  const contexte = new nav.AudioContext();
  let flux = null;
  try {
    await contexte.audioWorklet.addModule(new URL("./voix_worklet.js", import.meta.url));
    const lecture = new nav.AudioWorkletNode(contexte, "lecture-16k", {
      numberOfInputs: 0,
      outputChannelCount: [1],
    });
    lecture.connect(contexte.destination);
    const capture = new nav.AudioWorkletNode(contexte, "capture-16k");
    capture.port.onmessage = (evenement) => surBloc(evenement.data);
    // Un nœud n'est calculé que s'il mène au haut-parleur : la capture y va, muette.
    const muet = contexte.createGain();
    muet.gain.value = 0;
    capture.connect(muet).connect(contexte.destination);
    contexte.addEventListener("statechange", () => {
      // Sa fermeture vient de la page elle-même : ce n'est pas une interruption.
      if (contexte.state !== "closed") surEtat(contexte.state);
    });
    await contexte.resume();
    const ouvrirMicro = async () => {
      flux = await nav.navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      contexte.createMediaStreamSource(flux).connect(capture);
      for (const piste of flux.getAudioTracks()) piste.addEventListener("ended", () => surEtat("micro_coupe"));
    };
    await ouvrirMicro();
    const microVivant = () => flux.getAudioTracks().some((piste) => piste.readyState === "live");
    return {
      get etat() {
        return contexte.state;
      },
      get microVivant() {
        return microVivant();
      },
      jouer: (pcm) => lecture.port.postMessage(pcm, [pcm]),
      vider: () => lecture.port.postMessage("vider"),
      async reprendre() {
        await contexte.resume();
        if (!microVivant()) await ouvrirMicro();
        surEtat(contexte.state); // un micro rouvert ne change pas l'état du contexte
      },
      fermer() {
        for (const piste of flux.getTracks()) piste.stop();
        contexte.close();
      },
    };
  } catch (e) {
    for (const piste of flux?.getTracks() ?? []) piste.stop();
    contexte.close();
    throw e;
  }
}

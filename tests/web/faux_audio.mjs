// Un navigateur audio minimal pour node --test : contexte, processeurs et micro, qui
// gardent trace de ce que la page leur demande.

export function fauxNavigateurAudio({ micro = "accorde", securisee = true } = {}) {
  const trace = { contraintes: null, modules: [], pistes: [], contextes: [], postes: [] };
  class Port {
    postMessage(message, transferts) {
      trace.postes.push({ message, transferts });
    }
  }
  class Noeud {
    constructor(contexte, nom, options) {
      this.nom = nom;
      this.options = options;
      this.port = new Port();
      this.gain = { value: 1 };
    }

    connect(cible) {
      return cible;
    }
  }
  class AudioContext {
    constructor() {
      this.state = "suspended";
      this.destination = new Noeud();
      this.fermee = false;
      this.audioWorklet = { addModule: async (url) => trace.modules.push(String(url)) };
      trace.contextes.push(this);
    }

    addEventListener() {}

    async resume() {
      this.state = "running";
    }

    close() {
      this.fermee = true;
    }

    createGain() {
      return new Noeud();
    }

    createMediaStreamSource() {
      return new Noeud();
    }
  }
  return {
    trace,
    nav: {
      isSecureContext: securisee,
      AudioContext,
      AudioWorkletNode: Noeud,
      navigator: {
        mediaDevices: {
          async getUserMedia(contraintes) {
            trace.contraintes = contraintes;
            if (micro === "refuse") throw Object.assign(new Error("non"), { name: "NotAllowedError" });
            const piste = fauxPiste();
            trace.pistes.push(piste);
            return { getTracks: () => [piste], getAudioTracks: () => [piste] };
          },
        },
      },
    },
  };
}

// Une piste de micro : `stop()` la termine sans prévenir (comme le navigateur) ;
// `terminer()` simule une fin venue d'ailleurs (un appel, un casque débranché).
function fauxPiste() {
  const ecouteurs = [];
  return {
    readyState: "live",
    stop() {
      this.readyState = "ended";
    },
    addEventListener(type, rappel) {
      if (type === "ended") ecouteurs.push(rappel);
    },
    terminer() {
      this.readyState = "ended";
      for (const rappel of ecouteurs) rappel();
    },
  };
}

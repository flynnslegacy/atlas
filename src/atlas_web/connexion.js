// La connexion à /ws/web : authentification, messages, reconnexion espacée.

export const DELAIS_RECONNEXION_MS = [1000, 2000, 4000, 8000, 16000, 30000];
export const FERMETURE_CLE_ABSENTE = 4000;
export const FERMETURE_NON_AUTORISE = 4401;
const OUVERT = 1;

export class Connexion {
  constructor({
    url,
    lireCle,
    surMessage,
    surStatut,
    FabriqueWebSocket = globalThis.WebSocket,
    planifier = (rappel, delai) => setTimeout(rappel, delai),
  }) {
    this._url = url;
    this._lireCle = lireCle;
    this._surMessage = surMessage;
    this._surStatut = surStatut;
    this._Fabrique = FabriqueWebSocket;
    this._planifier = planifier;
    this._ws = null;
    this._enLigne = false;
    this._tentatives = 0;
    this._arretee = true;
  }

  demarrer() {
    this._arretee = false;
    this._tentatives = 0;
    this._abandonner();
    this._ouvrir();
  }

  arreter() {
    this._arretee = true;
    this._abandonner();
  }

  envoyer(message) {
    if (!this._ws || this._ws.readyState !== OUVERT || !this._enLigne) return false;
    this._ws.send(JSON.stringify(message));
    return true;
  }

  _abandonner() {
    const ancienne = this._ws;
    this._ws = null;
    this._enLigne = false;
    if (ancienne) {
      ancienne.onopen = null;
      ancienne.onmessage = null;
      ancienne.onclose = null;
      ancienne.close();
    }
  }

  _ouvrir() {
    const cle = this._lireCle();
    if (!cle) {
      this._surStatut("cle_requise");
      return;
    }
    this._surStatut("connexion");
    const ws = new this._Fabrique(this._url);
    this._ws = ws;
    this._enLigne = false;
    ws.onopen = () => ws.send(JSON.stringify({ type: "authentification", cle }));
    ws.onmessage = (evenement) => {
      let message;
      try {
        message = JSON.parse(evenement.data);
      } catch {
        return;
      }
      if (!this._enLigne && message.type !== "erreur") {
        this._enLigne = true;
        this._tentatives = 0;
        this._surStatut("en_ligne");
      }
      this._surMessage(message);
    };
    ws.onclose = (evenement) => {
      if (this._ws !== ws) return;
      this._ws = null;
      this._enLigne = false;
      if (this._arretee) return;
      if (evenement.code === FERMETURE_NON_AUTORISE) {
        this._surStatut("cle_refusee");
        return;
      }
      if (evenement.code === FERMETURE_CLE_ABSENTE) {
        this._surStatut("cle_absente");
        return;
      }
      this._surStatut("hors_ligne");
      const delai = DELAIS_RECONNEXION_MS[Math.min(this._tentatives, DELAIS_RECONNEXION_MS.length - 1)];
      this._tentatives += 1;
      this._planifier(() => {
        if (!this._arretee && !this._ws) this._ouvrir();
      }, delai);
    };
  }
}

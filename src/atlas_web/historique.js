// L'historique de la conversation, affiché dans son panneau. Texte brut seulement.

export function formaterDuree(ms) {
  if (ms === null || ms === undefined) return null;
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(1).replace(".", ",")} s`;
}

const DELAIS = [
  ["transcription_ms", "transcription"],
  ["reflexion_ms", "réflexion"],
  ["premiere_voix_ms", "voix"],
];

export function formaterLatences(latences) {
  if (!latences) return "";
  return DELAIS.map(([cle, libelle]) => {
    const duree = formaterDuree(latences[cle]);
    return duree ? `${libelle} ${duree}` : null;
  })
    .filter(Boolean)
    .join(" · ");
}

function paragraphe(document, classe, texte) {
  const p = document.createElement("p");
  p.className = classe;
  p.textContent = texte;
  return p;
}

export function rendreHistorique(document, liste, echanges) {
  const elements = echanges.map((echange) => {
    const li = document.createElement("li");
    li.append(paragraphe(document, "entete", `${echange.heure} ${echange.source === "clavier" ? "⌨" : "🎙"}`));
    li.append(paragraphe(document, "question", echange.question || "(rien d'entendu)"));
    if (echange.reponse) li.append(paragraphe(document, "reponse", echange.reponse));
    if (echange.erreur) li.append(paragraphe(document, "erreur", echange.erreur));
    const latences = formaterLatences(echange.latences);
    if (latences) li.append(paragraphe(document, "latences", latences));
    return li;
  });
  liste.replaceChildren(...elements);
}

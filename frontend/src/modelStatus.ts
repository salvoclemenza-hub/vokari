// Stato di display di una riga modello/runtime, derivato in modo puro dai dati reali.
// Estratto da Models.tsx / Settings.tsx per essere testabile e non duplicato.

import type { ModelEntry } from "./bridge";

// "active"               → scaricato E selezionato (pronto all'uso) → "Attivo"
// "selected-undownloaded"→ selezionato come default ma NON ancora scaricato → "Selezionato · da scaricare" + Download
// "downloaded"           → scaricato ma non è l'attivo → "Scaricato"
// "available"            → non scaricato e non selezionato → Download
export type WhisperRowState = "active" | "selected-undownloaded" | "downloaded" | "available";

// `state` (dal backend) è autorità per scaricato/attivo; `isSelected` distingue solo il caso
// available+selezionato (il bug B1: prima mostrava "Attivo" pur non essendo scaricato).
export function whisperRowState(state: ModelEntry["state"], isSelected: boolean): WhisperRowState {
  if (state === "active") return "active";
  if (state === "downloaded") return "downloaded";
  if (isSelected) return "selected-undownloaded"; // state === "available" & è il modello scelto
  return "available";
}

// Suggerimento per la verifica Ollama in Impostazioni (B2): distingue "installato ma fermo"
// (→ avvialo) da "non installato" (→ installalo). Prima entrambi dicevano "avvialo".
export type OllamaHint = "up" | "installed-down" | "not-installed";

export function ollamaHint(s: { running: boolean; installed: boolean }): OllamaHint {
  if (s.running) return "up";
  if (s.installed) return "installed-down";
  return "not-installed";
}

// Bus toast minimale (pub/sub a livello modulo): qualsiasi schermata può chiamare
// toast(msg, kind) senza prop-drilling; <Toaster/> (montato in App) si sottoscrive.
// Coerente con il bus onVokariEvent già usato per gli eventi Python→JS.
export type ToastKind = "success" | "error" | "info";

/** Azione opzionale su un toast (MDL3: "Annulla" per l'eliminazione differita). */
export interface ToastAction {
  label: string;
  onClick: () => void;
}

export interface ToastItem {
  id: number;
  message: string;
  kind: ToastKind;
  action?: ToastAction;   // MDL3: bottone azione nel toast
  durationMs?: number;    // override del TTL per tipo (MDL3: finestra di undo a 5s)
}

export interface ToastOptions {
  action?: ToastAction;
  durationMs?: number;
}

type ToastHandler = (t: ToastItem) => void;

const handlers = new Set<ToastHandler>();
let seq = 0;

/** Mostra un toast e ritorna il suo id. `error` resta finché non lo si chiude (azionabile);
 *  gli altri si auto-chiudono (TTL per tipo, salvo `durationMs`). */
export function toast(message: string, kind: ToastKind = "info", opts?: ToastOptions): number {
  seq += 1;
  const item: ToastItem = { id: seq, message, kind, action: opts?.action, durationMs: opts?.durationMs };
  for (const h of handlers) h(item);
  return seq;
}

export function onToast(handler: ToastHandler): () => void {
  handlers.add(handler);
  return () => {
    handlers.delete(handler);
  };
}

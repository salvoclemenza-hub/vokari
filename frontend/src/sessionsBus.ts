// Bus minimale per segnalare che la libreria sessioni è cambiata (es. dopo un'eliminazione),
// così la sidebar "Recenti" si aggiorna senza prop-drilling. Stesso pattern di toast.ts/confirm.ts.
type Handler = () => void;

const handlers = new Set<Handler>();

/** Notifica che le sessioni sono cambiate (chiamato dopo delete/import). */
export function notifySessionsChanged(): void {
  for (const h of handlers) h();
}

export function onSessionsChanged(handler: Handler): () => void {
  handlers.add(handler);
  return () => {
    handlers.delete(handler);
  };
}

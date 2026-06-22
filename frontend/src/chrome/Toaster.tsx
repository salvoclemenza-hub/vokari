import { useEffect, useState } from "react";
import { onToast, type ToastItem, type ToastKind } from "../toast";

// Auto-dismiss per tipo (ms). 0 = persistente finché l'utente non chiude (errori azionabili, A2).
const TTL: Record<ToastKind, number> = { success: 2600, info: 3200, error: 0 };
// Classe scocca per tipo (colore SOLO come segnale di stato).
const KIND_CLS: Record<ToastKind, string> = { success: "ok", error: "err", info: "info" };

export function Toaster() {
  const [items, setItems] = useState<ToastItem[]>([]);

  useEffect(
    () =>
      onToast((t) => {
        setItems((cur) => [...cur, t]);
        const ttl = t.durationMs ?? TTL[t.kind]; // MDL3: durata custom (finestra di undo)
        if (ttl > 0) {
          window.setTimeout(() => setItems((cur) => cur.filter((x) => x.id !== t.id)), ttl);
        }
      }),
    [],
  );

  function dismiss(id: number) {
    setItems((cur) => cur.filter((x) => x.id !== id));
  }

  if (items.length === 0) return null;

  return (
    <div className="vk-toast-stack" role="status" aria-live="polite">
      {items.map((t) => (
        <div key={t.id} className={"vk-toast " + KIND_CLS[t.kind]}>
          <span className="ic">
            {t.kind === "info" ? (
              <span className="vk-spin" />
            ) : t.kind === "success" ? (
              <svg viewBox="0 0 24 24"><path d="M9 16.2 4.8 12l-1.4 1.4L9 19 21 7l-1.4-1.4z" /></svg>
            ) : (
              <svg viewBox="0 0 24 24"><path d="M11 7h2v6h-2zm0 8h2v2h-2zm1-13C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z" /></svg>
            )}
          </span>
          <span className="tx">{t.message}</span>
          {t.action && (
            <button
              className="vk-toast-undo"
              onClick={() => { t.action!.onClick(); dismiss(t.id); }}
            >
              {t.action.label}
            </button>
          )}
          <button className="vk-x" aria-label="Chiudi notifica" onClick={() => dismiss(t.id)}>
            ✕
          </button>
        </div>
      ))}
    </div>
  );
}

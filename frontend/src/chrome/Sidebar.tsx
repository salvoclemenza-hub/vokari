import { useEffect, useState } from "react";
import { bridge, onVokariEvent, type SessionItem } from "../bridge";
import { onSessionsChanged } from "../sessionsBus";

export const VK_NAV = [
  "Registra",
  "Sessioni",
  "Modelli AI",
  "Impostazioni",
] as const;
export type NavItem = (typeof VK_NAV)[number];

// Formattazione coerente con screens/Sessions.tsx.
function fmtDur(ms: number): string {
  const s = Math.round(ms / 1000);
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

function fmtDate(iso: string): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString("it-IT", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  } catch {
    return iso.slice(0, 10);
  }
}

export function Sidebar({
  active,
  onNavigate,
  onOpenSession,
}: {
  active: NavItem;
  onNavigate: (n: NavItem) => void;
  onOpenSession?: (id: string) => void;
}) {
  const [recents, setRecents] = useState<SessionItem[]>([]);

  // Carica i recenti UNA volta al mount, poi ricarica solo quando nasce una nuova
  // sessione (evento status=ready). Prima ricaricava ad OGNI cambio schermata (R8):
  // un round-trip IPC + re-parse di tutte le sessioni per navigazione, inutile dato
  // che i recenti cambiano solo a fine briefing.
  useEffect(() => {
    let alive = true;
    const load = () => bridge.listSessions().then((xs) => { if (alive) setRecents(xs.slice(0, 4)); });
    void load();
    const off = onVokariEvent((event, payload) => {
      if (event === "status" && payload.status === "ready") void load();
    });
    // Ricarica anche quando la libreria cambia per un'eliminazione (no voce fantasma).
    const offChanged = onSessionsChanged(() => void load());
    return () => { alive = false; off(); offChanged(); };
  }, []);

  return (
    <aside className="vk-side">
      <div className="vk-side-brand">
        vokari<span className="vk-caret"></span>
      </div>
      <div className="vk-side-tag">local-first · open source</div>
      <nav className="vk-nav">
        {VK_NAV.map((label) => (
          <a
            key={label}
            className={active === label ? "on" : ""}
            onClick={() => onNavigate(label)}
          >
            <span className="gl"></span>
            {label}
          </a>
        ))}
      </nav>
      <div className="vk-side-sec">
        Recenti
        {recents.length > 0 && (
          <a role="button" tabIndex={0} onClick={() => onNavigate("Sessioni")}
             onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") onNavigate("Sessioni"); }}>
            Tutte →
          </a>
        )}
      </div>
      <div className="vk-side-rc">
        {recents.length === 0 ? (
          <div className="r" style={{ cursor: "default" }}>
            <div className="m" style={{ marginBottom: 6, opacity: 0.6 }}>nessuna sessione recente</div>
            <a role="button" tabIndex={0} onClick={() => onNavigate("Registra")}
               onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") onNavigate("Registra"); }}
               style={{ color: "var(--green-d)", fontWeight: 600, fontSize: 12, cursor: "pointer" }}>
              Registra la prima →
            </a>
          </div>
        ) : (
          recents.map((s) => {
            const meeting = /riun|meeting/i.test(s.mode);
            return (
              <div
                className="r rec"
                key={s.id}
                role="button"
                tabIndex={0}
                style={{ cursor: "pointer" }}
                onClick={() => onOpenSession?.(s.id)}
                onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") onOpenSession?.(s.id); }}
              >
                <span className={"vk-rc-tag " + (meeting ? "riun" : "solo")}>{meeting ? "riun" : "solo"}</span>
                <div className="rc-b">
                  <div className="t" title={s.title}>{s.title}</div>
                  <div className="m">{fmtDate(s.createdAt)} · {fmtDur(s.durationMs)}</div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </aside>
  );
}

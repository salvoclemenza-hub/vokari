import { useEffect, useRef, useState } from "react";
import type React from "react";
import { VkIcon } from "../icons";
import { bridge, type SessionItem } from "../bridge";
import { confirmDialog } from "../confirm";
import { toast } from "../toast";
import { notifySessionsChanged } from "../sessionsBus";

type ModeFilter = "all" | "solo" | "riunione";
type SortBy = "data" | "durata" | "titolo";

function fmtDur(ms: number): string {
  const s = Math.round(ms / 1000);
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}
function fmtDate(iso: string): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString("it-IT", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  } catch { return iso.slice(0, 10); }
}
// Etichetta di raggruppamento relativa (Oggi / Ieri / Questa settimana / data piena).
function groupLabel(iso: string): string {
  if (!iso) return "Senza data";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "Senza data";
  const day = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diff = Math.round((day(new Date()) - day(d)) / 86_400_000);
  if (diff <= 0) return "Oggi";
  if (diff === 1) return "Ieri";
  if (diff < 7) return "Questa settimana";
  return d.toLocaleDateString("it-IT", { day: "numeric", month: "long", year: "numeric" });
}

export function ScreenSessions({ onOpen, onImport }: {
  onOpen?: (id: string) => void; onImport?: () => void;
}) {
  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [filter, setFilter] = useState<ModeFilter>("all");
  const [sort, setSort] = useState<SortBy>("data");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  // MDL3: timer di eliminazione differita per id (finestra di undo da 5s).
  const undoTimers = useRef<Map<string, number>>(new Map());
  const UNDO_MS = 5000;

  useEffect(() => { bridge.listSessions().then(setSessions); }, []);

  // Allo smontaggio i delete in attesa si confermano subito (l'utente ha lasciato la schermata):
  // evita timer orfani e onora l'eliminazione richiesta.
  useEffect(() => {
    const timers = undoTimers.current;
    return () => {
      for (const [id, t] of timers) { window.clearTimeout(t); void bridge.deleteSession(id); }
      timers.clear();
    };
  }, []);

  function reload() {
    setSelected(new Set());
    if (query.trim()) bridge.searchSessions(query).then(setSessions);
    else bridge.listSessions().then(setSessions);
    notifySessionsChanged();   // aggiorna anche la sidebar "Recenti" (no voci fantasma post-delete)
  }
  function handleSearch(q: string) {
    setQuery(q);
    if (q.trim()) bridge.searchSessions(q).then(setSessions);
    else bridge.listSessions().then(setSessions);
  }
  function toggle(id: string, e: React.MouseEvent) {
    e.stopPropagation();
    setSelected((cur) => {
      const next = new Set(cur);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  // Conteggi per i chip filtro (sull'insieme correntemente caricato: lista o ricerca).
  const counts = {
    all: sessions.length,
    solo: sessions.filter((s) => s.mode === "solo").length,
    riunione: sessions.filter((s) => s.mode === "riunione").length,
  };

  const filtered = filter === "all" ? sessions : sessions.filter((s) => s.mode === filter);
  // Ordinamento: "data" tiene l'ordine del backend (decrescente) e raggruppa per giorno;
  // "durata"/"titolo" producono una lista piatta riordinata (niente intestazioni-data).
  const grouped = sort === "data";
  const visible = grouped
    ? filtered
    : [...filtered].sort((a, b) =>
        sort === "durata" ? b.durationMs - a.durationMs : a.title.localeCompare(b.title, "it"));
  const allVisibleSelected = visible.length > 0 && visible.every((s) => selected.has(s.id));
  const isFiltering = filter !== "all" || query.trim().length > 0;
  // Libreria genuinamente vuota: nessuna sessione e nessuna ricerca in corso →
  // mostra solo il card di benvenuto, niente toolbar/filtri/legenda (sarebbero
  // rumore: "Tutte 0 · Solo 0"). Il caso "ricerca senza risultati" tiene la
  // toolbar visibile (query non vuota) così l'utente può cancellare la ricerca.
  const libraryEmpty = sessions.length === 0 && !query.trim();

  function toggleAll() {
    setSelected((cur) => {
      if (allVisibleSelected) {
        const next = new Set(cur);
        visible.forEach((s) => next.delete(s.id));
        return next;
      }
      return new Set([...cur, ...visible.map((s) => s.id)]);
    });
  }

  async function handlePlay(e: React.MouseEvent, id: string) {
    e.stopPropagation(); // non aprire la sessione
    const res = await bridge.playSessionAudio(id);
    if (!res.ok) toast(res.error || "Audio non disponibile", "error");
  }

  // MDL3: eliminazione singola SENZA modale — rimozione ottimistica + toast "Annulla" (5s).
  // Se l'utente non annulla entro la finestra → commit reale (bridge.deleteSession); se annulla
  // → ripristina (reload, la sessione esiste ancora) e niente chiamata. La multi-eliminazione
  // resta col modale di conferma (azione più grossa, anteprima MDL1).
  function handleDelete(e: React.MouseEvent, id: string) {
    e.stopPropagation();
    setSessions((cur) => cur.filter((x) => x.id !== id)); // rimozione ottimistica
    setSelected((cur) => { const n = new Set(cur); n.delete(id); return n; });
    notifySessionsChanged();
    const timer = window.setTimeout(() => {
      undoTimers.current.delete(id);
      setSessions((cur) => cur.filter((x) => x.id !== id)); // idempotente anche dopo un reload
      void bridge.deleteSession(id).then((res) => {
        if (!res.ok) toast("Eliminazione non riuscita", "error");
        notifySessionsChanged();
      });
    }, UNDO_MS);
    undoTimers.current.set(id, timer);
    toast("Sessione eliminata", "info", {
      durationMs: UNDO_MS,
      action: {
        label: "Annulla",
        onClick: () => {
          const t = undoTimers.current.get(id);
          if (t !== undefined) { window.clearTimeout(t); undoTimers.current.delete(id); }
          reload(); // ripristina la riga (la sessione non è stata cancellata)
        },
      },
    });
  }

  async function handleDeleteSelected() {
    const ids = [...selected];
    if (ids.length === 0) return;
    // MDL1: anteprima delle sessioni che si stanno per eliminare (tag modo, titolo, meta, artefatti).
    const items = sessions
      .filter((s) => selected.has(s.id))
      .map((s) => ({
        title: s.title,
        mode: s.mode,
        meta: `${fmtDate(s.createdAt)} · ${fmtDur(s.durationMs)}`,
        hasBriefing: s.hasBriefing,
        hasRecap: s.hasRecap,
        hasObsidian: s.hasObsidian,
      }));
    const ok = await confirmDialog({
      title: `Eliminare ${ids.length} sessioni?`,
      message: "Le sessioni selezionate verranno rimosse dalla libreria. L'operazione non è reversibile.",
      confirmLabel: `Elimina ${ids.length}`, cancelLabel: "Annulla", danger: true,
      items,
    });
    if (!ok) return;
    const res = await bridge.deleteSessions(ids);
    if (res.ok) { toast(`${res.deleted} sessioni eliminate`, "success"); reload(); }
    else toast("Eliminazione non riuscita", "error");
  }

  return (
    <>
      <div className="vk-greet">
        <div>
          <div className="vk-kick">~/sessioni</div>
          <h1>Sessioni</h1>
          <p>{sessions.length} registrazioni · tutte trascritte e archiviate in locale.</p>
        </div>
        <button className="vk-btn-g" onClick={onImport}><VkIcon.plus />Importa audio</button>
      </div>

      {!libraryEmpty && (<>
      <div className="vk-sess-bar">
        <div className="vk-srch">
          <VkIcon.search />
          <input role="searchbox" type="search" placeholder="Cerca per titolo, parola nel testo, data…"
            value={query} onChange={(e) => handleSearch(e.target.value)}
            style={{ background: "none", border: "none", outline: "none", flex: 1, font: "inherit" }} />
        </div>
        <div className="vk-flt">
          <button className={filter === "all" ? "on" : ""} onClick={() => setFilter("all")}>
            Tutte <span className="c" aria-hidden="true">{counts.all}</span>
          </button>
          <button className={filter === "solo" ? "on" : ""} onClick={() => setFilter("solo")}>
            Solo <span className="c" aria-hidden="true">{counts.solo}</span>
          </button>
          <button className={filter === "riunione" ? "on" : ""} onClick={() => setFilter("riunione")}>
            Riunione <span className="c" aria-hidden="true">{counts.riunione}</span>
          </button>
        </div>
        <select className="vk-sort" aria-label="Ordina le sessioni"
          value={sort} onChange={(e) => setSort(e.target.value as SortBy)}>
          <option value="data">Ordina: data</option>
          <option value="durata">Ordina: durata</option>
          <option value="titolo">Ordina: titolo</option>
        </select>
      </div>

      {isFiltering && visible.length > 0 && (
        <div className="vk-count">
          {visible.length} {visible.length === 1 ? "risultato" : "risultati"}
          {query.trim() ? ` per «${query.trim()}»` : ""}
        </div>
      )}

      {selected.size > 0 && (
        <div className="vk-selbar">
          <span className="n">{selected.size} {selected.size === 1 ? "selezionata" : "selezionate"}</span>
          <span className="grow" />
          <button className="del" onClick={() => void handleDeleteSelected()}>Elimina {selected.size}</button>
          <button className="ann" onClick={() => setSelected(new Set())}>Annulla</button>
        </div>
      )}

      <div className={"vk-listbar" + (selected.size > 0 ? " selecting" : "")}>
        <label className="vk-selall">
          <input type="checkbox" checked={allVisibleSelected} onChange={toggleAll}
            aria-label="Seleziona tutte le sessioni visibili" />
          Seleziona tutto
        </label>
        <span className="grow" />
        <div className="vk-legend">
          file:
          <span><i className="brief" />briefing</span>
          <span><i className="recap" />recap</span>
          <span><i className="vault" />obsidian</span>
        </div>
      </div>
      </>)}

      <div className={"vk-sess-list" + (selected.size > 0 ? " selecting" : "")}>
        {(() => {
          // Righe: in modalità "data" un'intestazione .vk-sgrp a ogni cambio di giorno
          // (Oggi/Ieri/…); ordinando per durata/titolo la lista è piatta (no intestazioni).
          const out: React.ReactNode[] = [];
          let lastLabel = "";
          for (const s of visible) {
            if (grouped) {
              const label = groupLabel(s.createdAt);
              if (label !== lastLabel) {
                out.push(<div className="vk-sgrp" key={`grp-${s.id}`}>{label}</div>);
                lastLabel = label;
              }
            }
            const modeRiun = s.mode === "riunione";
            out.push(
              <div className={"vk-srow" + (selected.has(s.id) ? " sel" : "")} key={s.id}
                role="button" tabIndex={0} aria-label={`Apri la sessione ${s.title}`}
                onClick={() => onOpen?.(s.id)}
                onKeyDown={(e) => {
                  // Enter/Spazio su checkbox o "Elimina" interni resta loro (non aprire la sessione).
                  if (e.target !== e.currentTarget) return;
                  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onOpen?.(s.id); }
                }}>
                <input type="checkbox" className="vk-srow-chk" checked={selected.has(s.id)}
                  onClick={(e) => toggle(s.id, e)} onChange={() => {}} aria-label={`Seleziona ${s.title}`} />
                <span className="ic">.md</span>
                <span className="nm">
                  <span className="ti">
                    <span className="t" title={s.title}>{s.title}</span>
                    {s.clarCount > 0 && (
                      <span className="vk-dc"
                        title={`${s.clarCount} ${s.clarCount === 1 ? "domanda" : "domande"} da chiarire`}>
                        ? {s.clarCount}
                      </span>
                    )}
                  </span>
                  <span className="m">{fmtDate(s.createdAt)} · {s.model}</span>
                </span>
                <span className={"mode " + (modeRiun ? "riun" : "solo")}>{modeRiun ? "Riunione" : "Solo"}</span>
                <span className="dur">{fmtDur(s.durationMs)}</span>
                <span className="out">
                  <i className={"md" + (s.hasBriefing ? "" : " off")} title={s.hasBriefing ? "briefing" : "briefing assente"} />
                  <i className={"rc" + (s.hasRecap ? "" : " off")} title={s.hasRecap ? "recap" : "recap assente"} />
                  <i className={"ob" + (s.hasObsidian ? "" : " off")} title={s.hasObsidian ? "obsidian" : "obsidian assente"} />
                </span>
                {s.hasAudio && (
                  <button className="vk-play" aria-label={`Apri l'audio di ${s.title}`} title="Apri l'audio"
                    onClick={(e) => void handlePlay(e, s.id)}>
                    <VkIcon.play />
                  </button>
                )}
                <button className="vk-srow-del" aria-label={`Elimina ${s.title}`} title="Elimina sessione"
                  onClick={(e) => handleDelete(e, s.id)}>
                  <VkIcon.trash />
                </button>
              </div>,
            );
          }
          return out;
        })()}
        {visible.length === 0 && (
          query.trim() ? (
            <div className="vk-empty">
              <span className="ei"><VkIcon.search /></span>
              <div className="et">Nessun risultato per «{query.trim()}»</div>
              <div className="es">Prova con un&apos;altra parola del titolo o del testo, oppure cancella la ricerca.</div>
              <button className="vk-btn-gh" onClick={() => handleSearch("")}>Cancella ricerca</button>
            </div>
          ) : (
            <div className="vk-empty">
              <span className="ei"><VkIcon.mic /></span>
              <div className="et">Ancora nessuna sessione</div>
              <div className="es">Le tue registrazioni trascritte compaiono qui. Importa un file audio o registra dalla Home.</div>
              <button className="vk-btn-g" onClick={onImport}><VkIcon.plus />Importa audio</button>
            </div>
          )
        )}
      </div>
    </>
  );
}

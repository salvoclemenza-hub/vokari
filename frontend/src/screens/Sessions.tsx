import { useEffect, useRef, useState } from "react";
import type React from "react";
import { useTranslation } from "react-i18next";
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

export function ScreenSessions({ onOpen, onImport }: {
  onOpen?: (id: string) => void; onImport?: () => void;
}) {
  const { t, i18n } = useTranslation();
  // Locale data dipendente dalla lingua app (it-IT / en-US) per formati e raggruppamento.
  const dateLocale = i18n.language === "en" ? "en-US" : "it-IT";
  function fmtDate(iso: string): string {
    if (!iso) return "";
    try {
      return new Date(iso).toLocaleString(dateLocale, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
    } catch { return iso.slice(0, 10); }
  }
  // Etichetta di raggruppamento relativa (Oggi / Ieri / Questa settimana / data piena).
  function groupLabel(iso: string): string {
    if (!iso) return t("sess.noDate");
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return t("sess.noDate");
    const day = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
    const diff = Math.round((day(new Date()) - day(d)) / 86_400_000);
    if (diff <= 0) return t("sess.today");
    if (diff === 1) return t("sess.yesterday");
    if (diff < 7) return t("sess.thisWeek");
    return d.toLocaleDateString(dateLocale, { day: "numeric", month: "long", year: "numeric" });
  }
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
        sort === "durata" ? b.durationMs - a.durationMs : a.title.localeCompare(b.title, dateLocale));
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
    if (!res.ok) toast(res.error || t("sess.audioUnavailable"), "error");
  }

  // MDL3: eliminazione singola SENZA modale — rimozione ottimistica + toast "Annulla" (5s).
  // Se l'utente non annulla entro la finestra → commit reale (bridge.deleteSession); se annulla
  // → ripristina (reload, la sessione esiste ancora) e niente chiamata. La multi-eliminazione
  // resta col modale di conferma (azione più grossa, anteprima MDL1).
  function handleDelete(e: React.MouseEvent, id: string) {
    e.stopPropagation();
    setSessions((cur) => cur.filter((x) => x.id !== id)); // rimozione ottimistica
    setSelected((cur) => { const n = new Set(cur); n.delete(id); return n; });
    // NON notificare il bus qui: la sessione esiste ancora su disco (finestra undo 5s).
    // Il notify arriva solo dopo il commit reale (bridge.deleteSession sotto) → la sidebar
    // non può mostrare la sessione "fantasma" rileggendo disco prima che sia eliminata.
    const timer = window.setTimeout(() => {
      undoTimers.current.delete(id);
      setSessions((cur) => cur.filter((x) => x.id !== id)); // idempotente anche dopo un reload
      void bridge.deleteSession(id).then((res) => {
        if (!res.ok) toast(t("sess.deleteFailed"), "error");
        notifySessionsChanged();
      });
    }, UNDO_MS);
    undoTimers.current.set(id, timer);
    toast(t("sess.sessionDeleted"), "info", {
      durationMs: UNDO_MS,
      action: {
        label: t("sess.undo"),
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
      title: t("sess.deleteManyTitle", { count: ids.length }),
      message: t("sess.deleteManyMsg"),
      confirmLabel: t("sess.deleteN", { count: ids.length }), cancelLabel: t("sess.cancel"), danger: true,
      items,
    });
    if (!ok) return;
    const res = await bridge.deleteSessions(ids);
    if (res.ok) { toast(t("sess.deletedToast", { count: res.deleted }), "success"); reload(); }
    else toast(t("sess.deleteFailed"), "error");
  }

  return (
    <>
      <div className="vk-greet">
        <div>
          <div className="vk-kick">{t("sess.kick")}</div>
          <h1>{t("sess.heading")}</h1>
          <p>{t("sess.subtitle", { count: sessions.length })}</p>
        </div>
        <button className="vk-btn-g" onClick={onImport}><VkIcon.plus />{t("sess.importAudio")}</button>
      </div>

      {!libraryEmpty && (<>
      <div className="vk-sess-bar">
        <div className="vk-srch">
          <VkIcon.search />
          <input role="searchbox" type="search" placeholder={t("sess.searchPlaceholder")}
            value={query} onChange={(e) => handleSearch(e.target.value)}
            style={{ background: "none", border: "none", outline: "none", flex: 1, font: "inherit" }} />
        </div>
        <div className="vk-flt">
          <button className={filter === "all" ? "on" : ""} onClick={() => setFilter("all")}>
            {t("sess.filterAll")} <span className="c" aria-hidden="true">{counts.all}</span>
          </button>
          <button className={filter === "solo" ? "on" : ""} onClick={() => setFilter("solo")}>
            {t("sess.filterSolo")} <span className="c" aria-hidden="true">{counts.solo}</span>
          </button>
          <button className={filter === "riunione" ? "on" : ""} onClick={() => setFilter("riunione")}>
            {t("sess.filterMeeting")} <span className="c" aria-hidden="true">{counts.riunione}</span>
          </button>
        </div>
        <select className="vk-sort" aria-label={t("sess.sortAria")}
          value={sort} onChange={(e) => setSort(e.target.value as SortBy)}>
          <option value="data">{t("sess.sortDate")}</option>
          <option value="durata">{t("sess.sortDuration")}</option>
          <option value="titolo">{t("sess.sortTitle")}</option>
        </select>
      </div>

      {isFiltering && visible.length > 0 && (
        <div className="vk-count">
          {visible.length} {visible.length === 1 ? t("sess.resultSingular") : t("sess.resultPlural")}
          {query.trim() ? t("sess.resultsFor", { q: query.trim() }) : ""}
        </div>
      )}

      {selected.size > 0 && (
        <div className="vk-selbar">
          <span className="n">{selected.size} {selected.size === 1 ? t("sess.selectedSingular") : t("sess.selectedPlural")}</span>
          <span className="grow" />
          <button className="del" onClick={() => void handleDeleteSelected()}>{t("sess.deleteN", { count: selected.size })}</button>
          <button className="ann" onClick={() => setSelected(new Set())}>{t("sess.cancel")}</button>
        </div>
      )}

      <div className={"vk-listbar" + (selected.size > 0 ? " selecting" : "")}>
        <label className="vk-selall">
          <input type="checkbox" checked={allVisibleSelected} onChange={toggleAll}
            aria-label={t("sess.selectAllAria")} />
          {t("sess.selectAll")}
        </label>
        <span className="grow" />
        <div className="vk-legend">
          {t("sess.legendFile")}
          <span><i className="brief" />{t("sess.legendBriefing")}</span>
          <span><i className="recap" />{t("sess.legendRecap")}</span>
          <span><i className="vault" />{t("sess.legendObsidian")}</span>
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
                role="button" tabIndex={0} aria-label={t("sess.openSessionAria", { title: s.title })}
                onClick={() => onOpen?.(s.id)}
                onKeyDown={(e) => {
                  // Enter/Spazio su checkbox o "Elimina" interni resta loro (non aprire la sessione).
                  if (e.target !== e.currentTarget) return;
                  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onOpen?.(s.id); }
                }}>
                <input type="checkbox" className="vk-srow-chk" checked={selected.has(s.id)}
                  onClick={(e) => toggle(s.id, e)} onChange={() => {}} aria-label={t("sess.selectAria", { title: s.title })} />
                <span className="ic">.md</span>
                <span className="nm">
                  <span className="ti">
                    <span className="t" title={s.title}>{s.title}</span>
                    {s.clarCount > 0 && (
                      <span className="vk-dc"
                        title={t("sess.clarTitle", { count: s.clarCount, word: s.clarCount === 1 ? t("sess.clarSingular") : t("sess.clarPlural") })}>
                        ? {s.clarCount}
                      </span>
                    )}
                  </span>
                  <span className="m">{fmtDate(s.createdAt)} · {s.model}</span>
                </span>
                <span className={"mode " + (modeRiun ? "riun" : "solo")}>{modeRiun ? t("sess.modeMeeting") : t("sess.modeSolo")}</span>
                <span className="dur">{fmtDur(s.durationMs)}</span>
                <span className="out">
                  <i className={"md" + (s.hasBriefing ? "" : " off")} title={s.hasBriefing ? t("sess.outBriefing") : t("sess.outBriefingOff")} />
                  <i className={"rc" + (s.hasRecap ? "" : " off")} title={s.hasRecap ? t("sess.outRecap") : t("sess.outRecapOff")} />
                  <i className={"ob" + (s.hasObsidian ? "" : " off")} title={s.hasObsidian ? t("sess.outObsidian") : t("sess.outObsidianOff")} />
                </span>
                {s.hasAudio && (
                  <button className="vk-play" aria-label={t("sess.playAria", { title: s.title })} title={t("sess.playTitle")}
                    onClick={(e) => void handlePlay(e, s.id)}>
                    <VkIcon.play />
                  </button>
                )}
                <button className="vk-srow-del" aria-label={t("sess.deleteRowAria", { title: s.title })} title={t("sess.deleteRowTitle")}
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
              <div className="et">{t("sess.emptySearchTitle", { q: query.trim() })}</div>
              <div className="es">{t("sess.emptySearchDesc")}</div>
              <button className="vk-btn-gh" onClick={() => handleSearch("")}>{t("sess.clearSearch")}</button>
            </div>
          ) : (
            <div className="vk-empty">
              <span className="ei"><VkIcon.mic /></span>
              <div className="et">{t("sess.emptyTitle")}</div>
              <div className="es">{t("sess.emptyDesc")}</div>
              <button className="vk-btn-g" onClick={onImport}><VkIcon.plus />{t("sess.importAudio")}</button>
            </div>
          )
        )}
      </div>
    </>
  );
}

import { useEffect, useMemo, useRef, useState } from "react";
import type React from "react";
import { useTranslation } from "react-i18next";
import { VkIcon } from "../icons";
import { bridge, onVokariEvent } from "../bridge";
import { confirmDialog } from "../confirm";

type Source = "mic" | "system" | "both";

function fmt(ms: number): string {
  const s = Math.floor(ms / 1000);
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

/** Mappa un livello dBFS (~-60 silenzio … 0 fondo scala) su un fattore 0.05..1 per
 *  scalare le altezze delle barre. `undefined` (nessun evento, es. browser/test) → onde calme. */
function ampFromDb(db: number | undefined): number {
  if (db === undefined) return 0.12;
  return Math.min(1, Math.max(0.05, (db + 60) / 60));
}

export function ScreenLive({ source, title = "", onTitleChange, context = "", onContextChange, whisperModel, livePreviewActive = false, onStop, onCancel }: {
  source: Source; title?: string; onTitleChange?: (t: string) => void;
  context?: string; onContextChange?: (c: string) => void;
  whisperModel?: string; livePreviewActive?: boolean;
  onStop?: (source: Source) => void; onCancel?: () => void;
}) {
  const { t } = useTranslation();
  const [elapsed, setElapsed] = useState(0);
  const [paused, setPaused] = useState(false);
  const [markers, setMarkers] = useState<{ tMs: number; t: string; label: string }[]>([]);
  const [levelDb, setLevelDb] = useState<Record<string, number>>({});
  const [silent, setSilent] = useState<Record<string, boolean>>({});
  const [liveText, setLiveText] = useState("");
  const [flash, setFlash] = useState<string | null>(null);
  const startedRef = useRef<number>(Date.now());
  const pausedRef = useRef(false);
  const sourceRef = useRef<Source>(source);
  sourceRef.current = source;
  // Ultimo istante con segnale udibile per lane → rilevamento "nessun segnale" (mic morto).
  const lastSignalRef = useRef<Record<string, number>>({});
  const flashTimer = useRef<number | undefined>(undefined);

  // Profili barre statici memoizzati (i ~10 re-render/s da audio_level non li ricostruiscono).
  const micBars = useMemo(() => Array.from({ length: 64 }, (_, i) => 6 + Math.round(18 * Math.abs(Math.sin(i * 0.5)) + 11 * Math.abs(Math.sin(i * 0.21 + 0.6)))), []);
  const sysBars = useMemo(() => Array.from({ length: 64 }, (_, i) => 5 + Math.round(12 * Math.abs(Math.sin(i * 0.37 + 1.1)) + 8 * Math.abs(Math.sin(i * 0.13)))), []);

  useEffect(() => {
    startedRef.current = Date.now();
    // La registrazione è già stata avviata dalla Home (via bridge.startRecording).
    // Qui gestiamo timer, rilevamento silenzio, scorciatoie e gli eventi push.
    const id = setInterval(() => {
      if (pausedRef.current) return;
      const el = Date.now() - startedRef.current;
      setElapsed(el);
      if (el > 4000) {   // dai tempo all'audio di partire prima di gridare "nessun segnale"
        const now = Date.now();
        const lanesNow: Source[] = sourceRef.current === "both" ? ["mic", "system"] : [sourceRef.current];
        setSilent((prev) => {
          let changed = false; const next = { ...prev };
          for (const ln of lanesNow) {
            const s = now - (lastSignalRef.current[ln] || 0) > 3000;
            if (next[ln] !== s) { next[ln] = s; changed = true; }
          }
          return changed ? next : prev;
        });
      }
    }, 250);
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      const typing = !!el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable);
      if (e.key === "Escape" && !typing) { void handleCancelClick(); return; }
      if (typing) return;
      if (e.key === "m" || e.key === "M") void addMarker();
      else if (e.key === " ") { e.preventDefault(); void togglePause(); }
    };
    window.addEventListener("keydown", onKey);
    // Livelli RMS reali spinti da Python durante la cattura (decorativi se assenti).
    const offLevel = onVokariEvent((event, payload) => {
      if (event === "audio_level" && !pausedRef.current) {
        const lane = String(payload.lane);
        const db = Number(payload.db);
        setLevelDb((prev) => ({ ...prev, [lane]: db }));
        if (db > -55) lastSignalRef.current[lane] = Date.now();   // segnale udibile
      }
      if (event === "live_transcript") setLiveText(String(payload.text ?? ""));
    });
    return () => {
      clearInterval(id);
      window.removeEventListener("keydown", onKey);
      offLevel();
      if (flashTimer.current) window.clearTimeout(flashTimer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function addMarker() {
    const m = await bridge.addMarker(t("live.bookmarkDefault", { n: markers.length + 1 }));
    if (m && "t_ms" in m) {
      setMarkers((xs) => [...xs, { tMs: m.t_ms, t: fmt(m.t_ms), label: m.label }]);
      setFlash(t("live.bookmarkFlash", { time: fmt(m.t_ms) }));
      if (flashTimer.current) window.clearTimeout(flashTimer.current);
      flashTimer.current = window.setTimeout(() => setFlash(null), 1400);
    }
  }

  function renameMarker(i: number, label: string) {
    setMarkers((xs) => xs.map((mk, j) => (j === i ? { ...mk, label } : mk)));
  }

  function commitMarker(i: number, label: string) {
    void bridge.updateMarker(i, label);
  }

  async function togglePause() {
    if (pausedRef.current) {
      startedRef.current = Date.now() - elapsed;   // riprendi escludendo la pausa
      pausedRef.current = false;
      setPaused(false);
      await bridge.resumeRecording();
    } else {
      pausedRef.current = true;
      setPaused(true);
      await bridge.pauseRecording();
    }
  }

  async function handleCancelClick() {
    // Azione distruttiva: conferma in-app stilizzata (no window.confirm nativo/rudimentale).
    const ok = await confirmDialog({
      title: t("live.discardTitle"),
      message: t("live.discardMsg"),
      confirmLabel: t("live.discardConfirm"),
      cancelLabel: t("live.discardCancel"),
      danger: true,
    });
    if (ok) onCancel?.();
  }

  const lanes: Source[] = source === "both" ? ["mic", "system"] : [source];
  const laneMeta: Record<Source, { cls: string; lbl: string; sub: string; bars: number[]; warn: string }> = {
    mic: { cls: "mic", lbl: t("live.laneMic"), sub: t("live.laneMicSub"), bars: micBars, warn: t("live.laneMicWarn") },
    system: { cls: "sys", lbl: t("live.laneSys"), sub: t("live.laneSysSub"), bars: sysBars, warn: t("live.laneSysWarn") },
    both: { cls: "mic", lbl: t("live.laneBoth"), sub: "", bars: micBars, warn: t("live.laneBothWarn") },
  };

  const mm = String(Math.floor(elapsed / 60000)).padStart(2, "0");
  const ss = String(Math.floor(elapsed / 1000) % 60).padStart(2, "0");

  return (
    <div className={"vk-live" + (paused ? " paused" : "")}>
      <div className="vk-live-top">
        <div className="vk-live-topl">
          <div className="vk-rec-lbl">
            <span className="vk-rec-dot"></span>
            <span className="st">{paused ? t("live.paused") : t("live.recording")}</span>
            <input
              className="vk-rec-title" value={title} onChange={(e) => onTitleChange?.(e.target.value)}
              placeholder={t("live.titlePlaceholder")} aria-label={t("live.titleAria")} spellCheck={false} />
          </div>
          <div className="vk-ctx-wrap">
            <div className="vk-ctx-lbl">{t("live.ctxLblPre")}<span>—</span>{t("live.ctxLblPost")}</div>
            <input
              className="vk-ctx" value={context} onChange={(e) => onContextChange?.(e.currentTarget.value)}
              placeholder={t("live.ctxPlaceholder")} aria-label={t("live.ctxAria")} spellCheck={false} />
          </div>
        </div>
        {/* Indicatore di sorgente (scelta in Home, non modificabile qui): status INERTE. */}
        <div className="vk-src" aria-hidden="true">
          <div className={"s" + (source === "mic" ? " on" : "")}>
            <VkIcon.mic /><div><div className="nm">{t("live.micName")}</div><div className="ds">{t("live.micDesc")}</div></div></div>
          <div className={"s" + (source === "system" ? " on" : "")}>
            <VkIcon.speaker /><div><div className="nm">{t("live.sysName")}</div><div className="ds">{t("live.callVideo")}</div></div></div>
          <div className={"s" + (source === "both" ? " on" : "")}>
            <VkIcon.both /><div><div className="nm">{t("live.bothName")}</div><div className="ds">{source === "both" ? t("live.bothActive") : t("live.bothInactive")}</div></div></div>
        </div>
      </div>

      <div className="vk-timer-wrap">
        <div className="vk-timer"><span>{mm}</span><span className="cln">:</span><span>{ss}</span></div>
        {paused && <div className="vk-pausetag">{t("live.pausedTag")}</div>}
      </div>

      <div className="vk-meters" aria-hidden="true">
        {lanes.map((ln) => {
          const m = laneMeta[ln];
          const db = levelDb[ln];
          const amp = ampFromDb(db);
          const isSilent = !!silent[ln] && !paused;
          const dbText = db !== undefined ? `${Math.round(db)} dB` : "—";
          return (
            <div className={"vk-lane " + m.cls + (isSilent ? " silent" : "")} key={ln}>
              <span className="vk-lane-lbl"><span className="d"></span><span className="lt">{m.lbl}<small>{m.sub}</small></span></span>
              <span className="vk-lane-wave">{m.bars.map((h, i) => <i key={i} style={{ height: Math.max(3, Math.round(h * amp)) + "px", "--i": i } as React.CSSProperties}></i>)}</span>
              <span className="vk-lane-warn">⚠ {m.warn}</span>
              <span className="vk-lane-db">{dbText}</span>
            </div>
          );
        })}
      </div>

      {/* Pannello anteprima SOLO se l'anteprima live è davvero attiva: altrimenti non arriverebbe
          alcun live_transcript e il riquadro resterebbe "In ascolto…" per sempre. */}
      {livePreviewActive && (
        <div className="vk-live-transcript">
          <div className="vk-lt-head">{t("live.previewHead")}<small>{t("live.previewSub")}</small></div>
          <div className={"vk-lt-body" + (liveText ? " live" : "")}>
            {liveText
              ? <span>{liveText}<span className="cur"></span></span>
              : <span className="vk-lt-empty">{t("live.previewEmpty")}</span>}
          </div>
        </div>
      )}

      <div className="vk-bm-wrap">
        {flash && <span className="vk-bm-flash show">{flash}</span>}
        <button className="vk-bm" onClick={() => void addMarker()}>
          <VkIcon.flag />{t("live.bookmark")} <kbd>M</kbd>{markers.length > 0 && <span className="ct">{markers.length}</span>}
        </button>
      </div>

      {markers.length > 0 && (
        <div className="vk-bm-line">
          <div className="vk-bm-track" aria-hidden="true">
            {markers.map((mk, i) => <i key={i} style={{ left: Math.min(98, (mk.tMs / Math.max(elapsed, 1)) * 100) + "%" }}></i>)}
          </div>
          <div className="vk-bm-list">
            {markers.map((mk, i) => (
              <span className="vk-bm-item" key={i}>
                <span className="vk-bm-t">{mk.t}</span>
                <input
                  className="vk-bm-edit"
                  value={mk.label}
                  aria-label={t("live.markerLabel", { n: i + 1 })}
                  onChange={(e) => renameMarker(i, e.currentTarget.value)}
                  onBlur={(e) => commitMarker(i, e.currentTarget.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") e.currentTarget.blur(); }}
                  spellCheck={false}
                />
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="vk-kbd-hint"><kbd>{t("live.kbdSpace")}</kbd> {t("live.kbdPause")} · <kbd>M</kbd> {t("live.kbdBookmark")} · <kbd>{t("live.kbdEsc")}</kbd> {t("live.kbdCancel")}</div>

      <div className="vk-live-ctrl">
        <button className="vk-cbtn ghost" onClick={() => void handleCancelClick()}>{t("live.cancel")}</button>
        <button className="vk-cbtn pause" onClick={() => void togglePause()}><VkIcon.pause />{paused ? t("live.resume") : t("live.pause")}</button>
        <button className="vk-cbtn stop" onClick={() => onStop?.(source)}><VkIcon.stop />{t("live.stop")}</button>
      </div>

      <div className="vk-live-foot">
        <span className="ok"><span className="dot"></span>{t("live.footLocal")}</span>
        <span>{t("live.footPrivacy")}</span>
        <span className="model">{whisperModel || "large-v3-turbo"} · {t("live.ready")}</span>
      </div>
    </div>
  );
}

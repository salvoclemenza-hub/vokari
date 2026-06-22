import { useEffect, useRef, useState } from "react";
import {
  setConfirmListener, setPromptListener, setImportListener,
  type ConfirmRequest, type PromptRequest, type ImportRequest, type ImportDialogResult,
} from "../confirm";

const ICON_DANGER = <svg viewBox="0 0 24 24"><path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z" /></svg>;
const ICON_OK = <svg viewBox="0 0 24 24"><path d="M9 16.2 4.8 12l-1.4 1.4L9 19 21 7l-1.4-1.4z" /></svg>;
const ICON_EDIT = <svg viewBox="0 0 24 24"><path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a1 1 0 0 0 0-1.41l-2.34-2.34a1 1 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z" /></svg>;
const ICON_IMPORT = <svg viewBox="0 0 24 24"><path d="M5 20h14v-2H5v2zM12 3l-5.5 5.5 1.4 1.4L11 6.8V16h2V6.8l3.1 3.1 1.4-1.4L12 3z" /></svg>;

// Formattazione meta file (MDL2): durata m:ss e peso leggibile.
function fmtDur(s: number): string {
  const t = Math.round(s);
  return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`;
}
function fmtSize(b: number): string {
  if (b >= 1e9) return `${(b / 1e9).toFixed(1)} GB`;
  if (b >= 1e6) return `${Math.round(b / 1e6)} MB`;
  if (b >= 1e3) return `${Math.round(b / 1e3)} KB`;
  return `${b} B`;
}

export function ConfirmHost() {
  const [req, setReq] = useState<ConfirmRequest | null>(null);
  const [promptReq, setPromptReq] = useState<PromptRequest | null>(null);
  const [importReq, setImportReq] = useState<ImportRequest | null>(null);
  const [value, setValue] = useState("");
  const [importMode, setImportMode] = useState("solo");
  const [importCtx, setImportCtx] = useState("");
  const taRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    setConfirmListener((r) => setReq(r));
    setPromptListener((r) => { setValue(r.opts.defaultValue ?? ""); setPromptReq(r); });
    setImportListener((r) => { setImportMode(r.opts.defaultMode || "solo"); setImportCtx(r.opts.defaultContext ?? ""); setImportReq(r); });
    return () => { setConfirmListener(null); setPromptListener(null); setImportListener(null); };
  }, []);

  // Esc = annulla (tutti); Invio = conferma SOLO per il confirm (nei dialog con textarea
  // — prompt e import — Invio va a capo). Listener su window mentre un modale è aperto.
  useEffect(() => {
    if (!req && !promptReq && !importReq) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (importReq) { setImportReq(null); importReq.resolve(null); }
        else if (promptReq) { setPromptReq(null); promptReq.resolve(null); }
        else if (req) { setReq(null); req.resolve(false); }
      } else if (e.key === "Enter" && req && !promptReq && !importReq) {
        setReq(null); req.resolve(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [req, promptReq, importReq]);

  // Auto-grow del textarea del prompt all'apertura (e su defaultValue).
  useEffect(() => {
    const ta = taRef.current;
    if (promptReq && ta) { ta.style.height = "auto"; ta.style.height = Math.min(ta.scrollHeight, 200) + "px"; }
  }, [promptReq]);

  if (importReq) {
    const { opts, resolve } = importReq;
    const closeI = (r: ImportDialogResult | null) => { setImportReq(null); resolve(r); };
    const hasMeta = opts.durationS > 0 || opts.sizeBytes > 0;
    return (
      <div className="vk-modal show" role="dialog" aria-modal="true" aria-label="Importa registrazione" onClick={() => closeI(null)}>
        <div className="card" onClick={(e) => e.stopPropagation()}>
          <div className="mi neutral">{ICON_IMPORT}</div>
          <h3>Importa registrazione</h3>
          <div className="vk-mfile">
            <span className="fn" title={opts.fileName}>{opts.fileName}</span>
            {hasMeta && (
              <span className="fm">
                {opts.durationS > 0 && fmtDur(opts.durationS)}
                {opts.durationS > 0 && opts.sizeBytes > 0 && " · "}
                {opts.sizeBytes > 0 && fmtSize(opts.sizeBytes)}
              </span>
            )}
          </div>
          <div className="vk-mseg" role="group" aria-label="Tipo di sessione">
            <button className={importMode === "solo" ? "on" : ""} onClick={() => setImportMode("solo")}>Solo</button>
            <button className={importMode === "riunione" ? "on" : ""} onClick={() => setImportMode("riunione")}>Riunione</button>
          </div>
          <textarea
            autoFocus
            value={importCtx}
            placeholder="Di cosa parla? (opzionale)"
            onChange={(e) => setImportCtx(e.currentTarget.value)}
            onInput={(e) => {
              const ta = e.currentTarget;
              ta.style.height = "auto";
              ta.style.height = Math.min(ta.scrollHeight, 200) + "px";
            }}
          />
          <div className="vk-mfoot">
            <span className="vk-mkbd"><kbd>Esc</kbd> annulla</span>
            <div className="vk-actions">
              <button className="vk-ghost" onClick={() => closeI(null)}>Annulla</button>
              <button className="vk-primary" onClick={() => closeI({ mode: importMode, context: importCtx })}>Importa</button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (promptReq) {
    const { opts, resolve } = promptReq;
    const closeP = (v: string | null) => { setPromptReq(null); resolve(v); };
    return (
      <div className="vk-modal show" role="dialog" aria-modal="true" aria-label={opts.title ?? "Inserisci"} onClick={() => closeP(null)}>
        <div className="card" onClick={(e) => e.stopPropagation()}>
          <div className="mi neutral">{ICON_EDIT}</div>
          <h3>{opts.title ?? "Inserisci"}</h3>
          <p>{opts.message}</p>
          <textarea
            ref={taRef}
            autoFocus
            value={value}
            placeholder={opts.placeholder ?? ""}
            onChange={(e) => setValue(e.currentTarget.value)}
            onInput={(e) => {
              const ta = e.currentTarget;
              ta.style.height = "auto";
              ta.style.height = Math.min(ta.scrollHeight, 200) + "px";
            }}
          />
          <div className="vk-mfoot">
            <span className="vk-mkbd"><kbd>Esc</kbd> annulla</span>
            <div className="vk-actions">
              <button className="vk-ghost" onClick={() => closeP(null)}>{opts.cancelLabel ?? "Annulla"}</button>
              <button className="vk-primary" onClick={() => closeP(value)}>{opts.confirmLabel ?? "OK"}</button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (!req) return null;
  const { opts, resolve } = req;
  const close = (ok: boolean) => { setReq(null); resolve(ok); };

  return (
    <div className="vk-modal show" role="alertdialog" aria-modal="true" aria-label={opts.title ?? "Conferma"} onClick={() => close(false)}>
      <div className="card" onClick={(e) => e.stopPropagation()}>
        <div className={"mi " + (opts.danger ? "danger" : "neutral")}>{opts.danger ? ICON_DANGER : ICON_OK}</div>
        <h3>{opts.title ?? "Conferma"}</h3>
        <p>{opts.message}</p>
        {/* MDL1: anteprima elenco delle sessioni coinvolte (es. multi-eliminazione). */}
        {opts.items && opts.items.length > 0 && (
          <div className="vk-mlist">
            {opts.items.map((it, i) => (
              <div className="vk-mli" key={i}>
                <span className={"mode " + (it.mode === "riunione" ? "riun" : "solo")}>
                  {it.mode === "riunione" ? "Riun" : "Solo"}
                </span>
                <span className="t" title={it.title}>{it.title}</span>
                {it.meta && <span className="m">{it.meta}</span>}
                <span className="out">
                  {it.hasBriefing && <i className="brief" title="briefing" />}
                  {it.hasRecap && <i className="recap" title="recap" />}
                  {it.hasObsidian && <i className="vault" title="obsidian" />}
                </span>
              </div>
            ))}
          </div>
        )}
        <div className="vk-mfoot">
          <span className="vk-mkbd"><kbd>Esc</kbd> annulla · <kbd>Invio</kbd> conferma</span>
          <div className="vk-actions">
            <button className="vk-ghost" onClick={() => close(false)}>{opts.cancelLabel ?? "Annulla"}</button>
            <button className={opts.danger ? "vk-danger" : "vk-primary"} autoFocus onClick={() => close(true)}>
              {opts.confirmLabel ?? "Conferma"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

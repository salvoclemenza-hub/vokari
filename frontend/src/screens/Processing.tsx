import { Fragment, useEffect, useRef, useState } from "react";
import { VkIcon } from "../icons";
import type { JobStatus, AnalysisFit } from "../bridge";

const STEP_INDEX: Record<string, number> = {
  transcribing: 0, analyzing: 1, rendering: 2,
  awaiting_interview: 2, ready: 2, queued: 0, error: 0, cancelled: 0,
};

// Messaggi informativi a rotazione durante l'elaborazione: una registrazione lunga
// può richiedere minuti, questi rassicurano e spiegano cosa sta succedendo (sostituiscono
// la vecchia frase statica "su CPU … diversi minuti").
const ROT_MESSAGES = [
  "L'audio non lascia mai il tuo PC — esce solo il testo trascritto.",
  "La trascrizione gira in locale con faster-whisper, sulla tua CPU.",
  "L'analisi estrae decisioni, domande aperte e trascrizione integrale.",
  "Con Ollama nemmeno il testo esce dal dispositivo — tutto in locale.",
  "Il briefing finale è ottimizzato per darlo in pasto a un altro LLM.",
  "Una registrazione lunga può richiedere qualche minuto: è normale.",
];

export function ScreenProcessing({
  status = "transcribing", pct = 0, partialText = "", model,
  title, onRenameTitle, onCancel, fromCache, onRielabora,
  analyzeStep, analysisPreview, analysisFit,
}: {
  status?: JobStatus; pct?: number; partialText?: string; model?: string;
  title?: string; onRenameTitle?: (t: string) => void; onCancel?: () => void;
  fromCache?: boolean; onRielabora?: () => void;
  analyzeStep?: { step: string; label: string } | null;
  analysisPreview?: string;
  analysisFit?: AnalysisFit | null;
}) {
  const active = STEP_INDEX[status] ?? 0;
  const labels = ["Trascrizione", "Analisi AI", "Briefing"];
  const pctInt = Math.round(Math.min(1, Math.max(0, pct)) * 100);
  // Analisi/rendering LLM non hanno una percentuale reale: barra indeterminata animata
  // invece di restare ferma al 100% (che sembra "bloccato").
  const indeterminate = status === "analyzing" || status === "rendering" || status === "queued";
  const stepState = (i: number) => (i < active ? "done" : i === active ? "active" : "pending");

  // Caricamento modello: status transcribing ma nessun segmento ancora ricevuto.
  // Senza questo messaggio i ~20s di load del modello sembrano un blocco.
  const loadingModel = status === "transcribing" && !partialText;

  // Testo "fisso" mostrato nella console quando NON stiamo trascrivendo testo reale
  // (load modello / analisi / rendering): non va animato carattere per carattere.
  const fixedMessage =
    status === "queued" ? "Finalizzo la registrazione… (normalizzo e preparo l'audio)"
    : loadingModel ? "Carico il modello Whisper sul dispositivo… al primo avvio può richiedere ~20 secondi"
    : status === "analyzing" ? "L'AI sta organizzando la trascrizione nel briefing… su modello locale può richiedere 1–2 minuti"
    : status === "rendering" ? "Compongo il briefing…"
    : null;

  // Quando c'è testo trascritto reale lo riveliamo con un effetto "scrittura" (typewriter).
  const streaming = fixedMessage === null;

  const hint =
    status === "queued" ? "Preparo l'audio…"
    : loadingModel ? "Preparo la trascrizione locale…"
    : status === "analyzing" ? "Analisi AI…"
    : status === "rendering" ? "Genero il briefing…"
    : "Trascrizione locale…";

  // Sotto-fase descrittiva sotto il titolo (header): cosa sta succedendo, in chiaro.
  const phaseLabel =
    status === "queued" ? "Preparo l'audio — normalizzo e converto la registrazione"
    : loadingModel ? "Carico il modello Whisper sul tuo dispositivo…"
    : status === "transcribing" ? "Trascrizione in corso — il modello Whisper gira sulla tua CPU"
    : status === "analyzing" ? "Analisi AI — organizzo la trascrizione in un briefing"
    : status === "rendering" ? "Compongo il briefing finale"
    : "Elaborazione in corso";

  // --- effetto "scrittura" + auto-scroll ---------------------------------
  const [displayed, setDisplayed] = useState("");
  const targetRef = useRef("");
  const logRef = useRef<HTMLDivElement>(null);
  // Stick-to-bottom in stile chat LLM: di default seguiamo l'ultima parola scritta;
  // l'utente che scrolla su sospende l'auto-follow, tornare in fondo lo riattiva.
  const stickRef = useRef(true);

  useEffect(() => {
    if (!streaming) {
      // Analisi/rendering: usa partialText (sempre aggiornato, no race con useRef).
      // Se c'è transcript congelalo subito; se non c'è ancora mostra il messaggio fisso.
      setDisplayed(partialText || fixedMessage || "");
      return;
    }
    targetRef.current = partialText;
    const id = window.setInterval(() => {
      setDisplayed((cur) => {
        const t = targetRef.current;
        // partial_text è cumulativo → cur è sempre un prefisso di t.
        if (cur.length >= t.length) return cur.length === t.length ? cur : t;
        // Rivela un batch di caratteri; accelera se molto indietro così la coda
        // di un audio da 1h non resta perennemente arretrata rispetto al testo reale.
        const behind = t.length - cur.length;
        const step = Math.max(2, Math.floor(behind / 40));
        return t.slice(0, cur.length + step);
      });
    }, 22);
    return () => window.clearInterval(id);
  }, [streaming, partialText, fixedMessage]);

  useEffect(() => {
    const el = logRef.current;
    if (!el) return;
    // L'utente comanda: se scrolla via dal fondo sospendiamo l'auto-follow,
    // se torna a ridosso del fondo lo riprendiamo (soglia 48px).
    const onScroll = () => {
      stickRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48;
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, []);

  // --- messaggi informativi a rotazione ----------------------------------
  const [rotIdx, setRotIdx] = useState(0);
  useEffect(() => {
    const id = window.setInterval(() => setRotIdx((i) => (i + 1) % ROT_MESSAGES.length), 4500);
    return () => window.clearInterval(id);
  }, []);

  // --- timer per analisi AI (Livello 1) -----------------------------------
  const [elapsedS, setElapsedS] = useState(0);
  useEffect(() => {
    if (status !== "analyzing" && status !== "rendering") {
      setElapsedS(0);
      return;
    }
    const id = window.setInterval(() => {
      setElapsedS((s) => s + 1);
    }, 1000);
    return () => window.clearInterval(id);
  }, [status]);

  const formatTime = (seconds: number): string => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${s.toString().padStart(2, "0")}`;
  };

  // --- anteprima analisi streaming (Livello 2) -----------------------------------
  const [displayedPreview, setDisplayedPreview] = useState("");
  const previewTargetRef = useRef("");

  useEffect(() => {
    // Durante l'analisi, mostra l'anteprima con effetto typewriter come partialText.
    if (status !== "analyzing" || !analysisPreview) {
      setDisplayedPreview("");
      previewTargetRef.current = "";
      return;
    }
    previewTargetRef.current = analysisPreview;
    const id = window.setInterval(() => {
      setDisplayedPreview((cur) => {
        const t = previewTargetRef.current;
        if (cur.length >= t.length) return cur.length === t.length ? cur : t;
        const behind = t.length - cur.length;
        const step = Math.max(2, Math.floor(behind / 40));
        return t.slice(0, cur.length + step);
      });
    }, 22);
    return () => window.clearInterval(id);
  }, [status, analysisPreview]);

  // Auto-follow della coda: quando arriva nuovo testo — trascrizione (displayed)
  // O ragionamento (displayedPreview) — se stiamo seguendo riportiamo lo scroll
  // sull'ultima parola scritta. Prima dipendeva solo da `displayed`, così durante
  // l'analisi (ragionamento) la console non seguiva più e bisognava scrollare a mano.
  useEffect(() => {
    const el = logRef.current;
    if (el && stickRef.current) el.scrollTop = el.scrollHeight;
  }, [displayed, displayedPreview]);

  return (
    <div className="vk-proc">
      <div className="vk-proc-card">
        <div className="vk-proc-head">
          <div className="vk-proc-kick">Elaborazione</div>
          {title !== undefined ? (
            onRenameTitle ? (
              <input
                key={title}
                className="vk-proc-title-in"
                defaultValue={title}
                onBlur={(e) => { const v = e.currentTarget.value.trim(); if (v) onRenameTitle(v); }}
                onKeyDown={(e) => { if (e.key === "Enter") e.currentTarget.blur(); }}
                placeholder="Titolo sessione…"
              />
            ) : (
              <h2 className="vk-proc-title">{title || "Elaborazione in corso"}</h2>
            )
          ) : (
            <h2 className="vk-proc-title">Elaborazione in corso</h2>
          )}
          <div className="vk-proc-sub">{phaseLabel}</div>
        </div>

        <div className="vk-steps">
          {labels.map((lb, i) => {
            const st = stepState(i);
            return (
              <Fragment key={lb}>
                <div className={"vk-step " + st}>
                  <span className="n">{st === "done" ? <VkIcon.check /> : i + 1}</span>
                  <span className="lb">{lb}</span>
                </div>
                {i < labels.length - 1 && <span className={"vk-step-line" + (i < active ? " done" : "")}></span>}
              </Fragment>
            );
          })}
        </div>

        {analysisFit && (
          <div className="vk-fit-badge" data-testid="vk-fit-badge" data-level={analysisFit.level}>
            <span className="vk-fit-ico" aria-hidden="true">⚠</span>
            <div className="vk-fit-body">
              <div className="vk-fit-title">
                {analysisFit.level === "over_even_summarized"
                  ? "Trascrizione oltre il contesto del modello"
                  : "Trascrizione ampia per il modello scelto"}
              </div>
              <div className="vk-fit-meta">
                ~{analysisFit.tokensEst.toLocaleString("it-IT")} token · contesto{" "}
                {analysisFit.ctxMax.toLocaleString("it-IT")}
                {analysisFit.nChunks > 1 && ` · riassunta in ${analysisFit.nChunks} parti`}
              </div>
              {analysisFit.recommendation && (
                <div className="vk-fit-rec">{analysisFit.recommendation}</div>
              )}
            </div>
          </div>
        )}

        {fromCache && status === "transcribing" && (
          <div style={{ fontSize: 12, color: "var(--mut, #6b6358)", marginBottom: 8,
                        display: "flex", alignItems: "center", gap: 6 }}>
            <span className="dot" style={{ background: "var(--amber, #d8a24c)" }}></span>
            Trascrizione da cache
            {onRielabora && (
              <button onClick={onRielabora} style={{ background: "none", border: "none",
                color: "var(--green-d)", cursor: "pointer", font: "inherit",
                fontSize: 12, padding: 0, textDecoration: "underline" }}>· Rielabora</button>
            )}
          </div>
        )}
        <div className="vk-proc-meta">
          <span>
            {status === "analyzing"
              ? `Analisi AI · ${formatTime(elapsedS)}`
              : status === "rendering"
              ? `Briefing · ${formatTime(elapsedS)}`
              : `faster-whisper · ${model || "large-v3-turbo"} · ${status === "transcribing" || status === "queued" ? "in corso" : "completata"}`}
          </span>
          <span className="pct">{indeterminate ? "…" : pctInt + "%"}</span>
        </div>
        <div className={"vk-progress" + (indeterminate ? " indet" : "")}>
          <i style={indeterminate ? undefined : { width: pctInt + "%" }}></i>
        </div>

        <div className="vk-proc-log" data-phase={status}>
          {/* Mini-header con chip-etichetta dei due flussi (orientamento, non filtri):
              "trascrizione" si accende in trascrizione, "ragionamento" in analisi. */}
          <div className="vk-con-head">
            <span className="vk-chip trans">trascrizione</span>
            <span className="vk-chip reason">ragionamento</span>
          </div>
          <div className="vk-proc-stream" ref={logRef}>
            <div className="vk-con-line"><span className="vk-con-prompt">vokari@local ~ %</span></div>
            {fixedMessage && partialText && (
              <div style={{ opacity: 0.55, fontStyle: "italic", fontSize: 12, marginBottom: 8 }}>
                {fixedMessage}
              </div>
            )}
            <div className="vk-con-line">
              <span className="tx" style={!streaming && partialText ? { opacity: 0.5 } : undefined}>
                {displayed}
              </span>
              {streaming && <span className="cur"></span>}
            </div>
            {/* Ragionamento del modello: anteprima analisi in streaming (Livello 2),
                ∴ viola → "la macchina ragiona", distinto dal testo trascritto. */}
            {status === "analyzing" && displayedPreview && (
              <div className="vk-con-reason">
                <span className="pre">∴ ragiono</span>
                <span className="txt">{displayedPreview}<span className="cur"></span></span>
              </div>
            )}
          </div>
        </div>

        <div className="vk-wait">
          <div className="vk-wait-ico" aria-hidden="true">i</div>
          <div className="vk-wait-body">
            <div className="vk-wait-kick">Mentre aspetti</div>
            <div className="vk-wait-msg" key={rotIdx}>{ROT_MESSAGES[rotIdx]}</div>
          </div>
        </div>

        <div className="vk-proc-act">
          <span className="vk-proc-hint">
            <span className="dot"></span>
            {analyzeStep ? analyzeStep.label : hint}
          </span>
          <button className="vk-exit" onClick={onCancel}>Annulla elaborazione</button>
        </div>
      </div>
    </div>
  );
}

import { useEffect, useState } from "react";
import type React from "react";
import { VkIcon } from "../icons";
import { type Artifacts } from "../bridge";
import { Banner } from "../chrome/Banner";
import { MarkdownDoc } from "./MarkdownDoc";

type Source = "mic" | "system" | "both";
type Mode = "solo" | "riunione";

const SRC: Source[] = ["mic", "system", "both"];
const SRC_LABEL: Record<Source, string> = { mic: "mic", system: "system", both: "entrambi" };
const MODES: Mode[] = ["solo", "riunione"];

const HOME_BARS = Array.from({ length: 56 }, (_, i) =>
  14 + Math.round(16 * Math.abs(Math.sin(i * 0.55)) + 10 * Math.abs(Math.sin(i * 0.19 + 1.3))));

// Stato primo avvio: onboarding in 3 passi (redesign 2026-06-17). Le warning di
// configurazione (modello/chiave) restano nel Banner in alto, qui solo accoglienza.
const ONB_STEPS: { tt: string; dd: React.ReactNode }[] = [
  { tt: "Scegli tipo e sorgente", dd: "Da solo o riunione; microfono, audio di sistema o entrambi. Il tipo guida cosa cerca l'analisi." },
  { tt: "Premi Registra e parla", dd: <>Pulsante verde o <b>Ctrl R</b>. Puoi anche importare un file audio già esistente.</> },
  { tt: "Ottieni il tuo briefing", dd: "VOKARI trascrive in locale e struttura decisioni, domande aperte e trascrizione integrale." },
];

export function ScreenHome({
  onStart,
  onImport,
  lastArtifacts,
  mode = "solo",
  onModeChange,
  whisperModel,
  needsApiKey = false,
  needsModel = false,
  context = "",
  onContextChange,
  onOpenSettings,
  onOpenModels,
}: {
  onStart: (source: Source, context?: string) => void;
  onImport: () => void;
  lastArtifacts?: Artifacts | null;
  mode?: string;
  onModeChange?: (mode: Mode) => void;
  whisperModel?: string;
  needsApiKey?: boolean;
  needsModel?: boolean;
  context?: string;
  onContextChange?: (context: string) => void;
  onOpenSettings?: () => void;
  onOpenModels?: () => void;
}) {
  const [source, setSource] = useState<Source>("both");
  const [tab, setTab] = useState<"briefing.md" | "recap.md" | "obsidian/">("briefing.md");
  // ⌘ è il tasto modificatore su macOS; su Windows/Linux (VOKARI è desktop Windows) è Ctrl.
  const modKey = /Mac|iPhone|iPad/i.test(navigator.platform) ? "⌘" : "Ctrl";

  // Scorciatoia ⌘R / Ctrl+R → avvia registrazione con la sorgente attiva
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable)) return;
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "r") {
        e.preventDefault();
        onStart(source, context || undefined);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [source, context, onStart]);

  const hasBriefing = Boolean(lastArtifacts?.briefingMd);

  return (
    <>
      {(needsModel || needsApiKey) && (
        <Banner kind="warn" actions={
          <>
            {needsModel && <button className="vk-mini" onClick={onOpenModels}>Scarica un modello</button>}
            {needsApiKey && <button className="vk-mini" onClick={onOpenSettings}>Apri Impostazioni</button>}
          </>
        }>
          ⚙ <b>Configura VOKARI per iniziare.</b>{" "}
          {needsModel && "Scarica un modello Whisper per trascrivere. "}
          {needsApiKey && "Imposta la chiave Claude API (o passa a Ollama nelle Impostazioni)."}
        </Banner>
      )}
      <div className="vk-greet">
        <div>
          <div className="vk-kick">~/nuova-sessione</div>
          <h1>Registra. Trascrivi. Pensa meglio.</h1>
          <p>La tua voce diventa un <b>briefing pronto per l&apos;AI</b> — trascritta al 100% sul tuo dispositivo, senza cloud.</p>
        </div>
      </div>

      <div className="vk-grid">
        {/* ── Console (dark heart) ── */}
        <div className="vk-console">
          <div className="vk-con-head">
            <span className="vk-con-tag"><span className="dot"></span>capture</span>
          </div>

          <div className="vk-cap-rows">
            <div className="vk-seg-row">
              <span className="vk-src-lbl">tipo</span>
              <div className="vk-src" role="group" aria-label="Tipo sessione">
                {MODES.map((m) => (
                  <button key={m} className={mode === m ? "on" : ""} onClick={() => onModeChange?.(m)}>
                    {m}
                  </button>
                ))}
              </div>
            </div>
            <div className="vk-seg-row">
              <span className="vk-src-lbl">sorgente</span>
              <div className="vk-src" role="group" aria-label="Sorgente audio">
                {SRC.map((s) => (
                  <button key={s} className={source === s ? "on" : ""} onClick={() => setSource(s)}>
                    {SRC_LABEL[s]}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* B2: riga d'aiuto sul tipo sessione (solo UX, nessuna logica) */}
          <div style={{ padding: "6px 12px 0", fontSize: 11, color: "rgba(255,255,255,0.5)", lineHeight: 1.4 }}>
            <b>riunione</b> = più persone: l&apos;analisi cerca decisioni e responsabili
          </div>

          {/* Context/Scope optional input — leggibile sulla console scura */}
          <div style={{ padding: "8px 12px 4px", borderTop: "1px solid rgba(255,255,255,0.10)" }}>
            <label style={{ display: "block", fontSize: 11, color: "rgba(255,255,255,0.55)", marginBottom: 4 }}>
              Di cosa parla? <span style={{ opacity: 0.7 }}>(opzionale — aiuta l&apos;AI a cogliere lo scopo)</span>
            </label>
            <input
              type="text"
              placeholder="es. Decidere se fare la landing page"
              value={context}
              onChange={(e) => onContextChange?.(e.currentTarget.value)}
              style={{
                width: "100%", padding: "8px 10px", fontSize: 13,
                border: "1px solid rgba(255,255,255,0.22)", borderRadius: 6,
                background: "rgba(255,255,255,0.06)", color: "#f1ede5",
                fontFamily: "inherit", boxSizing: "border-box", outline: "none",
              }}
            />
          </div>

          <div className="vk-stage">
            <button
              className="vk-rec"
              onClick={() => onStart(source, context || undefined)}
              aria-label="Avvia registrazione"
            >
              <VkIcon.mic />
            </button>
            <div className="vk-rec-label">Avvia registrazione</div>
            <div className="vk-rec-sub">
              premi <kbd>{modKey}</kbd><kbd>R</kbd> o clicca il pulsante
            </div>
            <div className="vk-wave" aria-hidden="true">
              {HOME_BARS.map((h, i) => (
                <i key={i} style={{ height: h + "px", "--i": i } as React.CSSProperties}></i>
              ))}
            </div>
          </div>

          <div
            className="vk-drop"
            role="button"
            tabIndex={0}
            onClick={onImport}
            onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") onImport(); }}
          >
            <span className="ar">↧</span>
            <span><b>Trascina o clicca per importare un file audio</b></span>
            <span className="ext">.mp3 .wav .m4a .flac</span>
          </div>

          <div className="vk-con-foot">
            <span className="ok"><span className="dot"></span>locale · offline · privato</span>
            <span className="model">{whisperModel || "large-v3-turbo"} · on-device</span>
          </div>
        </div>

        {/* ── Output preview / Sessioni recenti ── */}
        <div className="vk-output">
          {hasBriefing ? (
            <>
              <div className="vk-tabs">
                {(["briefing.md", "recap.md", "obsidian/"] as const).map((t) => {
                  const disabled = t !== "briefing.md";
                  return (
                    <button
                      key={t}
                      className={tab === t ? "on" : ""}
                      disabled={disabled}
                      title={disabled ? "In arrivo" : undefined}
                      onClick={() => !disabled && setTab(t)}
                    >
                      {t}
                    </button>
                  );
                })}
              </div>

              <div className="vk-doc fade">
                <MarkdownDoc md={lastArtifacts!.briefingMd} />
              </div>

              <div className="vk-out-act">
                <button
                  className="vk-btn-g"
                  title="Copia il briefing negli appunti: incollalo in ChatGPT, Claude o un'altra AI"
                  onClick={() => void navigator.clipboard?.writeText(lastArtifacts!.briefingMd)}
                >
                  <VkIcon.arrow />
                  Copia il briefing per la tua AI
                </button>
              </div>
            </>
          ) : (
            <div className="vk-onb">
              <div className="vk-onb-kick">La tua configurazione</div>
              <h2>Pronto al primo briefing</h2>
              <p className="vk-onb-lead">
                Non hai ancora registrato nulla. Tre passi e avrai il tuo primo documento pronto per l&apos;AI.
              </p>
              <div className="vk-onb-steps">
                {ONB_STEPS.map((s, i) => (
                  <div className="vk-onb-step" key={i}>
                    <span className="n">{i + 1}</span>
                    <div>
                      <div className="tt">{s.tt}</div>
                      <div className="dd">{s.dd}</div>
                    </div>
                  </div>
                ))}
              </div>
              <div className="vk-onb-assure">
                <span className="dot"></span>
                Tutto resta sul tuo PC — l&apos;audio non lascia mai il dispositivo.
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}

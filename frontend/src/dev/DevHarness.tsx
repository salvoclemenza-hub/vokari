// Harness di rifinitura visiva (DEV-only). Monta ogni schermata/stato con dati
// finti (fixtures.ts) dentro la chrome reale (AppFrame), pixel-identico all'app.
// Routing via query string: ?screen=<id>&state=<id>. Senza screen → indice DEV.
//
// Guardia: importato solo dietro `import.meta.env.DEV` in main.tsx → il bundle di
// produzione non lo include (verificare con un grep su dist/).

import { useEffect, useRef, useState, type ReactNode } from "react";
import { AppFrame } from "../chrome/AppFrame";
import { Toaster } from "../chrome/Toaster";
import { ConfirmHost } from "../chrome/ConfirmHost";
import { WhatsNew } from "../chrome/WhatsNew";
import type { ChangelogEntry } from "../bridge";
import type { NavItem } from "../chrome/Sidebar";
import { toast } from "../toast";
import { confirmDialog, promptDialog } from "../confirm";
import { ScreenHome } from "../screens/Home";
import { ScreenLive } from "../screens/Live";
import { ScreenProcessing } from "../screens/Processing";
import { ScreenInterview } from "../screens/Interview";
import { ScreenTranscriptReview } from "../screens/TranscriptReview";
import { ScreenArtifacts } from "../screens/Artifacts";
import { ScreenSettings } from "../screens/Settings";
import { ScreenSessions } from "../screens/Sessions";
import { ScreenModels } from "../screens/Models";
import { ScreenError } from "../screens/ErrorScreen";
import { ScreenOnboarding } from "../screens/Onboarding";
import { installMockApi, setDevFlags } from "./mockApi";
import * as fx from "./fixtures";

installMockApi();

const noop = () => {};

// Voci finte per rifinire il popup "Novità della versione" (Tema 2).
const DEV_CHANGELOG: ChangelogEntry[] = [
  {
    version: "0.1.2", date: "2026-06-25", title: "Benvenuto guidato e modelli più chiari",
    highlights: [
      { kind: "feature", text: "Wizard di benvenuto al primo avvio: configuri cervello AI e modello passo dopo passo." },
      { kind: "feature", text: "Questa finestra: dopo ogni aggiornamento vedi cosa è cambiato." },
      { kind: "fix", text: "La schermata Modelli AI non mostra più \"Attivo\" un modello solo selezionato ma non scaricato." },
      { kind: "fix", text: "Lo stato di Ollama distingue \"installato ma fermo\" da \"non installato\"." },
    ],
  },
  {
    version: "0.1.1", date: "2026-06-20", title: "Primo pacchetto distribuibile",
    highlights: [
      { kind: "feature", text: "Pacchetto di installazione per Windows, nessuna configurazione manuale." },
      { kind: "improvement", text: "Avvisi più onesti sulla lingua rilevata nell'audio." },
    ],
  },
];

// Schermate "reali" (renderizzabili come corpo) vs voci solo-harness (pills/feedback) che
// sono overlay/eventi da mostrare SOPRA una schermata reale (dove avvengono davvero).
type RealScreen =
  | "home" | "live" | "processing" | "interview" | "artifacts"
  | "settings" | "sessions" | "models" | "error" | "onboarding" | "transcript_review";
type Screen = RealScreen | "pills" | "feedback" | "whatsnew";

const NAV_FOR: Record<Screen, NavItem> = {
  home: "Registra", live: "Registra", processing: "Registra", interview: "Registra",
  error: "Registra", pills: "Registra", feedback: "Registra", onboarding: "Registra",
  whatsnew: "Registra", transcript_review: "Registra",
  artifacts: "Sessioni", sessions: "Sessioni",
  models: "Modelli AI", settings: "Impostazioni",
};

/** Pills e feedback sono overlay/eventi: si testano SOPRA la schermata reale dove
 *  compaiono (non sopra l'indice dev). Mappa stato → (schermata di sfondo, stato). */
const PILL_BG: Record<string, { screen: RealScreen; state: string }> = {
  resume: { screen: "sessions", state: "list" },   // job in corso mentre sfogli la libreria
  download: { screen: "models", state: "default" }, // download avviato dai Modelli
  both: { screen: "models", state: "default" },     // download + job che riprende
};

const FEEDBACK: Record<string, { screen: RealScreen; state: string; fire: () => void }> = {
  "toast-success": { screen: "artifacts", state: "default",
    fire: () => toast("Copiato ✓ — incollalo nella tua AI", "success") },           // copia briefing
  "toast-info": { screen: "processing", state: "transcribing",
    fire: () => toast("Sto elaborando…", "info") },
  "toast-error": { screen: "artifacts", state: "default",
    fire: () => toast("Esportazione Obsidian non riuscita: vault non configurato", "error") }, // export
  "confirm": { screen: "sessions", state: "list",
    fire: () => void confirmDialog({ title: "Eliminare la sessione?", message: "L'operazione non è reversibile.", confirmLabel: "Elimina", danger: true }) },
  "prompt": { screen: "home", state: "default",
    fire: () => void promptDialog({ title: "Importa registrazione", message: "Di cosa parla? (opzionale)", placeholder: "es. Riunione produzione" }) },
};

/** Catalogo schermate → stati, per l'indice e la documentazione. */
const CATALOG: { screen: Screen; states: string[]; note?: string }[] = [
  { screen: "onboarding", states: ["welcome", "brain", "model", "ready"],
    note: "wizard primo avvio (4 passi)" },
  { screen: "processing", states: ["queued", "transcribing", "analyzing", "rendering"],
    note: "priorità #1 — punto di partenza della richiesta" },
  { screen: "home", states: ["with-briefing", "empty"] },
  { screen: "artifacts", states: ["default", "vuoto"] },
  { screen: "sessions", states: ["list", "empty"] },
  { screen: "interview", states: ["default"] },
  { screen: "transcript_review", states: ["default"], note: "rileggi/correggi la trascrizione (N1)" },
  { screen: "live", states: ["both", "mic"] },
  { screen: "models", states: ["default"] },
  { screen: "settings", states: ["default"] },
  { screen: "error", states: ["with-warnings"] },
  { screen: "pills", states: ["resume", "download", "both"],
    note: "overlay sopra la schermata reale dove compaiono" },
  { screen: "feedback", states: ["toast-success", "toast-info", "toast-error", "confirm", "prompt"],
    note: "toast/modali sopra la schermata reale dove avvengono" },
  { screen: "whatsnew", states: ["default"],
    note: "popup 'Novità della versione' dopo un aggiornamento" },
];

type GoFn = (screen: Screen, state: string) => void;

/** Pillole globali (overlay di App): ripresa + download. Replicate qui per rifinirle. */
function DevPills({ state }: { state: string }) {
  const showResume = state === "resume" || state === "both";
  const showDl = state === "download" || state === "both";
  return (
    <div className="vk-pill-stack">
      {showResume && (
        <div className="vk-pillc resume">
          <span className="ic resume"><svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z" /></svg></span>
          <div className="body">
            <div className="tt">Completa la rifinitura</div>
            <div className="sub">Riunione produzione · in sospeso</div>
          </div>
          <button className="act" title="Riprendi"><svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 4l-1.4 1.4L16.2 11H4v2h12.2l-5.6 5.6L12 20l8-8z" /></svg></button>
          <button className="vk-x">✕</button>
        </div>
      )}
      {showDl && (
        <div className="vk-pillc dl">
          <span className="ic dl"><svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 16l-5-5h3V4h4v7h3l-5 5zm-7 2h14v2H5v-2z" /></svg></span>
          <div className="body">
            <div className="tt">large-v3-turbo · scaricando</div>
            <div className="sub">64%</div>
            <div className="vk-pillbar"><i style={{ width: "64%" }} /></div>
          </div>
        </div>
      )}
    </div>
  );
}

function renderBody(screen: RealScreen, state: string): ReactNode {
  switch (screen) {
    case "home":
      return <ScreenHome onStart={noop} onImport={noop}
        lastArtifacts={state === "empty" ? null : fx.sampleArtifacts}
        mode={fx.sampleSettings.defaultMode} onModeChange={noop}
        whisperModel={fx.sampleSettings.whisperModel} context="" onContextChange={noop}
        onOpenSettings={noop} onOpenModels={noop} />;
    case "live":
      return <ScreenLive source={state === "mic" ? "mic" : "both"} title="Riunione produzione"
        onTitleChange={noop} context="scorte, turni e resa M2" onContextChange={noop}
        whisperModel={fx.sampleSettings.whisperModel} livePreviewActive onStop={noop} onCancel={noop} />;
    case "processing": {
      const base = { title: "Riunione produzione · scorte e turni", model: "large-v3-turbo",
        onCancel: noop, onRenameTitle: noop };
      if (state === "queued") return <ScreenProcessing {...base} status="queued" pct={0} />;
      if (state === "transcribing")
        return <ScreenProcessing {...base} status="transcribing" pct={0.42}
          partialText={fx.SAMPLE_PARTIAL_TRANSCRIPT} />;
      if (state === "rendering")
        return <ScreenProcessing {...base} status="rendering" pct={1} />;
      // analyzing (default): timer + analyze_step + anteprima streaming
      return <ScreenProcessing {...base} status="analyzing" pct={1}
        partialText={fx.SAMPLE_TRANSCRIPT}
        analyzeStep={{ step: "questions", label: "Preparo le domande di rifinitura" }}
        analysisPreview={fx.SAMPLE_ANALYSIS_PREVIEW} />;
    }
    case "interview":
      return <ScreenInterview questions={fx.sampleQuestions} onGenerate={noop} onCancel={noop} />;
    case "transcript_review":
      return <ScreenTranscriptReview transcript={fx.SAMPLE_TRANSCRIPT} onProceed={noop} onCancel={noop} />;
    case "artifacts": {
      // "vuoto": recap/obsidian assenti → tab recap disabilitato + invito Obsidian.
      const art = state === "vuoto"
        ? { ...fx.sampleArtifacts, recapMd: "", obsidianNote: "" }
        : fx.sampleArtifacts;
      return <ScreenArtifacts artifacts={art} onCopy={noop} onOpenFolder={noop}
        onExportPdf={noop} onExportObsidian={noop} onDownload={noop} onBack={noop} />;
    }
    case "settings":
      return <ScreenSettings onOpenModels={noop} />;
    case "sessions":
      return <ScreenSessions onOpen={noop} onImport={noop} />;
    case "models":
      return <ScreenModels />;
    case "onboarding":
      // initialStep dal `state` per rifinire ogni passo isolatamente (welcome/brain/model/ready)
      return <ScreenOnboarding onDone={noop} initialStep={{ welcome: 0, brain: 1, model: 2, ready: 3 }[state] ?? 0} />;
    case "error":
      return <ScreenError
        message="Impossibile contattare il modello Ollama (connessione rifiutata su http://localhost:11434). Verifica che Ollama sia avviato."
        warnings={["Cattura 'entrambi' caduta sul solo microfono — l'audio di sistema non è stato catturato"]}
        onRetry={noop} onOpenSettings={noop} onBack={noop} />;
  }
}

/** Avvolge una schermata reale di sfondo e fa partire il feedback (toast/modale) dopo il
 *  mount, così compare SOPRA quella schermata (e non sopra l'indice dev). Il delay garantisce
 *  che Toaster/ConfirmHost si siano già sottoscritti al bus. */
function DevFeedback({ fire, children }: { fire: () => void; children: ReactNode }) {
  useEffect(() => {
    const id = window.setTimeout(fire, 200);
    return () => window.clearTimeout(id);
  }, [fire]);
  return <>{children}</>;
}

function DevIndex({ go }: { go: GoFn }) {
  return (
    <div style={{ padding: "24px 28px", fontFamily: "var(--sans)", color: "var(--ink)", overflow: "auto", height: "100%" }}>
      <div style={{ fontFamily: "var(--mono)", fontSize: 12.5, color: "var(--green-d)", marginBottom: 6 }}>
        ~/dev · harness rifinitura visiva
      </div>
      <h1 style={{ fontFamily: "var(--disp)", fontSize: 28, margin: "0 0 4px" }}>Schermate & stati</h1>
      <p style={{ color: "var(--mut)", fontSize: 14, marginTop: 0 }}>
        Dati finti, nessuna pipeline. URL: <code>?screen=&lt;id&gt;&amp;state=&lt;id&gt;</code>.
        Aggiungi <code>&amp;nav=1</code> per il link di ritorno on-screen.
      </p>
      {CATALOG.map(({ screen, states, note }) => (
        <div key={screen} style={{ marginBottom: 16 }}>
          <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 6 }}>
            {screen}{note && <span style={{ color: "var(--faint)", fontWeight: 400, fontSize: 12.5 }}> — {note}</span>}
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {states.map((st) => (
              <button key={st} className="vk-btn-gh" onClick={() => go(screen, st)}>{st}</button>
            ))}
          </div>
        </div>
      ))}
      <div style={{ marginTop: 24, paddingTop: 16, borderTop: "1px solid var(--line)" }}>
        <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 6 }}>feedback transiente & modali</div>
        <p style={{ color: "var(--mut)", fontSize: 12.5, marginTop: 0, marginBottom: 8 }}>
          Si aprono <b>sopra la schermata reale</b> dove avvengono (artefatti, sessioni, …) — non sopra l'indice dev.
        </p>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          <button className="vk-btn-gh" onClick={() => go("feedback", "toast-success")}>toast success</button>
          <button className="vk-btn-gh" onClick={() => go("feedback", "toast-info")}>toast info</button>
          <button className="vk-btn-gh" onClick={() => go("feedback", "toast-error")}>toast error</button>
          <button className="vk-btn-gh" onClick={() => go("feedback", "confirm")}>confirm</button>
          <button className="vk-btn-gh" onClick={() => go("feedback", "prompt")}>prompt</button>
        </div>
      </div>
    </div>
  );
}

export function DevHarness() {
  // Navigazione SPA (non più reload): così le transizioni di schermata (E1) e lo
  // stagger d'ingresso (FD10) si vedono davvero — utile per la gif di anteprima.
  const initial = new URLSearchParams(location.search);
  const showNav = initial.has("nav");
  const [route, setRoute] = useState<{ screen: Screen | null; state: string }>({
    screen: initial.get("screen") as Screen | null,
    state: initial.get("state") ?? "default",
  });
  const { screen, state } = route;
  const prevRef = useRef<Screen | null>(screen);

  const go: GoFn = (next, st) => {
    const nav = showNav ? "&nav=1" : "";
    history.pushState(null, "", `?screen=${next}&state=${st}${nav}`);
    setRoute({ screen: next, state: st });
  };

  setDevFlags({ emptySessions: state === "empty" });

  // Direzione transizione: avanti nel flusso = da destra, indietro = da sinistra, resto crossfade.
  const FLOW = ["home", "live", "processing", "interview", "artifacts"];
  const prev = prevRef.current;
  let dir = "fade";
  if (prev !== screen && screen) {
    const a = FLOW.indexOf(prev ?? ""); const b = FLOW.indexOf(screen);
    dir = a !== -1 && b !== -1 ? (b > a ? "fwd" : "back") : "fade";
  }
  useEffect(() => { prevRef.current = screen; });

  // pills/feedback non sono schermate "corpo": si renderizzano SOPRA la schermata reale dove
  // avvengono (PILL_BG / FEEDBACK), così i test visivi non hanno l'indice dev come sfondo.
  let body: ReactNode;
  let active: NavItem;
  let frameScreen: RealScreen = "home";
  if (!screen) {
    body = <DevIndex go={go} />;
    active = "Registra";
  } else if (screen === "pills") {
    const bg = PILL_BG[state] ?? PILL_BG.resume;
    frameScreen = bg.screen;
    body = renderBody(bg.screen, bg.state);
    active = NAV_FOR[bg.screen];
  } else if (screen === "feedback") {
    const fb = FEEDBACK[state] ?? FEEDBACK["toast-success"];
    frameScreen = fb.screen;
    body = <DevFeedback fire={fb.fire}>{renderBody(fb.screen, fb.state)}</DevFeedback>;
    active = NAV_FOR[fb.screen];
  } else if (screen === "whatsnew") {
    // popup novità: overlay sopra la Home (come avviene davvero dopo un aggiornamento)
    frameScreen = "home";
    body = renderBody("home", "with-briefing");
    active = "Registra";
  } else {
    frameScreen = screen;
    body = renderBody(screen, state);
    active = NAV_FOR[screen];
  }

  return (
    <>
      <AppFrame active={active} screen={frameScreen} onNavigate={(n) => { const t = Object.entries(NAV_FOR).find(([, v]) => v === n)?.[0] as Screen; if (t) go(t, "default"); }}
        onOpenSession={() => go("artifacts", "default")} appInfo={fx.sampleAppInfo} resources={fx.sampleResources}
        bare={frameScreen === "onboarding"}>
        <div key={(screen ?? "index") + state} className={"vk-screen-anim " + dir}>
          {body}
        </div>
      </AppFrame>
      {screen === "pills" && <DevPills state={state} />}
      {screen === "whatsnew" && (
        <WhatsNew entries={DEV_CHANGELOG} currentVersion="0.1.2" onClose={() => go("home", "with-briefing")} />
      )}
      {showNav && (
        <button onClick={() => { history.pushState(null, "", "?nav=1"); setRoute({ screen: null, state: "default" }); }} title="Torna all'indice DEV"
          style={{ position: "fixed", top: 6, left: "50%", transform: "translateX(-50%)", zIndex: 9999,
            fontSize: 11, fontFamily: "var(--mono)", padding: "2px 10px", borderRadius: 999,
            background: "var(--ink)", color: "#fff", border: "none", cursor: "pointer", opacity: 0.7 }}>
          ≡ dev
        </button>
      )}
      <Toaster />
      <ConfirmHost />
    </>
  );
}

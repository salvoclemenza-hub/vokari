import { useEffect, useRef, useState } from "react";
import { bridge, getAppInfo, onVokariEvent, type AppInfo, type AnalysisFit, type Artifacts, type ChangelogResult, type JobView, type ResourceUsage } from "./bridge";
import { AppFrame } from "./chrome/AppFrame";
import { Banner } from "./chrome/Banner";
import { Toaster } from "./chrome/Toaster";
import { ConfirmHost } from "./chrome/ConfirmHost";
import { WhatsNew } from "./chrome/WhatsNew";
import { toast } from "./toast";
import { confirmDialog, importDialog } from "./confirm";
import { initNotifications, notifyComplete } from "./notify";
import type { NavItem } from "./chrome/Sidebar";
import { ScreenHome } from "./screens/Home";
import { ScreenLive } from "./screens/Live";
import { ScreenProcessing } from "./screens/Processing";
import { ScreenTranscriptReview } from "./screens/TranscriptReview";
import { ScreenInterview } from "./screens/Interview";
import { ScreenArtifacts } from "./screens/Artifacts";
import { ScreenSettings } from "./screens/Settings";
import { ScreenSessions } from "./screens/Sessions";
import { ScreenModels } from "./screens/Models";
import { ScreenError } from "./screens/ErrorScreen";
import { ScreenOnboarding } from "./screens/Onboarding";
import i18n from "./i18n";

type Screen =
  | "home" | "live" | "processing" | "transcript_review" | "interview" | "artifacts"
  | "settings" | "sessions" | "models" | "error" | "onboarding";

const NAV_FOR: Record<Screen, NavItem> = {
  home: "Registra", live: "Registra", processing: "Registra", transcript_review: "Registra",
  interview: "Registra", error: "Registra",
  onboarding: "Registra",
  artifacts: "Sessioni", sessions: "Sessioni",
  models: "Modelli AI", settings: "Impostazioni",
};

const SCREEN_FOR_NAV: Record<NavItem, Screen> = {
  Registra: "home", Sessioni: "sessions", "Modelli AI": "models", Impostazioni: "settings",
};

const FALLBACK: AppInfo = { version: "dev", license: "MIT", githubStars: 0, platform: "windows", systemAudioSupported: true };

export default function App() {
  const [screen, setScreen] = useState<Screen>("home");
  const [appInfo, setAppInfo] = useState<AppInfo>(FALLBACK);
  const [job, setJob] = useState<JobView | null>(null);
  const [artifacts, setArtifacts] = useState<Artifacts | null>(null);
  const [errorMsg, setErrorMsg] = useState<string>("");
  const [warnings, setWarnings] = useState<string[]>([]);
  const [recSource, setRecSource] = useState<"mic" | "system" | "both">("both");
  const [recMode, setRecMode] = useState<string>("solo");
  const [recWhisper, setRecWhisper] = useState<string>("");
  const [sessionTitle, setSessionTitle] = useState<string>("");
  const [recContext, setRecContext] = useState<string>("");
  const [lastArtifacts, setLastArtifacts] = useState<Artifacts | null>(null);
  const [needsApiKey, setNeedsApiKey] = useState(false);
  const [needsModel, setNeedsModel] = useState(false);
  const [dl, setDl] = useState<{ name: string; pct: number | null } | null>(null);
  const [resources, setResources] = useState<ResourceUsage | null>(null);
  // Anteprima live realmente attiva = live_preview ON e live_model ≠ whisper_model (deve
  // combaciare col gating backend in api.start_recording). Snapshot al mount (v1).
  const [livePreviewActive, setLivePreviewActive] = useState(false);
  const [fromCache, setFromCache] = useState(false);
  const [analyzeStep, setAnalyzeStep] = useState<{ step: string; label: string } | null>(null);
  const [analysisPreview, setAnalysisPreview] = useState<string>("");
  const [analysisFit, setAnalysisFit] = useState<AnalysisFit | null>(null);
  // Tema 2: novità della versione da mostrare dopo un aggiornamento (null = nessun popup).
  const [changelog, setChangelog] = useState<ChangelogResult | null>(null);
  const jobIdRef = useRef<string>("");
  // Azione di recupero per la schermata errore ("Riprova"): impostata da fail() solo dove
  // un retry è ben definito (start/import/generate). null dove non è ripetibile (es. errore
  // pipeline a job già azzerato, stop con audio perso) → il bottone Riprova non compare.
  const retryRef = useRef<(() => void) | null>(null);
  // Schermata precedente, per scegliere la direzione della transizione (E1).
  const prevScreenRef = useRef<Screen>("home");
  // A1: un job in elaborazione ritrovato all'avvio (tipicamente dopo un crash, non una
  // chiusura pulita che ora lo abbandona) NON va auto-ripreso (ripartirebbe da zero):
  // la ripresa è esplicita al click della pill.
  const resumeNeededRef = useRef(false);

  function fail(message: string, retry: (() => void) | null = null) {
    retryRef.current = retry;   // null = nessun "Riprova" (default): mostra solo le uscite sicure
    setErrorMsg(message || "Errore sconosciuto");
    setScreen("error");
  }

  useEffect(() => {
    getAppInfo().then(setAppInfo);
    bridge.getSettings().then((s) => {
      void i18n.changeLanguage(s.appLanguage || "it"); // Tema 3: applica la lingua salvata
      setRecMode(s.defaultMode || "solo");
      setRecWhisper(s.whisperModel || "");
      setLivePreviewActive(s.livePreview && s.liveModel !== s.whisperModel);
      // Onboarding: con brain Claude serve la chiave; Ollama no (offline, nessuna chiave).
      setNeedsApiKey(s.brain === "claude" && !s.hasApiKey);
      // Primo avvio: mostra il wizard di benvenuto finché non è stato completato (B4).
      // Mutua esclusione col popup "Novità": chi non ha ancora onboardato vede solo il wizard.
      if (!s.onboarded) {
        setScreen("onboarding");
      } else {
        // Tema 2: dopo un aggiornamento, mostra le novità non ancora viste. Il backend filtra
        // per versione (entries vuote = già viste o build dev/browser) → niente popup in quei casi.
        void bridge.getChangelog(s.lastSeenVersion).then((cl) => {
          if (cl.entries.length > 0) setChangelog(cl);
        });
      }
    });
    // Onboarding: serve almeno un modello Whisper scaricato/attivo per trascrivere.
    bridge.listModels().then((ms) => {
      setNeedsModel(ms.length > 0 && !ms.some((m) => m.state === "active" || m.state === "downloaded"));
    });
    bridge.getActiveJob().then((j) => {
      if (!j) return;
      // Un job 'queued' (finalizzazione audio post-Stop) ritrovato all'avvio = chiusura
      // imprevista durante la finalizzazione: l'audio temporaneo è perso e non è
      // ripristinabile. Marcalo terminale e avvisa, invece di lasciare una pill morta.
      if (j.status === "queued") {
        void bridge.cancelJob(j.jobId);
        toast("Una registrazione non è stata finalizzata (chiusura imprevista).", "info");
        return;
      }
      jobIdRef.current = j.jobId;
      setJob(j);
      // All'avvio NON forziamo la schermata né auto-riprendiamo l'elaborazione (A1):
      // restiamo su `home` e offriamo la ripresa con la pill. Senza cache parziale una
      // ripresa automatica ricomincerebbe da 0 ("al riavvio sta ancora elaborando").
      // NB: 'queued' è escluso di proposito — un job fermo a 'queued' (crash durante la
      // finalizzazione audio) non è ripristinabile (il temp audio è perso) e resume_job
      // non lo rilancia: niente pill morta.
      if (["transcribing", "analyzing", "rendering"].includes(j.status)) {
        resumeNeededRef.current = true;   // ripresa solo se l'utente clicca la pill
      }
    });
    const off = onVokariEvent((event, payload) => {
      if (event === "warning") {
        setWarnings((payload.messages as string[]) ?? []);
        return;
      }
      if (event === "resource_usage") {
        // Indicatore globale CPU/RAM nella status bar (nessun jobId associato).
        setResources({
          cpu: payload.cpu as number,
          ramMb: payload.ramMb as number,
          tempC: typeof payload.tempC === "number" ? payload.tempC : undefined,
        });
        return;
      }
      if (event === "model_download") {
        // Download modello: indicatore globale che resta visibile cambiando schermata.
        const st = payload.status as string;
        if (st === "start") setDl({ name: String(payload.name), pct: null });
        else if (st === "progress") {
          const p = typeof payload.pct === "number" ? payload.pct : null;
          setDl((cur) => (cur ? { ...cur, pct: p } : { name: String(payload.name), pct: p }));
        } else if (st === "done" || st === "error") setDl(null);
        return;
      }
      if (payload.jobId !== jobIdRef.current) return;
      if (event === "analyze_step") {
        // Substep dell'analisi (es. "verify", "questions") per il label nella Processing.
        setAnalyzeStep({
          step: String(payload.step),
          label: String(payload.label),
        });
        return;
      }
      if (event === "analysis_preview") {
        // Anteprima testuale leggibile del JSON parziale durante lo streaming dell'analisi.
        setAnalysisPreview(String(payload.text ?? ""));
        return;
      }
      if (event === "analysis_fit") {
        // Idoneità trascrizione↔modello (ADR-041): badge persistente in Processing. Il dato
        // strutturato resta finché dura l'elaborazione (lo azzeriamo all'avvio di un nuovo job
        // e all'uscita verso ready/cancelled/error, come gli altri state d'analisi).
        setAnalysisFit({
          jobId: String(payload.jobId),
          level: payload.level as AnalysisFit["level"],
          tokensEst: Number(payload.tokensEst ?? 0),
          ctxMax: Number(payload.ctxMax ?? 0),
          budget: Number(payload.budget ?? 0),
          nChunks: Number(payload.nChunks ?? 0),
          ctxIsFallback: Boolean(payload.ctxIsFallback),
          recommendation: String(payload.recommendation ?? ""),
        });
        return;
      }
      if (event === "transcribe_progress") {
        if (payload.fromCache) setFromCache(true);
        setJob((cur) => cur ? { ...cur, pct: payload.pct as number, partialText: payload.text as string } : cur);
      }
      if (event === "status") {
        const status = payload.status as JobView["status"];
        if (status !== "transcribing") setFromCache(false);
        // Resetta i state dell'analisi quando si esce dalla fase analyzing/rendering
        if (!["analyzing", "rendering"].includes(status)) {
          setAnalyzeStep(null);
          setAnalysisPreview("");
        }
        if (status === "error") {
          notifyComplete("VOKARI", "Elaborazione non riuscita");
          if (document.hidden) void bridge.flashTaskbar();
          // M1: error è terminale come cancelled → azzera il job così la pill di ripresa
          // ("Elaborazione in corso… →") non resta fantasma sulla schermata di errore.
          const failedId = jobIdRef.current;
          jobIdRef.current = "";
          setJob(null);
          setAnalysisFit(null);
          // "Riprova" SENZA re-importare l'audio né re-inserire il contesto: resume_job riparte
          // dall'analisi riusando la trascrizione salvata sul job (persistita PRIMA dell'analisi)
          // — il contesto resta sul job. Ripristina jobIdRef così gli eventi 'status' del retry
          // trovano il job. Caso reale: crash analisi su entità fuori-enum (bug 2026-06-30).
          const retry = failedId
            ? () => { jobIdRef.current = failedId; setScreen("processing"); void bridge.resumeJob(failedId); }
            : null;
          fail((payload.error as string) ?? "", retry);
          return;
        }
        if (status === "cancelled") {
          jobIdRef.current = "";
          setJob(null);
          setAnalysisFit(null);
          setScreen("home");
          return;
        }
        bridge.getJob(jobIdRef.current).then((j) => {
          if (j) setJob(j);
          // N1: naviga alla revisione DOPO aver caricato il job (getJob è async) così la textarea
          // monta con il transcript GIÀ presente — navigando prima mostrerebbe la box vuota fino
          // alla risoluzione (race documentata in CLAUDE.md). Il sync nel componente è la difesa.
          if (status === "awaiting_edit") setScreen("transcript_review");
        });
        if (status === "awaiting_interview") setScreen("interview");
        if (status === "awaiting_fit_decision") setScreen("processing");
        if (status === "ready") {
          notifyComplete("VOKARI", "Briefing pronto ✓");
          if (document.hidden) void bridge.flashTaskbar();
          void openArtifacts(jobIdRef.current);
        }
      }
    });
    return off;
  }, []);

  // Titolo finestra dinamico (round 2 F4): rende leggibili Alt-Tab e taskbar Windows.
  useEffect(() => {
    const names: Record<Screen, string> = {
      home: "Registra", live: "Registrazione", processing: "Elaborazione",
      transcript_review: "Revisione trascrizione",
      interview: "Rifinitura", artifacts: artifacts?.title || "Sessione",
      settings: "Impostazioni", sessions: "Sessioni", models: "Modelli AI", error: "Errore",
      onboarding: "Benvenuto",
    };
    document.title = `VOKARI — ${names[screen]}`;
  }, [screen, artifacts]);

  // Aggiorna la schermata precedente DOPO ogni render: alla navigazione successiva
  // transitionDir confronta la nuova schermata con questa.
  useEffect(() => { prevScreenRef.current = screen; });

  async function openArtifacts(jobId: string) {
    const art = await bridge.getArtifacts(jobId);
    setArtifacts(art);
    if (art) setLastArtifacts(art);
    setScreen("artifacts");
  }

  async function openSession(sessionId: string) {
    const art = await bridge.openSession(sessionId);
    if (art) {
      // session.id == job.id: punta il ref al job persistito così
      // exportPdf/exportObsidian(jobIdRef.current) ritrovano il job su disco.
      jobIdRef.current = sessionId;
      setArtifacts(art);
      setLastArtifacts(art);
      setScreen("artifacts");
    }
  }

  // Completamento (o salto) del wizard di primo avvio: segna onboarded=true, ricarica i flag
  // di configurazione (il wizard può aver impostato chiave/brain/modello) e va alla Home.
  async function finishOnboarding() {
    try {
      // Segna anche la versione corrente come "novità già viste": chi completa ora l'onboarding
      // su questa versione non deve rivedere il changelog di ciò che ha appena installato.
      await bridge.saveSettings({ onboarded: true, lastSeenVersion: appInfo.version });
      const s = await bridge.getSettings();
      setRecWhisper(s.whisperModel || "");
      setNeedsApiKey(s.brain === "claude" && !s.hasApiKey);
      const ms = await bridge.listModels();
      setNeedsModel(ms.length > 0 && !ms.some((m) => m.state === "active" || m.state === "downloaded"));
    } catch {
      /* non bloccare l'uscita dal wizard su un errore di salvataggio */
    }
    setScreen("home");
  }

  async function handleStart(source: "mic" | "system" | "both", context?: string) {
    try {
      setWarnings([]);                  // niente warning stantii della sessione precedente (M6)
      setRecSource(source);
      setSessionTitle("");              // nuova sessione: titolo da compilare in Live
      setRecContext(context || "");     // context opzionale dalla Home
      await bridge.startRecording(source);
      setScreen("live");
    } catch (e) {
      fail(String(e), () => void handleStart(source, context));
    }
  }

  async function handleImport() {
    try {
      const { path } = await bridge.browseAudioFile();
      if (!path) return;
      const fileName = path.split(/[\\/]/).pop() || path;
      // MDL2: dialog di import arricchito — durata/peso reali (probe ffprobe; 0 se ignoti →
      // non mostrati) + selettore tipo solo/riunione (init da recMode) + contesto.
      const meta = await bridge.probeAudio(path);
      const res = await importDialog({
        fileName,
        durationS: meta.durationS,
        sizeBytes: meta.sizeBytes,
        defaultMode: recMode,
        defaultContext: recContext,
      });
      if (res === null) return;            // Annulla → non importare
      setRecMode(res.mode);                // ricorda il tipo scelto
      setRecContext(res.context);
      setWarnings([]);
      setAnalysisFit(null);             // nuovo job → niente badge idoneità stantio del precedente
      initNotifications();              // operazione lunga: prepara il richiamo a fine elaborazione
      const imp = await bridge.importFile(path, res.mode, undefined, res.context || undefined);
      if (imp.error) { toast(imp.error, "error"); return; }   // gate backend: file mancante/vuoto
      if (!imp.jobId) return;
      jobIdRef.current = imp.jobId;
      // Pulisce il job precedente prima di navigare: evita che partialText della sessione
      // precedente venga mostrato nella console di Processing (il componente riceve il
      // vecchio job?.partialText se non viene resettato qui, come handleStop fa con il placeholder).
      const fresh = await bridge.getJob(imp.jobId);
      setJob(fresh);
      setScreen("processing");
    } catch (e) {
      fail(String(e), () => void handleImport());
    }
  }

  async function handleStop() {
    try {
      setWarnings([]);
      setAnalysisFit(null);             // nuovo job → niente badge idoneità stantio del precedente
      initNotifications();
      const res = await bridge.stopRecording(recMode, sessionTitle || undefined, recContext || undefined);
      if (res.error) { fail(res.error); return; }
      jobIdRef.current = res.jobId;
      // Mostra subito lo stato 'queued' ("Finalizzo la registrazione…"): la finalizzazione
      // audio (normalizzazione+mix) gira in un thread daemon e il primo evento 'transcribing'
      // arriva dopo. Senza, Processing partirebbe col default 'transcribing' (fuorviante).
      setJob({
        jobId: res.jobId, title: sessionTitle || "", status: "queued", pct: 0,
        source: recSource, mode: recMode, model: recWhisper, language: "",
        partialText: "", transcript: "", durationS: 0, questions: [], markers: [],
        briefingMd: "", briefingPath: "", draftBriefing: "", error: "",
      });
      setScreen("processing");
    } catch (e) {
      fail(String(e));
    }
  }

  async function handleCancel() {
    await bridge.cancelRecording();
    setScreen("home");
  }

  async function handleResolveFit(decision: "proceed" | "cancel") {
    // proceed → il backend riprende la pipeline ed emette gli status; cancel → emette
    // status=cancelled (gestito dal listener: azzera job + torna a home). Niente da fare qui.
    await bridge.resolveFit(jobIdRef.current, decision);
  }

  async function handleNavigate(n: NavItem) {
    // Navigare via da Live (sidebar o ingranaggio titlebar) lascerebbe la registrazione
    // orfana (mic attivo, nessun modo di fermarla). Chiedi conferma e annulla prima di uscire.
    if (screen === "live") {
      const ok = await confirmDialog({
        title: "Uscire dalla registrazione?",
        message: "La registrazione in corso verrà annullata e l'audio andrà perso.",
        confirmLabel: "Esci e annulla", cancelLabel: "Continua a registrare", danger: true,
      });
      if (!ok) return;
      await bridge.cancelRecording();
    }
    setScreen(SCREEN_FOR_NAV[n]);
  }

  function handleCancelJob() {
    const id = jobIdRef.current;
    jobIdRef.current = "";   // gli eventi residui del job non passano più il filtro
    setJob(null);            // niente job → niente pill di ripresa
    setAnalysisFit(null);
    setScreen("home");
    if (id) void bridge.cancelJob(id);
  }

  async function handleGenerate(answers: Record<string, string>, skipped: string[], extraContext = "") {
    setScreen("processing");
    try {
      // generate() ora gira off-thread (C1) e ritorna SUBITO il job pre-generazione:
      // le transizioni analyzing→rendering→ready / error arrivano via evento `status`.
      const j = await bridge.generate(jobIdRef.current, answers, skipped, extraContext);
      if (!j) { fail("Job non trovato: impossibile generare il briefing."); return; }
      setJob(j);
    } catch (e) {
      fail(String(e), () => void handleGenerate(answers, skipped, extraContext));
    }
  }

  // N1: l'utente ha corretto la trascrizione e clicca "Procedi" → salva l'edit e riprende la
  // pipeline (skip_transcribe lato backend) verso l'analisi. Le transizioni arrivano via evento
  // `status` (analyzing→…→awaiting_interview), come per generate(). Mostriamo subito Processing.
  async function handleProceedEdit(text: string) {
    setScreen("processing");
    try {
      const res = await bridge.updateTranscript(jobIdRef.current, text);
      if (res.error) { fail(res.error, () => void handleProceedEdit(text)); return; }
      await bridge.resumeJob(jobIdRef.current);
    } catch (e) {
      fail(String(e), () => void handleProceedEdit(text));
    }
  }

  // N1: "Annulla" al gate editing → conferma (l'audio/trascrizione vanno persi) e scarta il job.
  async function handleCancelEdit() {
    const ok = await confirmDialog({
      title: i18n.t("transcriptReview.cancelConfirmTitle"),
      message: i18n.t("transcriptReview.cancelConfirmMsg"),
      confirmLabel: i18n.t("transcriptReview.cancelConfirmYes"),
      cancelLabel: i18n.t("transcriptReview.cancelConfirmNo"),
      danger: true,
    });
    if (!ok) return;
    handleCancelJob();
  }

  function copy(md: string) {
    if (!navigator.clipboard) { toast("Copia non disponibile in questo contesto", "error"); return; }
    navigator.clipboard.writeText(md).then(
      () => toast("Copiato ✓ — incollalo nella tua AI", "success"),
      () => toast("Copia negli appunti non riuscita", "error"),
    );
  }

  // Indicatore globale: un job è in corso (o attende la rifinitura) ma non siamo sulle
  // schermate di flusso → pill cliccabile per riprenderlo (prima il job spariva dalla vista,
  // o all'avvio veniva forzata la schermata dell'intervista).
  const RESUMABLE: Partial<Record<JobView["status"], { title: string; screen: Screen }>> = {
    transcribing: { title: "Elaborazione in corso…", screen: "processing" },
    analyzing: { title: "Elaborazione in corso…", screen: "processing" },
    rendering: { title: "Elaborazione in corso…", screen: "processing" },
    awaiting_edit: { title: "Rivedi la trascrizione", screen: "transcript_review" },
    awaiting_interview: { title: "Completa la rifinitura", screen: "interview" },
    awaiting_fit_decision: { title: "Decisione richiesta…", screen: "processing" },
  };
  const resume =
    job && !["processing", "live", "interview", "transcript_review"].includes(screen)
      ? RESUMABLE[job.status]
      : undefined;

  // Transizione di schermata direzionale (E1/round 2): avanzare nel flusso entra da
  // destra, tornare da sinistra, cambio di sezione = crossfade. Il movimento È
  // wayfinding nel single-window. prefers-reduced-motion onorato nel CSS.
  const FLOW_ORDER: Screen[] = ["home", "live", "processing", "transcript_review", "interview", "artifacts"];
  const prevScreen = prevScreenRef.current;
  let transitionDir = "fade";
  if (prevScreen !== screen) {
    const a = FLOW_ORDER.indexOf(prevScreen);
    const b = FLOW_ORDER.indexOf(screen);
    transitionDir = a !== -1 && b !== -1 ? (b > a ? "fwd" : "back") : "fade";
  }

  const body = {
    home: <ScreenHome onStart={(s, c) => void handleStart(s, c)} onImport={() => void handleImport()}
                      lastArtifacts={lastArtifacts} mode={recMode} onModeChange={setRecMode}
                      whisperModel={recWhisper} needsApiKey={needsApiKey} needsModel={needsModel}
                      context={recContext} onContextChange={setRecContext}
                      systemAudioSupported={appInfo.systemAudioSupported}
                      onOpenSettings={() => setScreen("settings")} onOpenModels={() => setScreen("models")} />,
    live: <ScreenLive source={recSource} title={sessionTitle} onTitleChange={setSessionTitle}
                      context={recContext} onContextChange={setRecContext}
                      whisperModel={recWhisper} livePreviewActive={livePreviewActive}
                      onStop={() => void handleStop()} onCancel={() => void handleCancel()} />,
    processing: <ScreenProcessing status={job?.status ?? "transcribing"} pct={job?.pct ?? 0}
                                  partialText={job?.partialText ?? ""} model={job?.model}
                                  title={job?.title ?? ""}
                                  fromCache={fromCache}
                                  analyzeStep={analyzeStep}
                                  analysisPreview={analysisPreview}
                                  analysisFit={analysisFit}
                                  onRielabora={job ? () => { void bridge.invalidateTranscriptCache(job.jobId); } : undefined}
                                  onRenameTitle={(t) => void bridge.renameJob(jobIdRef.current, t)}
                                  onCancel={() => handleCancelJob()}
                                  onResolveFit={(d) => void handleResolveFit(d)}
                                  onOpenSettings={() => setScreen("settings")} />,
    transcript_review: <ScreenTranscriptReview transcript={job?.transcript ?? ""}
                                onProceed={(text) => void handleProceedEdit(text)}
                                onCancel={() => void handleCancelEdit()} />,
    interview: <ScreenInterview questions={job?.questions ?? []} draftBriefing={job?.draftBriefing ?? ""}
                                onGenerate={(a, s, c) => void handleGenerate(a, s, c)}
                                onCancel={() => handleCancelJob()} />,
    artifacts: <ScreenArtifacts artifacts={artifacts ?? undefined} onCopy={copy}
                                onOpenFolder={(p) => void bridge.openFolder(p)}
                                onExportPdf={() => bridge.exportPdf(jobIdRef.current)}
                                onExportObsidian={() => bridge.exportObsidian(jobIdRef.current)}
                                onDownload={(name, content) => bridge.saveTextFile(content, name)}
                                onReexport={async () => {
                                  const r = await bridge.reexportSession(jobIdRef.current);
                                  if (r.ok) {
                                    const art = await bridge.openSession(jobIdRef.current);
                                    if (art) setArtifacts(art);
                                  }
                                  return r;
                                }}
                                onBack={() => setScreen("sessions")} />,
    settings: <ScreenSettings onOpenModels={() => setScreen("models")} />,
    sessions: <ScreenSessions
                onOpen={(id) => void openSession(id)}
                onImport={() => void handleImport()} />,
    models: <ScreenModels />,
    onboarding: <ScreenOnboarding onDone={() => void finishOnboarding()} />,
    error: <ScreenError message={errorMsg} warnings={warnings}
                        onRetry={retryRef.current ?? undefined}
                        onOpenSettings={() => { setWarnings([]); setScreen("settings"); }}
                        onBack={() => { setWarnings([]); setScreen("home"); }} />,
  }[screen];

  return (
    <>
    <AppFrame active={NAV_FOR[screen]} screen={screen} onNavigate={(n) => void handleNavigate(n)}
              onOpenSession={(id) => void openSession(id)} appInfo={appInfo} resources={resources}
              bare={screen === "onboarding"}>
      {warnings.length > 0 && screen !== "error" && (
        <Banner kind="warn" onClose={() => setWarnings([])}>
          ⚠ {warnings.join(" · ")}
        </Banner>
      )}
      <div key={screen} className={"vk-screen-anim " + transitionDir}>
        {body}
      </div>
    </AppFrame>
    {(resume || dl) && (
      <div className="vk-pill-stack">
        {resume && (
          <div className="vk-pillc resume">
            <span className="ic resume">
              <svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z" /></svg>
            </span>
            <div className="body">
              <div className="tt">{resume.title}</div>
              <div className="sub">{(job?.title?.trim() || "Sessione") + " · in sospeso"}</div>
            </div>
            <button
              className="act"
              title="Riprendi la sessione in corso"
              onClick={() => {
                // Ripresa esplicita: se il job era in elaborazione e non sta più girando
                // (ritrovato all'avvio dopo un crash), rilancia la pipeline ora (A1).
                if (resumeNeededRef.current && job) {
                  resumeNeededRef.current = false;
                  void bridge.resumeJob(job.jobId);
                }
                setScreen(resume.screen);
              }}
            >
              <svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 4l-1.4 1.4L16.2 11H4v2h12.2l-5.6 5.6L12 20l8-8z" /></svg>
            </button>
            <button
              className="vk-x"
              title="Ignora questa sessione"
              onClick={(e) => {
                e.stopPropagation();
                const id = jobIdRef.current;
                jobIdRef.current = "";
                setJob(null);
                if (id) void bridge.cancelJob(id);
              }}
            >
              ✕
            </button>
          </div>
        )}
        {dl && (
          <div className="vk-pillc dl" title="Download del modello in corso (continua anche cambiando pagina)">
            <span className="ic dl">
              <svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 16l-5-5h3V4h4v7h3l-5 5zm-7 2h14v2H5v-2z" /></svg>
            </span>
            <div className="body">
              <div className="tt">{dl.name} · scaricando</div>
              <div className="sub">{dl.pct !== null ? `${Math.round(dl.pct * 100)}%` : "in corso…"}</div>
              {dl.pct !== null && (
                <div className="vk-pillbar"><i style={{ width: Math.round(dl.pct * 100) + "%" }} /></div>
              )}
            </div>
          </div>
        )}
      </div>
    )}
    <Toaster />
    <ConfirmHost />
    {changelog && (
      <WhatsNew
        entries={changelog.entries}
        currentVersion={changelog.currentVersion}
        onClose={() => {
          // Memorizza la versione vista così il popup non riappare al prossimo avvio.
          void bridge.saveSettings({ lastSeenVersion: changelog.currentVersion });
          setChangelog(null);
        }}
      />
    )}
    </>
  );
}

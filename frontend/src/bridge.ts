export interface AppInfo {
  version: string;
  license: string;
  githubStars: number;
}

/** Uso risorse dello stack VOKARI, spinto periodicamente dal backend via evento push
 *  `resource_usage`. cpu = % della macchina (0..100) usata da VOKARI + figli (Whisper, ffmpeg)
 *  E dai processi Ollama (serve/app/runner del modello, che girano staccati); ramMb = RAM totale
 *  dello stack in MB; tempC = temperatura CPU in °C (solo se il sensore è disponibile). */
export interface ResourceUsage {
  cpu: number;
  ramMb: number;
  tempC?: number;
}

export interface VokariSettings {
  brain: string;
  ollamaEndpoint: string;
  ollamaModel: string;
  whisperModel: string;
  claudeModel: string;
  briefingDir: string;
  obsidianVault: string;
  defaultMode: string;
  transcriptionLanguage: string;
  livePreview: boolean;
  liveModel: string;
  hasApiKey: boolean;
}

/** Impostazioni di default: fallback prima del load e fuori da pywebview (browser/test).
 *  Unica fonte di verità (prima duplicata 4× qui + in Models.tsx/Settings.tsx). */
export const DEFAULT_SETTINGS = {
  brain: "claude", ollamaEndpoint: "http://localhost:11434", ollamaModel: "qwen2.5:7b",
  whisperModel: "large-v3-turbo", claudeModel: "claude-sonnet-4-6",
  briefingDir: "", obsidianVault: "", defaultMode: "solo",
  transcriptionLanguage: "it", livePreview: true, liveModel: "base", hasApiKey: false,
} satisfies VokariSettings;

export interface ModelEntry {
  name: string;
  sizeLabel: string;
  speed: number;
  quality: number;
  languages: string;
  description: string;
  recommended: boolean;
  state: "active" | "downloaded" | "available";
}

export type JobStatus =
  | "queued" | "transcribing" | "analyzing" | "rendering"
  | "awaiting_interview" | "ready" | "error" | "cancelled";

export interface Question {
  id: string;
  text: string;
  priority: string;
  suggestions: string[];
  why?: string; // I1: perché la domanda (rationale); vuoto se l'LLM non l'ha popolato
  fromAudio?: boolean; // I2: nata da un dettaglio della registrazione (vs domanda di metodo)
}

export interface JobView {
  jobId: string;
  title: string;
  status: JobStatus;
  pct: number;
  source: string;
  mode: string;
  model: string;
  language: string;
  partialText: string;
  transcript: string;
  durationS: number;
  questions: Question[];
  markers: { t_ms: number; label: string }[];
  briefingMd: string;
  briefingPath: string;
  error: string;
}

export interface Artifacts {
  title: string;
  briefingMd: string;
  briefingPath: string;
  recapMd: string;
  obsidianNote: string;
  transcriptText: string;
  durationS: number;
  model: string;
  language: string;
  wordCount: number;
}

export interface SessionItem {
  id: string;
  title: string;
  createdAt: string;
  mode: string;
  model: string;
  durationMs: number;
  hasBriefing: boolean;
  hasRecap: boolean;
  hasObsidian: boolean;
  clarCount: number; // S1: marcatori [DA CHIARIRE] residui nel briefing → chip "? N"
  hasAudio: boolean; // S2: file audio locale ancora presente → bottone "Riproduci"
}

export interface ExportResult {
  ok: boolean;
  path?: string;
  count?: number;
  paths?: string[];
  error?: string;
  cancelled?: boolean;
}

export interface LhmStatus {
  installed: boolean;
  running: boolean;
}

export interface OllamaModelEntry {
  name: string;
  sizeLabel: string;
  description: string;
  /** Metadati "scheda modello" (stile Lemonade) per scegliere a colpo d'occhio.
   *  Per i modelli installati fuori dal catalogo curato restano neutri (0/""/[]). */
  speed: number;       // meter 0..3, indicativo su CPU
  quality: number;     // meter 0..3
  params: string;      // es. "7B"
  context: string;     // es. "128K"
  tags: string[];      // es. ["italiano", "JSON"]
  detailUrl: string;   // pagina dettagli del modello (ollama.com/library/…)
  minRamGb: number;    // MOD2: RAM minima stimata in GB (0 = ignota → niente avviso/filtro)
  isInstalled: boolean;
  isActive: boolean;
  recommended: boolean;
}

/** Specifiche hardware (MOD2): RAM totale per gli avvisi di compatibilità modelli.
 *  ramTotalGb = 0 se non rilevabile (psutil assente) → la UI non avvisa né filtra. */
export interface SystemSpecs {
  ramTotalGb: number;
}

/** Riepilogo disco (MOD3): GB occupati dai modelli (Whisper + Ollama) e GB liberi sul drive
 *  dei modelli Whisper. Valori in GB (10^9). 0 se non leggibili. */
export interface DiskUsage {
  usedByModelsGb: number;
  freeGb: number;
}

/** Metadati di un file audio da importare (MDL2). durationS=0 / sizeBytes=0 = ignoto
 *  (il dialog di import mostra solo ciò che conosce, niente valori inventati). */
export interface AudioMeta {
  durationS: number;
  sizeBytes: number;
}

/** Stato runtime di Ollama (per la gestione automatica avvio/installazione dall'app). */
export interface OllamaStatus {
  installed: boolean;   // eseguibile presente (di sistema o bundled in userData)
  running: boolean;     // server raggiungibile sull'endpoint
  bundled: boolean;     // copia gestita da VOKARI in userData/tools/ollama
  canInstall: boolean;  // l'app sa installarlo da sé (oggi: Windows)
  endpoint: string;
}

interface VokariApi {
  get_app_info(): Promise<AppInfo>;
  system_specs(): Promise<SystemSpecs>; // MOD2: RAM totale per compatibilità modelli
  disk_usage(): Promise<DiskUsage>; // MOD3: GB usati dai modelli / liberi
  flash_taskbar(): Promise<{ ok: boolean }>;
  open_url(url: string): Promise<{ ok: boolean }>;
  list_sources(): Promise<{ mic: unknown[]; system: unknown[] }>;
  start_recording(source: string, device?: number | string | null): Promise<{ ok: boolean }>;
  add_marker(label: string): Promise<{ t_ms: number; label: string } | { ok: false }>;
  cancel_recording(): Promise<{ ok: boolean }>;
  pause_recording(): Promise<{ ok: boolean; paused?: boolean }>;
  resume_recording(): Promise<{ ok: boolean; paused?: boolean }>;
  stop_recording(mode?: string, title?: string, context?: string): Promise<{ jobId: string; error?: string }>;
  import_file(path: string, mode?: string, title?: string, context?: string): Promise<{ jobId: string }>;
  get_job(jobId: string): Promise<JobView | null>;
  rename_job(jobId: string, title: string): Promise<{ ok: boolean }>;
  get_active_job(): Promise<JobView | null>;
  resume_job(jobId: string): Promise<JobView | null>;
  cancel_job(jobId: string): Promise<JobView | null>;
  invalidate_transcript_cache(jobId: string): Promise<{ ok: boolean; error?: string }>;
  get_questions(jobId: string): Promise<Question[]>;
  generate(jobId: string, answers: Record<string, string>, skipped: string[]): Promise<JobView | null>;
  get_artifacts(jobId: string): Promise<Artifacts | null>;
  open_folder(path: string): Promise<{ ok: boolean }>;
  browse_audio_file(): Promise<{ path: string }>;
  probe_audio(path: string): Promise<AudioMeta>; // MDL2: durata/peso del file da importare
  // F — Sessions
  list_sessions(): Promise<SessionItem[]>;
  search_sessions(q: string): Promise<SessionItem[]>;
  open_session(id: string): Promise<Artifacts | null>;
  delete_session(id: string): Promise<{ ok: boolean }>;
  delete_sessions(ids: string[]): Promise<{ ok: boolean; deleted: number }>;
  play_session_audio(id: string): Promise<{ ok: boolean; error?: string }>; // S2: apre l'audio nel lettore di sistema
  // H — Export
  export_pdf(jobId: string): Promise<ExportResult>;
  export_obsidian(jobId: string): Promise<ExportResult>;
  save_text_file(content: string, suggestedName: string): Promise<ExportResult>;
  // E — Settings
  get_settings(): Promise<VokariSettings>;
  save_settings(patch: Partial<Omit<VokariSettings, "hasApiKey">>): Promise<VokariSettings>;
  set_api_key(key: string): Promise<{ ok: boolean; hasApiKey: boolean }>;
  delete_api_key(): Promise<{ ok: boolean; hasApiKey: boolean }>; // SET2
  verify_api_key(): Promise<{ ok: boolean; reachable: boolean; error: string }>; // SET1
  browse_folder(): Promise<{ path: string }>;
  // G — Models (Whisper)
  list_models(): Promise<ModelEntry[]>;
  // L'esito reale è asincrono via evento `model_download`; il ritorno è solo {ok}.
  download_model(name: string): Promise<{ ok: boolean }>;
  set_active_model(name: string): Promise<VokariSettings>;
  set_brain(brain: string): Promise<VokariSettings>;
  // G2 — Ollama models (esito pull via evento `ollama_pull`)
  list_ollama_models(): Promise<OllamaModelEntry[]>;
  pull_ollama_model(name: string): Promise<{ ok: boolean }>;
  cancel_ollama_pull(name: string): Promise<{ ok: boolean }>; // MOD1: interrompe il pull in corso (esito via evento `ollama_pull` status=cancelled)
  delete_ollama_model(name: string): Promise<{ ok: boolean }>;
  // G3 — runtime Ollama (avvio/installazione gestiti da VOKARI; install async via evento `ollama_setup`)
  ollama_status(): Promise<OllamaStatus>;
  ollama_start(): Promise<{ ok: boolean; running: boolean }>;
  ollama_stop(): Promise<{ ok: boolean }>;
  ollama_install(): Promise<{ ok: boolean }>;
  // I — LibreHardwareMonitor (telemetria temperatura)
  lhm_status(): Promise<LhmStatus>;
  lhm_install(): Promise<{ ok: boolean }>;
  lhm_start(): Promise<{ ok: boolean }>;
  lhm_stop(): Promise<{ ok: boolean }>;
  lhm_uninstall(): Promise<{ ok: boolean }>;
  lhm_debug(): Promise<{ ok: boolean; stdout?: string; stderr?: string; error?: string }>;
}

type EmitHandler = (event: string, payload: Record<string, unknown>) => void;

/**
 * Payload dell'evento push `analysis_fit` (ADR check idoneità modello): emesso quando la
 * trascrizione NON è ideale per il contesto del modello scelto (verrà riassunta o sfora del
 * tutto). Il messaggio leggibile arriva in parallelo via l'evento `warning` (banner esistente);
 * questa shape è il dato strutturato per un eventuale badge "non ideale per il modello".
 */
export interface AnalysisFit {
  jobId: string;
  level: "summarize" | "over_even_summarized";
  tokensEst: number;
  ctxMax: number;
  budget: number;
  nChunks: number;
  ctxIsFallback: boolean;
  recommendation: string;
}

declare global {
  interface Window {
    pywebview?: { api: VokariApi };
    __vokari_emit?: (event: string, payload: Record<string, unknown>) => void;
    __vokari_handlers?: Set<EmitHandler>;
  }
}

const FALLBACK: AppInfo = { version: "dev", license: "MIT", githubStars: 0 };

/** Timeout oltre il quale assumiamo di girare SENZA pywebview (browser/dev/test)
 *  e usiamo i fallback. In-app pywebview inietta l'api entro ~1s. */
const READY_TIMEOUT_MS = 5000;

function rawApi(): VokariApi | null {
  return window.pywebview?.api ?? null;
}

/**
 * Risolve con l'api appena pywebview la inietta, o con null dopo il timeout.
 *
 * Necessario per la race: React monta e invoca il bridge (es. startRecording
 * della schermata Live) PRIMA che pywebview abbia iniettato window.pywebview.api
 * (~fino a 1s). Senza attesa le prime chiamate cadevano nel `?? fallback` e
 * sparivano in silenzio — registrazione mai avviata, schermata bloccata sulla
 * trascrizione. Attendiamo l'evento `pywebviewready` con un poll di sicurezza.
 */
let readyPromise: Promise<VokariApi | null> | null = null;
function apiReady(): Promise<VokariApi | null> {
  const now = rawApi();
  if (now) return Promise.resolve(now);
  if (!readyPromise) {
    readyPromise = new Promise<VokariApi | null>((resolve) => {
      // settled: la Promise va risolta UNA sola volta. Senza, l'evento `pywebviewready`
      // e il tick del poll possono entrambi chiamare finish() nella stessa coda di
      // microtask (I1); inoltre `pywebviewready` può scattare con l'api non ancora
      // iniettata → non risolviamo con null prematuramente, lasciamo proseguire il poll.
      let settled = false;
      const finish = (a: VokariApi | null) => { if (!settled) { settled = true; resolve(a); } };
      window.addEventListener("pywebviewready", () => { const a = rawApi(); if (a) finish(a); }, { once: true });
      const start = Date.now();
      const id = window.setInterval(() => {
        const a = rawApi();
        if (a) { window.clearInterval(id); finish(a); }
        else if (Date.now() - start > READY_TIMEOUT_MS) { window.clearInterval(id); finish(null); }
      }, 50);
    });
  }
  return readyPromise;
}

async function withApi<T>(fn: (a: VokariApi) => Promise<T>, fallback: T): Promise<T> {
  const a = await apiReady();
  if (!a) return fallback;
  return fn(a);
}

/** Bus eventi: Python chiama window.__vokari_emit(ev, payload) via evaluate_js. */
export function onVokariEvent(handler: EmitHandler): () => void {
  if (!window.__vokari_handlers) {
    window.__vokari_handlers = new Set<EmitHandler>();
    window.__vokari_emit = (event, payload) => {
      for (const h of window.__vokari_handlers ?? []) h(event, payload);
    };
  }
  window.__vokari_handlers.add(handler);
  return () => {
    window.__vokari_handlers?.delete(handler);
  };
}

export async function getAppInfo(): Promise<AppInfo> {
  try {
    return await withApi((a) => a.get_app_info(), FALLBACK);
  } catch {
    return FALLBACK;
  }
}

export const bridge = {
  systemSpecs: () => withApi<SystemSpecs>((a) => a.system_specs(), { ramTotalGb: 0 }),
  diskUsage: () => withApi<DiskUsage>((a) => a.disk_usage(), { usedByModelsGb: 0, freeGb: 0 }),
  flashTaskbar: () => withApi((a) => a.flash_taskbar(), { ok: false }),
  openUrl: (url: string) => withApi((a) => a.open_url(url), { ok: false }),
  listSources: () => withApi((a) => a.list_sources(), { mic: [] as unknown[], system: [] as unknown[] }),
  startRecording: (source: string, device?: number | string | null) =>
    withApi((a) => a.start_recording(source, device ?? null), { ok: false }),
  addMarker: (label: string) =>
    withApi<{ t_ms: number; label: string } | { ok: false }>((a) => a.add_marker(label), { ok: false }),
  cancelRecording: () => withApi((a) => a.cancel_recording(), { ok: false }),
  pauseRecording: () => withApi((a) => a.pause_recording(), { ok: false }),
  resumeRecording: () => withApi((a) => a.resume_recording(), { ok: false }),
  stopRecording: (mode?: string, title?: string, context?: string) =>
    withApi((a) => a.stop_recording(mode, title, context), { jobId: "" }),
  importFile: (path: string, mode?: string, title?: string, context?: string) =>
    withApi((a) => a.import_file(path, mode, title, context), { jobId: "" }),
  getJob: (jobId: string) => withApi<JobView | null>((a) => a.get_job(jobId), null),
  renameJob: (jobId: string, title: string) => withApi((a) => a.rename_job(jobId, title), { ok: false }),
  getActiveJob: () => withApi<JobView | null>((a) => a.get_active_job(), null),
  resumeJob: (jobId: string) => withApi<JobView | null>((a) => a.resume_job(jobId), null),
  cancelJob: (jobId: string) => withApi<JobView | null>((a) => a.cancel_job(jobId), null),
  invalidateTranscriptCache: (jobId: string) =>
    withApi((a) => a.invalidate_transcript_cache(jobId), { ok: false }),
  getQuestions: (jobId: string) => withApi<Question[]>((a) => a.get_questions(jobId), []),
  generate: (jobId: string, answers: Record<string, string>, skipped: string[]) =>
    withApi((a) => a.generate(jobId, answers, skipped), null as JobView | null),
  getArtifacts: (jobId: string) => withApi((a) => a.get_artifacts(jobId), null as Artifacts | null),
  openFolder: (path: string) => withApi((a) => a.open_folder(path), { ok: false }),
  browseAudioFile: () => withApi((a) => a.browse_audio_file(), { path: "" }),
  probeAudio: (path: string) => withApi<AudioMeta>((a) => a.probe_audio(path), { durationS: 0, sizeBytes: 0 }),
  // F — Sessions
  listSessions: () => withApi<SessionItem[]>((a) => a.list_sessions(), []),
  searchSessions: (q: string) => withApi<SessionItem[]>((a) => a.search_sessions(q), []),
  openSession: (id: string) => withApi<Artifacts | null>((a) => a.open_session(id), null),
  deleteSession: (id: string) => withApi((a) => a.delete_session(id), { ok: false }),
  deleteSessions: (ids: string[]) => withApi((a) => a.delete_sessions(ids), { ok: false, deleted: 0 }),
  playSessionAudio: (id: string) =>
    withApi<{ ok: boolean; error?: string }>((a) => a.play_session_audio(id), { ok: false, error: "non disponibile" }),
  // H — Export
  exportPdf: (jobId: string) =>
    withApi<ExportResult>((a) => a.export_pdf(jobId), { ok: false, error: "no api" }),
  exportObsidian: (jobId: string) =>
    withApi<ExportResult>((a) => a.export_obsidian(jobId), { ok: false, error: "no api" }),
  saveTextFile: (content: string, suggestedName: string) =>
    withApi<ExportResult>((a) => a.save_text_file(content, suggestedName), { ok: false, error: "no api" }),
  // E — Settings
  getSettings: () => withApi((a) => a.get_settings(), DEFAULT_SETTINGS),
  saveSettings: (patch: Partial<Omit<VokariSettings, "hasApiKey">>) =>
    withApi((a) => a.save_settings(patch), DEFAULT_SETTINGS),
  setApiKey: (key: string) => withApi((a) => a.set_api_key(key), { ok: false, hasApiKey: false }),
  deleteApiKey: () => withApi((a) => a.delete_api_key(), { ok: false, hasApiKey: false }),
  verifyApiKey: () =>
    withApi<{ ok: boolean; reachable: boolean; error: string }>((a) => a.verify_api_key(), {
      ok: false, reachable: false, error: "non disponibile",
    }),
  browseFolder: () => withApi((a) => a.browse_folder(), { path: "" }),
  // G — Models (Whisper)
  listModels: () => withApi<ModelEntry[]>((a) => a.list_models(), []),
  downloadModel: (name: string) =>
    withApi((a) => a.download_model(name), { ok: false }),
  setActiveModel: (name: string) => withApi((a) => a.set_active_model(name), DEFAULT_SETTINGS),
  setBrain: (brain: string) => withApi((a) => a.set_brain(brain), DEFAULT_SETTINGS),
  // G2 — Ollama models
  listOllamaModels: () => withApi<OllamaModelEntry[]>((a) => a.list_ollama_models(), []),
  pullOllamaModel: (name: string) => withApi((a) => a.pull_ollama_model(name), { ok: false }),
  cancelOllamaPull: (name: string) => withApi((a) => a.cancel_ollama_pull(name), { ok: false }),
  deleteOllamaModel: (name: string) => withApi((a) => a.delete_ollama_model(name), { ok: false }),
  // G3 — runtime Ollama (avvio/installazione)
  ollamaStatus: () =>
    withApi<OllamaStatus>((a) => a.ollama_status(), {
      installed: false,
      running: false,
      bundled: false,
      canInstall: false,
      endpoint: "",
    }),
  ollamaStart: () => withApi((a) => a.ollama_start(), { ok: false, running: false }),
  ollamaStop: () => withApi((a) => a.ollama_stop(), { ok: false }),
  ollamaInstall: () => withApi((a) => a.ollama_install(), { ok: false }),
  // I — LibreHardwareMonitor
  lhmStatus: () => withApi<LhmStatus>((a) => a.lhm_status(), { installed: false, running: false }),
  lhmInstall: () => withApi((a) => a.lhm_install(), { ok: false }),
  lhmStart: () => withApi((a) => a.lhm_start(), { ok: false }),
  lhmStop: () => withApi((a) => a.lhm_stop(), { ok: false }),
  lhmUninstall: () => withApi((a) => a.lhm_uninstall(), { ok: false }),
  lhmDebug: () =>
    withApi<{ ok: boolean; stdout?: string; stderr?: string; error?: string }>(
      (a) => a.lhm_debug(), { ok: false, error: "no api" }),
};

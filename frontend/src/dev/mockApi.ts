// Mock di window.pywebview.api per l'harness DEV (vedi fixtures.ts per il contesto).
// Le schermate Models/Settings/Sessions e la sidebar "Recenti"/Home leggono dal
// bridge; senza pywebview il bridge cade nei fallback vuoti dopo 5s. Qui iniettiamo
// un'api finta sincrona così mostrano subito dati realistici.
//
// DEV-only: importato solo dietro `import.meta.env.DEV` → fuori dal build di produzione.

import * as fx from "./fixtures";

const ok = { ok: true } as const;

// Interruttori per stati che le schermate self-fetch leggono internamente dal
// bridge (non pilotabili via props). Impostati da DevHarness prima del render.
const flags = { emptySessions: false };
export function setDevFlags(f: Partial<typeof flags>): void {
  Object.assign(flags, f);
}

/** Installa un'api finta su window.pywebview se non già presente (idempotente). */
export function installMockApi(): void {
  if (window.pywebview?.api) return;

  const api = {
    get_app_info: async () => fx.sampleAppInfo,
    system_specs: async () => fx.sampleSystemSpecs,
    disk_usage: async () => fx.sampleDiskUsage,
    flash_taskbar: async () => ok,
    open_url: async (url: string) => { console.info("[dev] open_url", url); return ok; },
    list_sources: async () => ({ mic: [{}], system: [{}] }),
    start_recording: async () => ok,
    add_marker: async (label: string) => ({ t_ms: 1000, label }),
    cancel_recording: async () => ok,
    pause_recording: async () => ({ ok: true, paused: true }),
    resume_recording: async () => ({ ok: true, paused: false }),
    stop_recording: async () => ({ jobId: "dev-job" }),
    import_file: async () => ({ jobId: "dev-job" }),
    get_job: async () => fx.jobView(),
    rename_job: async () => ok,
    get_active_job: async () => null,
    resume_job: async () => fx.jobView(),
    cancel_job: async () => fx.jobView({ status: "cancelled" }),
    invalidate_transcript_cache: async () => ok,
    get_questions: async () => fx.sampleQuestions,
    generate: async () => fx.jobView({ status: "ready" }),
    get_artifacts: async () => fx.sampleArtifacts,
    open_folder: async (path: string) => { console.info("[dev] open_folder", path); return ok; },
    browse_audio_file: async () => ({ path: "C:\\dev\\esempio.m4a" }),
    probe_audio: async () => fx.sampleAudioMeta,
    // F — Sessions
    list_sessions: async () => (flags.emptySessions ? [] : fx.sampleSessions),
    search_sessions: async (q: string) =>
      flags.emptySessions ? [] : fx.sampleSessions.filter((s) => s.title.toLowerCase().includes(q.toLowerCase())),
    open_session: async () => fx.sampleArtifacts,
    delete_session: async () => ok,
    delete_sessions: async (ids: string[]) => ({ ok: true, deleted: ids.length }),
    play_session_audio: async () => ok,
    // H — Export
    export_pdf: async () => ({ ok: true, path: "C:\\dev\\recap.pdf" }),
    export_obsidian: async () => ({ ok: true, count: 1 }),
    save_text_file: async (_c: string, name: string) => ({ ok: true, path: `C:\\dev\\${name}` }),
    // E — Settings
    get_settings: async () => fx.sampleSettings,
    save_settings: async (patch: Record<string, unknown>) => ({ ...fx.sampleSettings, ...patch }),
    set_api_key: async () => ({ ok: true, hasApiKey: true }),
    delete_api_key: async () => ({ ok: true, hasApiKey: false }),
    verify_api_key: async () => ({ ok: true, reachable: true, error: "" }),
    browse_folder: async () => ({ path: "C:\\dev\\cartella" }),
    // G — Models (Whisper)
    list_models: async () => fx.sampleModels,
    download_model: async () => ok,
    set_active_model: async () => fx.sampleSettings,
    set_brain: async (brain: string) => ({ ...fx.sampleSettings, brain }),
    // G2 — Ollama models
    list_ollama_models: async () => fx.sampleOllama,
    pull_ollama_model: async () => ok,
    cancel_ollama_pull: async () => ok,
    delete_ollama_model: async () => ok,
    // G3 — runtime Ollama
    ollama_status: async () => fx.sampleOllamaStatus,
    ollama_start: async () => ({ ok: true, running: true }),
    ollama_stop: async () => ok,
    ollama_install: async () => ok,
    // I — LibreHardwareMonitor
    lhm_status: async () => ({ installed: true, running: true }),
    lhm_install: async () => ok,
    lhm_start: async () => ok,
    lhm_stop: async () => ok,
    lhm_uninstall: async () => ok,
    lhm_debug: async () => ({ ok: true, stdout: "dev" }),
  };

  // Cast: l'oggetto rispetta il contratto VokariApi a runtime; evitiamo di
  // re-dichiarare i ~50 tipi qui (la sorgente di verità è bridge.ts).
  window.pywebview = { api: api as unknown as NonNullable<Window["pywebview"]>["api"] };
}

/** Spinge un evento push come farebbe il backend (window.__vokari_emit). */
export function devEmit(event: string, payload: Record<string, unknown>): void {
  window.__vokari_emit?.(event, payload);
}

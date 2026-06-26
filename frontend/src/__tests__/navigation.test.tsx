import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "../App";

describe("navigazione", () => {
  beforeEach(() => {
    // Simula pywebview presente (in-app): il bridge ora attende l'iniezione
    // dell'api prima di chiamare, quindi i test integrazione la forniscono.
    (window as unknown as { pywebview: { api: Record<string, unknown> } }).pywebview = {
      api: {
        get_app_info: async () => ({ version: "t", license: "MIT", githubStars: 0 }),
        get_changelog: async () => ({ currentVersion: "t", entries: [] }),
        system_specs: async () => ({ ramTotalGb: 16 }),
        disk_usage: async () => ({ usedByModelsGb: 1.6, freeGb: 200 }),
        get_active_job: async () => null,
        start_recording: async () => ({ ok: true }),
        stop_recording: async () => ({ jobId: "job-x" }),
        get_job: async () => null,
        browse_audio_file: async () => ({ path: "" }),
        probe_audio: async () => ({ durationS: 0, sizeBytes: 0 }),
        import_file: async () => ({ jobId: "job-import" }),
        // E — Settings
        get_settings: async () => ({
          brain: "claude", ollamaEndpoint: "http://localhost:11434", ollamaModel: "gemma2:9b",
          whisperModel: "large-v3-turbo", claudeModel: "claude-opus-4-8",
          briefingDir: "", obsidianVault: "", defaultMode: "solo",
          transcriptionLanguage: "auto", onboarded: true, lastSeenVersion: "", appLanguage: "it", hasApiKey: false,
        }),
        save_settings: async () => ({
          brain: "claude", ollamaEndpoint: "http://localhost:11434", ollamaModel: "gemma2:9b",
          whisperModel: "large-v3-turbo", claudeModel: "claude-opus-4-8",
          briefingDir: "", obsidianVault: "", defaultMode: "solo",
          transcriptionLanguage: "auto", onboarded: true, lastSeenVersion: "", appLanguage: "it", hasApiKey: false,
        }),
        set_api_key: async () => ({ ok: true, hasApiKey: false }),
        browse_folder: async () => ({ path: "" }),
        // G — Models (Whisper)
        list_models: async () => [],
        download_model: async () => ({ ok: false }),
        set_active_model: async () => ({
          brain: "claude", ollamaEndpoint: "http://localhost:11434", ollamaModel: "qwen2.5:7b",
          whisperModel: "large-v3-turbo", claudeModel: "claude-sonnet-4-6",
          briefingDir: "", obsidianVault: "", defaultMode: "solo",
          transcriptionLanguage: "it", hasApiKey: false,
        }),
        set_brain: async () => ({
          brain: "claude", ollamaEndpoint: "http://localhost:11434", ollamaModel: "qwen2.5:7b",
          whisperModel: "large-v3-turbo", claudeModel: "claude-sonnet-4-6",
          briefingDir: "", obsidianVault: "", defaultMode: "solo",
          transcriptionLanguage: "it", hasApiKey: false,
        }),
        // G2 — Ollama models
        list_ollama_models: async () => [],
        pull_ollama_model: async () => ({ ok: true }),
        cancel_ollama_pull: async () => ({ ok: true }),
        delete_ollama_model: async () => ({ ok: true }),
        // G3 — runtime Ollama (avvio/installazione)
        ollama_status: async () => ({
          installed: false, running: false, bundled: false, canInstall: false, endpoint: "http://localhost:11434",
        }),
        ollama_start: async () => ({ ok: true, running: true }),
        ollama_stop: async () => ({ ok: true }),
        ollama_install: async () => ({ ok: true }),
        open_url: async () => undefined,
        // F — Sessions
        list_sessions: async () => [],
        search_sessions: async () => [],
        open_session: async () => null,
        // I — LibreHardwareMonitor
        lhm_status: async () => ({ installed: false, running: false, canInstall: true }),
        lhm_install: async () => ({ ok: true }),
        lhm_start: async () => ({ ok: true }),
        lhm_stop: async () => ({ ok: true }),
        lhm_uninstall: async () => ({ ok: true }),
      },
    };
  });
  afterEach(() => {
    delete (window as unknown as { pywebview?: unknown }).pywebview;
  });

  it("parte da Home e raggiunge le 4 viste primarie dalla sidebar", async () => {
    render(<App />);
    // Inizia sulla Home
    expect(await screen.findByText(/Registra\. Trascrivi\. Pensa meglio/)).toBeInTheDocument();

    await userEvent.click(screen.getByText("Impostazioni"));
    expect(screen.getByText("Cervello AI")).toBeInTheDocument();

    await userEvent.click(screen.getByText("Modelli AI"));
    expect(screen.getByText(/Whisper \(locale\)/)).toBeInTheDocument();

    await userEvent.click(screen.getByText("Sessioni"));
    expect(screen.getByText(/registrazioni · tutte trascritte/)).toBeInTheDocument();
  });

  it("Home → Avvia registrazione (Live) → Stop e trascrivi → Processing", async () => {
    render(<App />);
    // Parte dalla Home
    expect(await screen.findByText(/Registra\. Trascrivi\. Pensa meglio/)).toBeInTheDocument();

    // Clicca "Avvia registrazione" → va su Live
    await userEvent.click(screen.getByRole("button", { name: /Avvia registrazione/i }));
    expect(await screen.findByText(/REGISTRAZIONE/)).toBeInTheDocument();

    // Clicca "Stop e trascrivi" → va su Processing
    await userEvent.click(await screen.findByText("Stop e trascrivi"));
    expect(await screen.findByText("Annulla elaborazione")).toBeInTheDocument();
  });
});

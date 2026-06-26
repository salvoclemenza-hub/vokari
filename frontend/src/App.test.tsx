import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, act, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";
import { importDialog } from "./confirm";

vi.mock("./confirm", async (orig) => ({
  ...(await orig<typeof import("./confirm")>()),
  promptDialog: vi.fn(),
  importDialog: vi.fn(),
}));

// Mock del modulo bridge per controllare le risposte
vi.mock("./bridge", async (importOriginal) => {
  const real = await importOriginal<typeof import("./bridge")>();
  return {
    ...real,
    getAppInfo: vi.fn().mockResolvedValue({ version: "test", license: "MIT", githubStars: 0 }),
    bridge: {
      ...real.bridge,
      getActiveJob: vi.fn().mockResolvedValue(null),
      getSettings: vi.fn().mockResolvedValue({
        brain: "claude", ollamaEndpoint: "", ollamaModel: "", whisperModel: "large-v3-turbo",
        claudeModel: "claude-opus-4-8", briefingDir: "", obsidianVault: "",
        defaultMode: "solo", transcriptionLanguage: "auto", livePreview: true, liveModel: "base", onboarded: true, lastSeenVersion: "", appLanguage: "it", hasApiKey: false,
      }),
      resumeJob: vi.fn().mockResolvedValue(null),
      getJob: vi.fn().mockResolvedValue(null),
      getArtifacts: vi.fn().mockResolvedValue(null),
      stopRecording: vi.fn().mockResolvedValue({ jobId: "job-1" }),
      cancelJob: vi.fn().mockResolvedValue(null),
      generate: vi.fn().mockResolvedValue(null),
      openFolder: vi.fn().mockResolvedValue({ ok: true }),
      startRecording: vi.fn().mockResolvedValue({ ok: true }),
      addMarker: vi.fn().mockResolvedValue({ ok: false }),
      browseAudioFile: vi.fn().mockResolvedValue({ path: "" }),
      probeAudio: vi.fn().mockResolvedValue({ durationS: 0, sizeBytes: 0 }),
      importFile: vi.fn().mockResolvedValue({ jobId: "job-import" }),
      listSessions: vi.fn().mockResolvedValue([]),
      listModels: vi.fn().mockResolvedValue([]),
      saveSettings: vi.fn().mockResolvedValue({
        brain: "claude", ollamaEndpoint: "", ollamaModel: "", whisperModel: "large-v3-turbo",
        claudeModel: "claude-opus-4-8", briefingDir: "", obsidianVault: "",
        defaultMode: "solo", transcriptionLanguage: "auto", livePreview: true, liveModel: "base", onboarded: true, lastSeenVersion: "", appLanguage: "it", hasApiKey: false,
      }),
      ollamaStatus: vi.fn().mockResolvedValue({ installed: false, running: false, canInstall: false }),
      getChangelog: vi.fn().mockResolvedValue({ currentVersion: "test", entries: [] }),
    },
  };
});

// Helper per emettere eventi Vokari dal lato Python (simulate evaluate_js)
function emit(event: string, payload: Record<string, unknown>) {
  window.__vokari_emit?.(event, payload);
}

/** Naviga da Home → Live cliccando "Avvia registrazione" */
async function goToLive() {
  await userEvent.click(await screen.findByRole("button", { name: /Avvia registrazione/i }));
}

describe("App — macchina a stati", () => {
  beforeEach(async () => {
    delete (window as unknown as { pywebview?: unknown }).pywebview;
    delete (window as unknown as { __vokari_emit?: unknown }).__vokari_emit;
    delete (window as unknown as { __vokari_handlers?: unknown }).__vokari_handlers;
    vi.clearAllMocks();
    // clearAllMocks azzera le chiamate ma NON le implementazioni mockResolvedValue → ripristina
    // il default (onboarded:true = niente wizard) così un test che imposta onboarded:false non
    // "contagia" i successivi. I test che vogliono altri settings lo ri-sovrascrivono nel corpo.
    const { bridge } = await import("./bridge");
    (bridge.getSettings as ReturnType<typeof vi.fn>).mockResolvedValue({
      brain: "claude", ollamaEndpoint: "", ollamaModel: "", whisperModel: "large-v3-turbo",
      claudeModel: "claude-opus-4-8", briefingDir: "", obsidianVault: "",
      defaultMode: "solo", transcriptionLanguage: "auto", livePreview: true, liveModel: "base", onboarded: true, lastSeenVersion: "", appLanguage: "it", hasApiKey: false,
    });
  });

  it("mount senza job attivo → mostra schermata Home", async () => {
    render(<App />);
    expect(await screen.findByText(/Registra\. Trascrivi\. Pensa meglio/)).toBeInTheDocument();
  });

  it("primo avvio (onboarded:false) → mostra il wizard; 'Salta' → Home e segna onboarded", async () => {
    const { bridge } = await import("./bridge");
    (bridge.getSettings as ReturnType<typeof vi.fn>).mockResolvedValue({
      brain: "claude", ollamaEndpoint: "", ollamaModel: "", whisperModel: "large-v3-turbo",
      claudeModel: "claude-opus-4-8", briefingDir: "", obsidianVault: "",
      defaultMode: "solo", transcriptionLanguage: "auto", livePreview: true, liveModel: "base", onboarded: false, lastSeenVersion: "", appLanguage: "it", hasApiKey: false,
    });
    render(<App />);
    // il gate del primo avvio mostra il wizard (passo Benvenuto) invece della Home
    expect(await screen.findByText(/Benvenuto in VOKARI/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Salta" }));
    // completando l'onboarding segna anche la versione corrente come novità già viste
    await waitFor(() => expect(bridge.saveSettings).toHaveBeenCalledWith({ onboarded: true, lastSeenVersion: "test" }));
    expect(await screen.findByText(/Registra\. Trascrivi\. Pensa meglio/)).toBeInTheDocument();
    // mutua esclusione: durante l'onboarding il popup "Novità" non viene nemmeno interrogato
    expect(bridge.getChangelog).not.toHaveBeenCalled();
  });

  it("aggiornamento con novità non viste → popup 'Novità'; chiudendolo segna lastSeenVersion (Tema 2)", async () => {
    const { bridge } = await import("./bridge");
    (bridge.getSettings as ReturnType<typeof vi.fn>).mockResolvedValue({
      brain: "claude", ollamaEndpoint: "", ollamaModel: "", whisperModel: "large-v3-turbo",
      claudeModel: "claude-opus-4-8", briefingDir: "", obsidianVault: "",
      defaultMode: "solo", transcriptionLanguage: "auto", livePreview: true, liveModel: "base",
      onboarded: true, lastSeenVersion: "0.1.1", appLanguage: "it", hasApiKey: false,
    });
    (bridge.getChangelog as ReturnType<typeof vi.fn>).mockResolvedValue({
      currentVersion: "0.1.2",
      entries: [
        {
          version: "0.1.2", date: "2026-06-25", title: "Benvenuto guidato",
          highlights: [{ kind: "feature", text: "Wizard di benvenuto." }],
        },
      ],
    });

    render(<App />);
    expect(await screen.findByText(/Novità di VOKARI/)).toBeInTheDocument();
    expect(await screen.findByText("Benvenuto guidato")).toBeInTheDocument();
    // interrogato con l'ultima versione vista
    expect(bridge.getChangelog).toHaveBeenCalledWith("0.1.1");
    // chiudendo memorizza la versione corrente così non riappare al prossimo avvio
    await userEvent.click(screen.getByRole("button", { name: /Ho capito/ }));
    await waitFor(() => expect(bridge.saveSettings).toHaveBeenCalledWith({ lastSeenVersion: "0.1.2" }));
  });

  it("click su Avvia registrazione → mostra schermata Live (REGISTRAZIONE)", async () => {
    render(<App />);
    await goToLive();
    expect(await screen.findByText(/REGISTRAZIONE/)).toBeInTheDocument();
  });

  it("Stop passa mode (da settings) e titolo digitato a stopRecording", async () => {
    const { bridge } = await import("./bridge");
    (bridge.getSettings as ReturnType<typeof vi.fn>).mockResolvedValue({
      brain: "claude", ollamaEndpoint: "", ollamaModel: "", whisperModel: "large-v3-turbo",
      claudeModel: "claude-opus-4-8", briefingDir: "", obsidianVault: "",
      defaultMode: "riunione", transcriptionLanguage: "auto", livePreview: true, liveModel: "base", onboarded: true, lastSeenVersion: "", appLanguage: "it", hasApiKey: false,
    });

    render(<App />);
    await goToLive();
    const input = await screen.findByLabelText("Titolo sessione");
    await userEvent.type(input, "Sprint planning");
    await userEvent.click(await screen.findByText("Stop e trascrivi"));

    expect(bridge.stopRecording).toHaveBeenCalledWith("riunione", "Sprint planning", undefined);
  });

  it("evento status=transcribing dopo stop → Processing visibile", async () => {
    const { bridge } = await import("./bridge");
    (bridge.getJob as ReturnType<typeof vi.fn>).mockResolvedValue({
      jobId: "job-1", status: "transcribing", pct: 0.35, partialText: "ciao",
      title: "T", source: "mic", mode: "solo", model: "large-v3-turbo",
      language: "it", transcript: "", durationS: 0, questions: [],
      markers: [], briefingMd: "", briefingPath: "", error: "",
    });

    render(<App />);
    // Home → Live → Stop
    await goToLive();
    await userEvent.click(await screen.findByText("Stop e trascrivi"));

    await act(async () => {
      emit("status", { jobId: "job-1", status: "transcribing" });
    });

    expect(await screen.findByText("Annulla elaborazione")).toBeInTheDocument();
    expect(await screen.findByText("35%")).toBeInTheDocument();
  });

  it("evento status=awaiting_interview → Interview visibile con domande", async () => {
    const { bridge } = await import("./bridge");
    (bridge.getJob as ReturnType<typeof vi.fn>).mockResolvedValue({
      jobId: "job-1", status: "awaiting_interview", pct: 1, partialText: "",
      title: "T", source: "mic", mode: "solo", model: "large-v3-turbo",
      language: "it", transcript: "", durationS: 0,
      questions: [
        { id: "q1", text: "Chi era presente?", priority: "high", suggestions: ["Team dev"] },
      ],
      markers: [], briefingMd: "", briefingPath: "", error: "",
    });

    render(<App />);
    await goToLive();
    await userEvent.click(await screen.findByText("Stop e trascrivi"));

    await act(async () => {
      emit("status", { jobId: "job-1", status: "awaiting_interview" });
    });

    expect(await screen.findByText(/domande per un briefing migliore/)).toBeInTheDocument();
    expect(await screen.findByText("Chi era presente?")).toBeInTheDocument();
  });

  it("evento status=ready → Artifacts visibile con briefing", async () => {
    const { bridge } = await import("./bridge");
    (bridge.getJob as ReturnType<typeof vi.fn>).mockResolvedValue({
      jobId: "job-1", status: "ready", pct: 1, partialText: "",
      title: "Test meeting", source: "mic", mode: "solo", model: "large-v3-turbo",
      language: "it", transcript: "", durationS: 120, questions: [],
      markers: [], briefingMd: "# Briefing reale", briefingPath: "/out/b.md", error: "",
    });
    (bridge.getArtifacts as ReturnType<typeof vi.fn>).mockResolvedValue({
      title: "Test meeting", briefingMd: "# Briefing reale", briefingPath: "/out/b.md",
      recapMd: "", obsidianNote: "", durationS: 120, model: "large-v3-turbo",
      language: "it", wordCount: 3,
    });

    render(<App />);
    await goToLive();
    await userEvent.click(await screen.findByText("Stop e trascrivi"));

    await act(async () => {
      emit("status", { jobId: "job-1", status: "ready" });
    });

    expect(await screen.findByRole("heading", { name: "Test meeting" })).toBeInTheDocument();
    // Markdown renderizzato (.vk-doc): "# Briefing reale" → <h2>Briefing reale</h2>.
    expect(await screen.findByRole("heading", { name: "Briefing reale" })).toBeInTheDocument();
  });

  it("stopRecording che ritorna error → schermata d'errore, niente crash", async () => {
    const { bridge } = await import("./bridge");
    (bridge.stopRecording as ReturnType<typeof vi.fn>).mockResolvedValue({
      jobId: "e1", error: "Cattura fallita: nessun audio catturato",
    });

    render(<App />);
    await goToLive();
    await userEvent.click(await screen.findByText("Stop e trascrivi"));

    expect(await screen.findByText(/Qualcosa è andato storto/)).toBeInTheDocument();
    expect(await screen.findByText(/Cattura fallita: nessun audio/)).toBeInTheDocument();
  });

  it("evento status=error dalla pipeline → schermata d'errore", async () => {
    const { bridge } = await import("./bridge");
    (bridge.stopRecording as ReturnType<typeof vi.fn>).mockResolvedValue({ jobId: "job-1" });

    render(<App />);
    await goToLive();
    await userEvent.click(await screen.findByText("Stop e trascrivi")); // jobIdRef = job-1

    await act(async () => {
      emit("status", { jobId: "job-1", status: "error", error: "Trascrizione fallita: ffmpeg" });
    });

    expect(await screen.findByText(/Trascrizione fallita: ffmpeg/)).toBeInTheDocument();
  });

  it("status=error NON lascia la pill di ripresa fantasma sulla schermata d'errore (M1)", async () => {
    const { bridge } = await import("./bridge");
    (bridge.stopRecording as ReturnType<typeof vi.fn>).mockResolvedValue({ jobId: "job-1" });

    render(<App />);
    await goToLive();
    await userEvent.click(await screen.findByText("Stop e trascrivi")); // jobIdRef = job-1

    await act(async () => {
      emit("status", { jobId: "job-1", status: "transcribing" });   // job attivo → pill possibile
    });
    await act(async () => {
      emit("status", { jobId: "job-1", status: "error", error: "Trascrizione vuota" });
    });

    expect(await screen.findByText(/Qualcosa è andato storto/)).toBeInTheDocument();
    // niente pill "Elaborazione in corso… →" sulla schermata di errore
    expect(screen.queryByTitle("Riprendi la sessione in corso")).not.toBeInTheDocument();
  });

  it("all'avvio un job in elaborazione NON viene auto-ripreso; la ripresa è al click (A1)", async () => {
    const { bridge } = await import("./bridge");
    const activeJob = {
      jobId: "job-old", status: "transcribing", pct: 0.2, partialText: "",
      title: "T", source: "mic", mode: "solo", model: "large-v3-turbo",
      language: "it", transcript: "", durationS: 0, questions: [],
      markers: [], briefingMd: "", briefingPath: "", error: "",
    };
    (bridge.getActiveJob as ReturnType<typeof vi.fn>).mockResolvedValue(activeJob);
    (bridge.getJob as ReturnType<typeof vi.fn>).mockResolvedValue(activeJob);

    render(<App />);
    // la pill di ripresa compare (siamo su home), ma resumeJob NON è stato chiamato da solo
    const pill = await screen.findByTitle("Riprendi la sessione in corso");
    expect(bridge.resumeJob).not.toHaveBeenCalled();

    await userEvent.click(pill);
    expect(bridge.resumeJob).toHaveBeenCalledWith("job-old");
    expect(await screen.findByText("Annulla elaborazione")).toBeInTheDocument();
  });

  it("pill 'job in background' compare fuori dal flusso e riporta a Processing (FS3)", async () => {
    const { bridge } = await import("./bridge");
    (bridge.getJob as ReturnType<typeof vi.fn>).mockResolvedValue({
      jobId: "job-1", status: "transcribing", pct: 0.4, partialText: "x",
      title: "T", source: "mic", mode: "solo", model: "large-v3-turbo",
      language: "it", transcript: "", durationS: 0, questions: [],
      markers: [], briefingMd: "", briefingPath: "", error: "",
    });

    render(<App />);
    await goToLive();
    await userEvent.click(await screen.findByText("Stop e trascrivi")); // jobIdRef = job-1, screen=processing
    await act(async () => {
      emit("status", { jobId: "job-1", status: "transcribing" });
    });

    // naviga via dalle schermate di flusso: il job resta in elaborazione
    await userEvent.click(screen.getByText("Modelli AI"));
    const pill = await screen.findByTitle("Riprendi la sessione in corso");
    await userEvent.click(pill);

    // tornati su Processing
    expect(await screen.findByText("Annulla elaborazione")).toBeInTheDocument();
  });

  it("download modello: pill globale 'Scaricando' persistente, sparisce a done (FB-D)", async () => {
    render(<App />);
    await screen.findByText(/Registra\. Trascrivi/);

    await act(async () => { emit("model_download", { name: "small", status: "start" }); });
    expect(await screen.findByText("small · scaricando")).toBeInTheDocument();

    await act(async () => { emit("model_download", { name: "small", status: "progress", pct: 0.42 }); });
    expect(await screen.findByText("42%")).toBeInTheDocument();

    await act(async () => { emit("model_download", { name: "small", status: "done" }); });
    await waitFor(() => expect(screen.queryByText("small · scaricando")).not.toBeInTheDocument());
  });

  it("evento warning → banner di avviso non bloccante", async () => {
    render(<App />);
    await act(async () => {
      emit("warning", { messages: ["audio di sistema non disponibile: registrato solo 'mic'"] });
    });
    expect(await screen.findByText(/audio di sistema non disponibile/)).toBeInTheDocument();
  });

  it("import: il dialog passa tipo e contesto scelti a importFile (MDL2)", async () => {
    const { bridge } = await import("./bridge");
    (bridge.getSettings as ReturnType<typeof vi.fn>).mockResolvedValue({
      brain: "claude", ollamaEndpoint: "", ollamaModel: "", whisperModel: "large-v3-turbo",
      claudeModel: "claude-opus-4-8", briefingDir: "", obsidianVault: "",
      defaultMode: "solo", transcriptionLanguage: "auto", livePreview: true, liveModel: "base", onboarded: true, lastSeenVersion: "", appLanguage: "it", hasApiKey: false,
    });
    (bridge.browseAudioFile as ReturnType<typeof vi.fn>).mockResolvedValue({ path: "C:/tmp/183.m4a" });
    (bridge.probeAudio as ReturnType<typeof vi.fn>).mockResolvedValue({ durationS: 1661, sizeBytes: 24_300_000 });
    (importDialog as ReturnType<typeof vi.fn>).mockResolvedValue({ mode: "riunione", context: "landing page" });

    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: /Trascina o clicca/i }));

    await waitFor(() =>
      expect(bridge.importFile).toHaveBeenCalledWith("C:/tmp/183.m4a", "riunione", undefined, "landing page"),
    );
  });

  it("import: su Annulla del dialog (null) NON importa", async () => {
    const { bridge } = await import("./bridge");
    (bridge.browseAudioFile as ReturnType<typeof vi.fn>).mockResolvedValue({ path: "C:/tmp/183.m4a" });
    (bridge.probeAudio as ReturnType<typeof vi.fn>).mockResolvedValue({ durationS: 0, sizeBytes: 0 });
    (importDialog as ReturnType<typeof vi.fn>).mockResolvedValue(null);

    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: /Trascina o clicca/i }));

    // diamo modo alle promise di risolvere; importFile non deve essere chiamato
    await new Promise((r) => setTimeout(r, 0));
    expect(bridge.importFile).not.toHaveBeenCalled();
  });

  it("import: file rifiutato dal gate (error) → toast, niente navigazione a Processing", async () => {
    const { bridge } = await import("./bridge");
    (bridge.browseAudioFile as ReturnType<typeof vi.fn>).mockResolvedValue({ path: "C:/tmp/sparito.m4a" });
    (bridge.probeAudio as ReturnType<typeof vi.fn>).mockResolvedValue({ durationS: 0, sizeBytes: 0 });
    (importDialog as ReturnType<typeof vi.fn>).mockResolvedValue({ mode: "solo", context: "" });
    (bridge.importFile as ReturnType<typeof vi.fn>).mockResolvedValue({
      error: "File non trovato: potrebbe essere stato spostato o eliminato.",
    });

    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: /Trascina o clicca/i }));

    // il messaggio compare come toast
    expect(await screen.findByText(/File non trovato/)).toBeInTheDocument();
    // NON siamo finiti in Processing
    expect(screen.queryByText("Annulla elaborazione")).not.toBeInTheDocument();
  });
});

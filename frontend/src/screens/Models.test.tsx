import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ModelEntry, VokariSettings } from "../bridge";

// ────────────────────────────────────────────────────────────
// Mock bridge
// ────────────────────────────────────────────────────────────
const FAKE_SETTINGS: VokariSettings = {
  brain: "claude",
  ollamaEndpoint: "http://localhost:11434",
  ollamaModel: "gemma2:9b",
  whisperModel: "large-v3-turbo",
  claudeModel: "claude-opus-4-8",
  briefingDir: "",
  obsidianVault: "",
  defaultMode: "solo",
  transcriptionLanguage: "auto",
  livePreview: true,
  liveModel: "base",
  onboarded: true,
  lastSeenVersion: "",
  appLanguage: "it",
  userContext: "",
  hasApiKey: false,
};

const FAKE_MODELS: ModelEntry[] = [
  { name: "small", sizeLabel: "~0.5 GB", speed: 5, quality: 2, languages: "IT·EN·+90", description: "Veloce", recommended: false, state: "available" },
  { name: "medium", sizeLabel: "~1.5 GB", speed: 3, quality: 3, languages: "IT·EN·+90", description: "Bilanciato", recommended: false, state: "downloaded" },
  { name: "large-v3-turbo", sizeLabel: "~1.6 GB", speed: 4, quality: 4, languages: "IT·EN·+90", description: "Consigliato", recommended: true, state: "active" },
  { name: "large-v3", sizeLabel: "~3.1 GB", speed: 2, quality: 5, languages: "IT·EN·+90", description: "Massima qualità", recommended: false, state: "available" },
];

const mockListModels = vi.fn();
const mockSystemSpecs = vi.fn();
const mockDiskUsage = vi.fn();
const mockGetSettings = vi.fn();
const mockDownloadModel = vi.fn();
const mockSetActiveModel = vi.fn();
const mockSetBrain = vi.fn();
const mockOnVokariEvent = vi.fn();
const mockListOllamaModels = vi.fn();
const mockPullOllamaModel = vi.fn();
const mockCancelOllamaPull = vi.fn();
const mockDeleteOllamaModel = vi.fn();
const mockSaveSettings = vi.fn();
const mockOpenUrl = vi.fn();
const mockOllamaStatus = vi.fn();
const mockOllamaInstall = vi.fn();
const mockOllamaStart = vi.fn();
const mockOllamaStop = vi.fn();

vi.mock("../bridge", () => ({
  // valore iniziale di useState (poi sovrascritto da getSettings nel test). Inline perché
  // la factory di vi.mock non può referenziare variabili out-of-scope non-`mock*`.
  DEFAULT_SETTINGS: {
    brain: "claude", ollamaEndpoint: "http://localhost:11434", ollamaModel: "qwen2.5:7b",
    whisperModel: "large-v3-turbo", claudeModel: "claude-sonnet-4-6", briefingDir: "",
    obsidianVault: "", defaultMode: "solo", transcriptionLanguage: "it",
    livePreview: true, liveModel: "base", hasApiKey: false,
  },
  bridge: {
    listModels: () => mockListModels() as Promise<ModelEntry[]>,
    systemSpecs: () => mockSystemSpecs() as Promise<{ ramTotalGb: number }>,
    diskUsage: () => mockDiskUsage() as Promise<{ usedByModelsGb: number; freeGb: number }>,
    getSettings: () => mockGetSettings() as Promise<VokariSettings>,
    downloadModel: (name: string) => mockDownloadModel(name) as Promise<{ ok: boolean }>,
    setActiveModel: (name: string) => mockSetActiveModel(name) as Promise<VokariSettings>,
    setBrain: (brain: string) => mockSetBrain(brain) as Promise<VokariSettings>,
    listOllamaModels: () => mockListOllamaModels(),
    pullOllamaModel: (name: string) => mockPullOllamaModel(name),
    cancelOllamaPull: (name: string) => mockCancelOllamaPull(name),
    deleteOllamaModel: (name: string) => mockDeleteOllamaModel(name),
    saveSettings: (patch: Partial<VokariSettings>) => mockSaveSettings(patch),
    openUrl: (url: string) => mockOpenUrl(url),
    ollamaStatus: () => mockOllamaStatus(),
    ollamaInstall: () => mockOllamaInstall(),
    ollamaStart: () => mockOllamaStart(),
    ollamaStop: () => mockOllamaStop(),
  },
  onVokariEvent: (handler: (event: string, payload: Record<string, unknown>) => void) =>
    mockOnVokariEvent(handler) as () => void,
}));

import { ScreenModels } from "./Models";

describe("ScreenModels", () => {
  beforeEach(() => {
    mockListModels.mockResolvedValue([...FAKE_MODELS]);
    mockSystemSpecs.mockResolvedValue({ ramTotalGb: 8 });
    mockDiskUsage.mockResolvedValue({ usedByModelsGb: 6.3, freeGb: 142 });
    mockGetSettings.mockResolvedValue({ ...FAKE_SETTINGS });
    mockDownloadModel.mockResolvedValue({ ok: true, state: "downloaded" });
    mockSetActiveModel.mockResolvedValue({ ...FAKE_SETTINGS });
    mockSetBrain.mockResolvedValue({ ...FAKE_SETTINGS });
    mockOnVokariEvent.mockReturnValue(() => {});
    mockListOllamaModels.mockResolvedValue([]);
    mockPullOllamaModel.mockResolvedValue({ ok: true });
    mockCancelOllamaPull.mockResolvedValue({ ok: true });
    mockDeleteOllamaModel.mockResolvedValue({ ok: true });
    mockSaveSettings.mockResolvedValue({ ...FAKE_SETTINGS });
    mockOpenUrl.mockResolvedValue(undefined);
    mockOllamaStatus.mockResolvedValue({
      installed: false, running: false, bundled: false, canInstall: false, endpoint: "http://localhost:11434",
    });
    mockOllamaInstall.mockResolvedValue({ ok: true });
    mockOllamaStart.mockResolvedValue({ ok: true, running: true });
    mockOllamaStop.mockResolvedValue({ ok: true });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("mostra 4 modelli dal catalogo reale", async () => {
    render(<ScreenModels />);
    await waitFor(() => {
      expect(screen.getByText("small")).toBeInTheDocument();
      expect(screen.getByText("medium")).toBeInTheDocument();
      expect(screen.getByText("large-v3-turbo")).toBeInTheDocument();
      expect(screen.getByText("large-v3")).toBeInTheDocument();
    });
  });

  it("mostra 'Attivo' per il modello active e 'Scaricato' per downloaded", async () => {
    render(<ScreenModels />);
    await waitFor(() => {
      expect(screen.getByText("Attivo")).toBeInTheDocument();
      expect(screen.getByText("Scaricato")).toBeInTheDocument();
    });
  });

  it("B1: il modello selezionato ma non scaricato mostra 'Selezionato · da scaricare', non 'Attivo'", async () => {
    // Scenario PC pulito (caso reale collega): large-v3-turbo è il whisperModel scelto ma
    // NON è ancora scaricato (state=available). Prima compariva "Attivo" + Download insieme.
    mockListModels.mockResolvedValue([
      { name: "large-v3-turbo", sizeLabel: "~1.6 GB", speed: 4, quality: 4, languages: "IT·EN·+90",
        description: "Consigliato", recommended: true, state: "available" },
    ]);
    render(<ScreenModels />);
    await waitFor(() => expect(screen.getByText("large-v3-turbo")).toBeInTheDocument());
    expect(screen.queryByText("Attivo")).not.toBeInTheDocument();
    expect(screen.getByText(/Selezionato · da scaricare/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Download/i })).toBeInTheDocument();
  });

  it("mostra bottoni Download per i modelli disponibili (state=available)", async () => {
    render(<ScreenModels />);
    await waitFor(() => {
      const downloadButtons = screen.getAllByRole("button", { name: /Download/i });
      // small e large-v3 sono available
      expect(downloadButtons.length).toBeGreaterThanOrEqual(2);
    });
  });

  it("chiama downloadModel e ricarica la lista al click su Download", async () => {
    render(<ScreenModels />);
    await waitFor(() => screen.getAllByRole("button", { name: /Download/i }));
    const buttons = screen.getAllByRole("button", { name: /Download/i });
    fireEvent.click(buttons[0]);
    await waitFor(() => {
      expect(mockDownloadModel).toHaveBeenCalled();
    });
  });

  it("mostra la percentuale durante il download (eventi model_download)", async () => {
    render(<ScreenModels />);
    await waitFor(() => screen.getAllByRole("button", { name: /Download/i }));
    const handler = mockOnVokariEvent.mock.calls[0][0] as
      (event: string, payload: Record<string, unknown>) => void;
    act(() => {
      handler("model_download", { status: "start", name: "small" });
      handler("model_download", { status: "progress", pct: 0.42 });
    });
    expect(await screen.findByRole("button", { name: /Scaricando 42%/i })).toBeInTheDocument();
  });

  it("chiama setActiveModel al click su un modello scaricato (state=downloaded)", async () => {
    render(<ScreenModels />);
    await waitFor(() => screen.getByText("Scaricato"));
    // "medium" ha state=downloaded — clicca sulla sua row
    // La riga è clicabile; cerchiamo il testo "medium" e clicchiamo il parent
    const mediumText = screen.getByText("medium");
    fireEvent.click(mediumText);
    await waitFor(() => {
      expect(mockSetActiveModel).toHaveBeenCalledWith("medium");
    });
  });

  it("chiama setBrain al click su 'Locale (Ollama)'", async () => {
    render(<ScreenModels />);
    await waitFor(() => screen.getByText("Locale (Ollama)"));
    fireEvent.click(screen.getByText("Locale (Ollama)"));
    await waitFor(() => {
      expect(mockSetBrain).toHaveBeenCalledWith("ollama");
    });
  });

  it("mostra l'endpoint Ollama reale dalle settings", async () => {
    render(<ScreenModels />);
    await waitFor(() => {
      // l'endpoint è in uno <span class="mono"> che può essere un testo singolo
      expect(screen.getByText(/localhost:11434/)).toBeInTheDocument();
    });
  });

  it("MOD1: durante il pull mostra ✕ Annulla e chiama cancelOllamaPull", async () => {
    mockListOllamaModels.mockResolvedValue([
      {
        name: "qwen2.5:14b", sizeLabel: "9.0 GB", description: "Qualità superiore",
        speed: 1, quality: 3, params: "14B", context: "128K", tags: [],
        detailUrl: "https://ollama.com/library/qwen2.5",
        isInstalled: false, isActive: false, recommended: false,
      },
    ]);
    render(<ScreenModels />);
    await waitFor(() => expect(screen.getByText("qwen2.5:14b")).toBeInTheDocument());
    // simula l'avvio del pull (evento ollama_pull start) su tutti gli handler registrati
    const handlers = mockOnVokariEvent.mock.calls.map((c) => c[0] as
      (event: string, payload: Record<string, unknown>) => void);
    act(() => handlers.forEach((h) => h("ollama_pull", { status: "start", name: "qwen2.5:14b" })));
    const cancelBtn = await screen.findByRole("button", { name: "Annulla download" });
    fireEvent.click(cancelBtn);
    await waitFor(() => expect(mockCancelOllamaPull).toHaveBeenCalledWith("qwen2.5:14b"));
  });

  it("MOD3: la pill disco mostra i GB usati dai modelli e i GB liberi", async () => {
    mockDiskUsage.mockResolvedValue({ usedByModelsGb: 6.3, freeGb: 142 });
    render(<ScreenModels />);
    expect(await screen.findByText(/6\.3 GB/)).toBeInTheDocument();
    expect(screen.getByText(/142 GB/)).toBeInTheDocument();
  });

  it("MOD3: mostra l'ETA durante il pull dai byte di progresso", async () => {
    const nowSpy = vi.spyOn(Date, "now").mockReturnValue(1000);
    mockListOllamaModels.mockResolvedValue([
      { name: "qwen2.5:7b", sizeLabel: "4.7 GB", description: "x", speed: 2, quality: 2, params: "7B",
        context: "128K", tags: [], minRamGb: 6.1, detailUrl: "https://ollama.com/library/qwen2.5",
        isInstalled: false, isActive: false, recommended: false },
    ]);
    render(<ScreenModels />);
    await waitFor(() => expect(screen.getByText("qwen2.5:7b")).toBeInTheDocument());
    const handlers = mockOnVokariEvent.mock.calls.map((c) => c[0] as
      (event: string, payload: Record<string, unknown>) => void);
    act(() => handlers.forEach((h) => h("ollama_pull", { status: "start", name: "qwen2.5:7b" })));
    // primo campione @ t=1000 (10/100 byte) → nessun ETA ancora
    act(() => handlers.forEach((h) =>
      h("ollama_pull", { status: "progress", name: "qwen2.5:7b", pct: 0.1, bytesDone: 10, bytesTotal: 100 })));
    // secondo campione @ t=2000 (20/100) → speed 10 B/s → ETA (100-20)/10 = 8s
    nowSpy.mockReturnValue(2000);
    act(() => handlers.forEach((h) =>
      h("ollama_pull", { status: "progress", name: "qwen2.5:7b", pct: 0.2, bytesDone: 20, bytesTotal: 100 })));
    expect(await screen.findByText(/~8s rimanenti/)).toBeInTheDocument();
    nowSpy.mockRestore();
  });

  it("MOD2: avvisa sui modelli pesanti per la RAM ed esclude col filtro Compatibili", async () => {
    mockSystemSpecs.mockResolvedValue({ ramTotalGb: 8 });
    mockListOllamaModels.mockResolvedValue([
      { name: "qwen2.5:7b", sizeLabel: "4.7 GB", description: "x", speed: 2, quality: 2, params: "7B",
        context: "128K", tags: [], minRamGb: 6.1, detailUrl: "https://ollama.com/library/qwen2.5",
        isInstalled: false, isActive: false, recommended: false },
      { name: "qwen2.5:14b", sizeLabel: "9.0 GB", description: "y", speed: 1, quality: 3, params: "14B",
        context: "128K", tags: [], minRamGb: 11.7, detailUrl: "https://ollama.com/library/qwen2.5",
        isInstalled: false, isActive: false, recommended: false },
    ]);
    render(<ScreenModels />);
    await waitFor(() => expect(screen.getByText("qwen2.5:14b")).toBeInTheDocument());
    // avviso solo sul 14B (≈11.7 GB > 8 GB)
    expect(screen.getByText(/pesante per la tua RAM/)).toBeInTheDocument();
    // filtro "Compatibili" → nasconde il 14B, tiene il 7B (6.1 ≤ 8)
    fireEvent.click(screen.getByRole("button", { name: "Compatibili" }));
    await waitFor(() => expect(screen.queryByText("qwen2.5:14b")).not.toBeInTheDocument());
    expect(screen.getByText("qwen2.5:7b")).toBeInTheDocument();
  });

  it("mostra specs (parametri/contesto/tag) e link dettagli per un modello locale", async () => {
    mockListOllamaModels.mockResolvedValue([
      {
        name: "qwen2.5:7b",
        sizeLabel: "~4.7 GB",
        description: "Default consigliato",
        speed: 3,
        quality: 2,
        params: "7B",
        context: "128K",
        tags: ["italiano", "json"],
        detailUrl: "https://ollama.com/library/qwen2.5",
        isInstalled: false,
        isActive: false,
        recommended: true,
      },
    ]);
    render(<ScreenModels />);
    await waitFor(() => expect(screen.getByText("qwen2.5:7b")).toBeInTheDocument());
    // tecnicismi a colpo d'occhio
    expect(screen.getByText("7B")).toBeInTheDocument();
    expect(screen.getByText(/contesto 128K/)).toBeInTheDocument();
    // i tag sono ora icone con title attribute; verifichiamo la presenza dell'icona italiano
    expect(screen.getByTitle("Ottimo in italiano")).toBeInTheDocument();
    // link "dettagli del modello" → apre l'URL nel browser di sistema
    fireEvent.click(screen.getByText(/dettagli del modello/i));
    await waitFor(() =>
      expect(mockOpenUrl).toHaveBeenCalledWith("https://ollama.com/library/qwen2.5"),
    );
  });
});

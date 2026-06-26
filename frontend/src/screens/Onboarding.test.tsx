import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ModelEntry } from "../bridge";

const mockGetSettings = vi.fn();
const mockSaveSettings = vi.fn();
const mockListModels = vi.fn();
const mockOllamaStatus = vi.fn();
const mockSetApiKey = vi.fn();
const mockVerifyApiKey = vi.fn();
const mockOllamaInstall = vi.fn();
const mockDownloadModel = vi.fn();
const mockSetActiveModel = vi.fn();
const mockOpenUrl = vi.fn();
const mockOnVokariEvent = vi.fn();

vi.mock("../bridge", () => ({
  DEFAULT_SETTINGS: {
    brain: "claude", ollamaEndpoint: "http://localhost:11434", ollamaModel: "qwen2.5:7b",
    whisperModel: "large-v3-turbo", claudeModel: "claude-sonnet-4-6", briefingDir: "",
    obsidianVault: "", defaultMode: "solo", transcriptionLanguage: "it",
    livePreview: true, liveModel: "base", onboarded: false, lastSeenVersion: "", appLanguage: "it", hasApiKey: false,
  },
  bridge: {
    getSettings: () => mockGetSettings(),
    saveSettings: (patch: Record<string, unknown>) => mockSaveSettings(patch),
    listModels: () => mockListModels() as Promise<ModelEntry[]>,
    ollamaStatus: () => mockOllamaStatus(),
    setApiKey: (k: string) => mockSetApiKey(k),
    verifyApiKey: () => mockVerifyApiKey(),
    ollamaInstall: () => mockOllamaInstall(),
    downloadModel: (n: string) => mockDownloadModel(n),
    setActiveModel: (n: string) => mockSetActiveModel(n),
    openUrl: (u: string) => mockOpenUrl(u),
  },
  onVokariEvent: (h: unknown) => mockOnVokariEvent(h) as () => void,
}));

import { ScreenOnboarding } from "./Onboarding";

const FAKE_SETTINGS = {
  brain: "claude", ollamaEndpoint: "http://localhost:11434", ollamaModel: "qwen2.5:7b",
  whisperModel: "large-v3-turbo", claudeModel: "claude-sonnet-4-6", briefingDir: "",
  obsidianVault: "", defaultMode: "solo", transcriptionLanguage: "it",
  livePreview: true, liveModel: "base", onboarded: false, lastSeenVersion: "", appLanguage: "it", hasApiKey: false,
};

const FAKE_MODELS: ModelEntry[] = [
  { name: "large-v3-turbo", sizeLabel: "~1.6 GB", speed: 4, quality: 4, languages: "IT·EN·+90", description: "Consigliato", recommended: true, state: "available" },
  { name: "small", sizeLabel: "~0.5 GB", speed: 5, quality: 2, languages: "IT·EN·+90", description: "Leggero", recommended: false, state: "available" },
];

describe("ScreenOnboarding", () => {
  beforeEach(() => {
    mockGetSettings.mockResolvedValue({ ...FAKE_SETTINGS });
    mockSaveSettings.mockResolvedValue({ ...FAKE_SETTINGS });
    mockListModels.mockResolvedValue([...FAKE_MODELS]);
    mockOllamaStatus.mockResolvedValue({ installed: false, running: false, canInstall: true });
    mockSetApiKey.mockResolvedValue({ ok: true, hasApiKey: true });
    mockVerifyApiKey.mockResolvedValue({ ok: true, reachable: true, error: "" });
    mockOnVokariEvent.mockReturnValue(() => {});
  });
  afterEach(() => vi.clearAllMocks());

  it("parte dal passo Benvenuto", async () => {
    render(<ScreenOnboarding onDone={() => {}} />);
    expect(await screen.findByText(/Benvenuto in VOKARI/)).toBeInTheDocument();
  });

  it("'Salta' chiude il wizard (onDone)", async () => {
    const onDone = vi.fn();
    render(<ScreenOnboarding onDone={onDone} />);
    fireEvent.click(await screen.findByRole("button", { name: "Salta" }));
    expect(onDone).toHaveBeenCalledTimes(1);
  });

  it("scegliere 'Locale (Ollama)' al passo 2 salva brain=ollama", async () => {
    render(<ScreenOnboarding onDone={() => {}} />);
    fireEvent.click(await screen.findByRole("button", { name: /Avanti/ })); // → passo Cervello AI
    fireEvent.click(await screen.findByText("Locale (Ollama)"));
    await waitFor(() => expect(mockSaveSettings).toHaveBeenCalledWith({ brain: "ollama" }));
  });

  it("naviga fino all'ultimo passo e 'Inizia a registrare' chiama onDone", async () => {
    const onDone = vi.fn();
    render(<ScreenOnboarding onDone={onDone} />);
    // 3 click su Avanti: Benvenuto → Cervello → Trascrizione → Pronto
    for (let i = 0; i < 3; i++) {
      fireEvent.click(await screen.findByRole("button", { name: /Avanti/ }));
    }
    fireEvent.click(await screen.findByRole("button", { name: /Inizia a registrare/ }));
    expect(onDone).toHaveBeenCalledTimes(1);
  });

  it("al passo Trascrizione offre i modelli e il Download chiama downloadModel", async () => {
    render(<ScreenOnboarding onDone={() => {}} />);
    fireEvent.click(await screen.findByRole("button", { name: /Avanti/ })); // Cervello AI
    fireEvent.click(await screen.findByRole("button", { name: /Avanti/ })); // Trascrizione
    expect(await screen.findByText("large-v3-turbo")).toBeInTheDocument();
    const dl = await screen.findAllByRole("button", { name: /Scarica/ });
    fireEvent.click(dl[0]);
    await waitFor(() => expect(mockDownloadModel).toHaveBeenCalled());
  });
});

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { LhmStatus, ModelEntry, VokariSettings } from "../bridge";

// ────────────────────────────────────────────────────────────
// Mock dell'intero modulo bridge prima di importare Settings
// ────────────────────────────────────────────────────────────
const FAKE_SETTINGS: VokariSettings = {
  brain: "claude",
  ollamaEndpoint: "http://localhost:11434",
  ollamaModel: "gemma2:9b",
  whisperModel: "large-v3-turbo",
  claudeModel: "claude-opus-4-8",
  briefingDir: "/home/user/briefing",
  obsidianVault: "/home/user/vault",
  defaultMode: "riunione",
  transcriptionLanguage: "it",
  livePreview: true,
  liveModel: "base",
  onboarded: true,
  lastSeenVersion: "",
  appLanguage: "it",
  userContext: "",
  hasApiKey: true,
};

const FAKE_MODELS: ModelEntry[] = [
  { name: "small", sizeLabel: "~0.5 GB", speed: 5, quality: 2, languages: "IT·EN·+90", description: "Veloce", recommended: false, state: "available" },
  { name: "large-v3-turbo", sizeLabel: "~1.6 GB", speed: 4, quality: 4, languages: "IT·EN·+90", description: "Consigliato", recommended: true, state: "active" },
];

const mockGetSettings = vi.fn();
const mockSaveSettings = vi.fn();
const mockSetApiKey = vi.fn();
const mockDeleteApiKey = vi.fn();
const mockVerifyApiKey = vi.fn();
const mockBrowseFolder = vi.fn();
const mockListModels = vi.fn();
const mockDownloadModel = vi.fn();
const mockSetActiveModel = vi.fn();
const mockLhmStatus = vi.fn();
const mockOllamaStatus = vi.fn();
const mockOnVokariEvent = vi.fn();

vi.mock("../bridge", () => ({
  // valore iniziale di useState (poi sovrascritto da getSettings nel test). Inline perché
  // la factory di vi.mock non può referenziare variabili out-of-scope non-`mock*`.
  DEFAULT_SETTINGS: {
    brain: "claude", ollamaEndpoint: "http://localhost:11434", ollamaModel: "gemma2:9b",
    whisperModel: "large-v3-turbo", claudeModel: "claude-opus-4-8", briefingDir: "",
    obsidianVault: "", defaultMode: "solo", transcriptionLanguage: "auto",
    livePreview: true, liveModel: "base", userContext: "", hasApiKey: false,
  },
  bridge: {
    getSettings: () => mockGetSettings() as Promise<VokariSettings>,
    saveSettings: (patch: Partial<Omit<VokariSettings, "hasApiKey">>) =>
      mockSaveSettings(patch) as Promise<VokariSettings>,
    setApiKey: (key: string) => mockSetApiKey(key) as Promise<{ ok: boolean; hasApiKey: boolean }>,
    deleteApiKey: () => mockDeleteApiKey() as Promise<{ ok: boolean; hasApiKey: boolean }>,
    verifyApiKey: () => mockVerifyApiKey() as Promise<{ ok: boolean; reachable: boolean; error: string }>,
    browseFolder: () => mockBrowseFolder() as Promise<{ path: string }>,
    listModels: () => mockListModels() as Promise<ModelEntry[]>,
    downloadModel: (name: string) => mockDownloadModel(name) as Promise<{ ok: boolean }>,
    setActiveModel: (name: string) => mockSetActiveModel(name) as Promise<VokariSettings>,
    lhmStatus: () => mockLhmStatus() as Promise<LhmStatus>,
    ollamaStatus: () => mockOllamaStatus() as Promise<{ installed: boolean; running: boolean; canInstall: boolean }>,
    lhmInstall: vi.fn().mockResolvedValue({ ok: true }),
    lhmStart: vi.fn().mockResolvedValue({ ok: true }),
    lhmStop: vi.fn().mockResolvedValue({ ok: true }),
    lhmUninstall: vi.fn().mockResolvedValue({ ok: true }),
    openUrl: vi.fn().mockResolvedValue({ ok: true }),
  },
  onVokariEvent: (handler: (event: string, payload: Record<string, unknown>) => void) =>
    mockOnVokariEvent(handler) as () => void,
}));

vi.mock("../confirm", () => ({ confirmDialog: vi.fn().mockResolvedValue(true) }));
vi.mock("../toast", () => ({ toast: vi.fn() }));

import { ScreenSettings } from "./Settings";

describe("ScreenSettings", () => {
  beforeEach(() => {
    mockGetSettings.mockResolvedValue({ ...FAKE_SETTINGS });
    mockSaveSettings.mockResolvedValue({ ...FAKE_SETTINGS });
    mockSetApiKey.mockResolvedValue({ ok: true, hasApiKey: true });
    mockDeleteApiKey.mockResolvedValue({ ok: true, hasApiKey: false });
    mockVerifyApiKey.mockResolvedValue({ ok: true, reachable: true, error: "" });
    mockBrowseFolder.mockResolvedValue({ path: "" });
    mockListModels.mockResolvedValue([...FAKE_MODELS]);
    mockSetActiveModel.mockResolvedValue({ ...FAKE_SETTINGS });
    mockLhmStatus.mockResolvedValue({ installed: false, running: false, canInstall: true });
    mockOllamaStatus.mockResolvedValue({ installed: false, running: false, canInstall: true });
    mockOnVokariEvent.mockReturnValue(() => {});
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  // Clicca il "Verifica" del runtime Ollama (≠ quello della chiave API), scope al campo Endpoint.
  async function clickOllamaVerify() {
    const label = await screen.findByText(/Endpoint Ollama/);
    const field = label.closest(".vk-field") as HTMLElement;
    fireEvent.click(within(field).getByRole("button", { name: "Verifica" }));
  }

  it("B2: Ollama installato ma fermo → messaggio 'avvialo' (non 'installalo')", async () => {
    mockOllamaStatus.mockResolvedValue({ installed: true, running: false, canInstall: true });
    render(<ScreenSettings />);
    await clickOllamaVerify();
    expect(await screen.findByText(/installato ma fermo/i)).toBeInTheDocument();
  });

  it("B2: Ollama non installato → messaggio 'installalo' (non 'avvialo')", async () => {
    mockOllamaStatus.mockResolvedValue({ installed: false, running: false, canInstall: true });
    render(<ScreenSettings />);
    await clickOllamaVerify();
    expect(await screen.findByText(/non installato — installalo/i)).toBeInTheDocument();
  });

  it("carica e mostra le impostazioni reali da getSettings", async () => {
    render(<ScreenSettings />);
    // defaultMode="riunione" → il pulsante "Riunione" deve avere classe "on"
    await waitFor(() => {
      const btn = screen.getByRole("button", { name: "Riunione" });
      expect(btn.className).toContain("on");
    });
    // hasApiKey=true → vista mascherata "(impostata)" (niente input editabile finché non si Sostituisce)
    expect(screen.getByText(/\(impostata\)/)).toBeInTheDocument();
  });

  it("NON mostra un valore di chiave API precaricato nel campo input", async () => {
    render(<ScreenSettings />);
    await waitFor(() => screen.getByText(/\(impostata\)/));
    // "Sostituisci" rivela l'input: il campo type=password non deve avere un value precaricato
    fireEvent.click(screen.getByRole("button", { name: "Sostituisci" }));
    const input = screen.getByPlaceholderText(/impostata/) as HTMLInputElement;
    expect(input.value).toBe("");
  });

  it("chiama saveSettings quando si cambia defaultMode", async () => {
    render(<ScreenSettings />);
    await waitFor(() => screen.getByRole("button", { name: "Riunione" }));
    fireEvent.click(screen.getByRole("button", { name: "Solo" }));
    await waitFor(() => {
      expect(mockSaveSettings).toHaveBeenCalledWith({ defaultMode: "solo" });
    });
  });

  it("chiama saveSettings quando si cambia brain su Ollama", async () => {
    render(<ScreenSettings />);
    await waitFor(() => screen.getByRole("button", { name: "Claude API" }));
    fireEvent.click(screen.getByRole("button", { name: "Locale (Ollama)" }));
    await waitFor(() => {
      expect(mockSaveSettings).toHaveBeenCalledWith({ brain: "ollama" });
    });
  });

  it("chiama setApiKey onBlur quando c'è testo nel campo chiave", async () => {
    render(<ScreenSettings />);
    await waitFor(() => screen.getByText(/\(impostata\)/));
    fireEvent.click(screen.getByRole("button", { name: "Sostituisci" }));
    const input = screen.getByPlaceholderText(/impostata/) as HTMLInputElement;
    fireEvent.change(input, { target: { value: "sk-ant-test" } });
    fireEvent.blur(input);
    await waitFor(() => {
      expect(mockSetApiKey).toHaveBeenCalledWith("sk-ant-test");
    });
  });

  it("mostra lingua corrente come attiva", async () => {
    render(<ScreenSettings />);
    // scoping al campo "Lingua di trascrizione": esiste anche il selettore lingua dell'app
    // con bottoni "Italiano"/"English" → una query non scopata sarebbe ambigua.
    const field = (await screen.findByText("Lingua di trascrizione")).closest(".vk-field") as HTMLElement;
    await waitFor(() => {
      const btn = within(field).getByRole("button", { name: "Italiano" });
      expect(btn.className).toContain("on");
    });
  });

  it("chiama saveSettings per transcriptionLanguage", async () => {
    render(<ScreenSettings />);
    const field = (await screen.findByText("Lingua di trascrizione")).closest(".vk-field") as HTMLElement;
    fireEvent.click(within(field).getByRole("button", { name: "English" }));
    await waitFor(() => {
      expect(mockSaveSettings).toHaveBeenCalledWith({ transcriptionLanguage: "en" });
    });
  });

  it("LHM: in MSIX (canInstall=false) guida all'install manuale, niente bottone Installa", async () => {
    mockLhmStatus.mockResolvedValue({ installed: false, running: false, canInstall: false });
    render(<ScreenSettings />);
    // testo guida con link a LibreHardwareMonitor (ramo Store)
    expect(await screen.findByText(/LibreHardwareMonitor/)).toBeInTheDocument();
    expect(screen.getByText(/Microsoft Store/)).toBeInTheDocument();
    // nessun bottone "Installa" (auto-download vietato in pacchetto)
    expect(screen.queryByRole("button", { name: "Installa" })).not.toBeInTheDocument();
  });

  it("nasconde la sezione Temperatura CPU quando supported=false", async () => {
    mockLhmStatus.mockResolvedValue({ installed: false, running: false, canInstall: false, supported: false });
    render(<ScreenSettings />);
    // Attende che lhmStatus carichi e la sezione sparisca (è visibile durante il loading)
    await waitFor(() => {
      expect(screen.queryByText(/Temperatura CPU/i)).toBeNull();
    });
  });
});

describe("ScreenSettings — verifica/rimuovi chiave API (SET1/SET2)", () => {
  beforeEach(() => {
    mockGetSettings.mockResolvedValue({ ...FAKE_SETTINGS, hasApiKey: true });
    mockListModels.mockResolvedValue([...FAKE_MODELS]);
    mockSetActiveModel.mockResolvedValue({ ...FAKE_SETTINGS });
    mockLhmStatus.mockResolvedValue({ installed: false, running: false, canInstall: true });
    mockOnVokariEvent.mockReturnValue(() => {});
  });
  afterEach(() => vi.clearAllMocks());

  // "Verifica" esiste due volte (chiave API + runtime Ollama vk-mini) → scope a .vk-key.
  async function clickKeyVerify(container: HTMLElement) {
    await screen.findByRole("button", { name: "Sostituisci" }); // attende il render della riga chiave
    const keyRow = container.querySelector(".vk-key") as HTMLElement;
    fireEvent.click(within(keyRow).getByRole("button", { name: "Verifica" }));
  }

  it("SET1: 'Verifica' chiama verifyApiKey e mostra l'esito valido", async () => {
    mockVerifyApiKey.mockResolvedValue({ ok: true, reachable: true, error: "" });
    const { container } = render(<ScreenSettings />);
    await clickKeyVerify(container);
    await waitFor(() => expect(mockVerifyApiKey).toHaveBeenCalled());
    expect(await screen.findByText(/Chiave valida/)).toBeInTheDocument();
  });

  it("SET1: chiave non valida mostra il messaggio d'errore", async () => {
    mockVerifyApiKey.mockResolvedValue({ ok: false, reachable: true, error: "Chiave API non valida o scaduta." });
    const { container } = render(<ScreenSettings />);
    await clickKeyVerify(container);
    expect(await screen.findByText("Chiave API non valida o scaduta.")).toBeInTheDocument();
  });

  it("SET2: 'Rimuovi' previa conferma chiama deleteApiKey e ricompare l'input chiave", async () => {
    const { confirmDialog } = await import("../confirm");
    (confirmDialog as ReturnType<typeof vi.fn>).mockResolvedValue(true);
    mockDeleteApiKey.mockResolvedValue({ ok: true, hasApiKey: false });
    render(<ScreenSettings />);
    fireEvent.click(await screen.findByRole("button", { name: "Rimuovi" }));
    await waitFor(() => expect(confirmDialog).toHaveBeenCalled());
    await waitFor(() => expect(mockDeleteApiKey).toHaveBeenCalled());
    expect(await screen.findByPlaceholderText("sk-ant-…")).toBeInTheDocument();
  });

  it("SET2: 'Rimuovi' annullato NON chiama deleteApiKey", async () => {
    const { confirmDialog } = await import("../confirm");
    (confirmDialog as ReturnType<typeof vi.fn>).mockResolvedValue(false);
    render(<ScreenSettings />);
    fireEvent.click(await screen.findByRole("button", { name: "Rimuovi" }));
    await waitFor(() => expect(confirmDialog).toHaveBeenCalled());
    expect(mockDeleteApiKey).not.toHaveBeenCalled();
  });
});

describe("ScreenSettings — sezione Il tuo contesto", () => {
  beforeEach(() => {
    mockGetSettings.mockResolvedValue({ ...FAKE_SETTINGS, userContext: "" });
    mockSaveSettings.mockResolvedValue({ ...FAKE_SETTINGS, userContext: "magazzino alimentare" });
    mockListModels.mockResolvedValue([...FAKE_MODELS]);
    mockLhmStatus.mockResolvedValue({ installed: false, running: false, canInstall: true });
    mockOnVokariEvent.mockReturnValue(() => {});
  });
  afterEach(() => vi.clearAllMocks());

  it("mostra e salva il campo Il tuo contesto", async () => {
    render(<ScreenSettings />);
    // Attende la textarea con il placeholder IT verbatim (da i18n lng:"it")
    const textarea = await screen.findByPlaceholderText(/Magazzino alimentare/);
    expect(textarea).toBeInTheDocument();
    fireEvent.change(textarea, { target: { value: "magazzino alimentare" } });
    fireEvent.blur(textarea);
    await waitFor(() => {
      expect(mockSaveSettings).toHaveBeenCalledWith({ userContext: "magazzino alimentare" });
    });
  });
});

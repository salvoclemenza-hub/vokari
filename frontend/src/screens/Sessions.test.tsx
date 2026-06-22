import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Artifacts } from "../bridge";

// ────────────────────────────────────────────────────────────
// SessionItem shape (mirrors bridge export)
// ────────────────────────────────────────────────────────────
interface SessionItem {
  id: string;
  title: string;
  createdAt: string;
  mode: string;
  model: string;
  durationMs: number;
  hasBriefing: boolean;
  hasRecap: boolean;
  hasObsidian: boolean;
  clarCount?: number;
  hasAudio?: boolean;
}

const FAKE_SESSIONS: SessionItem[] = [
  {
    id: "aaa111", title: "Riunione prodotto Q3", createdAt: "2026-06-07T09:41:00Z",
    mode: "riunione", model: "large-v3-turbo", durationMs: 2304000,
    hasBriefing: true, hasRecap: true, hasObsidian: true,
  },
  {
    id: "bbb222", title: "Memo idee app", createdAt: "2026-06-07T08:05:00Z",
    mode: "solo", model: "large-v3-turbo", durationMs: 432000,
    hasBriefing: true, hasRecap: true, hasObsidian: false,
  },
];

const FAKE_ARTIFACTS: Artifacts = {
  title: "Riunione prodotto Q3",
  briefingMd: "# Briefing", briefingPath: "/x/b.md",
  recapMd: "# Recap", obsidianNote: "# Nota",
  transcriptText: "",
  durationS: 2304, model: "large-v3-turbo", language: "it", wordCount: 800,
};

const mockListSessions = vi.fn();
const mockSearchSessions = vi.fn();
const mockOpenSession = vi.fn();
const mockDeleteSession = vi.fn();
const mockDeleteSessions = vi.fn();
const mockPlaySessionAudio = vi.fn();

vi.mock("../bridge", () => ({
  bridge: {
    listSessions: () => mockListSessions() as Promise<SessionItem[]>,
    searchSessions: (q: string) => mockSearchSessions(q) as Promise<SessionItem[]>,
    openSession: (id: string) => mockOpenSession(id) as Promise<Artifacts | null>,
    deleteSession: (id: string) => mockDeleteSession(id) as Promise<{ ok: boolean }>,
    deleteSessions: (ids: string[]) => mockDeleteSessions(ids) as Promise<{ ok: boolean; deleted: number }>,
    playSessionAudio: (id: string) => mockPlaySessionAudio(id) as Promise<{ ok: boolean; error?: string }>,
    browseAudioFile: () => Promise.resolve({ path: "" }),
  },
  onVokariEvent: () => () => {},
}));

vi.mock("../confirm", () => ({ confirmDialog: vi.fn().mockResolvedValue(true) }));
vi.mock("../toast", () => ({ toast: vi.fn() }));

import { ScreenSessions } from "./Sessions";

describe("ScreenSessions", () => {
  beforeEach(() => {
    mockListSessions.mockResolvedValue([...FAKE_SESSIONS]);
    mockSearchSessions.mockResolvedValue([...FAKE_SESSIONS]);
    mockOpenSession.mockResolvedValue({ ...FAKE_ARTIFACTS });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("carica e mostra le sessioni reali da listSessions", async () => {
    render(<ScreenSessions />);
    await waitFor(() => {
      expect(screen.getByText("Riunione prodotto Q3")).toBeInTheDocument();
      expect(screen.getByText("Memo idee app")).toBeInTheDocument();
    });
    expect(mockListSessions).toHaveBeenCalled();
  });

  it("le righe sessione mostrano la modalità e il modello", async () => {
    render(<ScreenSessions />);
    await waitFor(() => screen.getByText("Riunione prodotto Q3"));
    // mode "riunione" → "Riunione", "solo" → "Solo" — getAllByText perché "Riunione"
    // compare sia nel titolo che nella colonna mode
    expect(screen.getAllByText("Riunione").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Solo").length).toBeGreaterThanOrEqual(1);
  });

  it("la ricerca chiama searchSessions con la query inserita", async () => {
    render(<ScreenSessions />);
    await waitFor(() => screen.getByText("Riunione prodotto Q3"));

    const searchInput = screen.getByRole("searchbox");
    fireEvent.change(searchInput, { target: { value: "riunione" } });

    await waitFor(() => {
      expect(mockSearchSessions).toHaveBeenCalledWith("riunione");
    });
  });

  it("clic su riga chiama onOpen con l'id della sessione", async () => {
    const onOpen = vi.fn();
    render(<ScreenSessions onOpen={onOpen} />);
    await waitFor(() => screen.getByText("Riunione prodotto Q3"));

    fireEvent.click(screen.getByText("Riunione prodotto Q3"));

    await waitFor(() => {
      expect(onOpen).toHaveBeenCalledWith("aaa111");
    });
  });

  it("filtro Solo mostra solo le sessioni mode=solo", async () => {
    render(<ScreenSessions />);
    await waitFor(() => screen.getByText("Riunione prodotto Q3"));

    fireEvent.click(screen.getByRole("button", { name: "Solo" }));

    await waitFor(() => {
      expect(screen.queryByText("Riunione prodotto Q3")).not.toBeInTheDocument();
      expect(screen.getByText("Memo idee app")).toBeInTheDocument();
    });
  });

  it("filtro Tutte mostra tutte le sessioni dopo filtraggio", async () => {
    render(<ScreenSessions />);
    await waitFor(() => screen.getByText("Riunione prodotto Q3"));

    fireEvent.click(screen.getByRole("button", { name: "Solo" }));
    fireEvent.click(screen.getByRole("button", { name: "Tutte" }));

    await waitFor(() => {
      expect(screen.getByText("Riunione prodotto Q3")).toBeInTheDocument();
      expect(screen.getByText("Memo idee app")).toBeInTheDocument();
    });
  });

  it("MDL3: elimina singola — rimozione ottimistica + toast Annulla, niente modale", async () => {
    const { toast } = await import("../toast");
    const { confirmDialog } = await import("../confirm");
    render(<ScreenSessions />);
    await waitFor(() => screen.getByText("Riunione prodotto Q3"));

    fireEvent.click(screen.getAllByRole("button", { name: /Elimina/i })[0]);
    // niente conferma modale per la singola
    expect(confirmDialog).not.toHaveBeenCalled();
    // riga rimossa subito (ottimistico)
    await waitFor(() => expect(screen.queryByText("Riunione prodotto Q3")).not.toBeInTheDocument());
    // toast con azione "Annulla"
    const undoCall = (toast as ReturnType<typeof vi.fn>).mock.calls.find((c) => c[2]?.action);
    expect(undoCall).toBeTruthy();
    expect(undoCall![2].action.label).toBe("Annulla");
  });

  it("MDL3: senza Annulla, dopo la finestra conferma deleteSession", async () => {
    mockDeleteSession.mockResolvedValue({ ok: true });
    render(<ScreenSessions />);
    await waitFor(() => screen.getByText("Riunione prodotto Q3"));
    vi.useFakeTimers();
    try {
      fireEvent.click(screen.getAllByRole("button", { name: /Elimina/i })[0]);
      await vi.advanceTimersByTimeAsync(5000);
      expect(mockDeleteSession).toHaveBeenCalledWith("aaa111");
    } finally {
      vi.useRealTimers();
    }
  });

  it("MDL3: Annulla nel toast NON elimina la sessione", async () => {
    const { toast } = await import("../toast");
    mockDeleteSession.mockResolvedValue({ ok: true });
    render(<ScreenSessions />);
    await waitFor(() => screen.getByText("Riunione prodotto Q3"));
    vi.useFakeTimers();
    try {
      fireEvent.click(screen.getAllByRole("button", { name: /Elimina/i })[0]);
      const undoCall = (toast as ReturnType<typeof vi.fn>).mock.calls.find((c) => c[2]?.action);
      act(() => undoCall![2].action.onClick()); // clic su "Annulla"
      await vi.advanceTimersByTimeAsync(6000);  // oltre la finestra
      expect(mockDeleteSession).not.toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });

  it("Importa audio chiama onImport se fornita", async () => {
    const onImport = vi.fn();
    render(<ScreenSessions onImport={onImport} />);
    await waitFor(() => screen.getByText("Importa audio"));

    fireEvent.click(screen.getByText("Importa audio"));
    expect(onImport).toHaveBeenCalled();
  });
});

describe("ScreenSessions — chip domande da chiarire (S1)", () => {
  beforeEach(() => {
    mockListSessions.mockResolvedValue([
      { id: "s1", title: "Riunione con domande aperte", createdAt: "2026-06-15T09:12:00", mode: "riunione",
        model: "large-v3-turbo", durationMs: 60000, hasBriefing: true, hasRecap: true, hasObsidian: true, clarCount: 2 },
      { id: "s2", title: "Sessione completa", createdAt: "2026-06-15T15:40:00", mode: "solo",
        model: "small", durationMs: 30000, hasBriefing: true, hasRecap: false, hasObsidian: false, clarCount: 0 },
    ]);
  });

  it("mostra '? N' solo sulle sessioni con clarCount > 0", async () => {
    render(<ScreenSessions />);
    const chip = await screen.findByTitle("2 domande da chiarire");
    expect(chip).toHaveTextContent("? 2");
    // la sessione con clarCount=0 non ha chip → un solo chip in tutta la lista
    expect(screen.queryAllByTitle(/domand[ae] da chiarire/)).toHaveLength(1);
  });
});

describe("ScreenSessions — play audio (S2)", () => {
  beforeEach(() => {
    mockPlaySessionAudio.mockResolvedValue({ ok: true });
    mockListSessions.mockResolvedValue([
      { id: "s1", title: "Con audio", createdAt: "2026-06-15T09:12:00", mode: "solo",
        model: "small", durationMs: 60000, hasBriefing: true, hasRecap: false, hasObsidian: false, clarCount: 0, hasAudio: true },
      { id: "s2", title: "Senza audio", createdAt: "2026-06-15T10:12:00", mode: "solo",
        model: "small", durationMs: 60000, hasBriefing: true, hasRecap: false, hasObsidian: false, clarCount: 0, hasAudio: false },
    ]);
  });

  it("il bottone Riproduci compare solo se hasAudio, chiama playSessionAudio e NON apre la sessione", async () => {
    const onOpen = vi.fn();
    render(<ScreenSessions onOpen={onOpen} />);
    await screen.findByText("Con audio");
    const playButtons = screen.getAllByRole("button", { name: /Apri l'audio/i });
    expect(playButtons).toHaveLength(1); // solo la sessione con hasAudio
    fireEvent.click(playButtons[0]);
    await waitFor(() => expect(mockPlaySessionAudio).toHaveBeenCalledWith("s1"));
    expect(onOpen).not.toHaveBeenCalled(); // stopPropagation: il clic non apre la sessione
  });

  it("su errore (file sparito) mostra un toast", async () => {
    const { toast } = await import("../toast");
    mockPlaySessionAudio.mockResolvedValue({ ok: false, error: "file audio non trovato" });
    render(<ScreenSessions />);
    await screen.findByText("Con audio");
    fireEvent.click(screen.getByRole("button", { name: /Apri l'audio/i }));
    await waitFor(() => expect(toast).toHaveBeenCalledWith("file audio non trovato", "error"));
  });
});

describe("ScreenSessions multi-select", () => {
  beforeEach(() => {
    mockListSessions.mockResolvedValue([
      { id: "a", title: "Alfa", createdAt: "", mode: "solo", model: "base", durationMs: 1000, hasBriefing: true, hasRecap: false, hasObsidian: false },
      { id: "b", title: "Beta", createdAt: "", mode: "solo", model: "base", durationMs: 2000, hasBriefing: true, hasRecap: false, hasObsidian: false },
    ]);
  });

  it("seleziona righe e abilita Elimina N", async () => {
    render(<ScreenSessions />);
    await waitFor(() => expect(screen.getByText("Alfa")).toBeInTheDocument());
    const checks = screen.getAllByRole("checkbox");
    await userEvent.click(checks[1]); // prima riga (checks[0] = seleziona tutto)
    expect(await screen.findByText(/Elimina 1/)).toBeInTheDocument();
  });
});

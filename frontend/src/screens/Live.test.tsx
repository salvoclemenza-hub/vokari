import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ScreenLive } from "./Live";

vi.mock("../confirm", () => ({ confirmDialog: vi.fn().mockResolvedValue(false) }));

vi.mock("../bridge", () => ({
  bridge: {
    startRecording: vi.fn(() => Promise.resolve({ ok: true })),
    addMarker: vi.fn(() => Promise.resolve({ t_ms: 1000, label: "Segnalibro 1" })),
    updateMarker: vi.fn(() => Promise.resolve({ t_ms: 1000, label: "Lotto X" })),
    pauseRecording: vi.fn(() => Promise.resolve({ ok: true, paused: true })),
    resumeRecording: vi.fn(() => Promise.resolve({ ok: true, paused: false })),
  },
  // Mini-bus fedele al reale: registra gli handler e li invoca via window.__vokari_emit.
  onVokariEvent: (h: (e: string, p: Record<string, unknown>) => void) => {
    const w = window as unknown as {
      __vokari_handlers?: Set<typeof h>;
      __vokari_emit?: (e: string, p: Record<string, unknown>) => void;
    };
    (w.__vokari_handlers ??= new Set()).add(h);
    w.__vokari_emit = (e, p) => { for (const fn of w.__vokari_handlers ?? []) fn(e, p); };
    return () => { w.__vokari_handlers?.delete(h); };
  },
}));

describe("ScreenLive", () => {
  it("al mount NON chiama startRecording (la registrazione è già avviata dalla Home)", async () => {
    const { bridge } = await import("../bridge");
    (bridge.startRecording as ReturnType<typeof vi.fn>).mockClear();
    render(<ScreenLive source="both" onStop={() => {}} />);
    // Aspetta un tick per assicurarsi che nessun effetto asincrono chiami startRecording
    await new Promise((r) => setTimeout(r, 50));
    expect(bridge.startRecording).not.toHaveBeenCalled();
  });

  it("clicca Stop e trascrivi e segnala onStop con la sorgente passata via prop", () => {
    const onStop = vi.fn();
    render(<ScreenLive source="mic" onStop={onStop} />);
    fireEvent.click(screen.getByRole("button", { name: /Stop e trascrivi/i }));
    expect(onStop).toHaveBeenCalled();
  });

  it("mostra una sola lane quando la sorgente non è 'both'", () => {
    const { container } = render(<ScreenLive source="system" onStop={() => {}} />);
    expect(container.querySelectorAll(".vk-lane").length).toBe(1);
  });

  it("l'input titolo mostra il placeholder e il valore della prop", () => {
    render(<ScreenLive source="mic" title="Demo" onStop={() => {}} />);
    const input = screen.getByLabelText("Titolo sessione") as HTMLInputElement;
    expect(input.placeholder).toBe("Sessione senza titolo");
    expect(input.value).toBe("Demo");
  });

  it("digitando nel titolo chiama onTitleChange", () => {
    const onTitleChange = vi.fn();
    render(<ScreenLive source="mic" title="" onTitleChange={onTitleChange} onStop={() => {}} />);
    fireEvent.change(screen.getByLabelText("Titolo sessione"), { target: { value: "Nuovo" } });
    expect(onTitleChange).toHaveBeenCalledWith("Nuovo");
  });

  it("clicca Pausa → chiama pauseRecording e il bottone diventa 'Riprendi'", async () => {
    const { bridge } = await import("../bridge");
    (bridge.pauseRecording as ReturnType<typeof vi.fn>).mockClear();
    render(<ScreenLive source="mic" onStop={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: /^Pausa$/i }));
    expect(bridge.pauseRecording).toHaveBeenCalled();
    expect(await screen.findByRole("button", { name: /Riprendi/i })).toBeInTheDocument();
  });

  it("da pausa, clicca Riprendi → chiama resumeRecording e torna 'Pausa'", async () => {
    const { bridge } = await import("../bridge");
    (bridge.resumeRecording as ReturnType<typeof vi.fn>).mockClear();
    render(<ScreenLive source="mic" onStop={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: /^Pausa$/i }));
    fireEvent.click(await screen.findByRole("button", { name: /Riprendi/i }));
    expect(bridge.resumeRecording).toHaveBeenCalled();
    expect(await screen.findByRole("button", { name: /^Pausa$/i })).toBeInTheDocument();
  });

  it("evento audio_level aggiorna il dB reale mostrato per la lane", async () => {
    render(<ScreenLive source="mic" onStop={() => {}} />);
    const emit = (window as unknown as { __vokari_emit?: (e: string, p: Record<string, unknown>) => void }).__vokari_emit;
    await act(async () => { emit?.("audio_level", { lane: "mic", db: -9 }); });
    expect(await screen.findByText("-9 dB")).toBeInTheDocument();
  });

  it("clicca Annulla e conferma → invoca il callback onCancel", async () => {
    const { confirmDialog } = await import("../confirm");
    (confirmDialog as ReturnType<typeof vi.fn>).mockResolvedValue(true);
    const onCancel = vi.fn();
    render(<ScreenLive source="mic" onStop={() => {}} onCancel={onCancel} />);
    fireEvent.click(screen.getByRole("button", { name: /Annulla/i }));
    expect(confirmDialog).toHaveBeenCalled();
    await waitFor(() => expect(onCancel).toHaveBeenCalled());
  });

  it("clicca Annulla e NON conferma → onCancel NON viene invocato (niente perdita audio)", async () => {
    const { confirmDialog } = await import("../confirm");
    (confirmDialog as ReturnType<typeof vi.fn>).mockResolvedValue(false);
    const onCancel = vi.fn();
    render(<ScreenLive source="mic" onStop={() => {}} onCancel={onCancel} />);
    fireEvent.click(screen.getByRole("button", { name: /Annulla/i }));
    await Promise.resolve();
    expect(onCancel).not.toHaveBeenCalled();
  });

  it("editando l'etichetta di un segnalibro chiama bridge.updateMarker", async () => {
    const { bridge } = await import("../bridge");
    (bridge.updateMarker as ReturnType<typeof vi.fn>).mockClear();
    render(<ScreenLive source="mic" onStop={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: /^segnalibro/i }));
    const input = (await screen.findByLabelText(/Etichetta segnalibro 1/i)) as HTMLInputElement;
    fireEvent.change(input, { target: { value: "Lotto X" } });
    fireEvent.blur(input);
    expect(bridge.updateMarker).toHaveBeenCalledWith(0, "Lotto X");
  });
});

describe("ScreenLive campo contesto", () => {
  it("mostra il campo contesto e chiama onContextChange digitando", () => {
    const onContextChange = vi.fn();
    render(<ScreenLive source="mic" context="" onContextChange={onContextChange} />);
    const input = screen.getByLabelText(/Di cosa parla/i);
    fireEvent.change(input, { target: { value: "landing page" } });
    expect(onContextChange).toHaveBeenCalledWith("landing page");
  });
});

describe("ScreenLive anteprima live", () => {
  it("mostra il testo dall'evento live_transcript quando l'anteprima è attiva", async () => {
    render(<ScreenLive source="mic" livePreviewActive />);
    await act(async () => {
      window.__vokari_emit?.("live_transcript", { text: "ciao questa è la bozza" });
    });
    expect(await screen.findByText(/questa è la bozza/)).toBeInTheDocument();
  });

  it("NON mostra il pannello anteprima quando l'anteprima non è attiva (gating onesto)", () => {
    // live_preview off oppure live_model==whisper_model → nessun live_transcript arriverebbe:
    // il pannello resterebbe "In ascolto…" per sempre, quindi va nascosto.
    const { container } = render(<ScreenLive source="mic" />);
    expect(container.querySelector(".vk-live-transcript")).toBeNull();
  });
});

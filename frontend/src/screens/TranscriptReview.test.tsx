import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ScreenTranscriptReview } from "./TranscriptReview";

describe("ScreenTranscriptReview", () => {
  it("monta e mostra la trascrizione nella textarea editabile", () => {
    render(<ScreenTranscriptReview transcript="Ciao mondo" />);
    const ta = screen.getByLabelText(/Testo della trascrizione/i) as HTMLTextAreaElement;
    expect(ta).toBeInTheDocument();
    expect(ta.value).toBe("Ciao mondo");
  });

  it("mostra il contatore parole e lo aggiorna all'edit", () => {
    render(<ScreenTranscriptReview transcript="Ciao mondo" />);
    expect(screen.getByText("2 parole")).toBeInTheDocument();
    const ta = screen.getByLabelText(/Testo della trascrizione/i);
    fireEvent.change(ta, { target: { value: "uno due tre" } });
    expect(screen.getByText("3 parole")).toBeInTheDocument();
  });

  it("usa il singolare con una sola parola", () => {
    render(<ScreenTranscriptReview transcript="Ciao" />);
    expect(screen.getByText("1 parola")).toBeInTheDocument();
  });

  it("Procedi chiama onProceed col testo EDITATO", () => {
    const onProceed = vi.fn();
    render(<ScreenTranscriptReview transcript="testo grezzo" onProceed={onProceed} />);
    fireEvent.change(screen.getByLabelText(/Testo della trascrizione/i), {
      target: { value: "testo corretto a mano" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Procedi/i }));
    expect(onProceed).toHaveBeenCalledWith("testo corretto a mano");
  });

  it("Annulla chiama onCancel quando fornita", () => {
    const onCancel = vi.fn();
    render(<ScreenTranscriptReview transcript="x" onCancel={onCancel} />);
    fireEvent.click(screen.getByRole("button", { name: /^Annulla$/i }));
    expect(onCancel).toHaveBeenCalled();
  });

  it("Ctrl/⌘+Invio procede col testo corrente (scorciatoia)", () => {
    const onProceed = vi.fn();
    render(<ScreenTranscriptReview transcript="bozza" onProceed={onProceed} />);
    const ta = screen.getByLabelText(/Testo della trascrizione/i);
    fireEvent.change(ta, { target: { value: "bozza modificata" } });
    fireEvent.keyDown(ta, { key: "Enter", ctrlKey: true });
    expect(onProceed).toHaveBeenCalledWith("bozza modificata");
  });

  it("si ri-sincronizza quando la trascrizione arriva DOPO il mount (race getJob async)", () => {
    // In App il job arriva via getJob asincrono: la schermata può montare con transcript="" e
    // ricevere il testo reale subito dopo. La textarea DEVE riflettere il nuovo prop (ADR-010:
    // useState(prop) statico mostrerebbe la box vuota in produzione, nascosto dai mock).
    const { rerender } = render(<ScreenTranscriptReview transcript="" />);
    const ta = screen.getByLabelText(/Testo della trascrizione/i) as HTMLTextAreaElement;
    expect(ta.value).toBe("");
    rerender(<ScreenTranscriptReview transcript="trascrizione arrivata dopo" />);
    expect(ta.value).toBe("trascrizione arrivata dopo");
  });

  it("Invio semplice NON procede (solo con il modificatore)", () => {
    const onProceed = vi.fn();
    render(<ScreenTranscriptReview transcript="bozza" onProceed={onProceed} />);
    fireEvent.keyDown(screen.getByLabelText(/Testo della trascrizione/i), { key: "Enter" });
    expect(onProceed).not.toHaveBeenCalled();
  });
});

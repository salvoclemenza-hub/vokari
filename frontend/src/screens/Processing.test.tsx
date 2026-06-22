import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ScreenProcessing } from "./Processing";

describe("ScreenProcessing", () => {
  it("mostra la percentuale e il testo parziale ricevuti via props", async () => {
    render(<ScreenProcessing status="transcribing" pct={0.42} partialText="ciao mondo" />);
    expect(screen.getByText("42%")).toBeInTheDocument();
    // Il testo grezzo viene rivelato con effetto "scrittura" (typewriter) → compare in ~100ms.
    expect(await screen.findByText(/ciao mondo/)).toBeInTheDocument();
  });

  it("marca lo step Analisi come attivo quando status=analyzing", () => {
    const { container } = render(<ScreenProcessing status="analyzing" pct={1} partialText="" />);
    const steps = container.querySelectorAll(".vk-step");
    expect(steps[0].className).toContain("done");
    expect(steps[1].className).toContain("active");
  });

  it("mostra il messaggio di caricamento modello durante transcribing senza testo", () => {
    render(<ScreenProcessing status="transcribing" pct={0} partialText="" />);
    // Il caricamento modello compare sia nella sotto-fase (header) sia nella console.
    expect(screen.getAllByText(/Carico il modello Whisper/).length).toBeGreaterThan(0);
  });

  it("mostra un messaggio di attesa onesto durante l'analisi locale", () => {
    render(<ScreenProcessing status="analyzing" pct={1} partialText="" />);
    expect(screen.getByText(/organizzando la trascrizione/)).toBeInTheDocument();
  });
});

// Comportamento nuovo della fase "Analisi AI" (Livello 1 + 2): timer, sotto-fase, anteprima.
// Senza, il cablaggio frontend sarebbe verificato solo da tsc (ADR-010: il frontend non
// testato a comportamento è dove si annidano i path felici rotti).
describe("ScreenProcessing — fase Analisi AI", () => {
  it("mostra il timer 'Analisi AI · m:ss' durante analyzing", () => {
    render(<ScreenProcessing status="analyzing" pct={1} partialText="" />);
    expect(screen.getByText(/Analisi AI ·/)).toBeInTheDocument();
  });

  it("usa l'etichetta della sotto-fase quando arriva analyzeStep", () => {
    render(
      <ScreenProcessing
        status="analyzing"
        pct={1}
        partialText=""
        analyzeStep={{ step: "questions", label: "Preparo le domande" }}
      />,
    );
    expect(screen.getByText(/Preparo le domande/)).toBeInTheDocument();
  });

  it("rivela l'anteprima dell'analisi (typewriter) durante analyzing", async () => {
    render(<ScreenProcessing status="analyzing" pct={1} partialText="" analysisPreview="Decidere la data di lancio" />);
    // typewriter: il testo si rivela in ~300ms → findByText attende
    expect(await screen.findByText(/Decidere la data di lancio/)).toBeInTheDocument();
    expect(screen.getByText(/∴ ragiono/)).toBeInTheDocument();
  });

  it("NON mostra l'anteprima fuori dalla fase analyzing (es. rendering)", () => {
    render(<ScreenProcessing status="rendering" pct={1} partialText="" analysisPreview="non deve comparire" />);
    expect(screen.queryByText(/∴ ragiono/)).toBeNull();
    expect(screen.queryByText("non deve comparire")).toBeNull();
  });
});

// Badge idoneità trascrizione↔modello (evento analysis_fit, ADR-041): dato strutturato
// persistente, distinto dal warning transiente. Avvisa che la trascrizione verrà riassunta
// (summarize) o sfora comunque il contesto (over_even_summarized) e suggerisce un'alternativa.
describe("ScreenProcessing — badge idoneità modello", () => {
  const fit = {
    jobId: "j1", level: "summarize" as const, tokensEst: 34000, ctxMax: 32768,
    budget: 28000, nChunks: 9, ctxIsFallback: false,
    recommendation: "Usa Claude (200k) o dividi la registrazione.",
  };

  it("NON mostra il badge quando analysisFit è assente", () => {
    render(<ScreenProcessing status="analyzing" pct={1} partialText="" />);
    expect(screen.queryByTestId("vk-fit-badge")).toBeNull();
  });

  it("mostra il badge con n. parti e raccomandazione quando level=summarize", () => {
    render(<ScreenProcessing status="analyzing" pct={1} partialText="" analysisFit={fit} />);
    const badge = screen.getByTestId("vk-fit-badge");
    expect(badge).toBeInTheDocument();
    expect(badge.textContent).toMatch(/riassunta in 9 parti/);
    expect(badge.textContent).toMatch(/Usa Claude/);
  });

  it("distingue il titolo per level=over_even_summarized", () => {
    render(
      <ScreenProcessing status="analyzing" pct={1} partialText=""
        analysisFit={{ ...fit, level: "over_even_summarized" }} />,
    );
    expect(screen.getByTestId("vk-fit-badge").textContent).toMatch(/oltre il contesto/i);
  });

  it("resta visibile anche in rendering (non solo durante analyzing)", () => {
    render(<ScreenProcessing status="rendering" pct={1} partialText="" analysisFit={fit} />);
    expect(screen.getByTestId("vk-fit-badge")).toBeInTheDocument();
  });
});

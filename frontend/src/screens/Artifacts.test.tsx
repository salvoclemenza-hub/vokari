import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ScreenArtifacts } from "./Artifacts";
import type { Artifacts } from "../bridge";

const ART: Artifacts = {
  title: "Riunione X", briefingMd: "# Briefing X\n\ncorpo", briefingPath: "/out/x.briefing.md",
  recapMd: "# Recap X\n\nTesto del recap.", obsidianNote: "# Nota Obsidian\n\nContenuto.",
  transcriptText: "Testo trascritto di esempio.",
  durationS: 90, model: "large-v3-turbo",
  language: "it", wordCount: 1200,
};

const ART_NO_RECAP: Artifacts = {
  ...ART, recapMd: "", obsidianNote: "",
};

describe("ScreenArtifacts", () => {
  it("mostra titolo e contenuto del briefing reale", () => {
    render(<ScreenArtifacts artifacts={ART} />);
    expect(screen.getByRole("heading", { name: "Riunione X" })).toBeInTheDocument();
    // Il markdown è renderizzato (.vk-doc): "# Briefing X" → <h2>Briefing X</h2>, non testo grezzo.
    expect(screen.getByRole("heading", { name: "Briefing X" })).toBeInTheDocument();
  });

  it("i bottoni Scarica chiamano onDownload con nome+contenuto dell'artefatto (FB-C)", async () => {
    const onDownload = vi.fn().mockResolvedValue({ ok: true, path: "/tmp/briefing.md" });
    render(<ScreenArtifacts artifacts={ART} onDownload={onDownload} />);
    const btns = screen.getAllByRole("button", { name: /^Scarica$/i });
    expect(btns.length).toBe(3);                       // briefing + recap + nota
    fireEvent.click(btns[0]);
    await waitFor(() => expect(onDownload).toHaveBeenCalledWith("briefing.md", ART.briefingMd));
  });

  it("senza recap/nota i relativi Scarica non compaiono (FB-C)", () => {
    render(<ScreenArtifacts artifacts={ART_NO_RECAP} onDownload={vi.fn()} />);
    expect(screen.getAllByRole("button", { name: /^Scarica$/i }).length).toBe(1); // solo briefing
  });

  it("copia chiama il callback con il markdown del briefing", () => {
    const onCopy = vi.fn();
    render(<ScreenArtifacts artifacts={ART} onCopy={onCopy} />);
    fireEvent.click(screen.getByRole("button", { name: /Copia il briefing per la tua AI/i }));
    expect(onCopy).toHaveBeenCalledWith(ART.briefingMd);
  });

  it("il tab recap.md è cliccabile (non disabled) quando recapMd è presente", () => {
    render(<ScreenArtifacts artifacts={ART} />);
    const recapTab = screen.getByRole("button", { name: /recap\.md/i });
    expect(recapTab).not.toBeDisabled();
  });

  it("cliccare recap.md mostra il contenuto del recap", async () => {
    render(<ScreenArtifacts artifacts={ART} />);
    fireEvent.click(screen.getByRole("button", { name: /recap\.md/i }));
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Recap X" })).toBeInTheDocument();
    });
  });

  it("il tab obsidian/ è cliccabile quando obsidianNote è presente", () => {
    render(<ScreenArtifacts artifacts={ART} />);
    const obsidianTab = screen.getByRole("button", { name: /obsidian\//i });
    expect(obsidianTab).not.toBeDisabled();
  });

  it("cliccare obsidian/ mostra il contenuto della nota", async () => {
    render(<ScreenArtifacts artifacts={ART} />);
    fireEvent.click(screen.getByRole("button", { name: /obsidian\//i }));
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Nota Obsidian" })).toBeInTheDocument();
    });
  });

  it("il bottone Genera PDF del recap è attivo e chiama onExportPdf", async () => {
    const onExportPdf = vi.fn().mockResolvedValue({ ok: true, path: "/tmp/x.pdf" });
    render(<ScreenArtifacts artifacts={ART} onExportPdf={onExportPdf} />);
    const btn = screen.getByRole("button", { name: /Genera PDF del recap/i });
    expect(btn).not.toBeDisabled();
    fireEvent.click(btn);
    await waitFor(() => {
      expect(onExportPdf).toHaveBeenCalled();
    });
  });

  it("il bottone Esporta su Obsidian è attivo e chiama onExportObsidian", async () => {
    const onExportObsidian = vi.fn().mockResolvedValue({ ok: true, count: 2, paths: [] });
    render(<ScreenArtifacts artifacts={ART} onExportObsidian={onExportObsidian} />);
    const btn = screen.getByRole("button", { name: /Esporta su Obsidian/i });
    expect(btn).not.toBeDisabled();
    fireEvent.click(btn);
    await waitFor(() => {
      expect(onExportObsidian).toHaveBeenCalled();
    });
  });

  it("recap.md tab disabled quando recapMd è vuoto", () => {
    render(<ScreenArtifacts artifacts={ART_NO_RECAP} />);
    const recapTab = screen.getByRole("button", { name: /recap\.md/i });
    expect(recapTab).toBeDisabled();
  });

  it("il tasto indietro '← Sessioni' chiama onBack", () => {
    const onBack = vi.fn();
    render(<ScreenArtifacts artifacts={ART} onBack={onBack} />);
    fireEvent.click(screen.getByRole("button", { name: /Sessioni/i }));
    expect(onBack).toHaveBeenCalled();
  });

  it("senza onBack non mostra il tasto indietro", () => {
    render(<ScreenArtifacts artifacts={ART} />);
    expect(screen.queryByRole("button", { name: /← Sessioni/i })).not.toBeInTheDocument();
  });
});

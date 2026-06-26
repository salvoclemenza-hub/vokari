import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ChangelogEntry } from "../bridge";
import { WhatsNew } from "./WhatsNew";

const ENTRIES: ChangelogEntry[] = [
  {
    version: "0.1.2",
    date: "2026-06-25",
    title: "Benvenuto guidato",
    highlights: [
      { kind: "feature", text: "Wizard di benvenuto al primo avvio." },
      { kind: "fix", text: "Stato Ollama più chiaro nelle impostazioni." },
    ],
  },
  {
    version: "0.1.1",
    date: "2026-06-20",
    title: "Pacchetto distribuibile",
    highlights: [{ kind: "improvement", text: "Avvisi lingua più onesti." }],
  },
];

describe("WhatsNew", () => {
  it("mostra la versione corrente e i titoli delle voci", () => {
    render(<WhatsNew entries={ENTRIES} currentVersion="0.1.2" onClose={() => {}} />);
    expect(screen.getByText("v0.1.2")).toBeInTheDocument(); // chip versione
    expect(screen.getByText("Benvenuto guidato")).toBeInTheDocument();
    expect(screen.getByText("Pacchetto distribuibile")).toBeInTheDocument();
  });

  it("formatta la data in modo amichevole (non ISO)", () => {
    render(<WhatsNew entries={ENTRIES} currentVersion="0.1.2" onClose={() => {}} />);
    expect(screen.getByText("25 giu 2026")).toBeInTheDocument();
    expect(screen.queryByText("2026-06-25")).not.toBeInTheDocument();
  });

  it("mostra il testo di ogni highlight", () => {
    render(<WhatsNew entries={ENTRIES} currentVersion="0.1.2" onClose={() => {}} />);
    expect(screen.getByText(/Wizard di benvenuto al primo avvio/)).toBeInTheDocument();
    expect(screen.getByText(/Avvisi lingua più onesti/)).toBeInTheDocument();
  });

  it("il bottone 'Ho capito' chiama onClose", () => {
    const onClose = vi.fn();
    render(<WhatsNew entries={ENTRIES} currentVersion="0.1.2" onClose={onClose} />);
    fireEvent.click(screen.getByRole("button", { name: /Ho capito/ }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("il click sullo sfondo chiude (onClose)", () => {
    const onClose = vi.fn();
    render(<WhatsNew entries={ENTRIES} currentVersion="0.1.2" onClose={onClose} />);
    fireEvent.click(screen.getByRole("dialog"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("Esc chiude (onClose)", () => {
    const onClose = vi.fn();
    render(<WhatsNew entries={ENTRIES} currentVersion="0.1.2" onClose={onClose} />);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

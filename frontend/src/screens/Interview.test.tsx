import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ScreenInterview } from "./Interview";
import type { Question } from "../bridge";

const QS: Question[] = [
  { id: "q1", text: "Qual e il budget?", priority: "high", suggestions: ["10k", "20k"] },
  { id: "q2", text: "Chi legge il briefing?", priority: "medium", suggestions: [] },
];

describe("ScreenInterview", () => {
  it("invia risposte selezionate e segna come skipped quelle non risposte", () => {
    const onGenerate = vi.fn();
    render(<ScreenInterview questions={QS} onGenerate={onGenerate} />);
    fireEvent.click(screen.getByText("10k"));
    fireEvent.click(screen.getByRole("button", { name: /Genera briefing/i }));
    expect(onGenerate).toHaveBeenCalledWith({ q1: "10k" }, ["q2"]);
  });

  it("'Salta tutto e genera' manda tutte le domande come skipped", () => {
    const onGenerate = vi.fn();
    render(<ScreenInterview questions={QS} onGenerate={onGenerate} />);
    fireEvent.click(screen.getByRole("button", { name: /Salta tutto e genera/i }));
    expect(onGenerate).toHaveBeenCalledWith({}, ["q1", "q2"]);
  });

  it("'Annulla' chiama onCancel quando fornita", () => {
    const onCancel = vi.fn();
    render(<ScreenInterview questions={QS} onCancel={onCancel} />);
    fireEvent.click(screen.getByRole("button", { name: /^Annulla$/i }));
    expect(onCancel).toHaveBeenCalled();
  });

  it("mostra 'Perché:' (I1) e il tag 'dal tuo audio' (I2) solo quando presenti", () => {
    const qs: Question[] = [
      { id: "q1", text: "Budget 700 o 730?", priority: "high", suggestions: [],
        why: "i due importi si contraddicono", fromAudio: true },
      { id: "q2", text: "Per chi è il briefing?", priority: "low", suggestions: [] }, // niente why/fromAudio
    ];
    render(<ScreenInterview questions={qs} />);
    // I1: rationale presente solo sulla prima
    expect(screen.getByText("i due importi si contraddicono")).toBeInTheDocument();
    expect(screen.getByText("Perché:")).toBeInTheDocument();
    // I2: tag "dal tuo audio" presente solo sulla prima (fromAudio=true)
    expect(screen.getAllByText("dal tuo audio")).toHaveLength(1);
  });

  it("racchiude le domande in un contenitore scrollabile separato dalla barra azioni (interview-no-scroll)", () => {
    // Con molte domande il tasto 'Genera briefing' finiva fuori viewport: ora le domande
    // stanno in .vk-iv-scroll (overflow-y:auto) mentre la barra azioni resta ancorata fuori.
    const many: Question[] = Array.from({ length: 8 }, (_, i) => (
      { id: `q${i}`, text: `Domanda ${i}?`, priority: "medium", suggestions: [] }));
    const { container } = render(<ScreenInterview questions={many} />);
    const scroll = container.querySelector(".vk-iv-scroll");
    expect(scroll).not.toBeNull();
    expect(scroll!.querySelectorAll(".vk-q").length).toBe(many.length);
    // la barra azioni NON è dentro lo scroll → sempre raggiungibile
    expect(scroll!.querySelector(".vk-iv-act")).toBeNull();
    expect(container.querySelector(".vk-iv-act")).not.toBeNull();
  });
});

import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { MarkdownDoc } from "./MarkdownDoc";

const SAMPLE = `---
data: 2026-06-15
tipo: riunione
---

# Briefing — Riunione produzione

## Decisioni
- Priorità **FEFO** sui lotti MAC.
- [ ] Marco — riorganizzare il piano

## Domande aperte
- [DA CHIARIRE: Budget confermato? (domanda saltata in rifinitura)]

Collegamenti: [[Piano lavorazione]]
`;

describe("MarkdownDoc", () => {
  it("rende frontmatter, titoli, elenchi, todo, [DA CHIARIRE] e inline", () => {
    const { container } = render(<MarkdownDoc md={SAMPLE} />);

    // frontmatter → .vk-yaml (non un <pre> grezzo)
    expect(container.querySelector(".vk-yaml")).not.toBeNull();
    expect(container.textContent).toContain("data:");
    expect(container.textContent).toContain("2026-06-15");

    // # → h2 (titolo doc), ## → h3 (sezione)
    expect(container.querySelector("h2")?.textContent).toContain("Briefing");
    const h3s = [...container.querySelectorAll("h3")].map((e) => e.textContent);
    expect(h3s).toContain("Decisioni");
    expect(h3s).toContain("Domande aperte");

    // bullet con **bold**
    expect(container.querySelector("li b")?.textContent).toBe("FEFO");

    // checkbox → li.todo
    expect(container.querySelector("li.todo")?.textContent).toContain("Marco");

    // [DA CHIARIRE] → li.clar con badge .vk-clar
    const clar = container.querySelector("li.clar");
    expect(clar).not.toBeNull();
    expect(clar?.querySelector(".vk-clar")?.textContent).toBe("DA CHIARIRE");
    expect(clar?.textContent).toContain("Budget confermato?");

    // wikilink → .lnk
    expect(container.querySelector(".lnk")?.textContent).toBe("Piano lavorazione");

    // nessun <pre> grezzo
    expect(container.querySelector("pre")).toBeNull();
  });

  it("non esplode su markdown vuoto", () => {
    const { container } = render(<MarkdownDoc md="" />);
    expect(container).toBeTruthy();
  });
});

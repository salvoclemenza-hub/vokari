import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ScreenError } from "./ErrorScreen";

describe("ScreenError", () => {
  it("mostra il messaggio di errore", () => {
    render(<ScreenError message="Trascrizione vuota: nessun parlato rilevato" />);
    expect(screen.getByText(/Trascrizione vuota/i)).toBeTruthy();
  });

  it("mostra la diagnostica audio (warnings) quando presente — A2 visibile in schermata errore", () => {
    // Senza questo, la diagnostica 'both vuoto' veniva nascosta sulla schermata error
    // (App nascondeva i warning quando screen==='error') e l'utente non sapeva il perché.
    const w = "audio finale quasi silenzioso pur avendo segnale su system: controlla i livelli delle sorgenti";
    render(<ScreenError message="Trascrizione vuota: nessun parlato rilevato" warnings={[w]} />);
    expect(screen.getByText(/quasi silenzioso pur avendo segnale su system/i)).toBeTruthy();
  });

  it("nessun box diagnostica quando warnings è vuoto", () => {
    const { container } = render(<ScreenError message="errore generico" />);
    expect(container.querySelector('[role="note"]')).toBeNull();
  });
});

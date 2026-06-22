import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ConfirmHost } from "./ConfirmHost";
import { confirmDialog, promptDialog, importDialog } from "../confirm";

describe("ConfirmHost", () => {
  it("risolve true su Conferma, false su Annulla, e mostra il messaggio", async () => {
    render(<ConfirmHost />);
    const user = userEvent.setup();

    const p1 = confirmDialog({ message: "Scartare tutto?", confirmLabel: "Scarta", cancelLabel: "No" });
    expect(await screen.findByText("Scartare tutto?")).toBeInTheDocument();
    await user.click(screen.getByText("Scarta"));
    expect(await p1).toBe(true);

    const p2 = confirmDialog({ message: "Di nuovo?", cancelLabel: "Indietro" });
    await user.click(await screen.findByText("Indietro"));
    expect(await p2).toBe(false);
  });

  it("MDL1: con items mostra l'anteprima elenco; senza items resta il dialog semplice", async () => {
    render(<ConfirmHost />);
    const user = userEvent.setup();

    const p = confirmDialog({
      title: "Eliminare 2 sessioni?",
      message: "Verranno rimosse.",
      confirmLabel: "Elimina 2",
      danger: true,
      items: [
        { title: "Riunione produzione", mode: "riunione", meta: "15 giu · 27:41", hasBriefing: true },
        { title: "Idee packaging", mode: "solo", meta: "15 giu · 08:03", hasBriefing: true, hasRecap: true },
      ],
    });
    // entrambi i titoli delle sessioni compaiono nell'anteprima
    expect(await screen.findByText("Riunione produzione")).toBeInTheDocument();
    expect(screen.getByText("Idee packaging")).toBeInTheDocument();
    await user.click(screen.getByText("Elimina 2"));
    expect(await p).toBe(true);

    // dialog senza items: nessuna anteprima (retro-compatibile)
    const { container } = render(<ConfirmHost />);
    confirmDialog({ message: "Confermi?" });
    await screen.findByText("Confermi?");
    expect(container.querySelector(".vk-mlist")).toBeNull();
  });

  it("MDL2: importDialog mostra meta file + tipo e ritorna {mode, context}", async () => {
    render(<ConfirmHost />);
    const user = userEvent.setup();
    const p = importDialog({
      fileName: "183.m4a", durationS: 1661, sizeBytes: 24_300_000, defaultMode: "solo", defaultContext: "",
    });
    expect(await screen.findByText("183.m4a")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Riunione" })); // cambia tipo
    await user.type(screen.getByRole("textbox"), "scorte e turni");
    await user.click(screen.getByText("Importa"));
    expect(await p).toEqual({ mode: "riunione", context: "scorte e turni" });
  });

  it("MDL2: importDialog su Annulla ritorna null", async () => {
    render(<ConfirmHost />);
    const user = userEvent.setup();
    const p = importDialog({
      fileName: "x.wav", durationS: 0, sizeBytes: 0, defaultMode: "solo", defaultContext: "",
    });
    await screen.findByText("x.wav");
    await user.click(screen.getByText("Annulla"));
    expect(await p).toBeNull();
  });

  it("promptDialog: risolve col testo su OK, null su Annulla", async () => {
    render(<ConfirmHost />);
    const user = userEvent.setup();
    const p = promptDialog({ message: "Di cosa parla?", defaultValue: "" });
    const input = await screen.findByRole("textbox");
    await user.type(input, "landing page");
    await user.click(screen.getByText("OK"));
    expect(await p).toBe("landing page");

    const p2 = promptDialog({ message: "Di cosa parla?" });
    await screen.findByRole("textbox");
    await user.click(screen.getByText("Annulla"));
    expect(await p2).toBeNull();
  });
});

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Toaster } from "./Toaster";
import { toast } from "../toast";

describe("Toaster", () => {
  beforeEach(() => {
    vi.useRealTimers();
  });

  it("mostra il messaggio quando si chiama toast()", async () => {
    render(<Toaster />);
    act(() => toast("Copiato ✓", "success"));
    expect(await screen.findByText("Copiato ✓")).toBeInTheDocument();
  });

  it("un toast di errore resta visibile (persistente) e si chiude con ×", async () => {
    vi.useFakeTimers();
    try {
      render(<Toaster />);
      act(() => toast("Download fallito", "error"));
      expect(screen.getByText("Download fallito")).toBeInTheDocument();
      // anche dopo un lungo intervallo l'errore non si auto-chiude
      act(() => vi.advanceTimersByTime(10000));
      expect(screen.getByText("Download fallito")).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Chiudi notifica/i }));
    expect(screen.queryByText("Download fallito")).not.toBeInTheDocument();
  });

  it("MDL3: un toast con azione mostra il bottone e lo invoca al click", async () => {
    const onUndo = vi.fn();
    render(<Toaster />);
    act(() => toast("Sessione eliminata", "info", { action: { label: "Annulla", onClick: onUndo }, durationMs: 5000 }));
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Annulla" }));
    expect(onUndo).toHaveBeenCalled();
    expect(screen.queryByText("Sessione eliminata")).not.toBeInTheDocument(); // si chiude dopo l'azione
  });

  it("un toast success si auto-chiude dopo il TTL", async () => {
    vi.useFakeTimers();
    try {
      render(<Toaster />);
      act(() => toast("Salvato ✓", "success"));
      expect(screen.getByText("Salvato ✓")).toBeInTheDocument();
      act(() => vi.advanceTimersByTime(3000));
      expect(screen.queryByText("Salvato ✓")).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });
});

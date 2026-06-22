import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Sidebar } from "./Sidebar";
import type { SessionItem } from "../bridge";

// Mock del bridge: controlliamo cosa ritorna listSessions.
const listSessions = vi.fn<() => Promise<SessionItem[]>>();
vi.mock("../bridge", async (importOriginal) => {
  const real = await importOriginal<typeof import("../bridge")>();
  return {
    ...real,
    bridge: { ...real.bridge, listSessions: () => listSessions() },
  };
});

function sess(over: Partial<SessionItem>): SessionItem {
  return {
    id: "s1", title: "Riunione reale", createdAt: "2026-06-09T09:41:00",
    mode: "riunione", model: "large-v3-turbo", durationMs: 38 * 60 * 1000,
    hasBriefing: true, hasRecap: false, hasObsidian: false, clarCount: 0, hasAudio: false, ...over,
  };
}

describe("Sidebar — Recenti reali (F5)", () => {
  beforeEach(() => { listSessions.mockReset(); });

  it("rende le sessioni reali (max 4) e il clic chiama onOpenSession(id)", async () => {
    listSessions.mockResolvedValue([
      sess({ id: "a", title: "Sessione A" }),
      sess({ id: "b", title: "Sessione B" }),
      sess({ id: "c", title: "Sessione C" }),
      sess({ id: "d", title: "Sessione D" }),
      sess({ id: "e", title: "Sessione E" }),
    ]);
    const onOpen = vi.fn();
    render(<Sidebar active="Registra" onNavigate={() => {}} onOpenSession={onOpen} />);

    expect(await screen.findByText("Sessione A")).toBeInTheDocument();
    expect(screen.getByText("Sessione D")).toBeInTheDocument();
    // solo le prime 4
    expect(screen.queryByText("Sessione E")).not.toBeInTheDocument();

    await userEvent.click(screen.getByText("Sessione A"));
    expect(onOpen).toHaveBeenCalledWith("a");
  });

  it("con 0 sessioni mostra il placeholder, niente voci finte", async () => {
    listSessions.mockResolvedValue([]);
    render(<Sidebar active="Registra" onNavigate={() => {}} onOpenSession={() => {}} />);

    await waitFor(() => expect(screen.getByText(/nessuna sessione recente/)).toBeInTheDocument());
    // i vecchi dati finti hardcoded non devono comparire
    expect(screen.queryByText("Riunione prodotto Q3")).not.toBeInTheDocument();
    expect(screen.queryByText("Brainstorm naming")).not.toBeInTheDocument();
  });
});

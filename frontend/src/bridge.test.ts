import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { onVokariEvent } from "./bridge";

type WinMut = { pywebview?: { api: Record<string, unknown> } };

afterEach(() => {
  (window as unknown as { __vokari_emit?: unknown }).__vokari_emit = undefined;
  (window as unknown as { __vokari_handlers?: unknown }).__vokari_handlers = undefined;
});

describe("onVokariEvent", () => {
  it("riceve gli eventi pubblicati da window.__vokari_emit", () => {
    const handler = vi.fn();
    const off = onVokariEvent(handler);
    (window as unknown as { __vokari_emit: (e: string, p: unknown) => void })
      .__vokari_emit("status", { jobId: "j1", status: "ready" });
    expect(handler).toHaveBeenCalledWith("status", { jobId: "j1", status: "ready" });
    off();
  });

  it("smette di ricevere dopo l'unsubscribe", () => {
    const handler = vi.fn();
    const off = onVokariEvent(handler);
    off();
    (window as unknown as { __vokari_emit: (e: string, p: unknown) => void })
      .__vokari_emit("status", { jobId: "j1", status: "ready" });
    expect(handler).not.toHaveBeenCalled();
  });
});

describe("bridge — gating su pywebviewready (anti-race)", () => {
  beforeEach(() => {
    vi.resetModules(); // readyPromise è cache a livello modulo: serve fresh import
    delete (window as unknown as WinMut).pywebview;
  });
  afterEach(() => {
    vi.useRealTimers();
    delete (window as unknown as WinMut).pywebview;
  });

  it("una chiamata fatta PRIMA dell'iniezione raggiunge l'api appena disponibile", async () => {
    vi.useFakeTimers();
    const { bridge } = await import("./bridge");
    const start_recording = vi.fn().mockResolvedValue({ ok: true });

    const pending = bridge.startRecording("both"); // api ancora assente al mount

    // pywebview inietta l'api ~poco dopo (in-app fino a ~1s)
    (window as unknown as WinMut).pywebview = { api: { start_recording } };
    await vi.advanceTimersByTimeAsync(60); // fa scattare il poll (50ms)

    await expect(pending).resolves.toEqual({ ok: true });
    expect(start_recording).toHaveBeenCalledWith("both", null);
  });

  it("senza pywebview, dopo il timeout, ritorna il fallback (browser/dev)", async () => {
    vi.useFakeTimers();
    const { bridge } = await import("./bridge");
    const pending = bridge.stopRecording();
    await vi.advanceTimersByTimeAsync(5100);
    await expect(pending).resolves.toEqual({ jobId: "" });
  });
});

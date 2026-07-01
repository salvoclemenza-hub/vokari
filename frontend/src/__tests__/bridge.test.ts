import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { getAppInfo } from "../bridge";

describe("bridge", () => {
  beforeEach(() => {
    // simula ambiente browser/test: nessun pywebview iniettato
    delete (window as unknown as { pywebview?: unknown }).pywebview;
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("ritorna fallback deterministici dopo il timeout quando pywebview è assente", async () => {
    // Il bridge ora attende l'iniezione di pywebview (anti-race) e ripiega sul
    // fallback solo dopo il timeout: avanziamo i timer per non aspettare davvero.
    vi.useFakeTimers();
    const p = getAppInfo();
    await vi.advanceTimersByTimeAsync(5100);
    await expect(p).resolves.toEqual({
      version: "dev", license: "MIT", githubStars: 0, platform: "windows", systemAudioSupported: true,
    });
  });

  it("inoltra alla api di pywebview quando presente", async () => {
    (window as unknown as { pywebview: { api: Record<string, unknown> } }).pywebview = {
      api: { get_app_info: async () => ({ version: "0.1.0", license: "MIT", githubStars: 2400 }) },
    };
    const info = await getAppInfo();
    expect(info.version).toBe("0.1.0");
    expect(info.githubStars).toBe(2400);
  });
});

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AppFrame } from "../chrome/AppFrame";

const INFO = { version: "0.1.0", license: "MIT", githubStars: 2400, platform: "windows", systemAudioSupported: true };

describe("AppFrame chrome", () => {
  it("evidenzia la voce attiva e mostra version (license rimossa da T3)", () => {
    render(
      <AppFrame active="Registra" onNavigate={() => {}} appInfo={INFO}>
        x
      </AppFrame>,
    );
    // "Registra" ora compare due volte: voce sidebar (<a>) + titolo titlebar (<div>).
    // L'asserzione riguarda la voce di navigazione attiva → scegli l'<a>.
    const navRegistra = screen.getAllByText("Registra").find((el) => el.tagName === "A");
    expect(navRegistra?.className).toContain("on");
    expect(screen.getByText(/v0\.1\.0/)).toBeInTheDocument();
    // T3: license rimossa dalla chrome (non era in Titlebar né StatusBar dopo polish)
    expect(screen.queryByText("MIT")).not.toBeInTheDocument();
  });

  it("chiama onNavigate al click su una voce", async () => {
    const onNav = vi.fn();
    render(
      <AppFrame active="Registra" onNavigate={onNav} appInfo={INFO}>
        x
      </AppFrame>,
    );
    await userEvent.click(screen.getByText("Impostazioni"));
    expect(onNav).toHaveBeenCalledWith("Impostazioni");
  });

  it("l'icona impostazioni nella titlebar naviga a Impostazioni", async () => {
    const onNav = vi.fn();
    render(
      <AppFrame active="Registra" onNavigate={onNav} appInfo={INFO}>
        x
      </AppFrame>,
    );
    // il bottone-icona ha aria-label "Impostazioni" (la voce sidebar è un link, non button)
    await userEvent.click(screen.getByRole("button", { name: "Impostazioni" }));
    expect(onNav).toHaveBeenCalledWith("Impostazioni");
  });

  it("non mostra più controlli morti (⌘K, Contribuisci)", () => {
    render(
      <AppFrame active="Registra" onNavigate={() => {}} appInfo={INFO}>
        x
      </AppFrame>,
    );
    expect(screen.queryByText("⌘K")).not.toBeInTheDocument();
    expect(screen.queryByText(/Contribuisci/)).not.toBeInTheDocument();
  });

  it("mostra il contatore stelle quando githubStars > 0", () => {
    render(
      <AppFrame active="Registra" onNavigate={() => {}} appInfo={INFO}>
        x
      </AppFrame>,
    );
    // 2400 → "2.4k" (titlebar) + "2.4k su GitHub" (statusbar)
    expect(screen.getByText("2.4k")).toBeInTheDocument();
    expect(screen.getByText(/2\.4k su GitHub/)).toBeInTheDocument();
  });

  it("NON rende il contatore stelle quando githubStars === 0", () => {
    render(
      <AppFrame active="Registra" onNavigate={() => {}} appInfo={{ version: "0.1.0", license: "MIT", githubStars: 0, platform: "windows", systemAudioSupported: true }}>
        x
      </AppFrame>,
    );
    expect(screen.queryByText(/su GitHub/)).not.toBeInTheDocument();
    expect(screen.queryByText("0")).not.toBeInTheDocument();
    // il resto della chrome resta (T3: license rimossa — non si asserisce più MIT)
    expect(screen.getByText(/v0\.1\.0/)).toBeInTheDocument();
  });
});

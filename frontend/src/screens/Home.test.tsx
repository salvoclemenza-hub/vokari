import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ScreenHome } from "./Home";

describe("ScreenHome", () => {
  it("al mount NON chiama onStart", () => {
    const onStart = vi.fn();
    render(<ScreenHome onStart={onStart} onImport={() => {}} />);
    expect(onStart).not.toHaveBeenCalled();
  });

  it("banner onboarding: compare con needsModel/needsApiKey e i bottoni navigano (FS2)", () => {
    const onOpenModels = vi.fn();
    const onOpenSettings = vi.fn();
    render(<ScreenHome onStart={() => {}} onImport={() => {}} needsModel needsApiKey
                       onOpenModels={onOpenModels} onOpenSettings={onOpenSettings} />);
    expect(screen.getByText(/Configura VOKARI per iniziare/)).toBeInTheDocument();
    fireEvent.click(screen.getByText("Scarica un modello"));
    expect(onOpenModels).toHaveBeenCalled();
    // "Apri Impostazioni" compare sia nel banner sia nel pannello config: il primo è il banner.
    fireEvent.click(screen.getAllByText("Apri Impostazioni")[0]);
    expect(onOpenSettings).toHaveBeenCalled();
  });

  it("banner onboarding: assente quando tutto è configurato (FS2)", () => {
    render(<ScreenHome onStart={() => {}} onImport={() => {}} />);
    expect(screen.queryByText(/Configura VOKARI per iniziare/)).not.toBeInTheDocument();
  });

  it("click sul pulsante REC chiama onStart con la sorgente attiva (default both)", () => {
    const onStart = vi.fn();
    render(<ScreenHome onStart={onStart} onImport={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: /Avvia registrazione/i }));
    expect(onStart).toHaveBeenCalledWith("both", undefined);
  });

  it("click sul pulsante REC dopo aver cambiato sorgente → sorgente corretta", () => {
    const onStart = vi.fn();
    render(<ScreenHome onStart={onStart} onImport={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: /^mic$/i }));
    fireEvent.click(screen.getByRole("button", { name: /Avvia registrazione/i }));
    expect(onStart).toHaveBeenCalledWith("mic", undefined);
  });

  it("senza loopback (systemAudioSupported=false) mostra solo il microfono come sorgente (macOS)", () => {
    render(<ScreenHome onStart={() => {}} onImport={() => {}} systemAudioSupported={false} />);
    const group = screen.getByRole("group", { name: "Sorgente audio" });
    const labels = within(group).getAllByRole("button").map((b) => b.textContent);
    expect(labels).toEqual(["mic"]); // niente "system"/"entrambi"
  });

  it("avvia con 'mic' quando il loopback non è supportato (macOS)", () => {
    const onStart = vi.fn();
    render(<ScreenHome onStart={onStart} onImport={() => {}} systemAudioSupported={false} />);
    fireEvent.click(screen.getByRole("button", { name: /Avvia registrazione/i }));
    expect(onStart).toHaveBeenCalledWith("mic", undefined);
  });

  it("click su 'riunione' chiama onModeChange con il mode scelto", () => {
    const onModeChange = vi.fn();
    render(<ScreenHome onStart={() => {}} onImport={() => {}} mode="solo" onModeChange={onModeChange} />);
    fireEvent.click(screen.getByRole("button", { name: /^riunione$/i }));
    expect(onModeChange).toHaveBeenCalledWith("riunione");
  });

  it("il mode attivo (prop) è evidenziato con la classe .on", () => {
    const { container } = render(
      <ScreenHome onStart={() => {}} onImport={() => {}} mode="riunione" onModeChange={() => {}} />,
    );
    const active = container.querySelector('[aria-label="Tipo sessione"] button.on');
    expect(active?.textContent).toBe("riunione");
  });

  it("click sulla drop-zone chiama onImport", () => {
    const onImport = vi.fn();
    render(<ScreenHome onStart={() => {}} onImport={onImport} />);
    fireEvent.click(screen.getByRole("button", { name: /Trascina o clicca/i }));
    expect(onImport).toHaveBeenCalled();
  });

  it("senza lastArtifacts (a freddo) mostra il pannello configurazione, non le sessioni", () => {
    render(<ScreenHome onStart={() => {}} onImport={() => {}} onOpenSettings={() => {}} />);
    expect(screen.getByText("La tua configurazione")).toBeInTheDocument();
  });

  it("a freddo, lo stato primo-avvio mostra l'onboarding in 3 passi (redesign 2026-06-17)", () => {
    // Il bottone "Apri Impostazioni" nello stato vuoto è stato rimosso: Impostazioni resta
    // raggiungibile da sidebar/titlebar e dal banner (testato sopra in FS2).
    render(<ScreenHome onStart={() => {}} onImport={() => {}} />);
    expect(screen.getByText("Pronto al primo briefing")).toBeInTheDocument();
    expect(screen.getByText(/Scegli tipo e sorgente/)).toBeInTheDocument();
    expect(screen.getByText(/Ottieni il tuo briefing/)).toBeInTheDocument();
  });

  it("con lastArtifacts mostra il contenuto del briefing", () => {
    render(
      <ScreenHome
        onStart={() => {}}
        onImport={() => {}}
        lastArtifacts={{
          title: "Test", briefingMd: "# Il briefing reale", briefingPath: "/a.md",
          recapMd: "", obsidianNote: "", transcriptText: "", durationS: 60, model: "m", language: "it", wordCount: 3,
        }}
      />,
    );
    // Anteprima renderizzata (.vk-doc): "# Il briefing reale" → <h2>Il briefing reale</h2>.
    expect(screen.getByRole("heading", { name: "Il briefing reale" })).toBeInTheDocument();
  });
});

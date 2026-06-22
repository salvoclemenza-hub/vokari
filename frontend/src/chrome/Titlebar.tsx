import { Fragment } from "react";
import { VkIcon } from "../icons";
import type { AppInfo } from "../bridge";
import type { NavItem } from "./Sidebar";

// Passi del flusso lineare: usati per il breadcrumb di wayfinding nella titlebar.
const FLOW: { screen: string; label: string }[] = [
  { screen: "home", label: "Registra" },
  { screen: "live", label: "Live" },
  { screen: "processing", label: "Elaborazione" },
  { screen: "interview", label: "Rifinitura" },
  { screen: "artifacts", label: "Artefatti" },
];

// Titolo mostrato a sinistra fuori dal flusso (schermate primarie + errore/artefatti).
const TITLES: Record<string, string> = {
  home: "Registra", sessions: "Sessioni", models: "Modelli AI",
  settings: "Impostazioni", artifacts: "Artefatti", error: "Errore",
  live: "Registrazione", processing: "Elaborazione", interview: "Rifinitura",
};

export function Titlebar({
  appInfo,
  screen = "home",
  onNavigate,
}: {
  appInfo: AppInfo;
  screen?: string;
  onNavigate?: (n: NavItem) => void;
}) {
  const stars =
    appInfo.githubStars >= 1000
      ? (appInfo.githubStars / 1000).toFixed(1) + "k"
      : String(appInfo.githubStars);
  // Breadcrumb solo nelle schermate transitorie del flusso: su artefatti (raggiungibile
  // anche aprendo una sessione dalla libreria) un breadcrumb implicherebbe un flusso che
  // non è sempre vero → lì titolo semplice.
  const inFlow = screen === "live" || screen === "processing" || screen === "interview";
  const activeIdx = FLOW.findIndex((f) => f.screen === screen);

  return (
    <div className="vk-tbar">
      {inFlow ? (
        <div className="vk-tbar-crumbs" aria-label="Avanzamento del flusso">
          {FLOW.map((f, i) => (
            <Fragment key={f.screen}>
              {i > 0 && <span className="sep">›</span>}
              <span className={"c" + (i === activeIdx ? " cur" : i < activeIdx ? " done" : "")}>
                {f.label}
              </span>
            </Fragment>
          ))}
        </div>
      ) : (
        <div className="vk-tbar-title">{TITLES[screen] ?? "VOKARI"}</div>
      )}
      <div className="vk-tbar-r">
        {appInfo.githubStars > 0 && (
          <div className="vk-star">
            <VkIcon.star />
            {stars}
          </div>
        )}
        <div className="vk-ver">
          v{appInfo.version}
        </div>
        <button
          className="vk-icbtn"
          aria-label="Impostazioni"
          title="Impostazioni"
          onClick={() => onNavigate?.("Impostazioni")}
        >
          <VkIcon.sliders />
        </button>
      </div>
    </div>
  );
}

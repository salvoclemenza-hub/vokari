// Solo subset latin: app IT/EN. Evita di imbarcare cyrillic/greek/vietnamese/latin-ext
// (41 woff inutili nel dist, R10). Il latin copre gli accenti italiani (à è é ì ò ù);
// glifi rari fuori subset → fallback grazioso al font di sistema.
import "@fontsource/space-grotesk/latin-600.css";
import "@fontsource/hanken-grotesk/latin-400.css";
import "@fontsource/hanken-grotesk/latin-500.css";
import "@fontsource/hanken-grotesk/latin-600.css";
import "@fontsource/hanken-grotesk/latin-700.css";
import "@fontsource/jetbrains-mono/latin-400.css";
import "@fontsource/jetbrains-mono/latin-500.css";
import "@fontsource/jetbrains-mono/latin-700.css";
import "./styles/vokari.css";
import "./styles/base.css";
import "./i18n"; // init i18next (Tema 3) prima del render di App/DevHarness
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";

const root = ReactDOM.createRoot(document.getElementById("root")!);

// Harness di rifinitura visiva (DEV-only): attivo solo in `pnpm dev` con ?dev o
// ?screen= nell'URL. In produzione `import.meta.env.DEV` è false → l'intero ramo
// (e l'import dinamico di ./dev/) viene eliminato dal build, quindi dist/ non lo
// include.
const params = new URLSearchParams(location.search);
if (import.meta.env.DEV && (params.has("dev") || params.has("screen"))) {
  void import("./dev/DevHarness").then(({ DevHarness }) => {
    root.render(
      <React.StrictMode>
        <DevHarness />
      </React.StrictMode>,
    );
  });
} else {
  root.render(
    <React.StrictMode>
      <App />
    </React.StrictMode>,
  );
}

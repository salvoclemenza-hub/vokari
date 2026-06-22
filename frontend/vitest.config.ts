/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: "./",
  plugins: [react()],
  build: { outDir: "dist", emptyOutDir: true },
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    globals: true,
    coverage: {
      provider: "v8",
      reporter: ["text", "html"],
      // Baseline ri-misurata 2026-06-22 (137 test):
      //   statements 71.95% · branches 80% · functions 51.1% · lines 71.95%
      // statements/lines sono scesi dalla baseline precedente (82.69%, 2026-06-12) per il
      // codice UI aggiunto in ADR-042 (dialog import, MOD/MDL, badge idoneità) con test sotto
      // la media → DEBITO da recuperare con test su Settings/Models/Interview (follow-up).
      // Thresholds = guard di regressione impostati SOTTO il valore reale, NON target di qualità:
      // - statements/lines a 70 (margine ~2% dal reale 71.95%)
      // - branches a 77 (reale 80%), functions a 45 (reale 51%, molti handler non testati in isolamento)
      thresholds: {
        statements: 70,
        branches: 77,
        functions: 45,
        lines: 70,
      },
    },
  },
});

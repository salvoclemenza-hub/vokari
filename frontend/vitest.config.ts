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
      // Baseline misurata 2026-06-12 (100 test, pre-Wave 3):
      //   statements: 82.69%, branches: 81.33%, functions: 50.18%, lines: 82.69%
      // Thresholds impostati SOTTO la baseline per gate attivo non bloccante:
      // - functions al 45% (bassa perché molte funzioni handler non sono testate in isolamento)
      // - resto al 78% (margine ~4% dalla baseline)
      thresholds: {
        statements: 78,
        branches: 77,
        functions: 45,
        lines: 78,
      },
    },
  },
});

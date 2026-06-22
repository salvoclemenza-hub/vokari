// @ts-check
import js from "@eslint/js";
import tseslint from "typescript-eslint";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";

export default tseslint.config(
  // Global ignores
  {
    ignores: ["dist", "coverage", "node_modules", "vite.config.d.ts"],
  },

  // Base JS rules
  js.configs.recommended,

  // TypeScript type-checked rules
  ...tseslint.configs.recommendedTypeChecked,

  // React-specific rules
  {
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": [
        "warn",
        { allowConstantExport: true },
      ],
    },
  },

  // Project-level config for all TS/TSX files
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      parserOptions: {
        project: ["./tsconfig.json", "./tsconfig.node.json"],
        tsconfigRootDir: import.meta.dirname,
      },
    },
    rules: {
      // --- WARN (gate attivo, non bloccante — azzerare gradualmente) ---

      // Floating promises: il codebase usa void bridge.*() come pattern esteso.
      // Warn per ora, il team corregge gradualmente.
      "@typescript-eslint/no-floating-promises": "warn",

      // exhaustive-deps: useEffect con dep array intenzionalmente parziale (es. mount-only).
      "react-hooks/exhaustive-deps": "warn",

      // no-misused-promises: onClick={asyncFn} è il pattern React idiomatico
      // (il browser ignora il Promise ritornato). Warn finché non vengono avvolti in void.
      "@typescript-eslint/no-misused-promises": "warn",

      // require-await: async functions senza await nei mock dei test e in alcuni helper.
      // Declassato a warn — non richiede fix a mano su centinaia di mock.
      "@typescript-eslint/require-await": "warn",

      // set-state-in-effect: useState sync nell'effect di Processing.tsx è intenzionale
      // (effetto typewriter che aggiorna displayed). Warn per documentare.
      "react-hooks/set-state-in-effect": "warn",

      // no-base-to-string: String(unknown) su payload proveniente da evaluate_js.
      // La call String() è NECESSARIA per evitare [object Object] — ma ESLint
      // non lo capisce senza cast esplicito. Declassato a warn, non error.
      "@typescript-eslint/no-base-to-string": "warn",

      // Unsafe operations: il codebase lavora con payload Record<string,unknown>
      // da evaluate_js che non sono tipizzati staticamente. Warn per primo giro.
      "@typescript-eslint/no-unsafe-assignment": "warn",
      "@typescript-eslint/no-unsafe-member-access": "warn",
      "@typescript-eslint/no-unsafe-call": "warn",
      "@typescript-eslint/no-unsafe-argument": "warn",
      "@typescript-eslint/no-unsafe-return": "warn",

      // react-hooks/immutability: funzioni dichiarate dopo useEffect e usate dentro
      // (openArtifacts in App.tsx). JavaScript hoisting garantisce correttezza a runtime;
      // la regola è troppo conservativa qui. Warn per documentare, non error.
      "react-hooks/immutability": "warn",

      // Deprecate: alcuni hook di react-hooks v7 segnalano deprecation warnings.
      "@typescript-eslint/no-require-imports": "warn",
    },
  },

  // Test files: relax strict rules (mock objects, spy patterns, etc.)
  {
    files: ["**/*.test.{ts,tsx}", "vitest.setup.ts"],
    rules: {
      "@typescript-eslint/no-explicit-any": "off",
      "@typescript-eslint/no-unsafe-assignment": "off",
      "@typescript-eslint/no-unsafe-member-access": "off",
      "@typescript-eslint/no-unsafe-call": "off",
      "@typescript-eslint/no-unsafe-argument": "off",
      "@typescript-eslint/no-unsafe-return": "off",
      "@typescript-eslint/require-await": "off",
      "@typescript-eslint/no-unnecessary-type-assertion": "off",
    },
  },

  // JS config files (eslint.config.js) — no type-checked rules
  {
    files: ["*.js"],
    extends: [tseslint.configs.disableTypeChecked],
  },

  // Vite/vitest config — no type-checked rules (these files use import.meta.env etc.)
  {
    files: ["vite.config.ts", "vitest.config.ts"],
    extends: [tseslint.configs.disableTypeChecked],
  },
);

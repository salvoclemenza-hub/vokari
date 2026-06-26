import "@testing-library/jest-dom/vitest";
// Inizializza i18n (default lng "it") così useTranslation funziona nei test e t() rende
// le stringhe italiane originali → le asserzioni su testo IT restano verdi.
import "./src/i18n";

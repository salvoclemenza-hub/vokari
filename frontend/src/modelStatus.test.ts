import { describe, it, expect } from "vitest";
import { whisperRowState, ollamaHint } from "./modelStatus";

describe("whisperRowState", () => {
  it.each([
    // state,        isSelected, expected
    ["active", true, "active"],
    ["active", false, "active"], // state è autorità: 'active' = scaricato+selezionato
    ["downloaded", false, "downloaded"],
    ["downloaded", true, "downloaded"], // scaricato ma non è l'attivo: lo decide il backend
    // IL FIX B1: il modello selezionato come default ma NON scaricato non è "Attivo"
    ["available", true, "selected-undownloaded"],
    ["available", false, "available"],
  ] as const)("state=%s isSelected=%s → %s", (state, isSelected, expected) => {
    expect(whisperRowState(state, isSelected)).toBe(expected);
  });
});

describe("ollamaHint", () => {
  it.each([
    // running, installed, expected
    [true, true, "up"],
    [true, false, "up"], // running implica raggiungibile, comunque "up"
    // IL FIX B2: installato-ma-fermo ≠ non-installato (prima dicevano entrambi "avvialo")
    [false, true, "installed-down"],
    [false, false, "not-installed"],
  ] as const)("running=%s installed=%s → %s", (running, installed, expected) => {
    expect(ollamaHint({ running, installed })).toBe(expected);
  });
});

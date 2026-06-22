// Conferma in-app stilizzata, promise-based: sostituisce window.confirm (nativo, rudimentale
// e potenziale fonte di blocco del bridge pywebview). <ConfirmHost> (montato in App) si
// registra come unico listener; confirmDialog() risolve true/false.
/** MDL1: anteprima di una sessione coinvolta dalla conferma (mostrata come riga nell'elenco
 *  del dialog di multi-eliminazione). Solo dati: confirm.ts è importato anche fuori da React. */
export interface ConfirmPreviewItem {
  title: string;
  mode?: string;        // "solo" | "riunione" → tag colore
  meta?: string;        // es. "15 giu · 27:41"
  hasBriefing?: boolean;
  hasRecap?: boolean;
  hasObsidian?: boolean;
}

export interface ConfirmOptions {
  title?: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  items?: ConfirmPreviewItem[]; // MDL1: elenco delle sessioni coinvolte (anteprima nel dialog)
}

export interface ConfirmRequest {
  opts: ConfirmOptions;
  resolve: (ok: boolean) => void;
}

let listener: ((req: ConfirmRequest) => void) | null = null;

export function confirmDialog(opts: ConfirmOptions): Promise<boolean> {
  return new Promise((resolve) => {
    if (!listener) {
      resolve(false); // host non montato (test/browser): rifiuta in sicurezza
      return;
    }
    listener({ opts, resolve });
  });
}

export function setConfirmListener(fn: ((req: ConfirmRequest) => void) | null): void {
  listener = fn;
}

export interface PromptOptions {
  title?: string;
  message: string;
  placeholder?: string;
  defaultValue?: string;
  confirmLabel?: string;
  cancelLabel?: string;
}

export interface PromptRequest {
  opts: PromptOptions;
  resolve: (value: string | null) => void;
}

let promptListener: ((req: PromptRequest) => void) | null = null;

export function promptDialog(opts: PromptOptions): Promise<string | null> {
  return new Promise((resolve) => {
    if (!promptListener) {
      resolve(null); // host non montato (test/browser): null in sicurezza
      return;
    }
    promptListener({ opts, resolve });
  });
}

export function setPromptListener(fn: ((req: PromptRequest) => void) | null): void {
  promptListener = fn;
}

// ── Import dialog (MDL2): file meta + tipo (solo/riunione) + contesto ──────────
export interface ImportDialogOptions {
  fileName: string;
  durationS: number; // 0 = ignota (non mostrare)
  sizeBytes: number; // 0 = ignoto (non mostrare)
  defaultMode: string; // "solo" | "riunione"
  defaultContext: string;
}

export interface ImportDialogResult {
  mode: string;
  context: string;
}

export interface ImportRequest {
  opts: ImportDialogOptions;
  resolve: (result: ImportDialogResult | null) => void; // null = annullato
}

let importListener: ((req: ImportRequest) => void) | null = null;

export function importDialog(opts: ImportDialogOptions): Promise<ImportDialogResult | null> {
  return new Promise((resolve) => {
    if (!importListener) {
      resolve(null); // host non montato (test/browser): null in sicurezza
      return;
    }
    importListener({ opts, resolve });
  });
}

export function setImportListener(fn: ((req: ImportRequest) => void) | null): void {
  importListener = fn;
}

// Dati finti realistici per l'harness di rifinitura visiva (DEV-only).
// NON usati in produzione: il modulo `dev/` è importato solo dietro la guardia
// `import.meta.env.DEV` in main.tsx → tree-shaken dal build.
//
// Scopo: mostrare ogni schermata/stato senza eseguire whisper + LLM (lenti e,
// con Ollama su iGPU AMD, rischiosi). Le schermate prop-driven ricevono queste
// fixture come props; quelle che leggono dal bridge (Models/Settings/Sessions/
// la sidebar "Recenti", la Home) le ricevono via il mock di window.pywebview.api.

import type {
  AppInfo, Artifacts, AudioMeta, DiskUsage, JobView, ModelEntry, OllamaModelEntry, OllamaStatus,
  Question, ResourceUsage, SessionItem, SystemSpecs, VokariSettings,
} from "../bridge";

// ── Markdown realistici (dominio: magazzino alimentare B2B/B2C) ───────────────

export const SAMPLE_BRIEFING_MD = `---
data: 2026-06-15
tipo: riunione
durata: 27:41
modello: whisper-large-v3-turbo
lingua: it
parole: 4128
---

# Briefing — Riunione produzione · scorte e turni

## Contesto
- Allineamento settimanale sulla produzione del fresco: priorità sui lotti in
  scadenza, copertura turni e una resa anomala sulla linea di miscelazione.

## Decisioni
- I lotti MAC in scadenza venerdì vanno lavorati per primi (priorità FEFO).
- Secondo operaio sulla linea di confezionamento nel turno del mattino.
- Si attiva un controllo a campione sulla resa della miscelazione M2.

## Domande aperte
- [DA CHIARIRE: La resa anomala su M2 è un problema di taratura o di materia prima? (domanda saltata in rifinitura)]
- [DA CHIARIRE: Destinatario del briefing non specificato — è per il responsabile di produzione?]

## Prossimi passi
- [ ] Marco — riorganizzare il piano di lavorazione FEFO entro giovedì
- [ ] Sara — verificare la taratura della bilancia sulla linea M2
- [ ] Confermare la copertura del turno serale entro venerdì
`;

export const SAMPLE_RECAP_MD = `# Riunione produzione · scorte e turni

La riunione settimanale si è concentrata su tre temi: i lotti in scadenza, la
copertura dei turni e una resa anomala sulla linea di miscelazione M2.

Sui lotti, è stata confermata la priorità ai MAC in scadenza venerdì, da lavorare
per primi secondo la logica FEFO. Per i turni, si aggiunge un secondo operaio al
confezionamento del mattino, dove i volumi sono cresciuti.

Sul fronte qualità resta aperta la resa anomala su M2: non è ancora chiaro se sia
una questione di taratura della bilancia o di materia prima. Sara verificherà la
taratura, mentre Marco riorganizza il piano di lavorazione entro giovedì.
`;

export const SAMPLE_OBSIDIAN_MD = `---
data: 2026-06-15
tags: [riunione, produzione, fresco, scorte]
---

# Riunione produzione · 2026-06-15

Priorità **FEFO** sui lotti MAC in scadenza. Secondo operaio al confezionamento
mattutino. Aperta la resa anomala su [[Linea M2]] — taratura o materia prima?

Collegamenti: [[Piano lavorazione settimanale]] · [[Tracciabilità lotti MAC]]
`;

export const SAMPLE_TRANSCRIPT = `Allora, partiamo dai lotti in scadenza. Abbiamo tre bancali di MAC che scadono
venerdì, quindi quelli vanno lavorati per primi. Marco, riesci a riorganizzare il
piano? Sì, lo sistemo entro giovedì. Bene. Poi sul confezionamento del mattino:
i volumi sono cresciuti, serve un secondo operaio almeno fino a fine mese.
D'accordo. Ultima cosa, la resa sulla M2 è venuta strana questa settimana, più
bassa del solito. Non so se è la bilancia o la materia prima. Sara, puoi
controllare la taratura? Certo, ci guardo domani mattina.`;

// Anteprima leggibile dell'analisi mentre "si forma" in streaming (evento
// analysis_preview / preview_from_partial_json lato motore).
export const SAMPLE_ANALYSIS_PREVIEW =
  "Riunione produzione · scorte e turni. Allineamento sulla produzione del fresco: " +
  "priorità sui lotti in scadenza, copertura turni e una resa anomala sulla linea di " +
  "miscelazione. Lavorare per primi i lotti MAC in scadenza venerdì (FEFO). Aggiungere un " +
  "secondo operaio al confezionamento del mattino. Attivare un controllo a campione sulla resa M2";

// Spezzone di trascrizione "in corso" (per lo stato transcribing del typewriter).
export const SAMPLE_PARTIAL_TRANSCRIPT =
  "Allora, partiamo dai lotti in scadenza. Abbiamo tre bancali di MAC che scadono " +
  "venerdì, quindi quelli vanno lavorati per primi. Marco, riesci a riorganizzare il " +
  "piano? Sì, lo sistemo entro giovedì. Bene. Poi sul confezionamento del mattino";

// ── Strutture dati ────────────────────────────────────────────────────────────

export const sampleAppInfo: AppInfo = { version: "0.1.0", license: "MIT", githubStars: 42 };

// RAM bassa di proposito (8 GB) così l'harness mostra l'avviso "pesante per la tua RAM"
// sul modello da 14B (≈11.7 GB stimati) e il filtro "Compatibili" lo esclude (MOD2).
export const sampleSystemSpecs: SystemSpecs = { ramTotalGb: 8 };

// Riepilogo disco per la pill Modelli (MOD3).
export const sampleDiskUsage: DiskUsage = { usedByModelsGb: 6.3, freeGb: 142 };

// Metadati file per il dialog di import (MDL2): ~27 min, ~24 MB.
export const sampleAudioMeta: AudioMeta = { durationS: 27 * 60 + 41, sizeBytes: 24_300_000 };

export const sampleResources: ResourceUsage = { cpu: 38, ramMb: 1820, tempC: 61 };

export const sampleSettings: VokariSettings = {
  brain: "claude",
  ollamaEndpoint: "http://localhost:11434",
  ollamaModel: "qwen2.5:7b",
  whisperModel: "large-v3-turbo",
  claudeModel: "claude-sonnet-4-6",
  briefingDir: "C:\\Users\\salvo\\Documents\\VOKARI\\briefing",
  obsidianVault: "C:\\Users\\salvo\\Obsidian\\SecondoCervello",
  defaultMode: "riunione",
  transcriptionLanguage: "it",
  livePreview: true,
  liveModel: "base",
  hasApiKey: true,
};

export const sampleArtifacts: Artifacts = {
  title: "Riunione produzione · scorte e turni",
  briefingMd: SAMPLE_BRIEFING_MD,
  briefingPath: "C:\\Users\\salvo\\Documents\\VOKARI\\briefing\\2026-06-15-riunione-produzione\\briefing.md",
  recapMd: SAMPLE_RECAP_MD,
  obsidianNote: SAMPLE_OBSIDIAN_MD,
  transcriptText: SAMPLE_TRANSCRIPT,
  durationS: 27 * 60 + 41,
  model: "large-v3-turbo",
  language: "it",
  wordCount: 4128,
};

export const sampleModels: ModelEntry[] = [
  { name: "small", sizeLabel: "466 MB", speed: 3, quality: 1, languages: "IT·EN·+90",
    description: "Veloce, bozze rapide. Qualità modesta sui termini di settore.",
    recommended: false, state: "downloaded" },
  { name: "medium", sizeLabel: "1.5 GB", speed: 2, quality: 2, languages: "IT·EN·+90",
    description: "Buon compromesso velocità/qualità per audio pulito.",
    recommended: false, state: "available" },
  { name: "large-v3-turbo", sizeLabel: "1.6 GB", speed: 2, quality: 3, languages: "IT·EN·+90",
    description: "Consigliato: qualità alta, veloce quasi come medium.",
    recommended: true, state: "active" },
  { name: "large-v3", sizeLabel: "3.1 GB", speed: 1, quality: 3, languages: "IT·EN·+90",
    description: "Massima qualità, più lento. Per audio difficile o rumoroso.",
    recommended: false, state: "available" },
];

export const sampleOllama: OllamaModelEntry[] = [
  { name: "qwen2.5:7b", sizeLabel: "4.7 GB", description: "Ottimo su italiano e JSON. Default consigliato su CPU.",
    speed: 2, quality: 2, params: "7B", context: "128K", tags: ["italiano", "json", "veloce"], minRamGb: 6.1,
    detailUrl: "https://ollama.com/library/qwen2.5", isInstalled: true, isActive: true, recommended: true },
  { name: "llama3.1:8b", sizeLabel: "4.9 GB", description: "Generalista solido, multilingue.",
    speed: 2, quality: 2, params: "8B", context: "128K", tags: ["multilingue", "tool-calling"], minRamGb: 6.4,
    detailUrl: "https://ollama.com/library/llama3.1", isInstalled: true, isActive: false, recommended: false },
  { name: "qwen2.5:14b", sizeLabel: "9.0 GB", description: "Qualità superiore, più lento su CPU.",
    speed: 1, quality: 3, params: "14B", context: "128K", tags: ["italiano", "json", "reasoning"], minRamGb: 11.7,
    detailUrl: "https://ollama.com/library/qwen2.5", isInstalled: false, isActive: false, recommended: false },
  { name: "gemma2:9b", sizeLabel: "5.4 GB", description: "Alternativa Google, buona ma inferiore su IT.",
    speed: 2, quality: 2, params: "9B", context: "8K", tags: ["multilingue", "leggero"], minRamGb: 7.0,
    detailUrl: "https://ollama.com/library/gemma2", isInstalled: false, isActive: false, recommended: false },
];

export const sampleOllamaStatus: OllamaStatus = {
  installed: true, running: true, bundled: false, canInstall: true, endpoint: "http://localhost:11434",
};

export const sampleSessions: SessionItem[] = [
  { id: "s1", title: "Riunione produzione · scorte e turni", createdAt: "2026-06-15T09:12:00",
    mode: "riunione", model: "large-v3-turbo", durationMs: (27 * 60 + 41) * 1000,
    hasBriefing: true, hasRecap: true, hasObsidian: true, clarCount: 2, hasAudio: true },
  { id: "s2", title: "Idee packaging linea bio", createdAt: "2026-06-15T15:40:00",
    mode: "solo", model: "large-v3-turbo", durationMs: (8 * 60 + 3) * 1000,
    hasBriefing: true, hasRecap: true, hasObsidian: false, clarCount: 0, hasAudio: true },
  { id: "s3", title: "Call fornitore imballaggi", createdAt: "2026-06-14T11:05:00",
    mode: "riunione", model: "medium", durationMs: (19 * 60 + 22) * 1000,
    hasBriefing: true, hasRecap: false, hasObsidian: false, clarCount: 1, hasAudio: true },
  { id: "s4", title: "Brainstorming bando PSR misura 4.2", createdAt: "2026-06-12T17:30:00",
    mode: "solo", model: "large-v3-turbo", durationMs: (33 * 60 + 14) * 1000,
    hasBriefing: true, hasRecap: true, hasObsidian: true, clarCount: 0, hasAudio: true },
  { id: "s5", title: "Audit HACCP — note a caldo", createdAt: "2026-06-10T08:48:00",
    mode: "solo", model: "small", durationMs: (5 * 60 + 51) * 1000,
    hasBriefing: true, hasRecap: false, hasObsidian: false, clarCount: 0, hasAudio: false },
];

export const sampleQuestions: Question[] = [
  { id: "q1", text: "Per chi è questo briefing? (chi lo leggerà)", priority: "high",
    suggestions: ["Responsabile di produzione", "Tutto il team", "Solo per me"],
    why: "il taglio del briefing dipende dal lettore", fromAudio: false },
  { id: "q2", text: "La resa anomala su M2 è già stata segnalata in passato?", priority: "medium",
    suggestions: ["Sì, ricorrente", "No, è la prima volta", "Non so"],
    why: "citata una resa fuori norma su M2", fromAudio: true },
  { id: "q3", text: "C'è una scadenza per confermare i turni?", priority: "low",
    suggestions: [],
    why: "turni nominati senza data limite", fromAudio: true },
];

// Job di base + override per stato (usato dalla schermata Processing).
export function jobView(over: Partial<JobView> = {}): JobView {
  return {
    jobId: "dev-job", title: "Riunione produzione · scorte e turni",
    status: "transcribing", pct: 0, source: "both", mode: "riunione",
    model: "large-v3-turbo", language: "it", partialText: "", transcript: "",
    durationS: 27 * 60 + 41, questions: sampleQuestions, markers: [],
    briefingMd: SAMPLE_BRIEFING_MD, briefingPath: sampleArtifacts.briefingPath, error: "",
    ...over,
  };
}

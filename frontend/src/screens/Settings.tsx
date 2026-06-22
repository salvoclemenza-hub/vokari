import { useEffect, useState } from "react";
import { bridge, onVokariEvent, DEFAULT_SETTINGS, type ModelEntry, type VokariSettings, type LhmStatus } from "../bridge";
import { toast } from "../toast";
import { confirmDialog } from "../confirm";
import { VkIcon } from "../icons";

// ────────────────────────────────────────────────────────────
// Sezione Whisper (usata anche da Models.tsx se importata)
// ────────────────────────────────────────────────────────────
export function WhisperModelList({
  models,
  activeModel,
  downloading,
  onDownload,
  onActivate,
}: {
  models: ModelEntry[];
  activeModel: string;
  downloading: string | null;
  onDownload: (name: string) => void;
  onActivate: (name: string) => void;
}) {
  return (
    <>
      {models.map((m) => {
        const isActive = m.name === activeModel;
        const isDownloading = downloading === m.name;
        return (
          <div
            className={"vk-model" + (isActive ? " on" : "")}
            key={m.name}
            title={m.description}
            onClick={() => {
              if (m.state !== "available" && !isActive) onActivate(m.name);
            }}
            style={{ cursor: m.state !== "available" && !isActive ? "pointer" : "default" }}
          >
            <span className="vk-radio"></span>
            <span className="nm">
              <span className="t">
                {m.name}
                {m.recommended && <span className="df">DEFAULT</span>}
              </span>
              <span className="m">
                {m.sizeLabel} · {m.languages}
              </span>
            </span>
            {isActive ? (
              <span className="dl ok">
                <VkIcon.check />
                Attivo
              </span>
            ) : m.state === "downloaded" ? (
              <span className="dl ok">
                <VkIcon.check />
                Scaricato
              </span>
            ) : (
              <button
                className="dl get"
                disabled={isDownloading}
                onClick={(e) => {
                  e.stopPropagation();
                  onDownload(m.name);
                }}
              >
                <VkIcon.down />
                {isDownloading ? "Scaricando…" : "Scarica"}
              </button>
            )}
          </div>
        );
      })}
    </>
  );
}

// ────────────────────────────────────────────────────────────
// Schermata Impostazioni
// ────────────────────────────────────────────────────────────
export function ScreenSettings({ onOpenModels }: { onOpenModels?: () => void } = {}) {
  const [settings, setSettings] = useState<VokariSettings>(DEFAULT_SETTINGS);
  const [apiKeyInput, setApiKeyInput] = useState("");
  // Chiave già impostata: si mostra mascherata + "Sostituisci"; `replacing` rivela l'input.
  const [replacing, setReplacing] = useState(false);
  // SET1: esito della verifica chiave (ping a Claude). idle finché non si clicca "Verifica".
  const [keyVerify, setKeyVerify] = useState<{ state: "idle" | "checking" | "ok" | "err"; msg: string }>(
    { state: "idle", msg: "" });
  const [models, setModels] = useState<ModelEntry[]>([]);
  const [downloading, setDownloading] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  // Verifica runtime Ollama (metodo bridge esistente; gestione completa → schermata Modelli AI).
  const [ollamaState, setOllamaState] = useState<"unknown" | "checking" | "up" | "down">("unknown");
  const [lhmStatus, setLhmStatus] = useState<LhmStatus | null>(null);
  const [lhmInstalling, setLhmInstalling] = useState(false);

  // carica settings + modelli + stato LHM al mount
  useEffect(() => {
    bridge.getSettings().then(setSettings);
    bridge.listModels().then(setModels);
    bridge.lhmStatus().then(setLhmStatus);
  }, []);

  // ascolta eventi model_download per aggiornare la lista
  useEffect(() => {
    const off = onVokariEvent((event, payload) => {
      if (event !== "model_download") return;
      if (payload.status === "start") {
        setDownloading(payload.name as string);
      } else if (payload.status === "done") {
        setDownloading(null);
        toast(`Modello ${payload.name as string} scaricato ✓`, "success");
        bridge.listModels().then(setModels);
      } else if (payload.status === "error") {
        setDownloading(null);
        toast(`Download di ${payload.name as string} non riuscito: ${(payload.error as string) ?? "errore sconosciuto"}`, "error");
        bridge.listModels().then(setModels);
      }
    });
    return off;
  }, []);

  // ascolta eventi lhm_progress per aggiornare lo stato LHM
  useEffect(() => {
    const off = onVokariEvent((event, payload) => {
      if (event !== "lhm_progress") return;
      if (payload.status === "done") {
        setLhmInstalling(false);
        toast("LibreHardwareMonitor installato e avviato ✓", "success");
        bridge.lhmStatus().then(setLhmStatus);
      } else if (payload.status === "error") {
        setLhmInstalling(false);
        toast(`Installazione LHM non riuscita: ${(payload.error as string) ?? "errore sconosciuto"}`, "error");
      }
    });
    return off;
  }, []);

  // helper: salva un patch parziale e aggiorna lo stato locale
  async function savePatch(patch: Partial<Omit<VokariSettings, "hasApiKey">>) {
    setSaving(true);
    try {
      const updated = await bridge.saveSettings(patch);
      setSettings(updated);
      toast("Salvato ✓", "success");   // auto-save: feedback immediato a ogni cambio
    } catch (e) {
      toast(`Salvataggio impostazioni non riuscito: ${String(e)}`, "error");
    } finally {
      setSaving(false);
    }
  }

  // Verifica raggiungibilità del runtime Ollama (solo on-demand, mai al mount).
  async function verifyOllama() {
    setOllamaState("checking");
    try {
      const st = await bridge.ollamaStatus();
      setOllamaState(st.running ? "up" : "down");
    } catch {
      setOllamaState("down");
    }
  }

  // Ripristina le SOLE preferenze di comportamento ai default. Cartelle, chiave API e
  // selezione modelli (gestiti in Modelli AI) NON vengono toccati — pure-frontend via saveSettings.
  async function handleReset() {
    const ok = await confirmDialog({
      title: "Ripristinare le impostazioni predefinite?",
      message: "Le preferenze di comportamento tornano ai valori di default. Cartelle, chiave API e modelli non vengono toccati.",
      confirmLabel: "Ripristina",
      cancelLabel: "Annulla",
    });
    if (!ok) return;
    await savePatch({
      brain: DEFAULT_SETTINGS.brain,
      ollamaEndpoint: DEFAULT_SETTINGS.ollamaEndpoint,
      defaultMode: DEFAULT_SETTINGS.defaultMode,
      transcriptionLanguage: DEFAULT_SETTINGS.transcriptionLanguage,
      livePreview: DEFAULT_SETTINGS.livePreview,
      liveModel: DEFAULT_SETTINGS.liveModel,
    });
  }

  async function handleApiKeyBlur() {
    const trimmed = apiKeyInput.trim();
    if (!trimmed) return;
    try {
      const res = await bridge.setApiKey(trimmed);
      if (res.hasApiKey) {
        setSettings((s) => ({ ...s, hasApiKey: true }));
        setApiKeyInput("");          // svuota il campo: mai rimandare la chiave in chiaro
        setReplacing(false);          // torna alla vista mascherata "(impostata)"
        toast("Chiave API salvata ✓", "success");
      } else {
        toast("Chiave API non salvata", "error");
      }
    } catch (e) {
      toast(`Salvataggio chiave non riuscito: ${String(e)}`, "error");
    }
  }

  // SET1: verifica la chiave salvata con un ping a Claude (solo on-click, mai al mount).
  async function handleVerifyKey() {
    setKeyVerify({ state: "checking", msg: "Verifica in corso…" });
    const res = await bridge.verifyApiKey();
    if (res.ok) setKeyVerify({ state: "ok", msg: "Chiave valida · Claude raggiungibile" });
    else setKeyVerify({ state: "err", msg: res.error || "Verifica non riuscita" });
  }

  // SET2: rimuove la chiave dal keyring previa conferma in-app.
  async function handleRemoveKey() {
    const ok = await confirmDialog({
      title: "Rimuovere la chiave API?",
      message: "La chiave Claude verrà cancellata dal keyring. Potrai reinserirla quando vuoi.",
      confirmLabel: "Rimuovi", cancelLabel: "Annulla", danger: true,
    });
    if (!ok) return;
    const res = await bridge.deleteApiKey();
    if (res.ok) {
      setSettings((s) => ({ ...s, hasApiKey: false }));
      setReplacing(false);
      setApiKeyInput("");
      setKeyVerify({ state: "idle", msg: "" });
      toast("Chiave API rimossa", "success");
    } else {
      toast("Rimozione non riuscita", "error");
    }
  }

  async function handleBrowse(field: "briefingDir" | "obsidianVault") {
    const { path } = await bridge.browseFolder();
    if (path) await savePatch({ [field]: path });
  }

  async function handleLhmInstall() {
    setLhmInstalling(true);
    try {
      await bridge.lhmInstall();
    } catch (e) {
      toast(`Installazione LHM non riuscita: ${String(e)}`, "error");
      setLhmInstalling(false);
    }
  }

  async function handleLhmStart() {
    try {
      const res = await bridge.lhmStart();
      if (!res.ok) toast("Avvio LHM non riuscito (UAC annullato?)", "error");
      else { toast("LibreHardwareMonitor avviato ✓", "success"); bridge.lhmStatus().then(setLhmStatus); }
    } catch (e) { toast(`Avvio LHM non riuscito: ${String(e)}`, "error"); }
  }

  async function handleLhmStop() {
    try {
      await bridge.lhmStop();
      toast("LibreHardwareMonitor fermato", "success");
      bridge.lhmStatus().then(setLhmStatus);
    } catch (e) { toast(`Stop LHM non riuscito: ${String(e)}`, "error"); }
  }

  async function handleLhmUninstall() {
    try {
      await bridge.lhmUninstall();
      toast("LibreHardwareMonitor rimosso", "success");
      bridge.lhmStatus().then(setLhmStatus);
    } catch (e) { toast(`Rimozione LHM non riuscita: ${String(e)}`, "error"); }
  }

  async function handleDownload(name: string) {
    try {
      await bridge.downloadModel(name);   // l'esito reale arriva via evento model_download
      bridge.listModels().then(setModels);
    } catch (e) {
      toast(`Avvio download non riuscito: ${String(e)}`, "error");
    }
  }

  return (
    <>
      <div className="vk-greet">
        <div>
          <div className="vk-kick">~/impostazioni</div>
          <h1>Impostazioni{saving ? <span style={{ fontSize: 13, marginLeft: 8, opacity: 0.5 }}>Salvo…</span> : null}</h1>
        </div>
        <button className="vk-reset" onClick={() => void handleReset()}>
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
            <path d="M3 12a9 9 0 1 0 3-6.7L3 8" /><path d="M3 3v5h5" />
          </svg>
          Ripristina predefiniti
        </button>
      </div>

      <div className="vk-set">
        <div className="vk-set-grid">
          {/* colonna sinistra: Cervello AI · Modelli AI·Whisper · Temperatura CPU */}
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            {/* Cervello AI */}
            <div className="vk-sc">
              <div className="vk-sc-h">
                <span className="ico">
                  <VkIcon.brain />
                </span>
                Cervello AI
              </div>
              <div className="vk-sc-sub">
                Chi organizza la trascrizione nel briefing. Solo il testo viene inviato.
              </div>

              <div className="vk-field">
                <label>Anthropic API key</label>
                {settings.hasApiKey && !replacing ? (
                  <div className="vk-key">
                    <span className="val">••••••••••••••••<b>(impostata)</b></span>
                    <button className="vk-keyact" onClick={() => void handleVerifyKey()}
                            disabled={keyVerify.state === "checking"}>
                      {keyVerify.state === "checking" ? "Verifico…" : "Verifica"}
                    </button>
                    <button className="vk-keyact" onClick={() => setReplacing(true)}>Sostituisci</button>
                    <button className="vk-keyact danger" onClick={() => void handleRemoveKey()}>Rimuovi</button>
                  </div>
                ) : (
                  <input
                    className="vk-input key"
                    type="password"
                    value={apiKeyInput}
                    placeholder={settings.hasApiKey ? "••••••••••••••••••• (impostata)" : "sk-ant-…"}
                    onChange={(e) => setApiKeyInput(e.target.value)}
                    onBlur={() => void handleApiKeyBlur()}
                    onKeyDown={(e) => { if (e.key === "Enter") void handleApiKeyBlur(); }}
                    autoFocus={replacing}
                  />
                )}
                <div className="vk-hlp lock">
                  <VkIcon.lock />
                  Necessaria per Claude API. Salvata nel keyring del sistema, mai su disco.
                </div>
                {keyVerify.state !== "idle" && (
                  <div className={"vk-verify " + keyVerify.state} role="status">
                    {keyVerify.state === "ok" && <VkIcon.check />}
                    {keyVerify.msg}
                  </div>
                )}
                {replacing && settings.hasApiKey && (
                  <button className="vk-linkbtn" onClick={() => { setReplacing(false); setApiKeyInput(""); }}>
                    Annulla
                  </button>
                )}
              </div>

              <div className="vk-field">
                <label>Modalità di organizzazione</label>
                <div className="vk-seg2">
                  <button
                    className={settings.brain === "claude" ? "on" : ""}
                    onClick={() => void savePatch({ brain: "claude" })}
                  >
                    Claude API
                  </button>
                  <button
                    className={settings.brain === "ollama" ? "on" : ""}
                    onClick={() => void savePatch({ brain: "ollama" })}
                  >
                    Locale (Ollama)
                  </button>
                </div>
              </div>

              <div className="vk-field" style={{ marginBottom: 0 }}>
                <label>Endpoint Ollama (offline)</label>
                <div className="vk-path">
                  <input
                    className="vk-input"
                    type="text"
                    value={settings.ollamaEndpoint}
                    placeholder="http://localhost:11434"
                    onChange={(e) => setSettings((s) => ({ ...s, ollamaEndpoint: e.target.value }))}
                    onBlur={() => void savePatch({ ollamaEndpoint: settings.ollamaEndpoint })}
                  />
                  <button className="vk-mini" onClick={() => void verifyOllama()}>Verifica</button>
                </div>
                {ollamaState !== "unknown" && (
                  <div className={"vk-ollama-state" + (ollamaState === "up" ? " up" : "")}>
                    <span className="dot" />
                    {ollamaState === "checking"
                      ? "verifica in corso…"
                      : ollamaState === "up"
                      ? "runtime in esecuzione · raggiungibile"
                      : "runtime fermo — avvialo dalla schermata Modelli AI"}
                  </div>
                )}
                {onOpenModels && (
                  <button className="vk-xlink" onClick={() => onOpenModels()}>
                    Gestione completa dei modelli <VkIcon.arrow /> Modelli AI
                  </button>
                )}
              </div>
            </div>

            {/* Temperatura CPU (LHM) */}
            <div className="vk-sc">
              <div className="vk-sc-h">
                <span className="ico"><VkIcon.cpu /></span>
                Temperatura CPU
              </div>
              <div className="vk-sc-sub">
                LibreHardwareMonitor espone i sensori hardware via WMI. Richiede una
                conferma UAC al primo avvio; le letture successive non richiedono admin.
              </div>
              {lhmStatus === null ? (
                <div className="vk-hlp">Carico stato…</div>
              ) : (
                <div className="vk-field" style={{ marginBottom: 0 }}>
                  <div style={{ fontSize: 13, marginBottom: 10, opacity: 0.8 }}>
                    {!lhmStatus.installed
                      ? "Non installato"
                      : lhmStatus.running
                      ? "Attivo — temperatura visibile nella barra di stato"
                      : "Installato · non in esecuzione"}
                  </div>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    {!lhmStatus.installed ? (
                      <button
                        className="vk-mini"
                        disabled={lhmInstalling}
                        onClick={() => void handleLhmInstall()}
                      >
                        {lhmInstalling ? "Installando…" : "Installa"}
                      </button>
                    ) : (
                      <>
                        {!lhmStatus.running && (
                          <button className="vk-mini" onClick={() => void handleLhmStart()}>
                            Avvia
                          </button>
                        )}
                        {lhmStatus.running && (
                          <button className="vk-mini" onClick={() => void handleLhmStop()}>
                            Ferma
                          </button>
                        )}
                        <button
                          className="vk-mini"
                          style={{ opacity: 0.6 }}
                          onClick={() => void handleLhmUninstall()}
                        >
                          Rimuovi
                        </button>
                      </>
                    )}
                    <button
                      className="vk-mini"
                      style={{ opacity: 0.6 }}
                      onClick={() => bridge.lhmStatus().then(setLhmStatus)}
                    >
                      Aggiorna stato
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* colonna destra: Output & integrazioni · Generale */}
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            {/* Output & integrazioni */}
            <div className="vk-sc">
              <div className="vk-sc-h">
                <span className="ico">
                  <VkIcon.folder />
                </span>
                Output &amp; integrazioni
              </div>
              <div className="vk-sc-sub">Dove finiscono i briefing e le note.</div>

              <div className="vk-field">
                <label>Cartella dei briefing</label>
                <div className="vk-path">
                  <input
                    className="vk-input"
                    type="text"
                    value={settings.briefingDir}
                    placeholder="~/Documenti/Vokari/briefing"
                    onChange={(e) => setSettings((s) => ({ ...s, briefingDir: e.target.value }))}
                    onBlur={() => void savePatch({ briefingDir: settings.briefingDir })}
                  />
                  <button className="vk-mini" onClick={() => void handleBrowse("briefingDir")}>
                    Sfoglia
                  </button>
                </div>
              </div>

              <div className="vk-field" style={{ marginBottom: 0 }}>
                <label>Vault Obsidian</label>
                <div className="vk-path">
                  <input
                    className="vk-input"
                    type="text"
                    value={settings.obsidianVault}
                    placeholder="~/Obsidian/Secondo cervello"
                    onChange={(e) => setSettings((s) => ({ ...s, obsidianVault: e.target.value }))}
                    onBlur={() => void savePatch({ obsidianVault: settings.obsidianVault })}
                  />
                  <button className="vk-mini" onClick={() => void handleBrowse("obsidianVault")}>
                    Sfoglia
                  </button>
                </div>
              </div>
            </div>

            {/* Generale */}
            <div className="vk-sc">
              <div className="vk-sc-h">
                <span className="ico">
                  <VkIcon.gear />
                </span>
                Generale
              </div>
              <div className="vk-sc-sub">Comportamenti predefiniti.</div>

              <div className="vk-field">
                <label>Modalità di default</label>
                <div className="vk-seg2">
                  <button
                    className={settings.defaultMode === "solo" ? "on" : ""}
                    onClick={() => void savePatch({ defaultMode: "solo" })}
                  >
                    Solo
                  </button>
                  <button
                    className={settings.defaultMode === "riunione" ? "on" : ""}
                    onClick={() => void savePatch({ defaultMode: "riunione" })}
                  >
                    Riunione
                  </button>
                </div>
              </div>

              <div className="vk-field">
                <label>Lingua di trascrizione</label>
                <div className="vk-seg2">
                  <button
                    className={settings.transcriptionLanguage === "auto" ? "on" : ""}
                    onClick={() => void savePatch({ transcriptionLanguage: "auto" })}
                  >
                    Automatica
                  </button>
                  <button
                    className={settings.transcriptionLanguage === "it" ? "on" : ""}
                    onClick={() => void savePatch({ transcriptionLanguage: "it" })}
                  >
                    Italiano
                  </button>
                  <button
                    className={settings.transcriptionLanguage === "en" ? "on" : ""}
                    onClick={() => void savePatch({ transcriptionLanguage: "en" })}
                  >
                    English
                  </button>
                </div>
              </div>

              <div className="vk-field">
                <label>Anteprima live durante la registrazione</label>
                <div className="vk-seg2">
                  <button
                    className={settings.livePreview ? "on" : ""}
                    onClick={() => void savePatch({ livePreview: true })}
                  >
                    Attiva
                  </button>
                  <button
                    className={!settings.livePreview ? "on" : ""}
                    onClick={() => void savePatch({ livePreview: false })}
                  >
                    Disattiva
                  </button>
                </div>
              </div>

              {settings.livePreview && (
                <div className="vk-field" style={{ marginBottom: 0 }}>
                  <label>Modello live</label>
                  <div className="vk-seg2">
                    {(["tiny", "base", "small"] as const).map((m) => {
                      const notReady = (models.find((x) => x.name === m)?.state ?? "available") === "available";
                      return (
                        <button
                          key={m}
                          className={settings.liveModel === m ? "on" : ""}
                          onClick={() => void savePatch({ liveModel: m })}
                        >
                          {m === "tiny" ? "tiny · veloce" : m === "base" ? "base · bilanciato" : "small · preciso"}
                          {notReady && <span style={{ marginLeft: 4, opacity: 0.5, fontSize: 11 }}>↓</span>}
                        </button>
                      );
                    })}
                  </div>
                  {(() => {
                    const sel = models.find((x) => x.name === settings.liveModel);
                    if (!sel || sel.state === "available") {
                      return (
                        <div className="vk-dlnote">
                          <VkIcon.down />
                          <span><b>{settings.liveModel}</b> non è ancora scaricato.</span>
                          <button
                            disabled={downloading === settings.liveModel}
                            onClick={() => void handleDownload(settings.liveModel)}
                          >
                            {downloading === settings.liveModel ? "Scaricando…" : "Scarica ora"}
                          </button>
                        </div>
                      );
                    }
                    return (
                      <div className="vk-hlp">
                        tiny = quasi istantaneo ma impreciso · base = buon compromesso (default) · small = più accurato, ~3–5 s di ritardo
                      </div>
                    );
                  })()}
                </div>
              )}
            </div>
          </div>

          <div className="vk-set-priv">
            <VkIcon.lock />
            L'audio non lascia mai il dispositivo. Nessun account obbligatorio: solo il testo viene inviato
            all'AI scelta.
          </div>
        </div>
      </div>
    </>
  );
}

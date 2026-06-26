import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { bridge, onVokariEvent, DEFAULT_SETTINGS, type ModelEntry, type VokariSettings, type LhmStatus } from "../bridge";
import { toast } from "../toast";
import { confirmDialog } from "../confirm";
import { VkIcon } from "../icons";
import { ollamaHint, type OllamaHint } from "../modelStatus";
import i18n, { SUPPORTED_LANGUAGES, LANGUAGE_LABELS, type AppLanguage } from "../i18n";

// ────────────────────────────────────────────────────────────
// Schermata Impostazioni
// ────────────────────────────────────────────────────────────
export function ScreenSettings({ onOpenModels }: { onOpenModels?: () => void } = {}) {
  const { t } = useTranslation();
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
  // OllamaHint distingue installato-ma-fermo da non-installato (B2).
  const [ollamaState, setOllamaState] = useState<"unknown" | "checking" | OllamaHint>("unknown");
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
        toast(t("settings.modelDownloaded", { name: payload.name as string }), "success");
        bridge.listModels().then(setModels);
      } else if (payload.status === "error") {
        setDownloading(null);
        toast(t("settings.modelDownloadFail", { name: payload.name as string, error: (payload.error as string) ?? t("settings.unknownError") }), "error");
        bridge.listModels().then(setModels);
      }
    });
    return off;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ascolta eventi lhm_progress per aggiornare lo stato LHM
  useEffect(() => {
    const off = onVokariEvent((event, payload) => {
      if (event !== "lhm_progress") return;
      if (payload.status === "done") {
        setLhmInstalling(false);
        toast(t("settings.lhmInstalled"), "success");
        bridge.lhmStatus().then(setLhmStatus);
      } else if (payload.status === "error") {
        setLhmInstalling(false);
        toast(t("settings.lhmInstallFail", { error: (payload.error as string) ?? t("settings.unknownError") }), "error");
      }
    });
    return off;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // helper: salva un patch parziale e aggiorna lo stato locale
  async function savePatch(patch: Partial<Omit<VokariSettings, "hasApiKey">>) {
    setSaving(true);
    try {
      const updated = await bridge.saveSettings(patch);
      setSettings(updated);
      toast(t("settings.saved"), "success");   // auto-save: feedback immediato a ogni cambio
    } catch (e) {
      toast(t("settings.saveFail", { error: String(e) }), "error");
    } finally {
      setSaving(false);
    }
  }

  // Verifica raggiungibilità del runtime Ollama (solo on-demand, mai al mount).
  async function verifyOllama() {
    setOllamaState("checking");
    try {
      const st = await bridge.ollamaStatus();
      setOllamaState(ollamaHint(st)); // up | installed-down | not-installed
    } catch {
      setOllamaState("not-installed");
    }
  }

  // Ripristina le SOLE preferenze di comportamento ai default. Cartelle, chiave API e
  // selezione modelli (gestiti in Modelli AI) NON vengono toccati — pure-frontend via saveSettings.
  async function handleReset() {
    const ok = await confirmDialog({
      title: t("settings.resetTitle"),
      message: t("settings.resetMsg"),
      confirmLabel: t("settings.resetConfirm"),
      cancelLabel: t("settings.cancel"),
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
        toast(t("settings.keySaved"), "success");
      } else {
        toast(t("settings.keyNotSaved"), "error");
      }
    } catch (e) {
      toast(t("settings.keySaveFail", { error: String(e) }), "error");
    }
  }

  // SET1: verifica la chiave salvata con un ping a Claude (solo on-click, mai al mount).
  async function handleVerifyKey() {
    setKeyVerify({ state: "checking", msg: t("settings.verifying") });
    const res = await bridge.verifyApiKey();
    if (res.ok) setKeyVerify({ state: "ok", msg: t("settings.keyValid") });
    else setKeyVerify({ state: "err", msg: res.error || t("settings.verifyFail") });
  }

  // SET2: rimuove la chiave dal keyring previa conferma in-app.
  async function handleRemoveKey() {
    const ok = await confirmDialog({
      title: t("settings.removeKeyTitle"),
      message: t("settings.removeKeyMsg"),
      confirmLabel: t("settings.remove"), cancelLabel: t("settings.cancel"), danger: true,
    });
    if (!ok) return;
    const res = await bridge.deleteApiKey();
    if (res.ok) {
      setSettings((s) => ({ ...s, hasApiKey: false }));
      setReplacing(false);
      setApiKeyInput("");
      setKeyVerify({ state: "idle", msg: "" });
      toast(t("settings.keyRemoved"), "success");
    } else {
      toast(t("settings.removeFail"), "error");
    }
  }

  async function handleBrowse(field: "briefingDir" | "obsidianVault") {
    const { path } = await bridge.browseFolder();
    if (path) await savePatch({ [field]: path });
  }

  // Tema 3: cambia la lingua dell'app (UI + output AI). changeLanguage prima → UI a caldo
  // immediata; poi persiste in settings.app_language.
  async function changeAppLanguage(lang: AppLanguage) {
    if (lang === settings.appLanguage) return;
    void i18n.changeLanguage(lang);
    await savePatch({ appLanguage: lang });
  }

  async function handleLhmInstall() {
    setLhmInstalling(true);
    try {
      await bridge.lhmInstall();
    } catch (e) {
      toast(t("settings.lhmInstallFail", { error: String(e) }), "error");
      setLhmInstalling(false);
    }
  }

  async function handleLhmStart() {
    try {
      const res = await bridge.lhmStart();
      if (!res.ok) toast(t("settings.lhmStartFailUac"), "error");
      else { toast(t("settings.lhmStarted"), "success"); bridge.lhmStatus().then(setLhmStatus); }
    } catch (e) { toast(t("settings.lhmStartFail", { error: String(e) }), "error"); }
  }

  async function handleLhmStop() {
    try {
      await bridge.lhmStop();
      toast(t("settings.lhmStopped"), "success");
      bridge.lhmStatus().then(setLhmStatus);
    } catch (e) { toast(t("settings.lhmStopFail", { error: String(e) }), "error"); }
  }

  async function handleLhmUninstall() {
    try {
      await bridge.lhmUninstall();
      toast(t("settings.lhmRemoved"), "success");
      bridge.lhmStatus().then(setLhmStatus);
    } catch (e) { toast(t("settings.lhmUninstallFail", { error: String(e) }), "error"); }
  }

  async function handleDownload(name: string) {
    try {
      await bridge.downloadModel(name);   // l'esito reale arriva via evento model_download
      bridge.listModels().then(setModels);
    } catch (e) {
      toast(t("settings.downloadStartFail", { error: String(e) }), "error");
    }
  }

  return (
    <>
      <div className="vk-greet">
        <div>
          <div className="vk-kick">{t("settings.kick")}</div>
          <h1>{t("settings.heading")}{saving ? <span style={{ fontSize: 13, marginLeft: 8, opacity: 0.5 }}>{t("settings.savingInline")}</span> : null}</h1>
        </div>
        <button className="vk-reset" onClick={() => void handleReset()}>
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
            <path d="M3 12a9 9 0 1 0 3-6.7L3 8" /><path d="M3 3v5h5" />
          </svg>
          {t("settings.resetBtn")}
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
                {t("settings.brainTitle")}
              </div>
              <div className="vk-sc-sub">
                {t("settings.brainSub")}
              </div>

              <div className="vk-field">
                <label>{t("settings.apiKeyLabel")}</label>
                {settings.hasApiKey && !replacing ? (
                  <div className="vk-key">
                    <span className="val">••••••••••••••••<b>{t("settings.keySet")}</b></span>
                    <button className="vk-keyact" onClick={() => void handleVerifyKey()}
                            disabled={keyVerify.state === "checking"}>
                      {keyVerify.state === "checking" ? t("settings.verifyingShort") : t("settings.verify")}
                    </button>
                    <button className="vk-keyact" onClick={() => setReplacing(true)}>{t("settings.replace")}</button>
                    <button className="vk-keyact danger" onClick={() => void handleRemoveKey()}>{t("settings.remove")}</button>
                  </div>
                ) : (
                  <input
                    className="vk-input key"
                    type="password"
                    value={apiKeyInput}
                    placeholder={settings.hasApiKey ? t("settings.keyPlaceholderSet") : t("settings.keyPlaceholderEmpty")}
                    onChange={(e) => setApiKeyInput(e.target.value)}
                    onBlur={() => void handleApiKeyBlur()}
                    onKeyDown={(e) => { if (e.key === "Enter") void handleApiKeyBlur(); }}
                    autoFocus={replacing}
                  />
                )}
                <div className="vk-hlp lock">
                  <VkIcon.lock />
                  {t("settings.keyHelp")}
                </div>
                {keyVerify.state !== "idle" && (
                  <div className={"vk-verify " + keyVerify.state} role="status">
                    {keyVerify.state === "ok" && <VkIcon.check />}
                    {keyVerify.msg}
                  </div>
                )}
                {replacing && settings.hasApiKey && (
                  <button className="vk-linkbtn" onClick={() => { setReplacing(false); setApiKeyInput(""); }}>
                    {t("settings.cancel")}
                  </button>
                )}
              </div>

              <div className="vk-field">
                <label>{t("settings.orgModeLabel")}</label>
                <div className="vk-seg2">
                  <button
                    className={settings.brain === "claude" ? "on" : ""}
                    onClick={() => void savePatch({ brain: "claude" })}
                  >
                    {t("settings.claudeApi")}
                  </button>
                  <button
                    className={settings.brain === "ollama" ? "on" : ""}
                    onClick={() => void savePatch({ brain: "ollama" })}
                  >
                    {t("settings.localOllama")}
                  </button>
                </div>
              </div>

              <div className="vk-field" style={{ marginBottom: 0 }}>
                <label>{t("settings.ollamaEndpointLabel")}</label>
                <div className="vk-path">
                  <input
                    className="vk-input"
                    type="text"
                    value={settings.ollamaEndpoint}
                    placeholder="http://localhost:11434"
                    onChange={(e) => setSettings((s) => ({ ...s, ollamaEndpoint: e.target.value }))}
                    onBlur={() => void savePatch({ ollamaEndpoint: settings.ollamaEndpoint })}
                  />
                  <button className="vk-mini" onClick={() => void verifyOllama()}>{t("settings.verify")}</button>
                </div>
                {ollamaState !== "unknown" && (
                  <div className={"vk-ollama-state" + (ollamaState === "up" ? " up" : "")}>
                    <span className="dot" />
                    {ollamaState === "checking"
                      ? t("settings.ollamaChecking")
                      : ollamaState === "up"
                      ? t("settings.ollamaUp")
                      : ollamaState === "installed-down"
                      ? t("settings.ollamaDown")
                      : t("settings.ollamaNotInstalled")}
                  </div>
                )}
                {onOpenModels && (
                  <button className="vk-xlink" onClick={() => onOpenModels()}>
                    {t("settings.modelsManage")} <VkIcon.arrow /> {t("settings.modelsAI")}
                  </button>
                )}
              </div>
            </div>

            {/* Temperatura CPU (LHM) */}
            <div className="vk-sc">
              <div className="vk-sc-h">
                <span className="ico"><VkIcon.cpu /></span>
                {t("settings.cpuTempTitle")}
              </div>
              <div className="vk-sc-sub">
                {t("settings.cpuTempSub")}
              </div>
              {lhmStatus === null ? (
                <div className="vk-hlp">{t("settings.loadingState")}</div>
              ) : (
                <div className="vk-field" style={{ marginBottom: 0 }}>
                  <div style={{ fontSize: 13, marginBottom: 10, opacity: 0.8 }}>
                    {!lhmStatus.installed
                      ? t("settings.lhmNotInstalled")
                      : lhmStatus.running
                      ? t("settings.lhmActive")
                      : t("settings.lhmInstalledNotRunning")}
                  </div>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    {!lhmStatus.installed ? (
                      lhmStatus.canInstall ? (
                        <button
                          className="vk-mini"
                          disabled={lhmInstalling}
                          onClick={() => void handleLhmInstall()}
                        >
                          {lhmInstalling ? t("settings.installing") : t("settings.install")}
                        </button>
                      ) : (
                        <span style={{ fontSize: 12, opacity: 0.78, maxWidth: 360 }}>
                          {t("settings.msixPre")}
                          <span
                            className="mono"
                            style={{ cursor: "pointer", textDecoration: "underline" }}
                            onClick={() =>
                              void bridge.openUrl(
                                "https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases",
                              )
                            }
                          >
                            LibreHardwareMonitor
                          </span>
                          {t("settings.msixPost")}
                        </span>
                      )
                    ) : (
                      <>
                        {!lhmStatus.running && (
                          <button className="vk-mini" onClick={() => void handleLhmStart()}>
                            {t("settings.start")}
                          </button>
                        )}
                        {lhmStatus.running && (
                          <button className="vk-mini" onClick={() => void handleLhmStop()}>
                            {t("settings.stop")}
                          </button>
                        )}
                        <button
                          className="vk-mini"
                          style={{ opacity: 0.6 }}
                          onClick={() => void handleLhmUninstall()}
                        >
                          {t("settings.remove")}
                        </button>
                      </>
                    )}
                    <button
                      className="vk-mini"
                      style={{ opacity: 0.6 }}
                      onClick={() => bridge.lhmStatus().then(setLhmStatus)}
                    >
                      {t("settings.refreshState")}
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
                {t("settings.outputTitle")}
              </div>
              <div className="vk-sc-sub">{t("settings.outputSub")}</div>

              <div className="vk-field">
                <label>{t("settings.briefingDirLabel")}</label>
                <div className="vk-path">
                  <input
                    className="vk-input"
                    type="text"
                    value={settings.briefingDir}
                    placeholder={t("settings.briefingDirPlaceholder")}
                    onChange={(e) => setSettings((s) => ({ ...s, briefingDir: e.target.value }))}
                    onBlur={() => void savePatch({ briefingDir: settings.briefingDir })}
                  />
                  <button className="vk-mini" onClick={() => void handleBrowse("briefingDir")}>
                    {t("settings.browse")}
                  </button>
                </div>
              </div>

              <div className="vk-field" style={{ marginBottom: 0 }}>
                <label>{t("settings.vaultLabel")}</label>
                <div className="vk-path">
                  <input
                    className="vk-input"
                    type="text"
                    value={settings.obsidianVault}
                    placeholder={t("settings.vaultPlaceholder")}
                    onChange={(e) => setSettings((s) => ({ ...s, obsidianVault: e.target.value }))}
                    onBlur={() => void savePatch({ obsidianVault: settings.obsidianVault })}
                  />
                  <button className="vk-mini" onClick={() => void handleBrowse("obsidianVault")}>
                    {t("settings.browse")}
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
                {t("settings.generalTitle")}
              </div>
              <div className="vk-sc-sub">{t("settings.generalSub")}</div>

              <div className="vk-field">
                <label>{t("settings.language.label")}</label>
                <div className="vk-seg2">
                  {SUPPORTED_LANGUAGES.map((lang) => (
                    <button
                      key={lang}
                      className={settings.appLanguage === lang ? "on" : ""}
                      onClick={() => void changeAppLanguage(lang)}
                    >
                      {LANGUAGE_LABELS[lang]}
                    </button>
                  ))}
                </div>
                <div className="vk-hlp">{t("settings.language.hint")}</div>
              </div>

              <div className="vk-field">
                <label>{t("settings.defaultModeLabel")}</label>
                <div className="vk-seg2">
                  <button
                    className={settings.defaultMode === "solo" ? "on" : ""}
                    onClick={() => void savePatch({ defaultMode: "solo" })}
                  >
                    {t("settings.modeSolo")}
                  </button>
                  <button
                    className={settings.defaultMode === "riunione" ? "on" : ""}
                    onClick={() => void savePatch({ defaultMode: "riunione" })}
                  >
                    {t("settings.modeMeeting")}
                  </button>
                </div>
              </div>

              <div className="vk-field">
                <label>{t("settings.transcriptionLangLabel")}</label>
                <div className="vk-seg2">
                  <button
                    className={settings.transcriptionLanguage === "auto" ? "on" : ""}
                    onClick={() => void savePatch({ transcriptionLanguage: "auto" })}
                  >
                    {t("settings.langAuto")}
                  </button>
                  <button
                    className={settings.transcriptionLanguage === "it" ? "on" : ""}
                    onClick={() => void savePatch({ transcriptionLanguage: "it" })}
                  >
                    {t("settings.langItalian")}
                  </button>
                  <button
                    className={settings.transcriptionLanguage === "en" ? "on" : ""}
                    onClick={() => void savePatch({ transcriptionLanguage: "en" })}
                  >
                    {t("settings.langEnglish")}
                  </button>
                </div>
              </div>

              <div className="vk-field">
                <label>{t("settings.livePreviewLabel")}</label>
                <div className="vk-seg2">
                  <button
                    className={settings.livePreview ? "on" : ""}
                    onClick={() => void savePatch({ livePreview: true })}
                  >
                    {t("settings.enable")}
                  </button>
                  <button
                    className={!settings.livePreview ? "on" : ""}
                    onClick={() => void savePatch({ livePreview: false })}
                  >
                    {t("settings.disable")}
                  </button>
                </div>
              </div>

              {settings.livePreview && (
                <div className="vk-field" style={{ marginBottom: 0 }}>
                  <label>{t("settings.liveModelLabel")}</label>
                  <div className="vk-seg2">
                    {(["tiny", "base", "small"] as const).map((m) => {
                      const notReady = (models.find((x) => x.name === m)?.state ?? "available") === "available";
                      return (
                        <button
                          key={m}
                          className={settings.liveModel === m ? "on" : ""}
                          onClick={() => void savePatch({ liveModel: m })}
                        >
                          {m === "tiny" ? t("settings.liveTiny") : m === "base" ? t("settings.liveBase") : t("settings.liveSmall")}
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
                          <span><b>{settings.liveModel}</b>{t("settings.notDownloadedSuffix")}</span>
                          <button
                            disabled={downloading === settings.liveModel}
                            onClick={() => void handleDownload(settings.liveModel)}
                          >
                            {downloading === settings.liveModel ? t("settings.downloading") : t("settings.downloadNow")}
                          </button>
                        </div>
                      );
                    }
                    return (
                      <div className="vk-hlp">
                        {t("settings.liveModelHelp")}
                      </div>
                    );
                  })()}
                </div>
              )}
            </div>
          </div>

          <div className="vk-set-priv">
            <VkIcon.lock />
            {t("settings.privacyFooter")}
          </div>
        </div>
      </div>
    </>
  );
}

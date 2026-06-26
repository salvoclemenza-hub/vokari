import { Fragment, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  bridge,
  onVokariEvent,
  DEFAULT_SETTINGS,
  type ModelEntry,
  type OllamaStatus,
  type VokariSettings,
} from "../bridge";
import { VkIcon } from "../icons";
import { whisperRowState, ollamaHint } from "../modelStatus";

// Wizard di primo avvio (B4). 4 passi: benvenuto → cervello AI → modello trascrizione → pronto.
// Mostrato finché settings.onboarded è false; `onDone` segna onboarded=true e porta alla Home.
// Esperienza immersiva (chrome "bare": solo titlebar). Ogni passo è SALTABILE: il banner Home
// resta come rete di sicurezza. Verità onesta: nessun path è a zero attrito — o chiave Claude
// (a pagamento) o GB da scaricare per il locale.

const STEP_KEYS = ["onboarding.step0", "onboarding.step1", "onboarding.step2", "onboarding.step3"];
const WIZARD_MODELS = ["large-v3-turbo", "small"];

// Stepper orizzontale: cerchi numerati connessi da una linea che si "riempie" di verde.
function Stepper({ step }: { step: number }) {
  const { t } = useTranslation();
  return (
    <div style={{ display: "flex", alignItems: "center", margin: "0 auto 4px", maxWidth: 460 }}>
      {STEP_KEYS.map((labelKey, i) => (
        <Fragment key={labelKey}>
          {i > 0 && (
            <span
              style={{
                flex: 1,
                height: 2,
                borderRadius: 2,
                margin: "0 8px 20px",
                background: i <= step ? "var(--green)" : "var(--line2)",
                transition: "background .25s",
              }}
            />
          )}
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 7 }}>
            <span
              style={{
                width: 28,
                height: 28,
                borderRadius: "50%",
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 12.5,
                fontWeight: 600,
                background: i < step ? "var(--green)" : i === step ? "var(--ink)" : "transparent",
                border: i > step ? "1.5px solid var(--line2)" : "none",
                color: i <= step ? "#fff" : "var(--mut)",
                transition: "all .2s",
              }}
            >
              {i < step ? "✓" : i + 1}
            </span>
            <span
              style={{
                fontSize: 11,
                fontWeight: i === step ? 600 : 500,
                color: i === step ? "var(--ink)" : "var(--mut)",
                whiteSpace: "nowrap",
              }}
            >
              {t(labelKey)}
            </span>
          </div>
        </Fragment>
      ))}
    </div>
  );
}

export function ScreenOnboarding({ onDone, initialStep = 0 }: { onDone: () => void; initialStep?: number }) {
  const { t } = useTranslation();
  const [step, setStep] = useState(initialStep);
  const [settings, setSettings] = useState<VokariSettings>(DEFAULT_SETTINGS);

  // Claude
  const [apiKeyInput, setApiKeyInput] = useState("");
  const [keyVerify, setKeyVerify] = useState<{ state: "idle" | "checking" | "ok" | "err"; msg: string }>({
    state: "idle",
    msg: "",
  });

  // Ollama
  const [ollama, setOllama] = useState<OllamaStatus | null>(null);
  const [ollamaSetup, setOllamaSetup] = useState<{ status: string; pct: number } | null>(null);

  // Whisper
  const [models, setModels] = useState<ModelEntry[]>([]);
  const [downloading, setDownloading] = useState<string | null>(null);
  const [dlProgress, setDlProgress] = useState<number | null>(null);

  useEffect(() => {
    bridge.getSettings().then(setSettings);
    bridge.listModels().then(setModels);
    bridge.ollamaStatus().then(setOllama);
  }, []);

  useEffect(() => {
    const off = onVokariEvent((event, payload) => {
      if (event === "model_download") {
        const st = payload.status as string;
        if (st === "start") {
          setDownloading(String(payload.name));
          setDlProgress(null);
        } else if (st === "progress") {
          setDlProgress(typeof payload.pct === "number" ? payload.pct : null);
        } else if (st === "done") {
          setDownloading(null);
          setDlProgress(null);
          bridge.listModels().then(setModels);
        } else if (st === "error") {
          setDownloading(null);
          setDlProgress(null);
        }
      } else if (event === "ollama_setup") {
        const status = String(payload.status ?? "");
        const pct = typeof payload.pct === "number" ? payload.pct : 0;
        if (status === "done") {
          setOllamaSetup(null);
          bridge.ollamaStatus().then(setOllama);
        } else if (status === "error") {
          setOllamaSetup(null);
        } else {
          setOllamaSetup({ status, pct });
        }
      }
    });
    return off;
  }, []);

  async function chooseBrain(brain: "claude" | "ollama") {
    const updated = await bridge.saveSettings({ brain });
    setSettings(updated);
  }

  async function saveKey() {
    const k = apiKeyInput.trim();
    if (!k) return;
    const res = await bridge.setApiKey(k);
    if (res.hasApiKey) {
      setSettings((s) => ({ ...s, hasApiKey: true }));
      setApiKeyInput("");
    }
  }

  async function verifyKey() {
    setKeyVerify({ state: "checking", msg: t("onboarding.verifying") });
    const res = await bridge.verifyApiKey();
    setKeyVerify(res.ok ? { state: "ok", msg: t("onboarding.keyValid") } : { state: "err", msg: res.error || t("onboarding.verifyFail") });
  }

  async function installOllama() {
    setOllamaSetup({ status: "downloading", pct: 0 });
    try {
      await bridge.ollamaInstall();
    } catch {
      setOllamaSetup(null);
    }
  }

  async function selectModel(name: string) {
    const updated = await bridge.setActiveModel(name);
    setSettings(updated);
    bridge.listModels().then(setModels);
  }

  async function downloadModel(name: string) {
    try {
      await bridge.downloadModel(name);
    } catch {
      /* l'esito reale arriva via evento model_download */
    }
  }

  const modelReady = models.some((m) => m.state === "active" || m.state === "downloaded");
  const brainReady =
    settings.brain === "claude" ? settings.hasApiKey : Boolean(ollama && (ollama.running || ollama.installed));

  const wizardModels = WIZARD_MODELS.map((n) => models.find((m) => m.name === n)).filter(Boolean) as ModelEntry[];

  const isLast = step === STEP_KEYS.length - 1;

  return (
    <div style={{ flex: "1 1 auto", minHeight: 0, overflowY: "auto", display: "flex" }}>
      <div style={{ margin: "auto", width: "100%", maxWidth: 560, padding: "32px 28px" }}>
        {/* top: kicker + Salta */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 22 }}>
          <div className="vk-kick">{t("onboarding.kick")}</div>
          <button
            onClick={onDone}
            title={t("onboarding.skipTitle")}
            style={{ background: "none", border: 0, font: "inherit", fontSize: 12.5, color: "var(--mut)", cursor: "pointer", textDecoration: "underline", textUnderlineOffset: 3 }}
          >
            {t("onboarding.skip")}
          </button>
        </div>

        <Stepper step={step} />

        <div style={{ marginTop: 26 }}>
          {/* ── Passo 0 · Benvenuto (hero) ── */}
          {step === 0 && (
            <div style={{ textAlign: "center", padding: "4px 0" }}>
              <div
                className="vk-onb-ic"
                style={{
                  width: 84,
                  height: 84,
                  margin: "0 auto 22px",
                  padding: 24,
                  borderRadius: "50%",
                  color: "#fff",
                  background: "radial-gradient(circle at 50% 32%, var(--green) 0%, var(--green-d) 100%)",
                  boxShadow: "0 10px 28px rgba(47,158,111,.34)",
                }}
              >
                <VkIcon.mic />
              </div>
              <h1 style={{ fontFamily: "var(--disp)", fontSize: 30, lineHeight: 1.15, margin: "0 0 12px" }}>
                {t("onboarding.heroTitle")}
              </h1>
              <p style={{ fontSize: 14.5, lineHeight: 1.6, color: "var(--ink)", margin: "0 auto 12px", maxWidth: 440 }}>
                {t("onboarding.heroP1a")}<b>{t("onboarding.heroP1briefing")}</b>{t("onboarding.heroP1b")}<b>{t("onboarding.heroP1recap")}</b>{t("onboarding.heroP1c")}<b>{t("onboarding.heroP1obs")}</b>{t("onboarding.heroP1d")}
              </p>
              <p style={{ fontSize: 14.5, lineHeight: 1.6, color: "var(--mut)", margin: "0 auto", maxWidth: 440 }}>
                {t("onboarding.heroP2a")}<b>{t("onboarding.heroP2bold")}</b>{t("onboarding.heroP2b")}
              </p>
            </div>
          )}

          {/* ── Passo 1 · Cervello AI ── */}
          {step === 1 && (
            <div>
              <h1 style={{ fontFamily: "var(--disp)", fontSize: 25, margin: "0 0 6px" }}>{t("onboarding.brainTitle")}</h1>
              <p style={{ fontSize: 13.5, color: "var(--mut)", margin: "0 0 18px" }}>
                {t("onboarding.brainSub")}
              </p>

              <div
                className={"vk-brain-card" + (settings.brain === "claude" ? " on" : "")}
                onClick={() => void chooseBrain("claude")}
                style={{ cursor: "pointer" }}
              >
                <div className="bh">
                  <span className="ico"><VkIcon.brain /></span>
                  <div>
                    <div className="bt">{t("onboarding.claudeApi")}</div>
                    <div className="bs">{t("onboarding.claudeSub")}</div>
                  </div>
                  <span className="rd"></span>
                </div>
                {settings.brain === "claude" && (
                  <div className="bd" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {settings.hasApiKey ? (
                      <span className="vk-verify ok"><VkIcon.check /> {t("onboarding.keySet")}</span>
                    ) : (
                      <>
                        <span>
                          {t("onboarding.keyCreatePre")}
                          <span
                            className="mono"
                            style={{ cursor: "pointer", textDecoration: "underline" }}
                            onClick={(e) => {
                              e.stopPropagation();
                              void bridge.openUrl("https://console.anthropic.com/settings/keys");
                            }}
                          >
                            console.anthropic.com
                          </span>
                          {t("onboarding.keyCreatePost")}
                        </span>
                        <div className="vk-path" onClick={(e) => e.stopPropagation()}>
                          <input
                            className="vk-input"
                            type="password"
                            placeholder={t("onboarding.keyPlaceholder")}
                            value={apiKeyInput}
                            onChange={(e) => setApiKeyInput(e.target.value)}
                            onBlur={() => void saveKey()}
                            onKeyDown={(e) => { if (e.key === "Enter") void saveKey(); }}
                          />
                          <button className="vk-mini" onClick={() => void verifyKey()} disabled={keyVerify.state === "checking"}>
                            {keyVerify.state === "checking" ? t("onboarding.verifyingShort") : t("onboarding.verify")}
                          </button>
                        </div>
                      </>
                    )}
                    {keyVerify.state !== "idle" && keyVerify.state !== "ok" && (
                      <span className={"vk-verify " + keyVerify.state} role="status">
                        {keyVerify.msg}
                      </span>
                    )}
                  </div>
                )}
              </div>

              <div
                className={"vk-brain-card" + (settings.brain === "ollama" ? " on" : "")}
                onClick={() => void chooseBrain("ollama")}
                style={{ cursor: "pointer" }}
              >
                <div className="bh">
                  <span className="ico"><VkIcon.cpu /></span>
                  <div>
                    <div className="bt">{t("onboarding.localOllama")}</div>
                    <div className="bs">{t("onboarding.localSub")}</div>
                  </div>
                  <span className="rd"></span>
                </div>
                {settings.brain === "ollama" && (
                  <div className="bd" onClick={(e) => e.stopPropagation()}>
                    {ollamaSetup ? (
                      <span>
                        {ollamaSetup.status === "downloading"
                          ? t("onboarding.ollamaDownloading", { pct: Math.round(ollamaSetup.pct * 100) })
                          : t("onboarding.ollamaStarting")}
                      </span>
                    ) : !ollama ? (
                      <span style={{ opacity: 0.7 }}>{t("onboarding.ollamaChecking")}</span>
                    ) : ollamaHint(ollama) === "up" ? (
                      <span className="vk-verify ok"><VkIcon.check /> {t("onboarding.ollamaReady")}</span>
                    ) : ollama.installed ? (
                      <span className="vk-verify ok"><VkIcon.check /> {t("onboarding.ollamaInstalled")}</span>
                    ) : ollama.canInstall ? (
                      <span>
                        {t("onboarding.ollamaCanInstall")}
                        <button className="vk-mini" onClick={() => void installOllama()}>{t("onboarding.installOllama")}</button>
                      </span>
                    ) : (
                      <span>
                        {t("onboarding.ollamaManualPre")}
                        <span
                          className="mono"
                          style={{ cursor: "pointer", textDecoration: "underline" }}
                          onClick={() => void bridge.openUrl("https://ollama.com/download")}
                        >
                          ollama.com/download
                        </span>
                        {t("onboarding.ollamaManualPost")}
                      </span>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ── Passo 2 · Modello di trascrizione ── */}
          {step === 2 && (
            <div>
              <h1 style={{ fontFamily: "var(--disp)", fontSize: 25, margin: "0 0 6px" }}>{t("onboarding.transcribeTitle")}</h1>
              <p style={{ fontSize: 13.5, color: "var(--mut)", margin: "0 0 18px" }}>
                {t("onboarding.transcribeSub")}
              </p>

              {wizardModels.map((m) => {
                const rowState = whisperRowState(m.state, m.name === settings.whisperModel);
                const isDownloading = downloading === m.name;
                const isSelected = m.name === settings.whisperModel;
                return (
                  <div
                    key={m.name}
                    className={"vk-mrow" + (rowState === "active" ? " on" : "")}
                    onClick={() => { if (!isSelected) void selectModel(m.name); }}
                    style={{ cursor: isSelected ? "default" : "pointer" }}
                  >
                    <span className="nm">
                      <span className="t">
                        {m.name}
                        {m.recommended && <span className="df">{t("onboarding.recommended")}</span>}
                      </span>
                      <span className="m" style={{ fontSize: 12, opacity: 0.7 }}>
                        {m.sizeLabel} · {m.description}
                      </span>
                    </span>
                    <span className="act">
                      {rowState === "active" || rowState === "downloaded" ? (
                        <span className="saved"><VkIcon.check /> {t("onboarding.downloaded")}</span>
                      ) : (
                        <span className="vk-getwrap">
                          <button
                            className="get"
                            disabled={isDownloading}
                            onClick={(e) => {
                              e.stopPropagation();
                              if (!isSelected) void selectModel(m.name);
                              void downloadModel(m.name);
                            }}
                          >
                            <VkIcon.down />
                            {isDownloading ? (dlProgress !== null ? t("onboarding.downloadingPct", { pct: Math.round(dlProgress * 100) }) : t("onboarding.downloadingShort")) : t("onboarding.download")}
                          </button>
                          {isDownloading && dlProgress !== null && (
                            <span className="vk-dlbar"><i style={{ width: Math.round(dlProgress * 100) + "%" }}></i></span>
                          )}
                        </span>
                      )}
                    </span>
                  </div>
                );
              })}
              <div className="vk-note" style={{ marginTop: 10 }}>
                <span className="ni">!</span>
                <span>{t("onboarding.transcribeNote")}</span>
              </div>
            </div>
          )}

          {/* ── Passo 3 · Pronto ── */}
          {step === 3 && (
            <div>
              <h1 style={{ fontFamily: "var(--disp)", fontSize: 25, margin: "0 0 6px" }}>{t("onboarding.readyTitle")}</h1>
              <p style={{ fontSize: 13.5, color: "var(--mut)", margin: "0 0 18px" }}>
                {t("onboarding.readySub")}
              </p>

              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {[
                  {
                    ready: modelReady,
                    title: t("onboarding.rowModelTitle"),
                    txt: modelReady ? t("onboarding.rowModelReady") : t("onboarding.rowModelNotReady"),
                  },
                  {
                    ready: brainReady,
                    title: t("onboarding.rowBrainTitle"),
                    txt:
                      settings.brain === "claude"
                        ? brainReady
                          ? t("onboarding.rowBrainClaudeReady")
                          : t("onboarding.rowBrainClaudeNotReady")
                        : brainReady
                        ? t("onboarding.rowBrainOllamaReady")
                        : t("onboarding.rowBrainOllamaNotReady"),
                  },
                ].map((row) => (
                  <div
                    key={row.title}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 12,
                      padding: "12px 14px",
                      borderRadius: 12,
                      background: row.ready ? "var(--green-soft)" : "var(--surface)",
                      border: "1px solid " + (row.ready ? "#d3e4d3" : "var(--line)"),
                    }}
                  >
                    <span
                      style={{
                        width: 24,
                        height: 24,
                        flex: "0 0 auto",
                        borderRadius: "50%",
                        display: "inline-flex",
                        alignItems: "center",
                        justifyContent: "center",
                        fontSize: 13,
                        fontWeight: 700,
                        background: row.ready ? "var(--green)" : "transparent",
                        border: row.ready ? "none" : "1.5px solid var(--amber)",
                        color: row.ready ? "#fff" : "var(--amber)",
                      }}
                    >
                      {row.ready ? "✓" : "!"}
                    </span>
                    <span style={{ fontSize: 13.5 }}>
                      <b>{row.title}</b> — {row.txt}
                    </span>
                  </div>
                ))}
              </div>

              {!(modelReady && brainReady) && (
                <div className="vk-note" style={{ marginTop: 14 }}>
                  <span className="ni">!</span>
                  <span>{t("onboarding.readyNote")}</span>
                </div>
              )}
            </div>
          )}
        </div>

        {/* footer azioni */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 28 }}>
          <button
            className="vk-mini"
            style={{ visibility: step === 0 ? "hidden" : "visible" }}
            onClick={() => setStep((s) => Math.max(0, s - 1))}
          >
            {t("onboarding.back")}
          </button>
          {!isLast ? (
            <button className="vk-btn-g" onClick={() => setStep((s) => s + 1)}>
              {t("onboarding.next")} <VkIcon.arrow />
            </button>
          ) : (
            <button className="vk-btn-g" onClick={onDone}>
              <VkIcon.mic /> {t("onboarding.startRecording")}
            </button>
          )}
        </div>

        <div className="vk-set-priv" style={{ marginTop: 18, justifyContent: "center" }}>
          <VkIcon.lock />
          {t("onboarding.privacyFooter")}
        </div>
      </div>
    </div>
  );
}

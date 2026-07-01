import { useEffect, useState } from "react";
import type React from "react";
import { useTranslation } from "react-i18next";
import { VkIcon } from "../icons";
import { type Artifacts } from "../bridge";
import { Banner } from "../chrome/Banner";
import { MarkdownDoc } from "./MarkdownDoc";

type Source = "mic" | "system" | "both";
type Mode = "solo" | "riunione";

// I valori restano costanti (sono identità/dati: mode "solo"/"riunione" guida la pipeline);
// le ETICHETTE si traducono via t(`home.mode.<m>`) / t(`home.source.<s>`).
const SRC: Source[] = ["mic", "system", "both"];
const MODES: Mode[] = ["solo", "riunione"];

const HOME_BARS = Array.from({ length: 56 }, (_, i) =>
  14 + Math.round(16 * Math.abs(Math.sin(i * 0.55)) + 10 * Math.abs(Math.sin(i * 0.19 + 1.3))));

export function ScreenHome({
  onStart,
  onImport,
  lastArtifacts,
  mode = "solo",
  onModeChange,
  whisperModel,
  needsApiKey = false,
  needsModel = false,
  context = "",
  onContextChange,
  onOpenSettings,
  onOpenModels,
  systemAudioSupported = true,
}: {
  onStart: (source: Source, context?: string) => void;
  onImport: () => void;
  lastArtifacts?: Artifacts | null;
  mode?: string;
  onModeChange?: (mode: Mode) => void;
  whisperModel?: string;
  needsApiKey?: boolean;
  needsModel?: boolean;
  context?: string;
  onContextChange?: (context: string) => void;
  onOpenSettings?: () => void;
  onOpenModels?: () => void;
  systemAudioSupported?: boolean;
}) {
  const { t } = useTranslation();
  // Senza loopback (macOS/Linux: pyaudiowpatch è Windows-only) resta solo il microfono.
  const sources: Source[] = systemAudioSupported ? SRC : ["mic"];
  const [source, setSource] = useState<Source>(systemAudioSupported ? "both" : "mic");
  // appInfo arriva async (App parte da fallback systemAudioSupported=true): se poi si scopre
  // che il loopback non c'è, riallinea la sorgente attiva al microfono.
  useEffect(() => {
    if (!systemAudioSupported && source !== "mic") setSource("mic");
  }, [systemAudioSupported, source]);
  const [tab, setTab] = useState<"briefing.md" | "recap.md" | "obsidian/">("briefing.md");
  // ⌘ è il tasto modificatore su macOS; su Windows/Linux (VOKARI è desktop Windows) è Ctrl.
  const modKey = /Mac|iPhone|iPad/i.test(navigator.platform) ? "⌘" : "Ctrl";

  // Scorciatoia ⌘R / Ctrl+R → avvia registrazione con la sorgente attiva
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable)) return;
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "r") {
        e.preventDefault();
        onStart(source, context || undefined);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [source, context, onStart]);

  const hasBriefing = Boolean(lastArtifacts?.briefingMd);
  // Chiave del modo selezionato per la caption dinamica (solo/riunione → testo diverso).
  const modeKey = mode === "riunione" ? "riunione" : "solo";

  // Passi onboarding (no briefing): il passo 2 ha testo in grassetto (Ctrl R) → composto in JSX.
  const onbSteps: { tt: string; dd: React.ReactNode }[] = [
    { tt: t("home.onb.step1tt"), dd: t("home.onb.step1dd") },
    { tt: t("home.onb.step2tt"), dd: <>{t("home.onb.step2ddPre")} <b>{t("home.onb.step2ddBold")}</b>{t("home.onb.step2ddPost")}</> },
    { tt: t("home.onb.step3tt"), dd: t("home.onb.step3dd") },
  ];

  return (
    <>
      {(needsModel || needsApiKey) && (
        <Banner kind="warn" actions={
          <>
            {needsModel && <button className="vk-mini" onClick={onOpenModels}>{t("home.banner.downloadModel")}</button>}
            {needsApiKey && <button className="vk-mini" onClick={onOpenSettings}>{t("home.banner.openSettings")}</button>}
          </>
        }>
          ⚙ <b>{t("home.banner.configure")}</b>{" "}
          {needsModel && t("home.banner.needModel") + " "}
          {needsApiKey && t("home.banner.needKey")}
        </Banner>
      )}
      <div className="vk-greet">
        <div>
          <div className="vk-kick">{t("home.kicker")}</div>
          <h1>{t("home.title")}</h1>
          <p>{t("home.subtitlePre")} <b>{t("home.subtitleBold")}</b> {t("home.subtitlePost")}</p>
        </div>
      </div>

      <div className="vk-grid">
        {/* ── Console (dark heart) ── */}
        <div className="vk-console">
          <div className="vk-con-head">
            <span className="vk-con-tag"><span className="dot"></span>capture</span>
          </div>

          <div className="vk-cap-rows">
            <div className="vk-seg-row">
              <span className="vk-src-lbl">{t("home.typeLabel")}</span>
              <div className="vk-src" role="group" aria-label={t("home.typeGroup")}>
                {MODES.map((m) => (
                  <button key={m} className={mode === m ? "on" : ""} onClick={() => onModeChange?.(m)}>
                    {t("home.mode." + m)}
                  </button>
                ))}
              </div>
            </div>
            <div className="vk-seg-row">
              <span className="vk-src-lbl">{t("home.sourceLabel")}</span>
              <div className="vk-src" role="group" aria-label={t("home.sourceGroup")}>
                {sources.map((s) => (
                  <button key={s} className={source === s ? "on" : ""} onClick={() => setSource(s)}>
                    {t("home.source." + s)}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Caption del TIPO selezionato: dinamica per modo (spiega cosa cercherà l'analisi),
              allineata sotto i selettori → è chiaramente subordinata a TIPO/SORGENTE, non al
              campo contesto sotto. */}
          <div className="vk-mode-hint">
            <b>{t("home.mode." + modeKey)}</b> {t("home.modeHint." + modeKey)}
          </div>

          {/* Contesto/scopo (opzionale): sezione DISTINTA, separata dalla caption del TIPO da
              un divisore + spaziatura → non si legge più "allo stesso livello" dell'hint. */}
          <div className="vk-ctx-field">
            <label className="vk-ctx-q" htmlFor="vk-home-ctx">
              {t("home.contextLabel")} <span className="opt">{t("home.contextHint")}</span>
            </label>
            <input
              id="vk-home-ctx"
              className="vk-ctx-in"
              type="text"
              placeholder={t("home.contextPlaceholder")}
              value={context}
              onChange={(e) => onContextChange?.(e.currentTarget.value)}
            />
          </div>

          <div className="vk-stage">
            <button
              className="vk-rec"
              onClick={() => onStart(source, context || undefined)}
              aria-label={t("home.startRecording")}
            >
              <VkIcon.mic />
            </button>
            <div className="vk-rec-label">{t("home.startRecording")}</div>
            <div className="vk-rec-sub">
              {t("home.recHintPre")} <kbd>{modKey}</kbd><kbd>R</kbd> {t("home.recHintPost")}
            </div>
            <div className="vk-wave" aria-hidden="true">
              {HOME_BARS.map((h, i) => (
                <i key={i} style={{ height: h + "px", "--i": i } as React.CSSProperties}></i>
              ))}
            </div>
          </div>

          <div
            className="vk-drop"
            role="button"
            tabIndex={0}
            onClick={onImport}
            onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") onImport(); }}
          >
            <span className="ar">↧</span>
            <span><b>{t("home.dropTitle")}</b></span>
            <span className="ext">.mp3 .wav .m4a .flac</span>
          </div>

          <div className="vk-con-foot">
            <span className="ok"><span className="dot"></span>{t("home.footLocal")}</span>
            <span className="model">{whisperModel || "large-v3-turbo"} · {t("home.onDevice")}</span>
          </div>
        </div>

        {/* ── Output preview / Sessioni recenti ── */}
        <div className="vk-output">
          {hasBriefing ? (
            <>
              <div className="vk-tabs">
                {(["briefing.md", "recap.md", "obsidian/"] as const).map((tabId) => {
                  const disabled = tabId !== "briefing.md";
                  return (
                    <button
                      key={tabId}
                      className={tab === tabId ? "on" : ""}
                      disabled={disabled}
                      title={disabled ? t("home.comingSoon") : undefined}
                      onClick={() => !disabled && setTab(tabId)}
                    >
                      {tabId}
                    </button>
                  );
                })}
              </div>

              <div className="vk-doc fade">
                <MarkdownDoc md={lastArtifacts!.briefingMd} />
              </div>

              <div className="vk-out-act">
                <button
                  className="vk-btn-g"
                  title={t("home.copyBriefingTitle")}
                  onClick={() => void navigator.clipboard?.writeText(lastArtifacts!.briefingMd)}
                >
                  <VkIcon.arrow />
                  {t("home.copyBriefing")}
                </button>
              </div>
            </>
          ) : (
            <div className="vk-onb">
              <div className="vk-onb-kick">{t("home.onb.kick")}</div>
              <h2>{t("home.onb.title")}</h2>
              <p className="vk-onb-lead">
                {t("home.onb.lead")}
              </p>
              <div className="vk-onb-steps">
                {onbSteps.map((s, i) => (
                  <div className="vk-onb-step" key={i}>
                    <span className="n">{i + 1}</span>
                    <div>
                      <div className="tt">{s.tt}</div>
                      <div className="dd">{s.dd}</div>
                    </div>
                  </div>
                ))}
              </div>
              <div className="vk-onb-assure">
                <span className="dot"></span>
                {t("home.onb.assure")}
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}

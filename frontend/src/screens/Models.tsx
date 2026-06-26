import { useEffect, useRef, useState, type MutableRefObject } from "react";
import { useTranslation } from "react-i18next";
import { bridge, onVokariEvent, DEFAULT_SETTINGS, type DiskUsage, type ModelEntry, type OllamaModelEntry, type OllamaStatus, type VokariSettings } from "../bridge";
import { toast } from "../toast";
import { VkIcon } from "../icons";
import { whisperRowState } from "../modelStatus";

// ────────────────────────────────────────────────────────────
// MOD3 — ETA download dai bytesDone/bytesTotal degli eventi di progresso. Campiona la
// velocità tra due eventi consecutivi (Δbytes/Δt) e stima il tempo residuo. Tollerante:
// senza byte o senza un campione precedente → null (niente ETA, non un valore inventato).
// ────────────────────────────────────────────────────────────
type EtaSample = { t: number; bytes: number };
function computeEta(ref: MutableRefObject<EtaSample | null>, payload: Record<string, unknown>): number | null {
  const done = typeof payload.bytesDone === "number" ? payload.bytesDone : null;
  const total = typeof payload.bytesTotal === "number" ? payload.bytesTotal : null;
  if (done === null || total === null || total <= 0) return null;
  const now = Date.now();
  const prev = ref.current;
  ref.current = { t: now, bytes: done };
  if (!prev || now <= prev.t || done <= prev.bytes) return null;
  const speed = (done - prev.bytes) / ((now - prev.t) / 1000); // bytes/s
  return speed > 0 ? Math.max(0, (total - done) / speed) : null;
}
function formatEta(s: number): string {
  if (s < 60) return `~${Math.round(s)}s`;
  const m = Math.floor(s / 60);
  return `~${m}m ${Math.round(s - m * 60)}s`;
}

// ────────────────────────────────────────────────────────────
// Meter a BARRA (velocità verde, qualità viola). I valori reali sono interi ~1..3 →
// la barra si riempie su scala /3 (clamp [8,100]; il dato di test può arrivare a 5 → 100%).
// ────────────────────────────────────────────────────────────
function Meter({ label, n, kind }: { label: string; n: number; kind?: "q" }) {
  const w = Math.max(8, Math.min(100, Math.round((n / 3) * 100)));
  return (
    <span className={"vk-meter" + (kind === "q" ? " q" : "")}>
      {label}
      <span className="bar">
        <i style={{ width: w + "%" }}></i>
      </span>
    </span>
  );
}

// ────────────────────────────────────────────────────────────
// Tag-to-icon mapping (stile Lemonade): etichetta → icona + tooltip + categoria di colore
// (ml = multilingue/blu · json = json/reasoning/viola · tool = ambra · ctx = velocità/leggero/verde).
// ────────────────────────────────────────────────────────────
// I titoli sono chiavi i18n (lingua-agnostiche), tradotte al render via t(meta.titleKey).
const TAG_META: Record<string, { icon: () => JSX.Element; titleKey: string; cat: string }> = {
  italiano: { icon: () => <VkIcon.globe />, titleKey: "models.tagItaliano", cat: "ml" },
  multilingue: { icon: () => <VkIcon.globe />, titleKey: "models.tagMultilingue", cat: "ml" },
  json: { icon: () => <VkIcon.braces />, titleKey: "models.tagJson", cat: "json" },
  "tool-calling": { icon: () => <VkIcon.wrench />, titleKey: "models.tagTool", cat: "tool" },
  reasoning: { icon: () => <VkIcon.brain />, titleKey: "models.tagReasoning", cat: "json" },
  veloce: { icon: () => <VkIcon.zap />, titleKey: "models.tagVeloce", cat: "ctx" },
  leggero: { icon: () => <VkIcon.feather />, titleKey: "models.tagLeggero", cat: "ctx" },
};

/** Estrae i GB (approssimati) dalla sizeLabel ("4.7 GB", "466 MB") per l'ordinamento. */
function sizeGb(s: string): number {
  const gb = /([\d.]+)\s*GB/i.exec(s);
  if (gb) return parseFloat(gb[1]);
  const mb = /([\d.]+)\s*MB/i.exec(s);
  return mb ? parseFloat(mb[1]) / 1024 : 0;
}

// ────────────────────────────────────────────────────────────
// Scheda metadati di un modello locale (Ollama): badge tecnici
// (dimensione/parametri/velocità/qualità/contesto/tag) + descrizione
// d'uso + link ai dettagli. Ispirata al model manager di Lemonade: dà
// gli elementi per valutare quale modello usare e per quale scopo.
// ────────────────────────────────────────────────────────────
function LocalModelMeta({ m, ramTotalGb }: { m: OllamaModelEntry; ramTotalGb: number }) {
  const { t } = useTranslation();
  // MOD2: avviso solo se conosciamo davvero RAM totale e requisito (margine 90%).
  const ramHeavy = ramTotalGb > 0 && m.minRamGb > 0 && m.minRamGb > ramTotalGb * 0.9;
  return (
    <>
      <span className="badges" style={{ flexWrap: "wrap", rowGap: 6 }}>
        <span className="vk-badge">{m.sizeLabel}</span>
        {ramHeavy && (
          <span className="vk-ramwarn" title={t("models.ramWarnTitle", { min: m.minRamGb, total: ramTotalGb })}>
            {t("models.ramHeavy", { total: ramTotalGb })}
          </span>
        )}
        {m.params && <span className="vk-badge">{m.params}</span>}
        {/* meter solo se abbiamo metadati reali: i modelli fuori catalogo hanno speed/quality 0 */}
        {(m.speed > 0 || m.quality > 0) && (
          <>
            <Meter label={t("models.speed")} n={m.speed} />
            <Meter label={t("models.quality")} n={m.quality} kind="q" />
          </>
        )}
        {m.context && <span className="vk-badge">{t("models.contextBadge", { ctx: m.context })}</span>}
        {m.tags.length > 0 && (
          <span className="vk-tagico">
            {m.tags.map((tag) => {
              const meta = TAG_META[tag];
              return meta ? (
                <span key={tag} className={"ti " + meta.cat} title={t(meta.titleKey)} role="img" aria-label={t(meta.titleKey)}>
                  <meta.icon />
                </span>
              ) : (
                <span className="vk-badge" key={tag}>
                  {tag}
                </span>
              );
            })}
          </span>
        )}
      </span>
      {m.description && (
        <span style={{ fontSize: 12, color: "var(--mut, #6b6358)", marginTop: 4, display: "block", lineHeight: 1.4 }}>
          {m.description}
        </span>
      )}
      <span
        role="link"
        tabIndex={0}
        className="mono"
        style={{ fontSize: 11.5, color: "var(--green-d)", cursor: "pointer", textDecoration: "underline", marginTop: 5, display: "inline-block" }}
        onClick={(e) => {
          e.stopPropagation();
          void bridge.openUrl(m.detailUrl);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.stopPropagation();
            void bridge.openUrl(m.detailUrl);
          }
        }}
      >
        {t("models.modelDetails")}
      </span>
    </>
  );
}

export function ScreenModels() {
  const { t } = useTranslation();
  const [models, setModels] = useState<ModelEntry[]>([]);
  const [settings, setSettings] = useState<VokariSettings>(DEFAULT_SETTINGS);
  const [downloading, setDownloading] = useState<string | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  // MOD3: ETA per Whisper e Ollama (campioni in ref, valore mostrato in state).
  const [whisperEta, setWhisperEta] = useState<number | null>(null);
  const [ollamaEta, setOllamaEta] = useState<number | null>(null);
  const whisperEtaRef = useRef<EtaSample | null>(null);
  const ollamaEtaRef = useRef<EtaSample | null>(null);

  // Ollama state
  const [ollamaModels, setOllamaModels] = useState<OllamaModelEntry[]>([]);
  const [ollamaPulling, setOllamaPulling] = useState<string | null>(null);
  const [ollamaPullProgress, setOllamaPullProgress] = useState<number | null>(null);
  const [customModel, setCustomModel] = useState("");
  const customRef = useRef<HTMLInputElement>(null);
  // Filtri/ordina catalogo Ollama (pure-frontend sui metadati reali). "fit" = compatibili con la RAM.
  const [oFilter, setOFilter] = useState<"all" | "down" | "fit">("all");
  const [oSort, setOSort] = useState<"size" | "qual">("size");
  // MOD2: RAM totale della macchina per gli avvisi/filtro di compatibilità (0 = sconosciuta).
  const [ramTotalGb, setRamTotalGb] = useState(0);
  // MOD3: riepilogo disco (GB usati dai modelli / liberi).
  const [disk, setDisk] = useState<DiskUsage | null>(null);

  // Runtime Ollama (avvio/installazione gestiti dall'app)
  const [ollamaState, setOllamaState] = useState<OllamaStatus | null>(null);
  const [ollamaSetup, setOllamaSetup] = useState<{ status: string; pct: number } | null>(null);

  useEffect(() => {
    bridge.listModels().then(setModels);
    bridge.getSettings().then(setSettings);
    bridge.listOllamaModels().then(setOllamaModels);
    bridge.ollamaStatus().then(setOllamaState);
    bridge.systemSpecs().then((s) => setRamTotalGb(s.ramTotalGb));
    bridge.diskUsage().then(setDisk);
  }, []);

  async function handleOllamaInstall() {
    setOllamaSetup({ status: "downloading", pct: 0 });
    try {
      await bridge.ollamaInstall();
    } catch (e) {
      setOllamaSetup(null);
      toast(t("models.ollamaInstallFail", { error: String(e) }), "error");
    }
  }

  async function handleOllamaStartServer() {
    setOllamaSetup({ status: "starting", pct: 1 });
    try {
      const res = await bridge.ollamaStart();
      setOllamaSetup(null);
      if (res.running) {
        toast(t("models.ollamaStarted"), "success");
        bridge.ollamaStatus().then(setOllamaState);
        bridge.listOllamaModels().then(setOllamaModels);
      } else {
        toast(t("models.ollamaStartFailCheck"), "error");
      }
    } catch (e) {
      setOllamaSetup(null);
      toast(t("models.ollamaStartFail", { error: String(e) }), "error");
    }
  }

  // eventi model_download (Whisper)
  useEffect(() => {
    const off = onVokariEvent((event, payload) => {
      if (event !== "model_download") return;
      if (payload.status === "start") {
        setDownloading(payload.name as string);
        setProgress(null);
        whisperEtaRef.current = null;
        setWhisperEta(null);
      } else if (payload.status === "progress") {
        setProgress(typeof payload.pct === "number" ? payload.pct : null);
        setWhisperEta(computeEta(whisperEtaRef, payload));
      } else if (payload.status === "done") {
        setDownloading(null);
        setProgress(null);
        setWhisperEta(null);
        whisperEtaRef.current = null;
        toast(t("models.modelDownloaded", { name: payload.name as string }), "success");
        bridge.listModels().then(setModels);
        bridge.diskUsage().then(setDisk);
      } else if (payload.status === "error") {
        setDownloading(null);
        setProgress(null);
        setWhisperEta(null);
        whisperEtaRef.current = null;
        toast(t("models.modelDownloadFail", { name: payload.name as string, error: (payload.error as string) ?? t("models.unknownError") }), "error");
        bridge.listModels().then(setModels);
      }
    });
    return off;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // eventi ollama_pull
  useEffect(() => {
    const off = onVokariEvent((event, payload) => {
      if (event !== "ollama_pull") return;
      if (payload.status === "start") {
        setOllamaPulling(payload.name as string);
        setOllamaPullProgress(null);
        ollamaEtaRef.current = null;
        setOllamaEta(null);
      } else if (payload.status === "progress") {
        setOllamaPullProgress(typeof payload.pct === "number" ? payload.pct : null);
        setOllamaEta(computeEta(ollamaEtaRef, payload));
      } else if (payload.status === "done") {
        setOllamaEta(null);
        ollamaEtaRef.current = null;
        toast(t("models.ollamaModelDownloaded", { name: payload.name as string }), "success");
        bridge.listOllamaModels().then((models) => {
          setOllamaModels(models);
          setOllamaPulling(null);
          setOllamaPullProgress(null);
        });
        bridge.diskUsage().then(setDisk);
      } else if (payload.status === "cancelled") {
        setOllamaPulling(null);
        setOllamaPullProgress(null);
        setOllamaEta(null);
        ollamaEtaRef.current = null;
        toast(t("models.downloadCancelled", { name: payload.name as string }), "info");
      } else if (payload.status === "error") {
        setOllamaPulling(null);
        setOllamaPullProgress(null);
        setOllamaEta(null);
        ollamaEtaRef.current = null;
        toast(t("models.pullFail", { name: payload.name as string, error: (payload.error as string) ?? t("models.unknownError") }), "error");
      }
    });
    return off;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // eventi ollama_setup (installazione/avvio di Ollama gestiti da VOKARI).
  // Registrato DOPO model_download/ollama_pull: alcuni test prendono il primo handler.
  useEffect(() => {
    const off = onVokariEvent((event, payload) => {
      if (event !== "ollama_setup") return;
      const status = String(payload.status ?? "");
      const pct = typeof payload.pct === "number" ? payload.pct : 0;
      if (status === "done") {
        setOllamaSetup(null);
        toast(t("models.ollamaReady"), "success");
        bridge.ollamaStatus().then(setOllamaState);
        bridge.listOllamaModels().then(setOllamaModels);
      } else if (status === "error") {
        setOllamaSetup(null);
        toast(t("models.ollamaSetupError", { error: (payload.error as string) ?? t("models.startFailShort") }), "error");
        bridge.ollamaStatus().then(setOllamaState);
      } else {
        setOllamaSetup({ status, pct });
      }
    });
    return off;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleDownload(name: string) {
    try {
      await bridge.downloadModel(name);
      bridge.listModels().then(setModels);
    } catch (e) {
      toast(t("models.downloadStartFail", { error: String(e) }), "error");
    }
  }

  async function handleActivate(name: string) {
    try {
      const updated = await bridge.setActiveModel(name);
      setSettings(updated);
      bridge.listModels().then(setModels);
    } catch (e) {
      toast(t("models.activateFail", { error: String(e) }), "error");
    }
  }

  async function handleSetBrain(brain: string) {
    try {
      const updated = await bridge.setBrain(brain);
      setSettings(updated);
    } catch (e) {
      toast(t("models.brainChangeFail", { error: String(e) }), "error");
    }
  }

  async function handleOllamaPull(name: string) {
    try {
      await bridge.pullOllamaModel(name);
    } catch (e) {
      toast(t("models.pullStartFail", { error: String(e) }), "error");
    }
  }

  // MOD1: interrompe il pull Ollama in corso. L'esito reale (transizione a "annullato")
  // arriva via evento `ollama_pull` status=cancelled, che resetta lo stato di download.
  async function handleCancelOllamaPull(name: string) {
    try {
      await bridge.cancelOllamaPull(name);
    } catch (e) {
      toast(t("models.cancelFail", { error: String(e) }), "error");
    }
  }

  async function handleOllamaActivate(name: string) {
    try {
      const updated = await bridge.saveSettings({ ollamaModel: name });
      setSettings(updated);
      bridge.listOllamaModels().then(setOllamaModels);
    } catch (e) {
      toast(t("models.ollamaActivateFail", { error: String(e) }), "error");
    }
  }

  async function handleOllamaDelete(name: string) {
    try {
      const res = await bridge.deleteOllamaModel(name);
      if (res.ok) {
        toast(t("models.modelRemoved", { name }), "success");
        bridge.listOllamaModels().then(setOllamaModels);
        bridge.diskUsage().then(setDisk);
      } else {
        toast(t("models.removeFailName", { name }), "error");
      }
    } catch (e) {
      toast(t("models.removeFail", { error: String(e) }), "error");
    }
  }

  async function handleCustomPull() {
    const name = customModel.trim();
    if (!name || ollamaPulling) return;
    setCustomModel("");
    await handleOllamaPull(name);
  }

  // MOD2: un modello è "compatibile" se la sua RAM minima sta nella RAM della macchina; quando
  // RAM o requisito sono ignoti (0) lo consideriamo compatibile (non lo escludiamo per un dato mancante).
  const fitsRam = (m: OllamaModelEntry) => ramTotalGb === 0 || m.minRamGb === 0 || m.minRamGb <= ramTotalGb;
  // Lista Ollama unificata con filtro (Tutti/Scaricati/Compatibili) + ordina (dimensione/qualità).
  const visibleOllama = ollamaModels
    .filter((m) => (oFilter === "down" ? m.isInstalled : oFilter === "fit" ? fitsRam(m) : true))
    .slice()
    .sort((a, b) =>
      oSort === "size" ? sizeGb(a.sizeLabel) - sizeGb(b.sizeLabel) : b.quality - a.quality,
    );
  // Conteggio modelli presenti sul disco (Whisper scaricati/attivo + Ollama installati).
  const downloadedCount =
    models.filter((m) => m.state === "downloaded" || m.state === "active").length +
    ollamaModels.filter((m) => m.isInstalled).length;

  return (
    <>
      <div className="vk-greet">
        <div>
          <div className="vk-kick">{t("models.kick")}</div>
          <h1>{t("models.heading")}</h1>
          <p>
            {t("models.introA")}<b>Claude</b>{t("models.introB")}<b>{t("models.introLocal")}</b>{t("models.introC")}<b>Whisper</b>{t("models.introD")}
          </p>
        </div>
      </div>

      {downloadedCount > 0 && (
        <div className="vk-disk">
          <span className="d"></span>
          <b>{downloadedCount}</b> {downloadedCount === 1 ? t("models.modelDownloadedSing") : t("models.modelsDownloadedPlur")}
          {/* MOD3: GB usati dai modelli / liberi (se il dato è disponibile). */}
          {disk && (disk.usedByModelsGb > 0 || disk.freeGb > 0) ? (
            <span className="vk-disk-x"> · <b>{disk.usedByModelsGb} GB</b> {t("models.diskUsed")} · <b>{disk.freeGb} GB</b> {t("models.diskFree")}</span>
          ) : (
            <>{t("models.onDeviceSuffix")}</>
          )}
        </div>
      )}

      {/* Colonna singola: Organizzazione → Trascrizione → Modelli locali */}
      <div className="vk-mod-grid" style={{ display: "flex", flexDirection: "column", alignItems: "stretch", gap: 16 }}>
        {/* 1 · Organizzazione (brain) */}
        <div className="vk-sc">
          <div className="vk-sc-h">
            <span className="ico">
              <VkIcon.brain />
            </span>
            {t("models.orgTitle")}
          </div>
          <div className="vk-sc-sub">
            {t("models.orgSub")}
          </div>

          <div
            className={"vk-brain-card" + (settings.brain === "claude" ? " on" : "")}
            onClick={() => void handleSetBrain("claude")}
            style={{ cursor: "pointer" }}
          >
            <div className="bh">
              <span className="ico">
                <VkIcon.brain />
              </span>
              <div>
                <div className="bt">{t("models.claudeApi")}</div>
                <div className="bs">{t("models.claudeSub")}</div>
              </div>
              <span className="rd"></span>
            </div>
            <div className="bd">
              {t("models.claudeBdPre")}<span className="mono">{settings.claudeModel}</span>{t("models.claudeBdPost")}
            </div>
          </div>

          <div
            className={"vk-brain-card" + (settings.brain === "ollama" ? " on" : "")}
            onClick={() => void handleSetBrain("ollama")}
            style={{ cursor: "pointer" }}
          >
            <div className="bh">
              <span className="ico">
                <VkIcon.cpu />
              </span>
              <div>
                <div className="bt">{t("models.localOllama")}</div>
                <div className="bs">{t("models.localSub")}</div>
              </div>
              <span className="rd"></span>
            </div>
            <div className="bd">
              {t("models.endpointPre")}<span className="mono">{settings.ollamaEndpoint}</span> ·{" "}
              <span className="mono">{settings.ollamaModel}</span>
            </div>
          </div>
        </div>

        {/* 2 · Trascrizione · Whisper */}
        <div className="vk-sc">
          <div className="vk-sc-h">
            <span className="ico">
              <VkIcon.cpu />
            </span>
            {t("models.whisperTitle")}
          </div>
          <div className="vk-sc-sub">
            {t("models.whisperSub")}
          </div>

          {models.map((m) => {
            const isSelected = m.name === settings.whisperModel;
            const rowState = whisperRowState(m.state, isSelected);
            const isActive = rowState === "active";
            const needsGet = rowState === "available" || rowState === "selected-undownloaded";
            const isDownloading = downloading === m.name;
            return (
              <div
                className={"vk-mrow" + (isActive ? " on" : "")}
                key={m.name}
                onClick={() => {
                  // cliccare una riga già scaricata (ma non attiva) la rende il modello attivo
                  if (rowState === "downloaded") void handleActivate(m.name);
                }}
                style={{ cursor: rowState === "downloaded" ? "pointer" : "default" }}
              >
                <span className="nm">
                  <span className="t">
                    {m.name}
                    {isSelected && <span className="df">DEFAULT</span>}
                  </span>
                  <span className="badges">
                    <span className="vk-badge">{m.sizeLabel}</span>
                    <Meter label={t("models.speed")} n={m.speed} />
                    <Meter label={t("models.quality")} n={m.quality} kind="q" />
                    <span className="vk-badge">{m.languages}</span>
                  </span>
                  {m.description && (
                    <span style={{ fontSize: 12, color: "var(--mut, #6b6358)", marginTop: 4, display: "block", lineHeight: 1.4 }}>
                      {m.description}
                    </span>
                  )}
                </span>
                <span className="act">
                  {isActive && (
                    <span className="active">
                      <span className="d"></span>{t("models.active")}
                    </span>
                  )}
                  {rowState === "downloaded" && (
                    <span className="saved">
                      <VkIcon.check />
                      {t("models.downloaded")}
                    </span>
                  )}
                  {needsGet && (
                    <span className="vk-getwrap">
                      {/* B1: il modello selezionato come default ma non ancora scaricato non è "Attivo" */}
                      {rowState === "selected-undownloaded" && !isDownloading && (
                        <span style={{ fontSize: 11, color: "var(--mut, #6b6358)", marginRight: 8, whiteSpace: "nowrap" }}>
                          {t("models.selectedToDownload")}
                        </span>
                      )}
                      <button
                        className="get"
                        disabled={isDownloading}
                        title={isDownloading ? t("models.dlTitle", { size: m.sizeLabel }) : undefined}
                        onClick={(e) => {
                          e.stopPropagation();
                          void handleDownload(m.name);
                        }}
                      >
                        <VkIcon.down />
                        {isDownloading
                          ? progress !== null
                            ? t("models.downloadingPct", { pct: Math.round(progress * 100) })
                            : t("models.downloadingShort")
                          : t("models.download")}
                      </button>
                      {isDownloading && progress !== null && (
                        <span className="vk-dlbar"><i style={{ width: Math.round(progress * 100) + "%" }}></i></span>
                      )}
                      {isDownloading && whisperEta !== null && (
                        <span className="vk-eta">{formatEta(whisperEta)} {t("models.remaining")}</span>
                      )}
                      {/* B3: il modello è grande — chiarisci che è lento ma una sola volta */}
                      {isDownloading && (
                        <span style={{ fontSize: 11, color: "var(--mut, #6b6358)", marginTop: 4, display: "block", lineHeight: 1.3 }}>
                          {t("models.bigFileNote")}
                        </span>
                      )}
                    </span>
                  )}
                </span>
              </div>
            );
          })}

          <div className="vk-note">
            <span className="ni">!</span>
            <span>
              {t("models.noteA")}<b>distil-*</b>{t("models.noteB")}<b>{t("models.noteBold")}</b>{t("models.noteC")}
            </span>
          </div>
        </div>

        {/* 3 · Modelli locali · Ollama */}
        <div className="vk-sc">
          <div className="vk-sc-h">
            <span className="ico">
              <VkIcon.cpu />
            </span>
            {t("models.ollamaTitle")}
          </div>
          <div className="vk-sc-sub">
            {t("models.ollamaSubA")}<b>{t("models.ollamaSubSpeed")}</b>{t("models.ollamaSubMid")}<b>{t("models.ollamaSubQuality")}</b>{t("models.ollamaSubB")}
            <span
              className="mono"
              style={{ cursor: "pointer", textDecoration: "underline" }}
              onClick={() => void bridge.openUrl("https://ollama.com/library")}
            >
              ollama.com/library
            </span>
            {t("models.ollamaSubC")}
          </div>

          {/* Stato runtime Ollama come chip `.vk-runtime` (mock): VOKARI lo avvia/installa da sé. */}
          {ollamaSetup ? (
            <div className="vk-runtime">
              <span className="dot spin"></span>
              <span className="tx">
                {ollamaSetup.status === "downloading"
                  ? t("models.ollamaDownloading", { pct: Math.round(ollamaSetup.pct * 100) })
                  : t("models.ollamaStarting")}
              </span>
            </div>
          ) : ollamaState && ollamaState.running ? (
            <div className="vk-runtime">
              <span className="dot"></span>
              <span className="tx">
                <b>{t("models.ollamaRunningBold")}</b>{t("models.ollamaRunningRest")}
              </span>
            </div>
          ) : ollamaState && ollamaState.installed ? (
            <div className="vk-runtime">
              <span className="dot warn"></span>
              <span className="tx">
                <b>{t("models.ollamaInstalledBold")}</b>{t("models.ollamaInstalledRest")}
              </span>
              <button className="vk-mini" onClick={() => void handleOllamaStartServer()}>
                {t("models.startOllama")}
              </button>
            </div>
          ) : ollamaState && ollamaState.canInstall ? (
            <div className="vk-runtime">
              <span className="dot off"></span>
              <span className="tx">
                {t("models.ollamaNotInstA")}<b>{t("models.ollamaCanInstBold")}</b>{t("models.ollamaCanInstRest")}
              </span>
              <button className="vk-mini" onClick={() => void handleOllamaInstall()}>
                {t("models.installOllama")}
              </button>
            </div>
          ) : ollamaState && !ollamaState.installed ? (
            <div className="vk-runtime">
              <span className="dot off"></span>
              <span className="tx">
                {t("models.ollamaManualA")}
                <span
                  className="mono"
                  style={{ cursor: "pointer", textDecoration: "underline" }}
                  onClick={() => void bridge.openUrl("https://ollama.com/download")}
                >
                  ollama.com/download
                </span>
                {t("models.ollamaManualB")}<span className="mono">winget install Ollama.Ollama</span>{t("models.ollamaManualC")}
              </span>
            </div>
          ) : null}

          {/* Toolbar: filtra (Tutti/Scaricati) + ordina (dimensione/qualità) */}
          {ollamaModels.length > 0 && (
            <div className="vk-otoolbar">
              <div className="vk-ofilters">
                <button className={oFilter === "all" ? "on" : ""} onClick={() => setOFilter("all")}>{t("models.filterAll")}</button>
                <button className={oFilter === "down" ? "on" : ""} onClick={() => setOFilter("down")}>{t("models.filterDownloaded")}</button>
                {/* MOD2: "Compatibili" solo se conosciamo la RAM (altrimenti non avrebbe un criterio reale). */}
                {ramTotalGb > 0 && (
                  <button className={oFilter === "fit" ? "on" : ""} onClick={() => setOFilter("fit")}>{t("models.filterFit")}</button>
                )}
              </div>
              <select className="vk-osort" value={oSort} onChange={(e) => setOSort(e.target.value as "size" | "qual")}>
                <option value="size">{t("models.sortSize")}</option>
                <option value="qual">{t("models.sortQuality")}</option>
              </select>
            </div>
          )}

          {/* Lista Ollama unificata: installati (Attiva/Attivo + Rimuovi) e catalogo (Download) */}
          {visibleOllama.map((m) => {
            const isActive = m.name === settings.ollamaModel;
            const isPulling = ollamaPulling === m.name;
            return (
              <div className={"vk-mrow" + (isActive ? " on" : "")} key={m.name}>
                <span className="nm">
                  <span className="t">
                    {m.name}
                    {isActive && <span className="df">{t("models.activeBadge")}</span>}
                  </span>
                  <LocalModelMeta m={m} ramTotalGb={ramTotalGb} />
                </span>
                <span className="act" style={{ gap: 4 }}>
                  {m.isInstalled ? (
                    <>
                      {isActive ? (
                        <span className="active">
                          <span className="d"></span>{t("models.active")}
                        </span>
                      ) : (
                        <button className="get" onClick={() => void handleOllamaActivate(m.name)}>
                          {t("models.activate")}
                        </button>
                      )}
                      <button
                        className="get ghost"
                        onClick={() => void handleOllamaDelete(m.name)}
                        title={t("models.removeTitle")}
                      >
                        {t("models.remove")}
                      </button>
                    </>
                  ) : (
                    <span className="vk-getwrap">
                      <span className="vk-dlrow">
                        <button
                          className="get"
                          disabled={isPulling || ollamaPulling !== null}
                          title={isPulling ? t("models.dlTitle", { size: m.sizeLabel }) : undefined}
                          onClick={() => void handleOllamaPull(m.name)}
                        >
                          <VkIcon.down />
                          {isPulling
                            ? ollamaPullProgress !== null
                              ? t("models.downloadingPct", { pct: Math.round(ollamaPullProgress * 100) })
                              : t("models.downloadingShort")
                            : t("models.download")}
                        </button>
                        {/* MOD1: ✕ Annulla — solo durante il pull di QUESTO modello. */}
                        {isPulling && (
                          <button
                            className="vk-dlcancel"
                            title={t("models.cancelDownload")}
                            aria-label={t("models.cancelDownload")}
                            onClick={() => void handleCancelOllamaPull(m.name)}
                          >
                            <VkIcon.x />
                          </button>
                        )}
                      </span>
                      {isPulling && ollamaPullProgress !== null && (
                        <span className="vk-dlbar"><i style={{ width: Math.round(ollamaPullProgress * 100) + "%" }}></i></span>
                      )}
                      {isPulling && ollamaEta !== null && (
                        <span className="vk-eta">{formatEta(ollamaEta)} {t("models.remaining")}</span>
                      )}
                    </span>
                  )}
                </span>
              </div>
            );
          })}

          {/* Input modello personalizzato */}
          <div className="vk-field" style={{ marginTop: 12 }}>
            <label>{t("models.customLabel")}</label>
            <div className="vk-path">
              <input
                ref={customRef}
                className="vk-input"
                type="text"
                value={customModel}
                placeholder={t("models.customPlaceholder")}
                onChange={(e) => setCustomModel(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void handleCustomPull();
                }}
              />
              <button
                className="vk-mini"
                disabled={!customModel.trim() || ollamaPulling !== null}
                onClick={() => void handleCustomPull()}
              >
                {ollamaPulling && ollamaPulling === customModel.trim() ? t("models.downloadingShort") : t("models.downloadBtn")}
              </button>
            </div>
            <div className="vk-hlp">
              {t("models.customHelpA")}
              <span
                className="mono"
                style={{ cursor: "pointer", textDecoration: "underline" }}
                onClick={() => void bridge.openUrl("https://ollama.com/library")}
              >
                ollama.com/library
              </span>
              {t("models.customHelpB")}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

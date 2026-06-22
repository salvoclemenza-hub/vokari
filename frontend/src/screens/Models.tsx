import { useEffect, useRef, useState, type MutableRefObject } from "react";
import { bridge, onVokariEvent, DEFAULT_SETTINGS, type DiskUsage, type ModelEntry, type OllamaModelEntry, type OllamaStatus, type VokariSettings } from "../bridge";
import { toast } from "../toast";
import { VkIcon } from "../icons";

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
const TAG_META: Record<string, { icon: () => JSX.Element; title: string; cat: string }> = {
  italiano: { icon: () => <VkIcon.globe />, title: "Ottimo in italiano", cat: "ml" },
  multilingue: { icon: () => <VkIcon.globe />, title: "Multilingue", cat: "ml" },
  json: { icon: () => <VkIcon.braces />, title: "JSON affidabile", cat: "json" },
  "tool-calling": { icon: () => <VkIcon.wrench />, title: "Tool calling", cat: "tool" },
  reasoning: { icon: () => <VkIcon.brain />, title: "Reasoning avanzato", cat: "json" },
  veloce: { icon: () => <VkIcon.zap />, title: "Veloce su CPU", cat: "ctx" },
  leggero: { icon: () => <VkIcon.feather />, title: "Leggero / poca RAM", cat: "ctx" },
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
  // MOD2: avviso solo se conosciamo davvero RAM totale e requisito (margine 90%).
  const ramHeavy = ramTotalGb > 0 && m.minRamGb > 0 && m.minRamGb > ramTotalGb * 0.9;
  return (
    <>
      <span className="badges" style={{ flexWrap: "wrap", rowGap: 6 }}>
        <span className="vk-badge">{m.sizeLabel}</span>
        {ramHeavy && (
          <span className="vk-ramwarn" title={`Richiede ~${m.minRamGb} GB di RAM · ne hai ${ramTotalGb} GB`}>
            pesante per la tua RAM ({ramTotalGb} GB)
          </span>
        )}
        {m.params && <span className="vk-badge">{m.params}</span>}
        {/* meter solo se abbiamo metadati reali: i modelli fuori catalogo hanno speed/quality 0 */}
        {(m.speed > 0 || m.quality > 0) && (
          <>
            <Meter label="velocità" n={m.speed} />
            <Meter label="qualità" n={m.quality} kind="q" />
          </>
        )}
        {m.context && <span className="vk-badge">contesto {m.context}</span>}
        {m.tags.length > 0 && (
          <span className="vk-tagico">
            {m.tags.map((t) => {
              const meta = TAG_META[t];
              return meta ? (
                <span key={t} className={"ti " + meta.cat} title={meta.title} role="img" aria-label={meta.title}>
                  <meta.icon />
                </span>
              ) : (
                <span className="vk-badge" key={t}>
                  {t}
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
        ⓘ dettagli del modello
      </span>
    </>
  );
}

export function ScreenModels() {
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
      toast(`Installazione Ollama non riuscita: ${String(e)}`, "error");
    }
  }

  async function handleOllamaStartServer() {
    setOllamaSetup({ status: "starting", pct: 1 });
    try {
      const res = await bridge.ollamaStart();
      setOllamaSetup(null);
      if (res.running) {
        toast("Ollama avviato ✓", "success");
        bridge.ollamaStatus().then(setOllamaState);
        bridge.listOllamaModels().then(setOllamaModels);
      } else {
        toast("Ollama non si è avviato. Controlla l'installazione.", "error");
      }
    } catch (e) {
      setOllamaSetup(null);
      toast(`Avvio Ollama non riuscito: ${String(e)}`, "error");
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
        toast(`Modello ${payload.name as string} scaricato ✓`, "success");
        bridge.listModels().then(setModels);
        bridge.diskUsage().then(setDisk);
      } else if (payload.status === "error") {
        setDownloading(null);
        setProgress(null);
        setWhisperEta(null);
        whisperEtaRef.current = null;
        toast(`Download di ${payload.name as string} non riuscito: ${(payload.error as string) ?? "errore sconosciuto"}`, "error");
        bridge.listModels().then(setModels);
      }
    });
    return off;
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
        toast(`Modello Ollama ${payload.name as string} scaricato ✓`, "success");
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
        toast(`Download di ${payload.name as string} annullato`, "info");
      } else if (payload.status === "error") {
        setOllamaPulling(null);
        setOllamaPullProgress(null);
        setOllamaEta(null);
        ollamaEtaRef.current = null;
        toast(`Pull di ${payload.name as string} non riuscito: ${(payload.error as string) ?? "errore sconosciuto"}`, "error");
      }
    });
    return off;
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
        toast("Ollama pronto ✓", "success");
        bridge.ollamaStatus().then(setOllamaState);
        bridge.listOllamaModels().then(setOllamaModels);
      } else if (status === "error") {
        setOllamaSetup(null);
        toast(`Ollama: ${(payload.error as string) ?? "avvio non riuscito"}`, "error");
        bridge.ollamaStatus().then(setOllamaState);
      } else {
        setOllamaSetup({ status, pct });
      }
    });
    return off;
  }, []);

  async function handleDownload(name: string) {
    try {
      await bridge.downloadModel(name);
      bridge.listModels().then(setModels);
    } catch (e) {
      toast(`Avvio download non riuscito: ${String(e)}`, "error");
    }
  }

  async function handleActivate(name: string) {
    try {
      const updated = await bridge.setActiveModel(name);
      setSettings(updated);
      bridge.listModels().then(setModels);
    } catch (e) {
      toast(`Attivazione modello non riuscita: ${String(e)}`, "error");
    }
  }

  async function handleSetBrain(brain: string) {
    try {
      const updated = await bridge.setBrain(brain);
      setSettings(updated);
    } catch (e) {
      toast(`Cambio cervello AI non riuscito: ${String(e)}`, "error");
    }
  }

  async function handleOllamaPull(name: string) {
    try {
      await bridge.pullOllamaModel(name);
    } catch (e) {
      toast(`Avvio pull non riuscito: ${String(e)}`, "error");
    }
  }

  // MOD1: interrompe il pull Ollama in corso. L'esito reale (transizione a "annullato")
  // arriva via evento `ollama_pull` status=cancelled, che resetta lo stato di download.
  async function handleCancelOllamaPull(name: string) {
    try {
      await bridge.cancelOllamaPull(name);
    } catch (e) {
      toast(`Annullamento non riuscito: ${String(e)}`, "error");
    }
  }

  async function handleOllamaActivate(name: string) {
    try {
      const updated = await bridge.saveSettings({ ollamaModel: name });
      setSettings(updated);
      bridge.listOllamaModels().then(setOllamaModels);
    } catch (e) {
      toast(`Attivazione non riuscita: ${String(e)}`, "error");
    }
  }

  async function handleOllamaDelete(name: string) {
    try {
      const res = await bridge.deleteOllamaModel(name);
      if (res.ok) {
        toast(`Modello ${name} rimosso ✓`, "success");
        bridge.listOllamaModels().then(setOllamaModels);
        bridge.diskUsage().then(setDisk);
      } else {
        toast(`Rimozione di ${name} non riuscita`, "error");
      }
    } catch (e) {
      toast(`Rimozione non riuscita: ${String(e)}`, "error");
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
          <div className="vk-kick">~/modelli</div>
          <h1>Modelli AI</h1>
          <p>
            Organizzazione con <b>Claude</b> o un modello <b>locale</b> · trascrizione locale con{" "}
            <b>Whisper</b>.
          </p>
        </div>
      </div>

      {downloadedCount > 0 && (
        <div className="vk-disk">
          <span className="d"></span>
          <b>{downloadedCount}</b> {downloadedCount === 1 ? "modello scaricato" : "modelli scaricati"}
          {/* MOD3: GB usati dai modelli / liberi (se il dato è disponibile). */}
          {disk && (disk.usedByModelsGb > 0 || disk.freeGb > 0) ? (
            <span className="vk-disk-x"> · <b>{disk.usedByModelsGb} GB</b> usati · <b>{disk.freeGb} GB</b> liberi</span>
          ) : (
            <> sul dispositivo</>
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
            Organizzazione
          </div>
          <div className="vk-sc-sub">
            Chi trasforma la trascrizione in briefing. Solo il testo viene inviato.
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
                <div className="bt">Claude API</div>
                <div className="bs">Qualità migliore · richiede chiave</div>
              </div>
              <span className="rd"></span>
            </div>
            <div className="bd">
              Modello <span className="mono">{settings.claudeModel}</span> · veloce e accurato sui
              briefing.
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
                <div className="bt">Locale (Ollama)</div>
                <div className="bs">Offline · nessuna chiave</div>
              </div>
              <span className="rd"></span>
            </div>
            <div className="bd">
              Endpoint <span className="mono">{settings.ollamaEndpoint}</span> ·{" "}
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
            Trascrizione · Whisper (locale)
          </div>
          <div className="vk-sc-sub">
            Gira al 100% sul tuo dispositivo. Scarica i modelli on-demand; il default bilancia
            velocità e qualità.
          </div>

          {models.map((m) => {
            const isActive = m.name === settings.whisperModel;
            const isDownloading = downloading === m.name;
            return (
              <div
                className={"vk-mrow" + (isActive ? " on" : "")}
                key={m.name}
                onClick={() => {
                  if (m.state !== "available" && !isActive) void handleActivate(m.name);
                }}
                style={{ cursor: m.state !== "available" && !isActive ? "pointer" : "default" }}
              >
                <span className="nm">
                  <span className="t">
                    {m.name}
                    {isActive && <span className="df">DEFAULT</span>}
                  </span>
                  <span className="badges">
                    <span className="vk-badge">{m.sizeLabel}</span>
                    <Meter label="velocità" n={m.speed} />
                    <Meter label="qualità" n={m.quality} kind="q" />
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
                      <span className="d"></span>Attivo
                    </span>
                  )}
                  {!isActive && m.state === "downloaded" && (
                    <span className="saved">
                      <VkIcon.check />
                      Scaricato
                    </span>
                  )}
                  {m.state === "available" && (
                    <span className="vk-getwrap">
                      <button
                        className="get"
                        disabled={isDownloading}
                        title={isDownloading ? `${m.sizeLabel} · può richiedere alcuni minuti` : undefined}
                        onClick={(e) => {
                          e.stopPropagation();
                          void handleDownload(m.name);
                        }}
                      >
                        <VkIcon.down />
                        {isDownloading
                          ? progress !== null
                            ? `Scaricando ${Math.round(progress * 100)}%`
                            : "Scaricando…"
                          : "Download"}
                      </button>
                      {isDownloading && progress !== null && (
                        <span className="vk-dlbar"><i style={{ width: Math.round(progress * 100) + "%" }}></i></span>
                      )}
                      {isDownloading && whisperEta !== null && (
                        <span className="vk-eta">{formatEta(whisperEta)} rimanenti</span>
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
              I modelli <b>distil-*</b> sono solo inglese e quindi esclusi: Vokari è{" "}
              <b>multilingue</b> (IT + EN e oltre).
            </span>
          </div>
        </div>

        {/* 3 · Modelli locali · Ollama */}
        <div className="vk-sc">
          <div className="vk-sc-h">
            <span className="ico">
              <VkIcon.cpu />
            </span>
            Modelli locali · Ollama
          </div>
          <div className="vk-sc-sub">
            Per l'organizzazione offline. <b>Velocità</b> e <b>qualità</b> sono indicative su CPU;
            usale (con dimensione, parametri e contesto) per scegliere il modello giusto. Sfoglia
            l'intero catalogo su{" "}
            <span
              className="mono"
              style={{ cursor: "pointer", textDecoration: "underline" }}
              onClick={() => void bridge.openUrl("https://ollama.com/library")}
            >
              ollama.com/library
            </span>
            .
          </div>

          {/* Stato runtime Ollama come chip `.vk-runtime` (mock): VOKARI lo avvia/installa da sé. */}
          {ollamaSetup ? (
            <div className="vk-runtime">
              <span className="dot spin"></span>
              <span className="tx">
                {ollamaSetup.status === "downloading"
                  ? `Scaricamento di Ollama in corso… ${Math.round(ollamaSetup.pct * 100)}% (file grande, una sola volta)`
                  : "Avvio di Ollama in corso…"}
              </span>
            </div>
          ) : ollamaState && ollamaState.running ? (
            <div className="vk-runtime">
              <span className="dot"></span>
              <span className="tx">
                <b>Ollama in esecuzione</b> — VOKARI lo avvia da solo a ogni apertura.
              </span>
            </div>
          ) : ollamaState && ollamaState.installed ? (
            <div className="vk-runtime">
              <span className="dot warn"></span>
              <span className="tx">
                <b>Ollama installato</b> ma non in esecuzione.
              </span>
              <button className="vk-mini" onClick={() => void handleOllamaStartServer()}>
                Avvia Ollama
              </button>
            </div>
          ) : ollamaState && ollamaState.canInstall ? (
            <div className="vk-runtime">
              <span className="dot off"></span>
              <span className="tx">
                Ollama non è installato. VOKARI può <b>scaricarlo e configurarlo da sé</b> — nessun
                amministratore, tutto nella cartella dati dell'app.
              </span>
              <button className="vk-mini" onClick={() => void handleOllamaInstall()}>
                Installa Ollama
              </button>
            </div>
          ) : ollamaState && !ollamaState.installed ? (
            <div className="vk-runtime">
              <span className="dot off"></span>
              <span className="tx">
                Ollama non è installato. Scaricalo da{" "}
                <span
                  className="mono"
                  style={{ cursor: "pointer", textDecoration: "underline" }}
                  onClick={() => void bridge.openUrl("https://ollama.com/download")}
                >
                  ollama.com/download
                </span>{" "}
                e riavvia VOKARI.
              </span>
            </div>
          ) : null}

          {/* Toolbar: filtra (Tutti/Scaricati) + ordina (dimensione/qualità) */}
          {ollamaModels.length > 0 && (
            <div className="vk-otoolbar">
              <div className="vk-ofilters">
                <button className={oFilter === "all" ? "on" : ""} onClick={() => setOFilter("all")}>Tutti</button>
                <button className={oFilter === "down" ? "on" : ""} onClick={() => setOFilter("down")}>Scaricati</button>
                {/* MOD2: "Compatibili" solo se conosciamo la RAM (altrimenti non avrebbe un criterio reale). */}
                {ramTotalGb > 0 && (
                  <button className={oFilter === "fit" ? "on" : ""} onClick={() => setOFilter("fit")}>Compatibili</button>
                )}
              </div>
              <select className="vk-osort" value={oSort} onChange={(e) => setOSort(e.target.value as "size" | "qual")}>
                <option value="size">Ordina: dimensione</option>
                <option value="qual">Ordina: qualità</option>
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
                    {isActive && <span className="df">ATTIVO</span>}
                  </span>
                  <LocalModelMeta m={m} ramTotalGb={ramTotalGb} />
                </span>
                <span className="act" style={{ gap: 4 }}>
                  {m.isInstalled ? (
                    <>
                      {isActive ? (
                        <span className="active">
                          <span className="d"></span>Attivo
                        </span>
                      ) : (
                        <button className="get" onClick={() => void handleOllamaActivate(m.name)}>
                          Attiva
                        </button>
                      )}
                      <button
                        className="get ghost"
                        onClick={() => void handleOllamaDelete(m.name)}
                        title="Rimuovi modello dal disco"
                      >
                        Rimuovi
                      </button>
                    </>
                  ) : (
                    <span className="vk-getwrap">
                      <span className="vk-dlrow">
                        <button
                          className="get"
                          disabled={isPulling || ollamaPulling !== null}
                          title={isPulling ? `${m.sizeLabel} · può richiedere alcuni minuti` : undefined}
                          onClick={() => void handleOllamaPull(m.name)}
                        >
                          <VkIcon.down />
                          {isPulling
                            ? ollamaPullProgress !== null
                              ? `Scaricando ${Math.round(ollamaPullProgress * 100)}%`
                              : "Scaricando…"
                            : "Download"}
                        </button>
                        {/* MOD1: ✕ Annulla — solo durante il pull di QUESTO modello. */}
                        {isPulling && (
                          <button
                            className="vk-dlcancel"
                            title="Annulla download"
                            aria-label="Annulla download"
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
                        <span className="vk-eta">{formatEta(ollamaEta)} rimanenti</span>
                      )}
                    </span>
                  )}
                </span>
              </div>
            );
          })}

          {/* Input modello personalizzato */}
          <div className="vk-field" style={{ marginTop: 12 }}>
            <label>Altro modello Ollama</label>
            <div className="vk-path">
              <input
                ref={customRef}
                className="vk-input"
                type="text"
                value={customModel}
                placeholder="es. phi4:14b"
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
                {ollamaPulling && ollamaPulling === customModel.trim() ? "Scaricando…" : "Scarica"}
              </button>
            </div>
            <div className="vk-hlp">
              Qualsiasi nome da{" "}
              <span
                className="mono"
                style={{ cursor: "pointer", textDecoration: "underline" }}
                onClick={() => void bridge.openUrl("https://ollama.com/library")}
              >
                ollama.com/library
              </span>{" "}
              compatibile con la tua RAM.
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

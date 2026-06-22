import { useRef, useState } from "react";
import { VkIcon } from "../icons";
import { toast } from "../toast";
import { MarkdownDoc } from "./MarkdownDoc";
import type { Artifacts, ExportResult } from "../bridge";

function fmtDur(s: number): string {
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(Math.round(s % 60)).padStart(2, "0")}`;
}

// Tempo di lettura stimato dal contenuto del tab (escluso il frontmatter YAML),
// ~200 parole/min. Orienta l'utente prima di aprire il documento.
function countWords(s: string): number {
  const t = s.replace(/^---[\s\S]*?---/, "").trim();
  return t ? t.split(/\s+/).filter(Boolean).length : 0;
}
function readTime(words: number): string {
  if (!words) return "vuoto";
  const secs = Math.round((words / 200) * 60);
  const label = secs < 60 ? `~${Math.max(5, secs)} sec` : `~${Math.round(secs / 60)} min`;
  return `${label} · ${words} parole`;
}

// Tag della nota Obsidian, letti dal frontmatter reale: supporta sia l'array inline
// `tags: [a, b]` sia la lista YAML su più righe. Mostrati come chip #tag sotto i collegamenti.
function cleanTag(t: string): string {
  return t.trim().replace(/^['"#]+/, "").replace(/['"]+$/, "").trim();
}
function extractTags(md: string): string[] {
  const fm = md.match(/^---\r?\n([\s\S]*?)\r?\n---/);
  if (!fm) return [];
  const body = fm[1];
  const line = body.match(/^tags:\s*(.*)$/m);
  if (!line) return [];
  const rest = line[1].trim();
  let raw: string[];
  if (rest.startsWith("[")) {
    raw = rest.replace(/^\[/, "").replace(/\]$/, "").split(",");
  } else if (rest) {
    raw = rest.split(",");
  } else {
    raw = [];
    const lines = body.split(/\r?\n/);
    const idx = lines.findIndex((l) => /^tags:\s*$/.test(l));
    for (let i = idx + 1; i < lines.length; i++) {
      const lm = lines[i].match(/^\s*-\s*(.+)$/);
      if (!lm) break;
      raw.push(lm[1]);
    }
  }
  return [...new Set(raw.map(cleanTag).filter(Boolean))];
}

// Icone solide (fill currentColor) locali a questa schermata: file/recap/vault,
// info, orologio, barre. Le altre arrivano da VkIcon.
const IcoFile = () => (
  <svg viewBox="0 0 24 24" fill="currentColor"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zm-1 7V3.5L18.5 9H13z" /></svg>
);
const IcoRecap = () => (
  <svg viewBox="0 0 24 24" fill="currentColor"><path d="M18 2H9a2 2 0 0 0-2 2v1H6a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h9a2 2 0 0 0 2-2v-1h1a2 2 0 0 0 2-2V6l-4-4zM6 20V7h1v11a2 2 0 0 0 2 2H6zm12-3H9V4h5v4h4v9z" /></svg>
);
const IcoVault = () => (
  <svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l9 5v10l-9 5-9-5V7l9-5zm0 2.3L5 8v8l7 3.9 7-3.9V8l-7-3.7z" /></svg>
);
const IcoInfo = () => (
  <svg viewBox="0 0 24 24" fill="currentColor"><path d="M11 7h2v2h-2V7zm0 4h2v6h-2v-6zm1-9C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z" /></svg>
);
const IcoClock = () => (
  <svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm0 18a8 8 0 1 1 0-16 8 8 0 0 1 0 16zm.5-13H11v6l5 3 .75-1.23-4.25-2.52V7z" /></svg>
);
const IcoBars = () => (
  <svg viewBox="0 0 24 24" fill="currentColor"><path d="M3 10h2v4H3v-4zm4-3h2v10H7V7zm4-3h2v16h-2V4zm4 3h2v10h-2V7zm4 3h2v4h-2v-4z" /></svg>
);

export function ScreenArtifacts({
  artifacts, onCopy, onOpenFolder, onExportPdf, onExportObsidian, onDownload, onBack,
}: {
  artifacts?: Artifacts;
  onCopy?: (md: string) => void;
  onOpenFolder?: (path: string) => void;
  onExportPdf?: () => Promise<ExportResult> | void;
  onExportObsidian?: () => Promise<ExportResult> | void;
  onDownload?: (suggestedName: string, content: string) => Promise<ExportResult> | void;
  onBack?: () => void;
}) {
  const [tab, setTab] = useState<"briefing" | "recap" | "obsidian" | "transcript">("briefing");
  const [busy, setBusy] = useState<"pdf" | "obsidian" | null>(null);
  const [openInfo, setOpenInfo] = useState<string | null>(null);
  const a = artifacts;
  const briefing = a?.briefingMd ?? "";
  const recap = a?.recapMd ?? "";
  const obsidian = a?.obsidianNote ?? "";
  const transcript = a?.transcriptText ?? "";

  const hasRecap = recap.length > 0;
  const hasObsidian = obsidian.length > 0;
  const hasTranscript = transcript.length > 0;

  const tabContent =
    tab === "briefing" ? briefing
    : tab === "recap" ? recap
    : tab === "obsidian" ? obsidian
    : transcript;

  // Mini-indice sezioni + chip "da chiarire": solo sul briefing, derivati dal markdown reale.
  const sections =
    tab === "briefing" ? Array.from(briefing.matchAll(/^##\s+(.+)$/gm)).map((m) => m[1].trim()) : [];
  const clarCount = tab === "briefing" ? (briefing.match(/\[DA CHIARIRE/g) || []).length : 0;
  const obsTags = tab === "obsidian" ? extractTags(obsidian) : [];

  const docRef = useRef<HTMLDivElement>(null);
  const clarIdx = useRef(0);

  function jumpSection(title: string) {
    const root = docRef.current;
    if (!root) return;
    const el = Array.from(root.querySelectorAll("h3")).find((h) => h.textContent?.trim() === title);
    el?.scrollIntoView?.({ behavior: "smooth", block: "start" });
  }

  function jumpClar() {
    const root = docRef.current;
    if (!root) return;
    const badges = root.querySelectorAll<HTMLElement>(".vk-clar");
    if (!badges.length) return;
    const host = (badges[clarIdx.current % badges.length].closest("li, p") as HTMLElement) ?? badges[0];
    host.scrollIntoView?.({ behavior: "smooth", block: "center" });
    root.querySelectorAll(".vk-clar-hl").forEach((e) => e.classList.remove("vk-clar-hl"));
    host.classList.add("vk-clar-hl");
    window.setTimeout(() => host.classList.remove("vk-clar-hl"), 1500);
    clarIdx.current += 1;
  }

  function toggleInfo(id: string) {
    setOpenInfo((cur) => (cur === id ? null : id));
  }

  async function handleExportPdf() {
    if (!onExportPdf) return;
    setBusy("pdf");
    try {
      const res = await onExportPdf();
      if (res && typeof res === "object") {
        if (res.ok) toast(`PDF del recap salvato: ${res.path ?? ""}`, "success");
        else if (res.error) toast(`PDF non generato: ${res.error}`, "error");
        // res.cancelled (utente ha chiuso il dialogo) → nessun toast
      } else {
        toast("PDF del recap generato.", "success");
      }
    } catch (e) {
      toast(`PDF non generato: ${String(e)}`, "error");
    } finally {
      setBusy(null);
    }
  }

  async function handleExportObsidian() {
    if (!onExportObsidian) return;
    setBusy("obsidian");
    try {
      const res = await onExportObsidian();
      if (res && typeof res === "object") {
        if (res.ok) toast(`Esportate ${res.count ?? 0} note su Obsidian.`, "success");
        else if (res.error) toast(`Esportazione Obsidian non riuscita: ${res.error}`, "error");
      } else {
        toast("Esportato su Obsidian.", "success");
      }
    } catch (e) {
      toast(`Esportazione Obsidian non riuscita: ${String(e)}`, "error");
    } finally {
      setBusy(null);
    }
  }

  async function handleDownload(suggestedName: string, content: string) {
    if (!onDownload) return;
    try {
      const res = await onDownload(suggestedName, content);
      if (res && typeof res === "object") {
        if (res.ok) toast(`Salvato: ${res.path ?? suggestedName}`, "success");
        else if (res.error) toast(`Salvataggio non riuscito: ${res.error}`, "error");
      }
    } catch (e) {
      toast(`Salvataggio non riuscito: ${String(e)}`, "error");
    }
  }

  return (
    <>
      <div className="vk-art-head">
        <div>
          {onBack && (
            <button className="vk-back" onClick={onBack}
                    style={{ display: "inline-flex", alignItems: "center", gap: 5, background: "none", border: "none", color: "var(--mut)", cursor: "pointer", font: "inherit", padding: 0, marginBottom: 6 }}>
              <VkIcon.back />Sessioni
            </button>
          )}
          <div className="vk-kick">~/sessione</div>
          <h1>{a?.title || "Sessione"}</h1>
          <div className="meta">
            <span><b>{a ? fmtDur(a.durationS) : "—"}</b></span>
            <span>{a?.model || "—"}</span>
            <span>{a?.language || "—"}</span>
            <span><b>{a?.wordCount ?? 0}</b> parole</span>
          </div>
        </div>
      </div>

      <div className="vk-art-grid">
        <div className="vk-art-doc">
          <div className="vk-tabs">
            <button className={"t-brief" + (tab === "briefing" ? " on" : "")} onClick={() => setTab("briefing")}>
              <span className="dot" />briefing.md</button>
            <button
              className={"t-recap" + (tab === "recap" ? " on" : "")}
              disabled={!hasRecap}
              title={!hasRecap ? "recap.md non disponibile" : undefined}
              onClick={() => setTab("recap")}
            ><span className="dot" />recap.md</button>
            <button
              className={"t-obs" + (tab === "obsidian" ? " on" : "")}
              title={!hasObsidian ? "Nota Obsidian non ancora creata" : undefined}
              onClick={() => setTab("obsidian")}
            ><span className="dot" />obsidian/</button>
            <button
              className={"t-trans" + (tab === "transcript" ? " on" : "")}
              disabled={!hasTranscript}
              title={!hasTranscript ? "Trascrizione non disponibile" : undefined}
              onClick={() => setTab("transcript")}
            ><span className="dot" />trascrizione</button>
            <span className="vk-tabs-grow" />
            <span className="vk-readtime">{readTime(countWords(tabContent))}</span>
            <button className="vk-copy" title="Copia il contenuto del tab visualizzato"
                    onClick={() => onCopy?.(tabContent)}>⧉ copia</button>
          </div>
          <div className="vk-doc" ref={docRef}>
            {tabContent ? (
              <>
                {tab === "briefing" && (sections.length > 1 || clarCount > 0) && (
                  <div className="vk-doc-toc">
                    {sections.length > 1 && (
                      <div className="vk-index">
                        {sections.map((s) => (
                          <button key={s} type="button" onClick={() => jumpSection(s)}>{s}</button>
                        ))}
                      </div>
                    )}
                    {clarCount > 0 && (
                      <button type="button" className="vk-dc-count" onClick={jumpClar}
                              title="Salta alle domande aperte rimaste senza risposta">
                        ? {clarCount} da chiarire
                      </button>
                    )}
                  </div>
                )}
                {tab === "transcript"
                  ? <pre className="vk-transcript-pre">{tabContent}</pre>
                  : <MarkdownDoc md={tabContent} />}
                {tab === "obsidian" && obsTags.length > 0 && (
                  <div className="vk-otags">
                    {obsTags.map((t) => <span key={t} className="vk-otag">#{t}</span>)}
                  </div>
                )}
              </>
            ) : tab === "obsidian" ? (
              <div className="vk-empty">
                <div className="ico"><IcoVault /></div>
                <div className="tt">Nota Obsidian non ancora creata</div>
                <div className="dd">Esportala nel tuo vault come nota atomica con frontmatter e wikilink,
                  pronta per il tuo second brain.</div>
                <button type="button" onClick={handleExportObsidian} disabled={busy === "obsidian"}>
                  <VkIcon.share />{busy === "obsidian" ? "Esportazione…" : "Esporta su Obsidian"}</button>
              </div>
            ) : (
              <p className="vk-doc-empty">{tab === "briefing" ? "(briefing non ancora generato)" : "(nessun contenuto)"}</p>
            )}
          </div>
        </div>

        <aside className="vk-art-side">
          <div className="vk-card">
            <button className="vk-btn-g vk-rail-cta vk-cta-pop"
                    title="Copia il briefing.md negli appunti: incollalo in ChatGPT, Claude o un'altra AI"
                    onClick={() => onCopy?.(briefing)}><VkIcon.arrow />Copia il briefing per la tua AI</button>

            <div className="vk-rail-sep" />
            <div className="vk-rail-lbl">File generati</div>

            <div className={"vk-fileitem" + (openInfo === "briefing" ? " open" : "")}>
              <div className="vk-file">
                <span className="ico md"><IcoFile /></span>
                <div className="info"><div className="nm">briefing.md</div><div className="ds">per l'AI</div></div>
                <div className="acts">
                  <button type="button" className="vk-info-btn" aria-label="Cos'è il briefing"
                          onClick={() => toggleInfo("briefing")}><IcoInfo /></button>
                  <button type="button" className="vk-mini"
                          onClick={() => void handleDownload("briefing.md", briefing)}>Scarica</button>
                </div>
              </div>
              <div className="vk-file-exp">Documento ottimizzato per essere incollato in un'altra AI come
                contesto: sezioni, decisioni, domande aperte e trascrizione integrale.</div>
            </div>

            <div className={"vk-fileitem" + (openInfo === "recap" ? " open" : "")}>
              <div className="vk-file">
                <span className="ico rc"><IcoRecap /></span>
                <div className="info"><div className="nm">recap.md</div><div className="ds">leggibile</div></div>
                <div className="acts">
                  <button type="button" className="vk-info-btn" aria-label="Cos'è il recap"
                          onClick={() => toggleInfo("recap")}><IcoInfo /></button>
                  <button type="button" className="vk-mini" aria-label="Genera PDF del recap"
                          title="Crea un PDF del recap e ti chiede dove salvarlo"
                          disabled={busy === "pdf"} onClick={handleExportPdf}>{busy === "pdf" ? "…" : "PDF"}</button>
                  {hasRecap && (
                    <button type="button" className="vk-mini"
                            onClick={() => void handleDownload("recap.md", recap)}>Scarica</button>
                  )}
                </div>
              </div>
              <div className="vk-file-exp">Versione in prosa, pensata per essere letta da una persona.
                Esportabile in PDF per condividerla o archiviarla.</div>
            </div>

            <div className={"vk-fileitem" + (openInfo === "vault" ? " open" : "")}>
              <div className="vk-file">
                <span className="ico vault"><IcoVault /></span>
                <div className="info"><div className="nm">vault</div><div className="ds">nota Obsidian</div></div>
                <div className="acts">
                  <button type="button" className="vk-info-btn" aria-label="Cos'è la nota Obsidian"
                          onClick={() => toggleInfo("vault")}><IcoInfo /></button>
                  <button type="button" className="vk-mini" aria-label="Esporta su Obsidian"
                          title="Scrive la nota nel vault Obsidian configurato in Impostazioni"
                          disabled={busy === "obsidian"} onClick={handleExportObsidian}>{busy === "obsidian" ? "…" : "esporta"}</button>
                  {hasObsidian && (
                    <button type="button" className="vk-mini"
                            onClick={() => void handleDownload("nota.md", obsidian)}>Scarica</button>
                  )}
                </div>
              </div>
              <div className="vk-file-exp">Nota atomica per Obsidian con frontmatter e wikilink: alimenta il
                tuo "second brain" collegando i concetti tra le sessioni.</div>
            </div>

            <div className="vk-rail-sep" />
            <button type="button" className="vk-openfolder"
                    onClick={() => a?.briefingPath && onOpenFolder?.(a.briefingPath)}>
              <VkIcon.folder />Apri cartella</button>
          </div>

          <div className="vk-card">
            <div className="vk-rail-lbl">Dettagli</div>
            <div className="vk-det-row">
              <span className="di"><IcoClock /></span>
              <span className="dl">durata</span><span className="dv">{a ? fmtDur(a.durationS) : "—"}</span>
            </div>
            <div className="vk-det-row">
              <span className="di"><IcoBars /></span>
              <span className="dl">trascrizione</span><span className="dv">{a?.model || "—"}</span>
            </div>
            <div className="vk-det-row">
              <span className="di"><VkIcon.globe /></span>
              <span className="dl">lingua</span><span className="dv">{a?.language || "—"}</span>
            </div>
            <div className="vk-det-row">
              <span className="di priv"><VkIcon.lock /></span>
              <span className="dl">privacy</span><span className="dv">solo testo all'AI</span>
            </div>
          </div>
        </aside>
      </div>
    </>
  );
}

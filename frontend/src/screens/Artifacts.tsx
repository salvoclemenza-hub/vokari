import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
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
  const body = s.replace(/^---[\s\S]*?---/, "").trim();
  return body ? body.split(/\s+/).filter(Boolean).length : 0;
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
  artifacts, onCopy, onOpenFolder, onExportPdf, onExportObsidian, onDownload, onReexport, onBack,
}: {
  artifacts?: Artifacts;
  onCopy?: (md: string) => void;
  onOpenFolder?: (path: string) => void;
  onExportPdf?: () => Promise<ExportResult> | void;
  onExportObsidian?: () => Promise<ExportResult> | void;
  onDownload?: (suggestedName: string, content: string) => Promise<ExportResult> | void;
  onReexport?: () => Promise<ExportResult> | void;
  onBack?: () => void;
}) {
  const { t } = useTranslation();
  // Tempo di lettura tradotto (~200 parole/min). Locale alla schermata per usare t().
  const readTimeLabel = (words: number): string => {
    if (!words) return t("art.empty");
    const secs = Math.round((words / 200) * 60);
    const label = secs < 60 ? t("art.readSec", { n: Math.max(5, secs) }) : t("art.readMin", { n: Math.round(secs / 60) });
    return t("art.readTime", { label, words });
  };
  const [tab, setTab] = useState<"briefing" | "recap" | "obsidian" | "transcript">("briefing");
  const [busy, setBusy] = useState<"pdf" | "obsidian" | "reexport" | null>(null);
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
        if (res.ok) toast(t("art.toastPdfSaved", { path: res.path ?? "" }), "success");
        else if (res.error) toast(t("art.toastPdfFail", { error: res.error }), "error");
        // res.cancelled (utente ha chiuso il dialogo) → nessun toast
      } else {
        toast(t("art.toastPdfDone"), "success");
      }
    } catch (e) {
      toast(t("art.toastPdfFail", { error: String(e) }), "error");
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
        if (res.ok) toast(t("art.toastObsExported", { count: res.count ?? 0 }), "success");
        else if (res.error) toast(t("art.toastObsFail", { error: res.error }), "error");
      } else {
        toast(t("art.toastObsDone"), "success");
      }
    } catch (e) {
      toast(t("art.toastObsFail", { error: String(e) }), "error");
    } finally {
      setBusy(null);
    }
  }

  async function handleReexport() {
    if (!onReexport) return;
    setBusy("reexport");
    try {
      const res = await onReexport();
      if (res && typeof res === "object") {
        if (res.ok) {
          const vaultBit = res.count ? t("art.reexportVaultBit", { count: res.count }) : "";
          toast(t("art.toastReexportOk", { vault: vaultBit }), "success");
        } else if (res.error) toast(t("art.toastReexportFail", { error: res.error }), "error");
      } else {
        toast(t("art.toastReexportDone"), "success");
      }
    } catch (e) {
      toast(t("art.toastReexportFail", { error: String(e) }), "error");
    } finally {
      setBusy(null);
    }
  }

  async function handleDownload(suggestedName: string, content: string) {
    if (!onDownload) return;
    try {
      const res = await onDownload(suggestedName, content);
      if (res && typeof res === "object") {
        if (res.ok) toast(t("art.toastSaved", { path: res.path ?? suggestedName }), "success");
        else if (res.error) toast(t("art.toastSaveFail", { error: res.error }), "error");
      }
    } catch (e) {
      toast(t("art.toastSaveFail", { error: String(e) }), "error");
    }
  }

  return (
    <>
      <div className="vk-art-head">
        <div>
          {onBack && (
            <button className="vk-back" onClick={onBack}
                    style={{ display: "inline-flex", alignItems: "center", gap: 5, background: "none", border: "none", color: "var(--mut)", cursor: "pointer", font: "inherit", padding: 0, marginBottom: 6 }}>
              <VkIcon.back />{t("art.back")}
            </button>
          )}
          <div className="vk-kick">{t("art.kick")}</div>
          <h1>{a?.title || t("art.titleFallback")}</h1>
          <div className="meta">
            <span><b>{a ? fmtDur(a.durationS) : "—"}</b></span>
            <span>{a?.model || "—"}</span>
            <span>{a?.language || "—"}</span>
            <span><b>{a?.wordCount ?? 0}</b> {t("art.wordsLabel")}</span>
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
              title={!hasRecap ? t("art.ttRecapUnavailable") : undefined}
              onClick={() => setTab("recap")}
            ><span className="dot" />recap.md</button>
            <button
              className={"t-obs" + (tab === "obsidian" ? " on" : "")}
              title={!hasObsidian ? t("art.ttObsNotCreated") : undefined}
              onClick={() => setTab("obsidian")}
            ><span className="dot" />obsidian/</button>
            <button
              className={"t-trans" + (tab === "transcript" ? " on" : "")}
              disabled={!hasTranscript}
              title={!hasTranscript ? t("art.ttTranscriptUnavailable") : undefined}
              onClick={() => setTab("transcript")}
            ><span className="dot" />{t("art.tabTranscript")}</button>
            <span className="vk-tabs-grow" />
            <span className="vk-readtime">{readTimeLabel(countWords(tabContent))}</span>
            <button className="vk-copy" title={t("art.copyTitle")}
                    onClick={() => onCopy?.(tabContent)}>{t("art.copy")}</button>
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
                              title={t("art.toClarifyTitle")}>
                        {t("art.toClarify", { n: clarCount })}
                      </button>
                    )}
                  </div>
                )}
                {tab === "transcript"
                  ? <pre className="vk-transcript-pre">{tabContent}</pre>
                  : <MarkdownDoc md={tabContent} />}
                {tab === "obsidian" && obsTags.length > 0 && (
                  <div className="vk-otags">
                    {obsTags.map((tag) => <span key={tag} className="vk-otag">#{tag}</span>)}
                  </div>
                )}
              </>
            ) : tab === "obsidian" ? (
              <div className="vk-empty">
                <div className="ico"><IcoVault /></div>
                <div className="tt">{t("art.ttObsNotCreated")}</div>
                <div className="dd">{t("art.obsEmptyDesc")}</div>
                <button type="button" onClick={handleExportObsidian} disabled={busy === "obsidian"}>
                  <VkIcon.share />{busy === "obsidian" ? t("art.exporting") : t("art.exportObsidian")}</button>
              </div>
            ) : (
              <p className="vk-doc-empty">{tab === "briefing" ? t("art.emptyBriefing") : t("art.emptyNoContent")}</p>
            )}
          </div>
        </div>

        <aside className="vk-art-side">
          <div className="vk-card">
            <button className="vk-btn-g vk-rail-cta vk-cta-pop"
                    title={t("art.ctaTitle")}
                    onClick={() => onCopy?.(briefing)}><VkIcon.arrow />{t("art.ctaCopy")}</button>

            <div className="vk-rail-sep" />
            <div className="vk-rail-lbl">{t("art.filesGenerated")}</div>

            <div className={"vk-fileitem" + (openInfo === "briefing" ? " open" : "")}>
              <div className="vk-file">
                <span className="ico md"><IcoFile /></span>
                <div className="info"><div className="nm">briefing.md</div><div className="ds">{t("art.dsForAI")}</div></div>
                <div className="acts">
                  <button type="button" className="vk-info-btn" aria-label={t("art.whatBriefing")}
                          onClick={() => toggleInfo("briefing")}><IcoInfo /></button>
                  <button type="button" className="vk-mini"
                          onClick={() => void handleDownload("briefing.md", briefing)}>{t("art.download")}</button>
                </div>
              </div>
              <div className="vk-file-exp">{t("art.expBriefing")}</div>
            </div>

            <div className={"vk-fileitem" + (openInfo === "recap" ? " open" : "")}>
              <div className="vk-file">
                <span className="ico rc"><IcoRecap /></span>
                <div className="info"><div className="nm">recap.md</div><div className="ds">{t("art.dsReadable")}</div></div>
                <div className="acts">
                  <button type="button" className="vk-info-btn" aria-label={t("art.whatRecap")}
                          onClick={() => toggleInfo("recap")}><IcoInfo /></button>
                  <button type="button" className="vk-mini" aria-label={t("art.pdfAria")}
                          title={t("art.pdfTitle")}
                          disabled={busy === "pdf"} onClick={handleExportPdf}>{busy === "pdf" ? "…" : "PDF"}</button>
                  {hasRecap && (
                    <button type="button" className="vk-mini"
                            onClick={() => void handleDownload("recap.md", recap)}>{t("art.download")}</button>
                  )}
                </div>
              </div>
              <div className="vk-file-exp">{t("art.expRecap")}</div>
            </div>

            <div className={"vk-fileitem" + (openInfo === "vault" ? " open" : "")}>
              <div className="vk-file">
                <span className="ico vault"><IcoVault /></span>
                <div className="info"><div className="nm">vault</div><div className="ds">{t("art.dsObsNote")}</div></div>
                <div className="acts">
                  <button type="button" className="vk-info-btn" aria-label={t("art.whatVault")}
                          onClick={() => toggleInfo("vault")}><IcoInfo /></button>
                  <button type="button" className="vk-mini" aria-label={t("art.exportObsidian")}
                          title={t("art.vaultTitle")}
                          disabled={busy === "obsidian"} onClick={handleExportObsidian}>{busy === "obsidian" ? "…" : t("art.exportLower")}</button>
                  {hasObsidian && (
                    <button type="button" className="vk-mini"
                            onClick={() => void handleDownload("nota.md", obsidian)}>{t("art.download")}</button>
                  )}
                </div>
              </div>
              <div className="vk-file-exp">{t("art.expVault")}</div>
            </div>

            <div className="vk-rail-sep" />
            {onReexport && (
              <button type="button" className="vk-openfolder" disabled={busy === "reexport"}
                      title={t("art.reexportTitle")}
                      onClick={handleReexport}>
                <VkIcon.arrow />{busy === "reexport" ? t("art.reexporting") : t("art.reexport")}</button>
            )}
            <button type="button" className="vk-openfolder"
                    onClick={() => a?.briefingPath && onOpenFolder?.(a.briefingPath)}>
              <VkIcon.folder />{t("art.openFolder")}</button>
          </div>

          <div className="vk-card">
            <div className="vk-rail-lbl">{t("art.details")}</div>
            <div className="vk-det-row">
              <span className="di"><IcoClock /></span>
              <span className="dl">{t("art.detDuration")}</span><span className="dv">{a ? fmtDur(a.durationS) : "—"}</span>
            </div>
            <div className="vk-det-row">
              <span className="di"><IcoBars /></span>
              <span className="dl">{t("art.detTranscription")}</span><span className="dv">{a?.model || "—"}</span>
            </div>
            <div className="vk-det-row">
              <span className="di"><VkIcon.globe /></span>
              <span className="dl">{t("art.detLanguage")}</span><span className="dv">{a?.language || "—"}</span>
            </div>
            <div className="vk-det-row">
              <span className="di priv"><VkIcon.lock /></span>
              <span className="dl">{t("art.detPrivacy")}</span><span className="dv">{t("art.detPrivacyVal")}</span>
            </div>
          </div>
        </aside>
      </div>
    </>
  );
}

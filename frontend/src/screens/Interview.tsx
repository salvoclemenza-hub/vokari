import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { VkIcon } from "../icons";
import type { Question } from "../bridge";

type View = "list" | "focus";

export function ScreenInterview({
  questions = [], onGenerate, onCancel,
}: {
  questions?: Question[];
  onGenerate?: (answers: Record<string, string>, skipped: string[]) => void;
  onCancel?: () => void;
}) {
  const { t } = useTranslation();
  const [answers, setAnswers] = useState<Record<string, string>>({});
  // Stato di skip esplicito (solo visivo): "Salta" su una domanda la marca saltata.
  // Il contratto verso generate resta "risposta presente → risposta, altrimenti saltata":
  // sia le saltate sia le intatte arrivano in skipped[] (→ marcatori [DA CHIARIRE]).
  const [skipped, setSkipped] = useState<Set<string>>(new Set());
  const [view, setView] = useState<View>("list");
  const [cur, setCur] = useState(0);

  // Clamp dell'indice focus se cambia il numero di domande.
  useEffect(() => {
    if (cur > questions.length - 1) setCur(Math.max(0, questions.length - 1));
  }, [questions.length, cur]);

  function answerChip(id: string, val: string) {
    setAnswers((a) => ({ ...a, [id]: val }));
    setSkipped((sk) => { if (!sk.has(id)) return sk; const n = new Set(sk); n.delete(id); return n; });
  }
  function answerText(id: string, val: string) {
    setAnswers((a) => ({ ...a, [id]: val }));
    if (val.trim()) setSkipped((sk) => { if (!sk.has(id)) return sk; const n = new Set(sk); n.delete(id); return n; });
  }
  function toggleSkip(id: string) {
    setSkipped((sk) => {
      const n = new Set(sk);
      if (n.has(id)) { n.delete(id); return n; }
      n.add(id); return n;
    });
    setAnswers((a) => ({ ...a, [id]: "" }));   // saltare azzera l'eventuale risposta
  }

  const isAnswered = (q: Question) => (answers[q.id] || "").trim().length > 0;
  const isSkipped = (q: Question) => skipped.has(q.id) && !isAnswered(q);

  const answeredCount = questions.filter(isAnswered).length;
  const skippedCount = questions.filter(isSkipped).length;
  const doneCount = answeredCount + skippedCount;

  // Scorciatoie da tastiera attive solo in modalità "Una alla volta".
  useEffect(() => {
    if (view !== "focus") return;
    const onKey = (e: KeyboardEvent) => {
      const el = document.activeElement as HTMLElement | null;
      const typing = el?.tagName === "INPUT" || el?.tagName === "TEXTAREA";
      if (e.key === "Escape") { el?.blur(); return; }
      const q = questions[cur];
      if (!q) return;
      if (e.key >= "1" && e.key <= "9" && !typing) {
        const s = q.suggestions[+e.key - 1];
        if (s) { answerChip(q.id, s); e.preventDefault(); }
      } else if ((e.key === "s" || e.key === "S") && !typing) {
        toggleSkip(q.id); e.preventDefault();
      } else if (e.key === "Enter" && !typing) {
        setCur((c) => Math.min(c + 1, questions.length - 1)); e.preventDefault();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [view, cur, questions]);

  function buildAndGenerate(forceSkipAll: boolean) {
    const out: Record<string, string> = {};
    const skip: string[] = [];
    for (const q of questions) {
      const v = (forceSkipAll ? "" : answers[q.id] || "").trim();
      if (v) out[q.id] = v;
      else skip.push(q.id);
    }
    onGenerate?.(out, skip);
  }

  const last = cur === questions.length - 1;

  return (
    <div className="vk-iv">
      <div className="vk-iv-inner">
        <div className="vk-iv-head">
          <div className="vk-kick">{t("interview.kicker")}</div>
          <h1>{t("interview.title")}</h1>
          <p>{t("interview.leadPre")}<b>{t("interview.leadBold")}</b>{t("interview.leadPost")}</p>
        </div>

        <div className="vk-iv-prog">
          <div className="dots">
            {questions.map((q) => (
              <i key={q.id} className={isAnswered(q) ? "done" : isSkipped(q) ? "skip" : ""} />
            ))}
          </div>
          <span className="lab">
            {t("interview.progress", { done: doneCount, total: questions.length })}
            {skippedCount ? t("interview.progSkipped", { count: skippedCount }) : t("interview.progAnswerAny")}
          </span>
          <div className="vk-iv-toggle" role="group" aria-label={t("interview.viewAria")}>
            <button className={view === "list" ? "on" : ""} onClick={() => setView("list")}>{t("interview.viewList")}</button>
            <button className={view === "focus" ? "on" : ""} onClick={() => { setCur(0); setView("focus"); }}>
              {t("interview.viewOneByOne")}
            </button>
          </div>
        </div>

        <div className={"vk-iv-scroll" + (view === "focus" ? " focus" : "")}>
        {questions.map((q, idx) => {
          const answered = isAnswered(q);
          const skip = isSkipped(q);
          return (
            <div className={"vk-q" + (answered ? " answered" : "") + (skip ? " skipped" : "") + (view === "focus" && idx === cur ? " current" : "")}
                 key={q.id}>
              <div className="vk-q-top">
                <span className="vk-q-num">
                  {answered ? <VkIcon.check /> : <span className="n">{String(idx + 1).padStart(2, "0")}</span>}
                </span>
                <span className="vk-q-title">{q.text}</span>
                {q.fromAudio && (
                  <span className="vk-q-src" title={t("interview.fromAudioTitle")}>{t("interview.fromAudio")}</span>
                )}
              </div>
              {q.why && <div className="vk-q-why"><b>{t("interview.why")}</b> {q.why}</div>}
              {q.suggestions.length > 0 && (
                <div className="vk-chips-lbl">{t("interview.quickSuggestions")}</div>
              )}
              <div className="vk-chips">
                {q.suggestions.map((c) => (
                  <button key={c} className={"vk-chip" + (answers[q.id] === c ? " on" : "")}
                          onClick={() => answerChip(q.id, c)}>{c}</button>
                ))}
                <button className={"vk-chip skip" + (skip ? " on" : "")} onClick={() => toggleSkip(q.id)}>{t("interview.skip")}</button>
              </div>
              <input className="vk-qi one" type="text"
                     value={answers[q.id] && !q.suggestions.includes(answers[q.id]) ? answers[q.id] : ""}
                     onChange={(e) => answerText(q.id, e.target.value)}
                     placeholder={t("interview.answerPlaceholder")} />
            </div>
          );
        })}
        </div>

        {view === "focus" && questions.length > 0 && (
          <div className="vk-iv-focusnav">
            <button className="vk-btn-gh" onClick={() => setCur((c) => Math.max(0, c - 1))}
                    style={{ visibility: cur > 0 ? "visible" : "hidden" }}>{t("interview.navBack")}</button>
            <span className="pos">{cur + 1} / {questions.length}</span>
            <div className="grow" />
            <span className="vk-iv-kbd"><kbd>1</kbd>–<kbd>9</kbd> {t("interview.kbdChoose")} · <kbd>{t("interview.kbdEnter")}</kbd> {t("interview.kbdNext")} · <kbd>S</kbd> {t("interview.kbdSkip")}</span>
            <button className="vk-btn-g" onClick={() => setCur((c) => Math.min(c + 1, questions.length - 1))}
                    disabled={last}>{last ? t("interview.navDone") : t("interview.navNext")}</button>
          </div>
        )}

        <div className="vk-iv-act">
          <span className="vk-iv-note"><span className="dot"></span>{t("interview.note")}</span>
          <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
            {onCancel && (
              <button className="vk-exit" onClick={onCancel}>{t("interview.cancel")}</button>
            )}
            <button className="vk-btn-gh" onClick={() => buildAndGenerate(true)}>{t("interview.skipAllGenerate")}</button>
            <button className="vk-btn-g" onClick={() => buildAndGenerate(false)}>
              {t("interview.generate")}<span className="ct"> · {answeredCount} {answeredCount === 1 ? t("interview.answerSingular") : t("interview.answerPlural")}</span><VkIcon.arrow />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

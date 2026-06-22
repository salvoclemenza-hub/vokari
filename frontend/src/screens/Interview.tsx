import { useEffect, useState } from "react";
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
          <div className="vk-kick">~/rifinitura · opzionale</div>
          <h1>Un paio di domande per un briefing migliore.</h1>
          <p>Usa i suggerimenti rapidi <b>oppure rispondi a parole</b> — e puoi sempre saltare.</p>
        </div>

        <div className="vk-iv-prog">
          <div className="dots">
            {questions.map((q) => (
              <i key={q.id} className={isAnswered(q) ? "done" : isSkipped(q) ? "skip" : ""} />
            ))}
          </div>
          <span className="lab">
            {doneCount} di {questions.length}
            {skippedCount ? ` · ${skippedCount} saltate` : " · rispondi quante vuoi"}
          </span>
          <div className="vk-iv-toggle" role="group" aria-label="Vista domande">
            <button className={view === "list" ? "on" : ""} onClick={() => setView("list")}>Lista</button>
            <button className={view === "focus" ? "on" : ""} onClick={() => { setCur(0); setView("focus"); }}>
              Una alla volta
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
                  <span className="vk-q-src" title="domanda nata da un dettaglio della registrazione">dal tuo audio</span>
                )}
              </div>
              {q.why && <div className="vk-q-why"><b>Perché:</b> {q.why}</div>}
              {q.suggestions.length > 0 && (
                <div className="vk-chips-lbl">Suggerimenti rapidi</div>
              )}
              <div className="vk-chips">
                {q.suggestions.map((c) => (
                  <button key={c} className={"vk-chip" + (answers[q.id] === c ? " on" : "")}
                          onClick={() => answerChip(q.id, c)}>{c}</button>
                ))}
                <button className={"vk-chip skip" + (skip ? " on" : "")} onClick={() => toggleSkip(q.id)}>Salta</button>
              </div>
              <input className="vk-qi one" type="text"
                     value={answers[q.id] && !q.suggestions.includes(answers[q.id]) ? answers[q.id] : ""}
                     onChange={(e) => answerText(q.id, e.target.value)}
                     placeholder="Oppure rispondi a parole…" />
            </div>
          );
        })}
        </div>

        {view === "focus" && questions.length > 0 && (
          <div className="vk-iv-focusnav">
            <button className="vk-btn-gh" onClick={() => setCur((c) => Math.max(0, c - 1))}
                    style={{ visibility: cur > 0 ? "visible" : "hidden" }}>← Indietro</button>
            <span className="pos">{cur + 1} / {questions.length}</span>
            <div className="grow" />
            <span className="vk-iv-kbd"><kbd>1</kbd>–<kbd>9</kbd> scegli · <kbd>Invio</kbd> avanti · <kbd>S</kbd> salta</span>
            <button className="vk-btn-g" onClick={() => setCur((c) => Math.min(c + 1, questions.length - 1))}
                    disabled={last}>{last ? "Fine" : "Avanti →"}</button>
          </div>
        )}

        <div className="vk-iv-act">
          <span className="vk-iv-note"><span className="dot"></span>Mai bloccante — puoi sempre rigenerare dopo.</span>
          <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
            {onCancel && (
              <button className="vk-exit" onClick={onCancel}>Annulla</button>
            )}
            <button className="vk-btn-gh" onClick={() => buildAndGenerate(true)}>Salta tutto e genera</button>
            <button className="vk-btn-g" onClick={() => buildAndGenerate(false)}>
              Genera briefing<span className="ct"> · {answeredCount} {answeredCount === 1 ? "risposta" : "risposte"}</span><VkIcon.arrow />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

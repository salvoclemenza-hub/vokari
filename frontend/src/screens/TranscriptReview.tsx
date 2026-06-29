import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { VkIcon } from "../icons";

/** N1 — Revisione trascrizione (gate `awaiting_edit`): l'utente corregge il testo riconosciuto
 *  PRIMA dell'analisi AI (omofoni, nomi propri, interruzioni degradano il briefing). Solo
 *  contenuto del <main>: la cornice (sidebar/titlebar) la mette App.tsx. */
export function ScreenTranscriptReview({
  transcript = "",
  onProceed,
  onCancel,
}: {
  transcript?: string;
  onProceed?: (text: string) => void;
  onCancel?: () => void;
}) {
  const { t } = useTranslation();
  const [text, setText] = useState(transcript);
  const taRef = useRef<HTMLTextAreaElement>(null);

  // In App il transcript arriva via getJob ASINCRONO → la schermata può montare con "" e
  // ricevere il testo reale subito dopo. Senza questo sync `useState(transcript)` resterebbe
  // statico e la textarea mostrerebbe la box VUOTA in produzione (ADR-010: il mock dei test la
  // nascondeva). Sincronizziamo SOLO quando cambia il transcript di backend (`transcript` nel dep
  // array): le digitazioni dell'utente non lo toccano → nessun clobber dell'edit in corso.
  useEffect(() => {
    setText(transcript);
  }, [transcript]);

  // Auto-focus al mount: la textarea è pronta alla correzione immediata.
  useEffect(() => {
    taRef.current?.focus();
  }, []);

  // ⌘ su macOS, Ctrl altrove (VOKARI è desktop Windows). Solo etichetta: l'handler accetta
  // entrambi i modificatori così funziona su ogni piattaforma.
  const modKey = /Mac|iPhone|iPad/i.test(navigator.platform) ? "⌘+Invio" : "Ctrl+Invio";

  const words = text.trim() ? text.trim().split(/\s+/).length : 0;
  const wordLabel = words === 1 ? t("transcriptReview.wordsOne", { count: words }) : t("transcriptReview.wordsMany", { count: words });

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      onProceed?.(text);
    }
  }

  return (
    <div className="vk-tr">
      <div className="vk-tr-inner">
        <div className="vk-tr-head">
          <div className="vk-kick">{t("transcriptReview.kicker")}</div>
          <h1>{t("transcriptReview.title")}</h1>
          <p>{t("transcriptReview.lead")}</p>
        </div>

        <textarea
          ref={taRef}
          className="vk-tr-ta"
          aria-label={t("transcriptReview.ariaLabel")}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          spellCheck
        />

        <div className="vk-tr-act">
          <span className="vk-tr-count">{wordLabel}</span>
          <div className="vk-tr-note"><span className="dot"></span>{t("transcriptReview.note")}</div>
          <div className="grow" />
          {onCancel && (
            <button className="vk-exit" onClick={onCancel}>{t("transcriptReview.cancel")}</button>
          )}
          <button className="vk-btn-g" onClick={() => onProceed?.(text)}>
            {t("transcriptReview.proceed")}
            <span className="ct"> · {t("transcriptReview.kbdHint", { key: modKey })}</span>
            <VkIcon.arrow />
          </button>
        </div>
      </div>
    </div>
  );
}

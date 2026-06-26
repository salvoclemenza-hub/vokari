import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "../toast";

export function ScreenError({ message, warnings = [], onBack, onRetry, onOpenSettings }:
  {
    message: string;
    warnings?: string[];
    onBack?: () => void;
    onRetry?: () => void;
    onOpenSettings?: () => void;
  }) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const detail = message || t("errorScreen.unknown");

  function copyDetail() {
    if (!navigator.clipboard) { toast(t("errorScreen.copyUnavailable"), "error"); return; }
    navigator.clipboard.writeText(detail).then(
      () => { setCopied(true); window.setTimeout(() => setCopied(false), 1400); },
      () => toast(t("errorScreen.copyFailed"), "error"),
    );
  }

  return (
    <div className="vk-proc">
      <section className="vk-err">
        <div className="vk-err-ico">
          <svg viewBox="0 0 24 24"><path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z" /></svg>
        </div>
        <h1>{t("errorScreen.heading")}</h1>
        <p className="lead">{t("errorScreen.lead")}</p>

        {/* Dettaglio tecnico su pannello "carta" (non console nera): è il `message` reale. */}
        <div className="vk-err-detail">
          <div className="row">
            <span className="ic">
              <svg viewBox="0 0 24 24"><path d="M11 7h2v6h-2zm0 8h2v2h-2zm1-13C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z" /></svg>
            </span>
            <code>{detail}</code>
          </div>
          <button className={"copy" + (copied ? " done" : "")} onClick={copyDetail}>
            {copied ? t("errorScreen.copied") : t("errorScreen.copy")}
          </button>
        </div>

        {/* A2: diagnostica di degrado (es. "both" caduta sul solo microfono). Visibile QUI o
            l'utente non saprebbe perché la registrazione è uscita incompleta. role="note" per a11y. */}
        {warnings.length > 0 && (
          <div className="vk-err-warn" role="note">
            <svg viewBox="0 0 24 24"><path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z" /></svg>
            <span>⚠ {warnings.join(" · ")}</span>
          </div>
        )}

        <div className="vk-err-foot">
          <div className="vk-reassure">
            <svg viewBox="0 0 24 24"><path d="M12 1 3 5v6c0 5.5 3.8 10.7 9 12 5.2-1.3 9-6.5 9-12V5l-9-4z" /></svg>
            {t("errorScreen.reassure")}
          </div>
          <div className="vk-err-actions">
            {onOpenSettings && (
              <button className="vk-link" onClick={onOpenSettings}>{t("errorScreen.openSettings")}</button>
            )}
            <button className="vk-ghost" onClick={onBack}>{t("errorScreen.back")}</button>
            {onRetry && (
              <button className="vk-primary" onClick={onRetry}>
                <svg viewBox="0 0 24 24"><path d="M12 5V1L7 6l5 5V7a6 6 0 1 1-6 6H4a8 8 0 1 0 8-8z" /></svg>
                {t("errorScreen.retry")}
              </button>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}

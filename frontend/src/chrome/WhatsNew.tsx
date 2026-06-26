import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import type { ChangelogEntry } from "../bridge";

// Etichetta leggibile per il tipo di voce (allineata a app/assets/changelog.json) → chiave i18n.
const KIND_KEY: Record<string, string> = {
  feature: "whatsNew.kindFeature",
  fix: "whatsNew.kindFix",
  improvement: "whatsNew.kindImprovement",
};

// Data ISO (YYYY-MM-DD) → formato amichevole "25 giu 2026" (coerente col tono dell'app;
// gli utenti non tecnici non devono leggere date ISO). Input non valido → invariato.
const MONTHS_IT = ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"];
const MONTHS_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
function fmtDate(iso: string, months: string[]): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!m) return iso;
  const [, y, mo, d] = m;
  return `${Number(d)} ${months[Number(mo) - 1] ?? mo} ${y}`;
}

const ICON_SPARK = (
  <svg viewBox="0 0 24 24">
    <path d="M12 2l1.9 5.6L19.5 9l-4.4 3.2 1.6 5.8L12 14.8 7.3 18l1.6-5.8L4.5 9l5.6-1.4L12 2z" />
  </svg>
);

/** Popup "Novità della versione" (Tema 2). Overlay app-level (come ConfirmHost/Toaster):
 *  App lo monta dopo un aggiornamento, quando ci sono voci più recenti dell'ultima vista.
 *  Props pure (i dati arrivano dal bridge in App) → testabile senza pywebview. */
export function WhatsNew({
  entries,
  currentVersion,
  onClose,
}: {
  entries: ChangelogEntry[];
  currentVersion: string;
  onClose: () => void;
}) {
  const { t, i18n } = useTranslation();
  const months = i18n.language === "en" ? MONTHS_EN : MONTHS_IT;
  // Esc chiude (coerente con gli altri modali; il modale è esclusivo a schermo).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="vk-modal show"
      role="dialog"
      aria-modal="true"
      aria-label={t("whatsNew.ariaLabel")}
      onClick={onClose}
    >
      <div className="card vk-whatsnew" onClick={(e) => e.stopPropagation()}>
        <div className="mi neutral">{ICON_SPARK}</div>
        <h3>{t("whatsNew.title")}</h3>
        <p>
          {t("whatsNew.updatedPre")}<strong>{currentVersion}</strong>{t("whatsNew.updatedPost")}
        </p>
        <div className="vk-wn-list">
          {entries.map((e) => (
            <section className="vk-wn-ver" key={e.version}>
              <header>
                <span className="v">v{e.version}</span>
                <span className="t">{e.title}</span>
                {e.date && <span className="d">{fmtDate(e.date, months)}</span>}
              </header>
              <ul>
                {e.highlights.map((h, i) => (
                  <li className={"vk-wn-hl " + h.kind} key={i}>
                    <span className="k">{t(KIND_KEY[h.kind] ?? "whatsNew.kindDefault")}</span>
                    <span className="x">{h.text}</span>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
        <div className="vk-mfoot">
          <span className="vk-mkbd">
            <kbd>{t("whatsNew.kbdEsc")}</kbd> {t("whatsNew.close")}
          </span>
          <div className="vk-actions">
            <button className="vk-primary" autoFocus onClick={onClose}>
              {t("whatsNew.gotIt")}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

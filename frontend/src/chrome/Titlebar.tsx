import { Fragment } from "react";
import { useTranslation } from "react-i18next";
import { VkIcon } from "../icons";
import type { AppInfo } from "../bridge";
import type { NavItem } from "./Sidebar";

// Passi del flusso lineare (id schermata): il breadcrumb di wayfinding traduce le etichette
// via chiave `titlebar.flow.<screen>`.
const FLOW_SCREENS = ["home", "live", "processing", "transcript_review", "interview", "artifacts"] as const;

// Schermate con un titolo proprio (fuori dal flusso): etichetta via `titlebar.titles.<screen>`.
const TITLE_SCREENS = new Set([
  "home", "sessions", "models", "settings", "artifacts", "error", "live", "processing",
  "transcript_review", "interview",
]);

export function Titlebar({
  appInfo,
  screen = "home",
  onNavigate,
  bare = false,
}: {
  appInfo: AppInfo;
  screen?: string;
  onNavigate?: (n: NavItem) => void;
  bare?: boolean;
}) {
  const { t } = useTranslation();
  const stars =
    appInfo.githubStars >= 1000
      ? (appInfo.githubStars / 1000).toFixed(1) + "k"
      : String(appInfo.githubStars);
  // Breadcrumb solo nelle schermate transitorie del flusso: su artefatti (raggiungibile
  // anche aprendo una sessione dalla libreria) un breadcrumb implicherebbe un flusso che
  // non è sempre vero → lì titolo semplice.
  const inFlow =
    screen === "live" || screen === "processing" || screen === "transcript_review" || screen === "interview";
  const activeIdx = FLOW_SCREENS.indexOf(screen as (typeof FLOW_SCREENS)[number]);

  return (
    <div className="vk-tbar">
      {inFlow ? (
        <div className="vk-tbar-crumbs" aria-label={t("titlebar.flowProgress")}>
          {FLOW_SCREENS.map((s, i) => (
            <Fragment key={s}>
              {i > 0 && <span className="sep">›</span>}
              <span className={"c" + (i === activeIdx ? " cur" : i < activeIdx ? " done" : "")}>
                {t("titlebar.flow." + s)}
              </span>
            </Fragment>
          ))}
        </div>
      ) : (
        <div className="vk-tbar-title">{TITLE_SCREENS.has(screen) ? t("titlebar.titles." + screen) : t("titlebar.fallback")}</div>
      )}
      <div className="vk-tbar-r">
        {appInfo.githubStars > 0 && (
          <div className="vk-star">
            <VkIcon.star />
            {stars}
          </div>
        )}
        <div className="vk-ver">
          v{appInfo.version}
        </div>
        {!bare && (
          <button
            className="vk-icbtn"
            aria-label={t("titlebar.settings")}
            title={t("titlebar.settings")}
            onClick={() => onNavigate?.("Impostazioni")}
          >
            <VkIcon.sliders />
          </button>
        )}
      </div>
    </div>
  );
}

import { useTranslation } from "react-i18next";
import { VkIcon } from "../icons";
import { bridge, type AppInfo, type ResourceUsage } from "../bridge";

const REPO_URL = "https://github.com/salvoclemenza-hub/vokari";

function fmtRam(mb: number): string {
  return mb >= 1024 ? (mb / 1024).toFixed(1) + " GB" : Math.round(mb) + " MB";
}

export function StatusBar({ appInfo, resources }: { appInfo: AppInfo; resources?: ResourceUsage | null }) {
  const { t } = useTranslation();
  const stars =
    appInfo.githubStars >= 1000
      ? (appInfo.githubStars / 1000).toFixed(1) + "k"
      : String(appInfo.githubStars);
  return (
    <div className="vk-status">
      {/* Sinistra: segnale di fiducia (allineato ai mock). */}
      <span className="priv">
        <span className="dot"></span>{t("status.private")}
      </span>
      {/* Destra: credito + consumi reali + stelle. */}
      <div className="vk-status-r">
        <span className="os">
          {t("status.developedBy")} ·{" "}
          <button className="repo" onClick={() => void bridge.openUrl(REPO_URL)}>{t("status.repository")}</button>
        </span>
        {resources && (
          <>
            <span className="sep">·</span>
            <span className="res" title={t("status.resourcesTitle")}>
              CPU {Math.round(resources.cpu)}%
              {resources.tempC !== undefined && ` · ${Math.round(resources.tempC)}°C`}
              {" · "}RAM {fmtRam(resources.ramMb)}
            </span>
          </>
        )}
        {appInfo.githubStars > 0 && (
          <>
            <span className="sep">·</span>
            <span className="it">
              <VkIcon.star />
              {t("status.onGithub", { stars })}
            </span>
          </>
        )}
      </div>
    </div>
  );
}

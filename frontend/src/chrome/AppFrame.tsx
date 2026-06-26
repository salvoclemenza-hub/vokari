import type { ReactNode } from "react";
import type { AppInfo, ResourceUsage } from "../bridge";
import { Titlebar } from "./Titlebar";
import { Sidebar, type NavItem } from "./Sidebar";
import { StatusBar } from "./StatusBar";

export function AppFrame({
  active,
  screen,
  onNavigate,
  onOpenSession,
  appInfo,
  resources,
  bare = false,
  children,
}: {
  active: NavItem;
  screen?: string;
  onNavigate: (n: NavItem) => void;
  onOpenSession?: (id: string) => void;
  appInfo: AppInfo;
  resources?: ResourceUsage | null;
  // `bare`: chrome minimale (solo titlebar + main, niente sidebar/status bar). Usato
  // dall'onboarding per un'esperienza immersiva e focalizzata al primo avvio.
  bare?: boolean;
  children: ReactNode;
}) {
  return (
    <div className="vk-screen-app">
      <Titlebar appInfo={appInfo} screen={screen} onNavigate={onNavigate} bare={bare} />
      <div className="vk-shell">
        {!bare && <Sidebar active={active} onNavigate={onNavigate} onOpenSession={onOpenSession} />}
        <main className="vk-main">{children}</main>
      </div>
      {!bare && <StatusBar appInfo={appInfo} resources={resources} />}
    </div>
  );
}

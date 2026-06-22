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
  children,
}: {
  active: NavItem;
  screen?: string;
  onNavigate: (n: NavItem) => void;
  onOpenSession?: (id: string) => void;
  appInfo: AppInfo;
  resources?: ResourceUsage | null;
  children: ReactNode;
}) {
  return (
    <div className="vk-screen-app">
      <Titlebar appInfo={appInfo} screen={screen} onNavigate={onNavigate} />
      <div className="vk-shell">
        <Sidebar active={active} onNavigate={onNavigate} onOpenSession={onOpenSession} />
        <main className="vk-main">{children}</main>
      </div>
      <StatusBar appInfo={appInfo} resources={resources} />
    </div>
  );
}

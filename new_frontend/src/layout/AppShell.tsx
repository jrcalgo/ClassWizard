import { Outlet } from "react-router-dom";

import { Canvas } from "@/features/canvas/Canvas";
import { SearchMenu } from "@/features/search/SearchMenu";
import { useAuditSession } from "@/features/session/useAuditSession";

import { EmailVerifyBanner } from "./EmailVerifyBanner";
import { TopBar } from "./TopBar";

/** TopBar over [SearchMenu | Canvas]. Auth and account routes render on top via <Outlet/>. */
export function AppShell() {
  useAuditSession();
  return (
    <div className="flex h-full flex-col">
      <TopBar />
      <EmailVerifyBanner />
      <div className="relative flex min-h-0 flex-1">
        <SearchMenu />
        <Canvas />
      </div>
      <Outlet />
    </div>
  );
}

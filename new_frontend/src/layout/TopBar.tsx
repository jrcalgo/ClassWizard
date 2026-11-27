import { useQueryClient } from "@tanstack/react-query";
import { Activity, History, LogOut, Menu, UserRound } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { logOut } from "@/api/endpoints";
import { markSignedOut, useMe } from "@/api/queries";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { usePlanStore } from "@/state/planStore";
import { ThemeToggle } from "@/theme/ThemeToggle";

function initials(name: string | null, email: string): string {
  const source = (name || email).trim();
  const parts = source.split(/[\s@._-]+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase() || "?";
}

function AccountMenu() {
  const { data: user, isLoading } = useMe();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  if (isLoading) return <div className="h-9 w-[84px]" aria-hidden />;
  if (!user) {
    return (
      <Button onClick={() => navigate("/login")} className="px-4">
        Sign in
      </Button>
    );
  }
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label="Account menu"
          className="flex h-9 w-9 items-center justify-center rounded-full bg-green text-xs font-bold text-on-green ring-offset-2 ring-offset-card transition hover:ring-2 hover:ring-green/50"
        >
          {initials(user.display_name, user.email)}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-60">
        <DropdownMenuLabel className="truncate text-text">
          {user.display_name && <span className="block truncate text-sm">{user.display_name}</span>}
          <span className="block truncate font-normal text-muted">{user.email}</span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link to="/account/history">
            <History /> Search history
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link to="/account/activity">
            <Activity /> Activity
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link to="/account">
            <UserRound /> Account
          </Link>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onSelect={async () => {
            try {
              await logOut();
            } catch {
              // The cookie is cleared server-side; a failure still leaves us signed out locally.
            }
            markSignedOut(queryClient);
            toast.success("Signed out.");
            navigate("/");
          }}
        >
          <LogOut /> Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function TopBar() {
  const menuOpen = usePlanStore((s) => s.menuOpen);
  const toggleMenu = usePlanStore((s) => s.toggleMenu);
  return (
    <header className="relative z-40 flex h-14 shrink-0 items-center gap-3 border-b bg-card px-3 sm:px-4">
      <Button
        variant="ghost"
        size="icon"
        onClick={toggleMenu}
        aria-label={menuOpen ? "Hide search preferences" : "Show search preferences"}
        aria-expanded={menuOpen}
        aria-controls="search-menu"
      >
        <Menu className="!h-5 !w-5" />
      </Button>
      <Link to="/" className="flex min-w-0 items-center gap-2.5">
        <img src="/classwizard-logo.png" alt="" className="h-9 w-9 shrink-0" />
        <span className="min-w-0">
          <span className="block text-lg font-bold leading-5 tracking-tight">ClassWizard</span>
          <span className="hidden truncate text-xs text-muted sm:block">Career-aware course planning</span>
        </span>
      </Link>
      <div className="ml-auto flex items-center gap-1.5">
        <ThemeToggle />
        <AccountMenu />
      </div>
    </header>
  );
}

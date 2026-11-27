import { useEffect } from "react";
import { create } from "zustand";

import { safeStorageGet, safeStorageSet } from "@/lib/utils";

export type ThemePreference = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

export const THEME_STORAGE_KEY = "cw-theme";
const QUERY = "(prefers-color-scheme: dark)";

export function readPreference(): ThemePreference {
  const stored = safeStorageGet(THEME_STORAGE_KEY);
  return stored === "light" || stored === "dark" || stored === "system" ? stored : "system";
}

export function systemPrefersDark(): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function"
    ? window.matchMedia(QUERY).matches
    : false;
}

export function resolveTheme(preference: ThemePreference, prefersDark: boolean): ResolvedTheme {
  if (preference === "system") return prefersDark ? "dark" : "light";
  return preference;
}

export function applyTheme(theme: ResolvedTheme): void {
  const root = document.documentElement;
  root.classList.toggle("dark", theme === "dark");
  root.style.colorScheme = theme;
}

interface ThemeState {
  preference: ThemePreference;
  resolved: ResolvedTheme;
  setPreference: (preference: ThemePreference) => void;
  syncSystem: () => void;
}

export const useThemeStore = create<ThemeState>((set, get) => {
  const preference = readPreference();
  return {
    preference,
    resolved: resolveTheme(preference, systemPrefersDark()),
    setPreference: (next) => {
      safeStorageSet(THEME_STORAGE_KEY, next);
      const resolved = resolveTheme(next, systemPrefersDark());
      applyTheme(resolved);
      set({ preference: next, resolved });
    },
    syncSystem: () => {
      const resolved = resolveTheme(get().preference, systemPrefersDark());
      applyTheme(resolved);
      set({ resolved });
    },
  };
});

/** Mount once: keeps "System default" in step with the OS appearance. */
export function useSystemThemeListener(): void {
  const syncSystem = useThemeStore((s) => s.syncSystem);
  useEffect(() => {
    syncSystem();
    if (typeof window.matchMedia !== "function") return;
    const media = window.matchMedia(QUERY);
    media.addEventListener("change", syncSystem);
    return () => media.removeEventListener("change", syncSystem);
  }, [syncSystem]);
}

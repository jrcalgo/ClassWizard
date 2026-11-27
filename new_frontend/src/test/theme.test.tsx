import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { THEME_STORAGE_KEY, readPreference, resolveTheme, useThemeStore } from "@/theme/theme";
import { ThemeToggle } from "@/theme/ThemeToggle";

function mockSystemDark(dark: boolean) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: dark && query.includes("dark"),
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  })) as unknown as typeof window.matchMedia;
}

describe("theme preference", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.classList.remove("dark");
  });

  it("resolves light, dark and system", () => {
    expect(resolveTheme("light", true)).toBe("light");
    expect(resolveTheme("dark", false)).toBe("dark");
    expect(resolveTheme("system", true)).toBe("dark");
    expect(resolveTheme("system", false)).toBe("light");
  });

  it("defaults to system and ignores junk in storage", () => {
    expect(readPreference()).toBe("system");
    localStorage.setItem(THEME_STORAGE_KEY, "purple");
    expect(readPreference()).toBe("system");
  });

  it("applies and saves the chosen preference", () => {
    mockSystemDark(true);
    useThemeStore.getState().setPreference("light");
    expect(document.documentElement.classList.contains("dark")).toBe(false);
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
    useThemeStore.getState().setPreference("system");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    mockSystemDark(false);
    useThemeStore.getState().syncSystem();
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });

  it("offers Light, Dark and System default in the dropdown", async () => {
    mockSystemDark(false);
    // Radix menus need pointer capture and ResizeObserver in jsdom.
    window.HTMLElement.prototype.hasPointerCapture = vi.fn();
    window.HTMLElement.prototype.scrollIntoView = vi.fn();
    globalThis.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    } as unknown as typeof ResizeObserver;
    const user = userEvent.setup();
    render(<ThemeToggle />);
    await user.click(screen.getByRole("button", { name: "Theme" }));
    for (const name of ["Light", "Dark", "System default"]) {
      expect(screen.getByRole("menuitemradio", { name })).toBeInTheDocument();
    }
    await user.click(screen.getByRole("menuitemradio", { name: "Dark" }));
    expect(useThemeStore.getState().preference).toBe("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });
});

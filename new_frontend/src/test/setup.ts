import "@testing-library/jest-dom/vitest";

// Node 25+ ships its own (file-backed, often undefined) localStorage global,
// which shadows jsdom's. Give tests a plain in-memory Storage instead.
class MemoryStorage implements Storage {
  private items = new Map<string, string>();
  get length() {
    return this.items.size;
  }
  clear() {
    this.items.clear();
  }
  getItem(key: string) {
    return this.items.has(key) ? (this.items.get(key) as string) : null;
  }
  key(index: number) {
    return Array.from(this.items.keys())[index] ?? null;
  }
  removeItem(key: string) {
    this.items.delete(key);
  }
  setItem(key: string, value: string) {
    this.items.set(key, String(value));
  }
}

for (const name of ["localStorage", "sessionStorage"] as const) {
  Object.defineProperty(globalThis, name, { value: new MemoryStorage(), configurable: true, writable: true });
  Object.defineProperty(window, name, { value: globalThis[name], configurable: true, writable: true });
}

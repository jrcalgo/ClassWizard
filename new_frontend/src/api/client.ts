/** Thin fetch wrapper. All paths go through /api (nginx or the Vite proxy strips it). */

export class ApiError extends Error {
  status: number;
  detail: string;
  body: Record<string, unknown>;

  constructor(status: number, detail: string, body: Record<string, unknown> = {}) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.body = body;
  }

  get timedOut(): boolean {
    return this.status === 0 && this.detail === "timed out";
  }
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  json?: unknown;
  form?: FormData;
  timeoutMs?: number;
  keepalive?: boolean;
  signal?: AbortSignal;
}

export const API_BASE = "/api";

function detailOf(body: Record<string, unknown>, fallback: string): string {
  const detail = body.detail;
  if (typeof detail === "string") return detail;
  // FastAPI validation errors: [{loc, msg, type}, ...]
  if (Array.isArray(detail) && detail.length && typeof detail[0]?.msg === "string") return detail[0].msg;
  return fallback;
}

export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = options.json || options.form ? "POST" : "GET", json, form, timeoutMs = 30_000, keepalive } = options;
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort("timeout"), timeoutMs);
  options.signal?.addEventListener("abort", () => controller.abort(options.signal?.reason));
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method,
      credentials: "same-origin",
      keepalive,
      signal: controller.signal,
      headers: json !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: json !== undefined ? JSON.stringify(json) : form,
    });
  } catch (error) {
    if (controller.signal.aborted && controller.signal.reason === "timeout") {
      throw new ApiError(0, "timed out");
    }
    if (controller.signal.aborted) throw error;
    throw new ApiError(0, "The server could not be reached.");
  } finally {
    window.clearTimeout(timer);
  }
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  let body: Record<string, unknown> = {};
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = { detail: text };
    }
  }
  if (!response.ok) {
    throw new ApiError(response.status, detailOf(body, response.statusText || "request failed"), body);
  }
  return body as T;
}

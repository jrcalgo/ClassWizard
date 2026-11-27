import { api } from "./client";
import type {
  ActivityEvent,
  AppConfig,
  AuditResponse,
  ChatMessage,
  ConceptMap,
  ExplainResponse,
  OccupationsResponse,
  PlanPrefs,
  RecommendResponse,
  RestoreResponse,
  SavedAudit,
  SavedSearch,
  User,
} from "./types";

export const RECOMMEND_LIMIT = 10;

// ---- planning (anonymous-friendly, keyed by the Redis session id)

export const getConfig = () => api<AppConfig>("/config");
export const getOccupations = () => api<OccupationsResponse>("/occupations", { timeoutMs: 5_000 });

export function uploadAudit(file: File, sessionId: string | null) {
  const form = new FormData();
  if (sessionId) form.append("session_id", sessionId);
  form.append("file", file, file.name);
  return api<AuditResponse>("/audit", { form, timeoutMs: 60_000 });
}

export const refreshAudit = (sessionId: string) => api<AuditResponse>(`/audit/${sessionId}`, { timeoutMs: 60_000 });

export function discardAudit(sessionId: string) {
  // keepalive lets the request outlive the page on pagehide.
  return api<void>(`/audit/${sessionId}`, { method: "DELETE", keepalive: true, timeoutMs: 5_000 });
}

export function postRecommend(sessionId: string, socCodes: string[], prefs: PlanPrefs, auditId: string | null) {
  return api<RecommendResponse>("/recommend", {
    json: { session_id: sessionId, soc_codes: socCodes, limit: RECOMMEND_LIMIT, audit_id: auditId, prefs },
    timeoutMs: 30_000,
  });
}

export function postExplain(sessionId: string, socCodes: string[], question: string, searchId: string | null) {
  return api<ExplainResponse>("/explain", {
    json: { session_id: sessionId, soc_codes: socCodes, question, search_id: searchId },
    timeoutMs: 240_000,
  });
}

export function postChat(
  sessionId: string,
  message: string,
  history: { role: string; content: string }[],
  prefs: PlanPrefs,
  searchId: string | null,
) {
  return api<{ reply: string }>("/chat", {
    json: { session_id: sessionId, message, history: history.slice(-8), prefs, search_id: searchId },
    timeoutMs: 60_000,
  });
}

export const getConceptMapCourses = () => api<{ courses: string[] }>("/concept-maps");
export const getConceptMap = (code: string) => api<ConceptMap>(`/concept-maps/${encodeURIComponent(code)}`);

// ---- accounts

export const getMe = () => api<{ user: User | null }>("/auth/me");
export const signUp = (email: string, password: string) =>
  api<{ user: User }>("/auth/signup", { json: { email, password } });
export const logIn = (email: string, password: string) =>
  api<{ user: User }>("/auth/login", { json: { email, password } });
export const logOut = () => api<void>("/auth/logout", { method: "POST" });
export const verifyEmail = (token: string) => api<{ user: User }>("/auth/verify", { json: { token } });
export const resendVerification = () => api<void>("/auth/verify/resend", { method: "POST" });
export const forgotPassword = (email: string) => api<void>("/auth/password/forgot", { json: { email } });
export const resetPassword = (token: string, password: string) =>
  api<void>("/auth/password/reset", { json: { token, password } });
export const changePassword = (currentPassword: string | null, newPassword: string) =>
  api<{ user: User }>("/auth/password/change", {
    json: { current_password: currentPassword, new_password: newPassword },
  });
export const GOOGLE_LOGIN_URL = "/api/auth/google/login";

export const updateProfile = (displayName: string) =>
  api<{ user: User }>("/me", { method: "PATCH", json: { display_name: displayName } });
export const deleteAccount = () => api<void>("/me", { method: "DELETE" });

export const listSavedAudits = () => api<{ audits: SavedAudit[] }>("/me/audits");
export const loadSavedAudit = (id: string) => api<AuditResponse>(`/me/audits/${id}/load`, { method: "POST" });
export const deleteSavedAudit = (id: string) => api<void>(`/me/audits/${id}`, { method: "DELETE" });

export const listSearches = (limit = 30) => api<{ searches: SavedSearch[] }>(`/me/searches?limit=${limit}`);
export const restoreSearch = (id: string) => api<RestoreResponse>(`/me/searches/${id}/restore`, { method: "POST" });
export const deleteSearch = (id: string) => api<void>(`/me/searches/${id}`, { method: "DELETE" });
export const saveMessages = (searchId: string, messages: ChatMessage[]) =>
  api<void>(`/me/searches/${searchId}/messages`, {
    json: { messages: messages.map(({ role, content, sources }) => ({ role, content, sources: sources ?? null })) },
  });

export const listActivity = (before?: number) =>
  api<{ events: ActivityEvent[]; next_before: number | null }>(
    `/me/activity${before ? `?before=${before}` : ""}`,
  );

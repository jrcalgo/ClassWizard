import { create } from "zustand";

import type { Audit, ChatMessage, Occupation, PlanPrefs, Priority, RecommendResponse } from "@/api/types";
import { MAX_CAREERS } from "@/lib/plan";

/** What the canvas shows after Search. Null until the first search. */
export interface Plan {
  prefs: PlanPrefs;
  recommendation: RecommendResponse | null;
  recommendError: string | null;
  searchId: string | null;
}

interface PlanState {
  // Layout
  menuOpen: boolean;
  resultsOpen: boolean;
  conceptCourse: string | null; // open concept-map dialog (folder key, e.g. ITSC_3160)
  conceptOpen: boolean;

  // Search form
  pendingFile: File | null; // chosen but not uploaded yet
  uploadedFile: File | null; // last uploaded PDF, kept in memory to save it after signing in
  selectedCareers: Record<string, string>; // soc_code -> title
  credits: number;
  includeSummer: boolean;
  priority: Priority;

  // Audit session (Redis-backed on the server)
  sessionId: string | null;
  audit: Audit | null;
  auditId: string | null; // saved encrypted copy, signed-in users only
  filename: string | null;

  // Results
  plan: Plan | null;
  messages: ChatMessage[];
  searching: boolean;
  replying: boolean;

  setMenuOpen: (open: boolean) => void;
  toggleMenu: () => void;
  setResultsOpen: (open: boolean) => void;
  openConceptMap: (course: string | null) => void;
  closeConceptMap: () => void;
  setPendingFile: (file: File | null) => void;
  toggleCareer: (career: Occupation, checked: boolean) => void;
  setSelectedCareers: (careers: Occupation[]) => void;
  setCredits: (credits: number) => void;
  setIncludeSummer: (value: boolean) => void;
  setPriority: (priority: Priority) => void;
  setAuditSession: (session: { sessionId: string; audit: Audit; auditId: string | null; filename: string | null }) => void;
  setPlan: (plan: Plan | null) => void;
  setMessages: (messages: ChatMessage[]) => void;
  appendMessage: (message: ChatMessage) => void;
  setSearching: (value: boolean) => void;
  setReplying: (value: boolean) => void;
  /** The audit expired or was discarded: drop everything that depended on it. */
  clearAudit: () => void;
}

export const usePlanStore = create<PlanState>((set) => ({
  menuOpen: true,
  resultsOpen: typeof window === "undefined" ? true : window.innerWidth >= 1024,
  conceptCourse: null,
  conceptOpen: false,

  pendingFile: null,
  uploadedFile: null,
  selectedCareers: {},
  credits: 15,
  includeSummer: true,
  priority: "Finish sooner",

  sessionId: null,
  audit: null,
  auditId: null,
  filename: null,

  plan: null,
  messages: [],
  searching: false,
  replying: false,

  setMenuOpen: (menuOpen) => set({ menuOpen }),
  toggleMenu: () => set((s) => ({ menuOpen: !s.menuOpen })),
  setResultsOpen: (resultsOpen) => set({ resultsOpen }),
  openConceptMap: (conceptCourse) => set({ conceptCourse, conceptOpen: true }),
  closeConceptMap: () => set({ conceptOpen: false }),
  setPendingFile: (pendingFile) => set({ pendingFile }),
  toggleCareer: (career, checked) =>
    set((s) => {
      const next = { ...s.selectedCareers };
      if (checked) {
        if (Object.keys(next).length >= MAX_CAREERS) return s;
        next[career.soc_code] = career.title;
      } else {
        delete next[career.soc_code];
      }
      return { selectedCareers: next };
    }),
  setSelectedCareers: (careers) =>
    set({
      selectedCareers: Object.fromEntries(careers.slice(0, MAX_CAREERS).map((c) => [c.soc_code, c.title])),
    }),
  setCredits: (credits) => set({ credits }),
  setIncludeSummer: (includeSummer) => set({ includeSummer }),
  setPriority: (priority) => set({ priority }),
  setAuditSession: ({ sessionId, audit, auditId, filename }) => set({ sessionId, audit, auditId, filename }),
  setPlan: (plan) => set({ plan }),
  setMessages: (messages) => set({ messages }),
  appendMessage: (message) => set((s) => ({ messages: [...s.messages, message] })),
  setSearching: (searching) => set({ searching }),
  setReplying: (replying) => set({ replying }),
  clearAudit: () =>
    set({
      sessionId: null,
      audit: null,
      auditId: null,
      filename: null,
      uploadedFile: null,
      plan: null,
      messages: [],
      replying: false,
    }),
}));

export function selectedCareerList(selected: Record<string, string>): Occupation[] {
  return Object.entries(selected).map(([soc_code, title]) => ({ soc_code, title }));
}

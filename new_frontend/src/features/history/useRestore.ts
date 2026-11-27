import { useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { toast } from "sonner";

import { ApiError } from "@/api/client";
import { loadSavedAudit, restoreSearch } from "@/api/endpoints";
import { keys } from "@/api/queries";
import type { PlanPrefs } from "@/api/types";
import { usePlanStore } from "@/state/planStore";

/** Reopen a saved search: audit, careers, preferences, graph and chat. */
export function useRestoreSearch() {
  const queryClient = useQueryClient();
  return useCallback(
    async (searchId: string) => {
      try {
        const data = await restoreSearch(searchId);
        const store = usePlanStore.getState();
        const saved = data.search.prefs ?? {};
        const prefs: PlanPrefs = {
          filename: saved.filename ?? "saved audit",
          careers: saved.careers ?? [],
          credits: saved.credits ?? 15,
          include_summer: saved.include_summer ?? true,
          priority: saved.priority ?? "Finish sooner",
        };
        store.setAuditSession({
          sessionId: data.session_id,
          audit: data.audit,
          auditId: data.audit_id,
          filename: prefs.filename,
        });
        store.setPendingFile(null);
        usePlanStore.setState({ uploadedFile: null });
        store.setSelectedCareers(prefs.careers);
        store.setCredits(prefs.credits);
        store.setIncludeSummer(prefs.include_summer);
        store.setPriority(prefs.priority);
        store.setPlan({
          prefs,
          recommendation: data.search.recommendation,
          recommendError: data.search.recommendation ? null : "Recommendations were not saved for this search.",
          searchId: data.search.id,
        });
        store.setMessages(data.messages.map(({ role, content, sources }) => ({ role, content, sources })));
        void queryClient.invalidateQueries({ queryKey: keys.activity });
        return true;
      } catch (error) {
        toast.error(error instanceof ApiError ? error.detail : "The search could not be restored.");
        return false;
      }
    },
    [queryClient],
  );
}

/** Use a previously uploaded (encrypted) audit instead of uploading the PDF again. */
export function useLoadSavedAudit() {
  return useCallback(async (auditId: string, filename: string | null) => {
    try {
      const data = await loadSavedAudit(auditId);
      const store = usePlanStore.getState();
      store.setAuditSession({
        sessionId: data.session_id,
        audit: data.audit,
        auditId: data.audit_id ?? auditId,
        filename: filename ?? "saved audit",
      });
      store.setPendingFile(null);
      usePlanStore.setState({ uploadedFile: null });
      toast.success("Saved audit loaded.");
    } catch (error) {
      toast.error(error instanceof ApiError ? error.detail : "The saved audit could not be loaded.");
    }
  }, []);
}

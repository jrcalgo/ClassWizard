import { useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { toast } from "sonner";

import { postChat, postRecommend, saveMessages, uploadAudit } from "@/api/endpoints";
import { keys, useConfig, useMe } from "@/api/queries";
import type { ChatMessage, PlanPrefs, RecommendResponse } from "@/api/types";
import {
  chatErrorMessage,
  chatReplyMessage,
  chatSeedPrompt,
  recommendError,
  recommendationSeed,
  uploadErrorMessage,
} from "@/lib/plan";
import { selectedCareerList, usePlanStore } from "@/state/planStore";

/** The Search button: upload (if a new PDF was chosen), rank courses, seed the chat. */
export function useRunSearch() {
  const queryClient = useQueryClient();
  const { data: config } = useConfig();
  const { data: user } = useMe();

  return useCallback(async () => {
    const state = usePlanStore.getState();
    if (state.searching) return;
    if (!state.pendingFile && !state.sessionId) {
      toast.warning("Upload the DegreeWorks audit first.");
      return;
    }
    const careers = selectedCareerList(state.selectedCareers);
    if (!careers.length) {
      toast.warning("Select at least one career.");
      return;
    }
    state.setSearching(true);
    try {
      let { sessionId, audit, auditId, filename } = state;
      // An audit uploaded before signing in has no saved copy yet; upload it
      // again so this search can be reopened later.
      const resave = !state.pendingFile && user && config?.audit_persistence && !auditId ? state.uploadedFile : null;
      const file = state.pendingFile ?? resave;
      if (file) {
        try {
          const payload = await uploadAudit(file, state.sessionId);
          sessionId = payload.session_id;
          audit = payload.audit;
          auditId = payload.audit_id ?? null;
          filename = file.name;
          state.setAuditSession({ sessionId, audit, auditId, filename });
          state.setPendingFile(null);
          usePlanStore.setState({ uploadedFile: file });
          if (auditId) void queryClient.invalidateQueries({ queryKey: keys.audits });
        } catch (error) {
          toast.error(uploadErrorMessage(error));
          return;
        }
      }
      if (!sessionId || !audit) return;

      const prefs: PlanPrefs = {
        filename: filename ?? "your audit",
        careers,
        credits: state.credits,
        include_summer: state.includeSummer,
        priority: state.priority,
      };
      const socCodes = careers.map((c) => c.soc_code);

      let recommendation: RecommendResponse | null = null;
      let error: string | null = null;
      try {
        recommendation = await postRecommend(sessionId, socCodes, prefs, auditId);
      } catch (err) {
        error = recommendError(err);
      }
      const searchId = recommendation?.search_id ?? null;
      usePlanStore.getState().setPlan({ prefs, recommendation, recommendError: error, searchId });
      usePlanStore.getState().setMessages([]);

      let seed: ChatMessage;
      if ((config?.chat_mode ?? "explain") === "explain") {
        // No model call on search: the first message comes from /recommend.
        seed = { role: "assistant", content: recommendationSeed(prefs, audit, recommendation) };
      } else {
        usePlanStore.getState().setReplying(true);
        try {
          const reply = await postChat(sessionId, chatSeedPrompt(prefs, audit), [], prefs, searchId);
          seed = chatReplyMessage(reply.reply);
        } catch (err) {
          seed = chatErrorMessage(err);
        } finally {
          usePlanStore.getState().setReplying(false);
        }
      }
      usePlanStore.getState().setMessages([seed]);
      // The menu stays docked, except on phones where it covers the whole canvas.
      if (window.matchMedia?.("(max-width: 639px)").matches) usePlanStore.getState().setMenuOpen(false);
      if (user && searchId) {
        saveMessages(searchId, [seed]).catch(() => undefined);
        void queryClient.invalidateQueries({ queryKey: keys.searches });
      }
    } finally {
      usePlanStore.getState().setSearching(false);
    }
  }, [config?.chat_mode, config?.audit_persistence, queryClient, user]);
}

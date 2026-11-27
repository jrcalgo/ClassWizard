import { useCallback } from "react";

import { postChat, postExplain, saveMessages } from "@/api/endpoints";
import { useConfig, useMe } from "@/api/queries";
import type { ChatMessage } from "@/api/types";
import { AUDIT_GONE, chatErrorMessage, chatReplyMessage, explainErrorMessage, explainMessage } from "@/lib/plan";
import { usePlanStore } from "@/state/planStore";

export const MAX_QUESTION = 500; // backend/main.py _MAX_QUESTION

export function useSendMessage() {
  const { data: config } = useConfig();
  const { data: user } = useMe();

  return useCallback(
    async (text: string) => {
      const question = text.split(/\s+/).filter(Boolean).join(" ");
      const state = usePlanStore.getState();
      if (!question || state.replying || !state.plan) return;
      const history = state.messages.map(({ role, content }) => ({ role, content }));
      const userMessage: ChatMessage = { role: "user", content: question };
      state.appendMessage(userMessage);
      state.setReplying(true);
      const { sessionId, plan } = state;
      const socCodes = plan.prefs.careers.map((c) => c.soc_code);
      let reply: ChatMessage;
      try {
        if (!sessionId) {
          reply = { role: "assistant", content: AUDIT_GONE };
        } else if ((config?.chat_mode ?? "explain") === "explain") {
          try {
            reply = explainMessage(await postExplain(sessionId, socCodes, question, plan.searchId));
          } catch (error) {
            reply = explainErrorMessage(error);
          }
        } else {
          try {
            const payload = await postChat(sessionId, question, history, plan.prefs, plan.searchId);
            reply = chatReplyMessage(payload.reply);
          } catch (error) {
            reply = chatErrorMessage(error);
          }
        }
      } finally {
        usePlanStore.getState().setReplying(false);
      }
      // A new search may have started while waiting; drop a stale answer.
      if (usePlanStore.getState().plan !== plan) return;
      usePlanStore.getState().appendMessage(reply);
      if (user && plan.searchId) saveMessages(plan.searchId, [userMessage, reply]).catch(() => undefined);
    },
    [config?.chat_mode, user],
  );
}

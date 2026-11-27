import { useEffect, useRef } from "react";
import { toast } from "sonner";

import { ApiError } from "@/api/client";
import { discardAudit, refreshAudit } from "@/api/endpoints";
import { usePlanStore } from "@/state/planStore";

const HEARTBEAT_MS = 20_000;

/**
 * Keeps the server-side audit alive while the page is open (the Redis copy
 * expires after AUDIT_TTL_SECONDS), and discards it when the page goes away,
 * as the Streamlit app did. Signed-in users keep their encrypted saved copy.
 */
export function useAuditSession() {
  const sessionId = usePlanStore((s) => s.sessionId);
  const warned = useRef(false);

  useEffect(() => {
    if (!sessionId) return;
    warned.current = false;
    const timer = window.setInterval(async () => {
      try {
        await refreshAudit(sessionId);
        warned.current = false;
      } catch (error) {
        if (usePlanStore.getState().sessionId !== sessionId) return;
        if (error instanceof ApiError && error.status === 404) {
          usePlanStore.getState().clearAudit();
          toast.warning("This audit expired. Upload it again.");
        } else if (!warned.current) {
          warned.current = true;
          toast.warning("The saved audit could not be refreshed.");
        }
      }
    }, HEARTBEAT_MS);

    const onPageHide = (event: PageTransitionEvent) => {
      // A page kept in the back/forward cache may come back; keep its audit.
      if (event.persisted) return;
      discardAudit(sessionId).catch(() => undefined);
    };
    window.addEventListener("pagehide", onPageHide);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("pagehide", onPageHide);
    };
  }, [sessionId]);
}

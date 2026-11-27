import { MailWarning } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { ApiError } from "@/api/client";
import { resendVerification } from "@/api/endpoints";
import { useConfig, useMe } from "@/api/queries";
import { Button } from "@/components/ui/button";

export function EmailVerifyBanner() {
  const { data: user } = useMe();
  const { data: config } = useConfig();
  const [sending, setSending] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  if (!user || user.email_verified || !config?.email_enabled || dismissed) return null;
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-gold/40 bg-gold/10 px-4 py-1.5 text-sm">
      <MailWarning className="h-4 w-4 shrink-0 text-gold" />
      <span>
        Confirm <strong>{user.email}</strong> using the link we emailed you.
      </span>
      <Button
        variant="link"
        className="text-sm"
        disabled={sending}
        onClick={async () => {
          setSending(true);
          try {
            await resendVerification();
            toast.success("Verification email sent.");
          } catch (error) {
            toast.error(error instanceof ApiError ? error.detail : "The email could not be sent.");
          } finally {
            setSending(false);
          }
        }}
      >
        Resend email
      </Button>
      <button type="button" className="ml-auto text-xs text-muted hover:text-text" onClick={() => setDismissed(true)}>
        Dismiss
      </button>
    </div>
  );
}

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { Activity, Clock, History, RotateCcw, Trash2, UserRound } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { NavLink, Navigate, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { z } from "zod";

import { ApiError } from "@/api/client";
import { changePassword, deleteAccount, deleteSavedAudit, deleteSearch, updateProfile } from "@/api/endpoints";
import { keys, markSignedOut, useActivity, useMe, useSavedAudits, useSearches } from "@/api/queries";
import type { ActivityEvent, User } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";
import { FieldError, FormError, Overlay } from "@/features/auth/AuthLayout";
import { newPasswordField } from "@/features/auth/schemas";
import { useRestoreSearch } from "@/features/history/useRestore";
import { cn, formatDateTime } from "@/lib/utils";
import { usePlanStore } from "@/state/planStore";

function errorText(error: unknown, fallback: string) {
  return error instanceof ApiError && error.status !== 0 ? error.detail : fallback;
}

const TABS = [
  { to: "/account", label: "Account", Icon: UserRound, end: true },
  { to: "/account/history", label: "Search history", Icon: History, end: false },
  { to: "/account/activity", label: "Activity", Icon: Activity, end: false },
];

function AccountFrame({ title, children }: { title: string; children: (user: User) => React.ReactNode }) {
  const { data: user, isLoading } = useMe();
  if (isLoading)
    return (
      <Overlay label={title} wide>
        <div className="flex items-center gap-2 p-8 text-sm text-muted">
          <Spinner /> Loading…
        </div>
      </Overlay>
    );
  if (!user) return <Navigate to="/login" replace />;
  return (
    <Overlay label={title} wide>
      <div className="flex max-h-[calc(100dvh-2rem)] flex-col">
        <div className="border-b px-6 pb-0 pt-6 sm:px-8">
          <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
          <nav className="mt-4 flex gap-1 overflow-x-auto" aria-label="Account sections">
            {TABS.map(({ to, label, Icon, end }) => (
              <NavLink
                key={to}
                to={to}
                end={end}
                className={({ isActive }) =>
                  cn(
                    "-mb-px flex items-center gap-1.5 whitespace-nowrap border-b-2 px-3 py-2 text-sm font-semibold transition-colors",
                    isActive ? "border-green text-text" : "border-transparent text-muted hover:text-text",
                  )
                }
              >
                <Icon className="h-4 w-4" /> {label}
              </NavLink>
            ))}
          </nav>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6 sm:px-8">{children(user)}</div>
      </div>
    </Overlay>
  );
}

function Section({ title, description, children }: { title: string; description?: string; children: React.ReactNode }) {
  return (
    <section className="border-b pb-6 last:border-b-0 [&+&]:pt-6">
      <h2 className="text-base font-bold">{title}</h2>
      {description && <p className="mt-0.5 text-sm text-muted">{description}</p>}
      <div className="mt-3">{children}</div>
    </section>
  );
}

function ProfileForm({ user }: { user: User }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState(user.display_name ?? "");
  const [saving, setSaving] = useState(false);
  return (
    <form
      className="flex flex-wrap items-end gap-3"
      onSubmit={async (e) => {
        e.preventDefault();
        setSaving(true);
        try {
          const { user: updated } = await updateProfile(name);
          queryClient.setQueryData(keys.me, { user: updated });
          toast.success("Profile saved.");
        } catch (err) {
          toast.error(errorText(err, "The profile could not be saved."));
        } finally {
          setSaving(false);
        }
      }}
    >
      <div className="min-w-[14rem] flex-1">
        <Label htmlFor="display_name">Display name</Label>
        <Input id="display_name" className="mt-1.5" maxLength={80} value={name} onChange={(e) => setName(e.target.value)} />
      </div>
      <Button type="submit" variant="outline" disabled={saving}>
        {saving && <Spinner />} Save
      </Button>
    </form>
  );
}

const passwordSchema = z
  .object({ current: z.string(), password: newPasswordField, confirm: z.string() })
  .refine((v) => v.password === v.confirm, { message: "Passwords don't match.", path: ["confirm"] });

function PasswordForm({ user }: { user: User }) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const form = useForm<z.infer<typeof passwordSchema>>({
    resolver: zodResolver(passwordSchema),
    defaultValues: { current: "", password: "", confirm: "" },
  });
  const { errors, isSubmitting } = form.formState;
  return (
    <form
      noValidate
      className="grid gap-3 sm:grid-cols-3"
      onSubmit={form.handleSubmit(async ({ current, password }) => {
        setError(null);
        try {
          const { user: updated } = await changePassword(user.has_password ? current : null, password);
          queryClient.setQueryData(keys.me, { user: updated });
          form.reset();
          toast.success(user.has_password ? "Password changed. Other devices were signed out." : "Password set.");
        } catch (err) {
          setError(errorText(err, "The password could not be changed."));
        }
      })}
    >
      <div className="sm:col-span-3">
        <FormError message={error} />
      </div>
      {user.has_password && (
        <div>
          <Label htmlFor="current">Current password</Label>
          <Input id="current" type="password" autoComplete="current-password" className="mt-1.5" {...form.register("current")} />
        </div>
      )}
      <div>
        <Label htmlFor="new">New password</Label>
        <Input id="new" type="password" autoComplete="new-password" className="mt-1.5" aria-invalid={Boolean(errors.password)} {...form.register("password")} />
        <FieldError message={errors.password?.message} />
      </div>
      <div>
        <Label htmlFor="confirm">Confirm new password</Label>
        <Input id="confirm" type="password" autoComplete="new-password" className="mt-1.5" aria-invalid={Boolean(errors.confirm)} {...form.register("confirm")} />
        <FieldError message={errors.confirm?.message} />
      </div>
      <div className="sm:col-span-3">
        <Button type="submit" variant="outline" disabled={isSubmitting}>
          {isSubmitting && <Spinner />} {user.has_password ? "Change password" : "Set password"}
        </Button>
      </div>
    </form>
  );
}

function SavedAudits() {
  const queryClient = useQueryClient();
  const { data: audits, isLoading } = useSavedAudits(true);
  const auditId = usePlanStore((s) => s.auditId);
  if (isLoading) return <Spinner />;
  if (!audits?.length) return <p className="text-sm text-muted">No saved audits. Audits you upload while signed in are saved here, encrypted.</p>;
  return (
    <ul className="divide-y rounded-btn border">
      {audits.map((a) => (
        <li key={a.id} className="flex items-center gap-3 px-3 py-2 text-sm">
          <div className="min-w-0 flex-1">
            <p className="truncate font-medium">{a.filename ?? "Audit"}</p>
            <p className="truncate text-xs text-muted">
              {[a.summary.major, a.summary.catalog_year].filter(Boolean).join(" · ")} · uploaded {formatDateTime(a.created_at)}
            </p>
          </div>
          <Button
            variant="ghost"
            size="icon"
            aria-label={`Delete ${a.filename ?? "audit"}`}
            title="Delete this saved audit"
            onClick={async () => {
              if (!window.confirm("Delete this saved audit? Searches that used it can no longer be reopened.")) return;
              try {
                await deleteSavedAudit(a.id);
                if (auditId === a.id) usePlanStore.setState({ auditId: null });
                void queryClient.invalidateQueries({ queryKey: ["me"] });
                toast.success("Saved audit deleted.");
              } catch (err) {
                toast.error(errorText(err, "The audit could not be deleted."));
              }
            }}
          >
            <Trash2 className="text-danger" />
          </Button>
        </li>
      ))}
    </ul>
  );
}

function DeleteAccount({ user }: { user: User }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const ready = confirm.trim().toLowerCase() === user.email.toLowerCase();
  return (
    <div className="rounded-btn border border-danger/40 bg-danger/5 p-4">
      <p className="text-sm">
        This permanently deletes your account, saved audits, searches, conversations and activity log. It cannot be undone.
      </p>
      <Label htmlFor="confirm-delete" className="mt-3 block">
        Type <span className="font-mono">{user.email}</span> to confirm
      </Label>
      <div className="mt-1.5 flex flex-wrap gap-2">
        <Input id="confirm-delete" className="min-w-[14rem] flex-1" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="off" />
        <Button
          variant="danger"
          disabled={!ready || busy}
          onClick={async () => {
            setBusy(true);
            try {
              await deleteAccount();
              // Leave the account page first, or its signed-out redirect sends us to /login.
              navigate("/");
              markSignedOut(queryClient);
              usePlanStore.setState({ auditId: null, plan: null, messages: [] });
              toast.success("Your account and all of its data were deleted.");
            } catch (err) {
              toast.error(errorText(err, "The account could not be deleted."));
              setBusy(false);
            }
          }}
        >
          {busy && <Spinner />} Delete account
        </Button>
      </div>
    </div>
  );
}

export function AccountPage() {
  return (
    <AccountFrame title="Your account">
      {(user) => (
        <div>
          <Section title="Profile" description={`${user.email} · ${user.email_verified ? "verified" : "not verified yet"}${user.google_linked ? " · Google linked" : ""}`}>
            <ProfileForm user={user} />
          </Section>
          <Section title="Password" description={user.has_password ? undefined : "You sign in with Google. Set a password to also sign in with your email."}>
            <PasswordForm user={user} />
          </Section>
          <Section title="Saved audits" description="Encrypted copies of DegreeWorks audits you uploaded while signed in.">
            <SavedAudits />
          </Section>
          <Section title="Delete account">
            <DeleteAccount user={user} />
          </Section>
        </div>
      )}
    </AccountFrame>
  );
}

export function HistoryPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const restore = useRestoreSearch();
  const [busy, setBusy] = useState<string | null>(null);
  const { data: user } = useMe();
  const { data: searches, isLoading } = useSearches(Boolean(user), 100);
  return (
    <AccountFrame title="Search history">
      {() =>
        isLoading ? (
          <Spinner />
        ) : !searches?.length ? (
          <p className="text-sm text-muted">No searches yet. Searches you run while signed in appear here.</p>
        ) : (
          <ul className="space-y-2">
            {searches.map((s) => (
              <li key={s.id} className="flex flex-wrap items-center gap-3 rounded-btn border bg-card-alt p-3">
                <div className="min-w-0 flex-1">
                  <p className="font-semibold">
                    {(s.prefs.careers ?? []).map((c) => c.title).join(", ") || s.soc_codes.join(", ")}
                  </p>
                  <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-muted">
                    <Clock className="h-3 w-3" /> {formatDateTime(s.created_at)}
                    {s.audit_summary?.major && <span>· {s.audit_summary.major}</span>}
                    {s.prefs.credits && <span>· {s.prefs.credits} credits</span>}
                    {s.prefs.priority && <span>· {s.prefs.priority}</span>}
                    <span>· {s.message_count} message(s)</span>
                    {!s.audit_id && <span className="text-gold">· audit deleted</span>}
                  </p>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={busy !== null || !s.audit_id}
                  onClick={async () => {
                    setBusy(s.id);
                    const ok = await restore(s.id);
                    setBusy(null);
                    if (ok) navigate("/");
                  }}
                >
                  {busy === s.id ? <Spinner /> : <RotateCcw />} Reopen
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label="Delete this search"
                  title="Delete this search"
                  onClick={async () => {
                    if (!window.confirm("Delete this search and its conversation?")) return;
                    try {
                      await deleteSearch(s.id);
                      void queryClient.invalidateQueries({ queryKey: ["me"] });
                    } catch (err) {
                      toast.error(errorText(err, "The search could not be deleted."));
                    }
                  }}
                >
                  <Trash2 className="text-danger" />
                </Button>
              </li>
            ))}
          </ul>
        )
      }
    </AccountFrame>
  );
}

const EVENT_LABELS: Record<string, string> = {
  sign_up: "Created account",
  sign_in: "Signed in",
  sign_out: "Signed out",
  email_verified: "Confirmed email",
  password_change: "Changed password",
  password_reset_requested: "Requested a password reset",
  password_reset: "Reset password",
  profile_update: "Updated profile",
  audit_upload: "Uploaded an audit",
  audit_load: "Reused a saved audit",
  audit_delete: "Deleted a saved audit",
  search: "Ran a search",
  search_restore: "Reopened a search",
  search_delete: "Deleted a search",
  question: "Asked a question",
};

function eventDetail(event: ActivityEvent): string {
  const detail = event.detail ?? {};
  if (typeof detail.method === "string") return detail.method === "google" ? "with Google" : "with email and password";
  if (typeof detail.question === "string") return `“${detail.question}”`;
  if (Array.isArray(detail.soc_codes)) return (detail.soc_codes as string[]).join(", ");
  return "";
}

function browserOf(agent: string | null): string {
  if (!agent) return "";
  const browser = /Edg\//.test(agent)
    ? "Edge"
    : /Firefox\//.test(agent)
      ? "Firefox"
      : /Chrome\//.test(agent)
        ? "Chrome"
        : /Safari\//.test(agent)
          ? "Safari"
          : "Browser";
  const os = /Windows/.test(agent)
    ? "Windows"
    : /Mac OS X/.test(agent)
      ? /iPhone|iPad/.test(agent)
        ? "iOS"
        : "macOS"
      : /Android/.test(agent)
        ? "Android"
        : /Linux/.test(agent)
          ? "Linux"
          : "";
  return os ? `${browser} on ${os}` : browser;
}

export function ActivityPage() {
  const { data: user } = useMe();
  const activity = useActivity(Boolean(user));
  const events = activity.data?.pages.flatMap((p) => p.events) ?? [];
  return (
    <AccountFrame title="Activity">
      {() =>
        activity.isLoading ? (
          <Spinner />
        ) : !events.length ? (
          <p className="text-sm text-muted">No activity yet.</p>
        ) : (
          <div>
            <div className="overflow-x-auto rounded-btn border">
              <table className="w-full text-left text-sm">
                <thead className="bg-card-alt text-xs uppercase tracking-wide text-muted">
                  <tr>
                    <th className="px-3 py-2 font-semibold">When</th>
                    <th className="px-3 py-2 font-semibold">Event</th>
                    <th className="px-3 py-2 font-semibold">Device</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {events.map((e) => (
                    <tr key={e.id} className="align-top">
                      <td className="whitespace-nowrap px-3 py-2 text-muted">{formatDateTime(e.created_at)}</td>
                      <td className="px-3 py-2">
                        <span className="font-medium">{EVENT_LABELS[e.event] ?? e.event}</span>
                        {eventDetail(e) && <span className="block break-words text-xs text-muted">{eventDetail(e)}</span>}
                      </td>
                      <td className="whitespace-nowrap px-3 py-2 text-xs text-muted">
                        {browserOf(e.user_agent)}
                        {e.ip && <span className="block">{e.ip}</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {activity.hasNextPage && (
              <Button variant="outline" className="mt-3" disabled={activity.isFetchingNextPage} onClick={() => void activity.fetchNextPage()}>
                {activity.isFetchingNextPage && <Spinner />} Load more
              </Button>
            )}
          </div>
        )
      }
    </AccountFrame>
  );
}

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, MailCheck } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { z } from "zod";

import { ApiError } from "@/api/client";
import { forgotPassword, logIn, resetPassword, signUp, verifyEmail } from "@/api/endpoints";
import { keys, markSignedOut, useConfig } from "@/api/queries";
import type { User } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";

import { AuthCard, FieldError, FormError } from "./AuthLayout";
import { GoogleButton, OrDivider } from "./GoogleButton";
import { emailField, loginSchema, resetSchema, signupSchema } from "./schemas";

const GOOGLE_ERRORS: Record<string, string> = {
  google: "Google sign-in failed. Try again.",
  google_cancelled: "Google sign-in was cancelled.",
  google_state: "Google sign-in expired. Try again.",
  google_unverified: "That Google account's email isn't verified, so it can't be linked to an existing account.",
  server: "Sign-in is unavailable right now. Try again shortly.",
};

function messageOf(error: unknown, fallback: string) {
  return error instanceof ApiError && error.status !== 0 ? error.detail : fallback;
}

function useSignedIn() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  return (user: User, message: string) => {
    queryClient.setQueryData(keys.me, { user });
    void queryClient.invalidateQueries({ queryKey: ["me"] });
    toast.success(message);
    navigate("/");
  };
}

export function LoginPage() {
  const [params] = useSearchParams();
  const signedIn = useSignedIn();
  const [error, setError] = useState<string | null>(GOOGLE_ERRORS[params.get("error") ?? ""] ?? null);
  const form = useForm<z.infer<typeof loginSchema>>({ resolver: zodResolver(loginSchema), defaultValues: { email: "", password: "" } });
  const { errors, isSubmitting } = form.formState;

  return (
    <AuthCard title="Sign in" subtitle="Save your audits, searches and conversations.">
      <form
        noValidate
        className="space-y-4"
        onSubmit={form.handleSubmit(async ({ email, password }) => {
          setError(null);
          try {
            const { user } = await logIn(email, password);
            signedIn(user, "Signed in.");
          } catch (err) {
            setError(messageOf(err, "Sign-in failed. Try again."));
          }
        })}
      >
        <FormError message={error} />
        <div>
          <Label htmlFor="email">Email</Label>
          <Input id="email" type="email" autoComplete="email" autoFocus className="mt-1.5" aria-invalid={Boolean(errors.email)} {...form.register("email")} />
          <FieldError message={errors.email?.message} />
        </div>
        <div>
          <div className="flex items-center justify-between">
            <Label htmlFor="password">Password</Label>
            <Link to="/forgot" className="text-xs font-semibold text-link hover:underline">
              Forgot password?
            </Link>
          </div>
          <Input id="password" type="password" autoComplete="current-password" className="mt-1.5" aria-invalid={Boolean(errors.password)} {...form.register("password")} />
          <FieldError message={errors.password?.message} />
        </div>
        <Button type="submit" className="w-full" disabled={isSubmitting}>
          {isSubmitting && <Spinner />} Sign in
        </Button>
      </form>
      <OrDivider />
      <GoogleButton label="Continue with Google" />
      <p className="mt-6 text-center text-sm text-muted">
        New to ClassWizard?{" "}
        <Link to="/signup" className="font-semibold text-link hover:underline">
          Create an account
        </Link>
      </p>
    </AuthCard>
  );
}

export function SignupPage() {
  const signedIn = useSignedIn();
  const { data: config } = useConfig();
  const [error, setError] = useState<string | null>(null);
  const form = useForm<z.infer<typeof signupSchema>>({
    resolver: zodResolver(signupSchema),
    defaultValues: { email: "", password: "", confirm: "" },
  });
  const { errors, isSubmitting } = form.formState;

  return (
    <AuthCard title="Create an account" subtitle="Keep your plans between visits. Using ClassWizard without an account still works.">
      <form
        noValidate
        className="space-y-4"
        onSubmit={form.handleSubmit(async ({ email, password }) => {
          setError(null);
          try {
            const { user } = await signUp(email, password);
            signedIn(
              user,
              config?.email_enabled ? "Account created. Check your email to confirm your address." : "Account created.",
            );
          } catch (err) {
            setError(messageOf(err, "The account could not be created."));
          }
        })}
      >
        <FormError message={error} />
        <div>
          <Label htmlFor="email">Email</Label>
          <Input id="email" type="email" autoComplete="email" autoFocus className="mt-1.5" aria-invalid={Boolean(errors.email)} {...form.register("email")} />
          <FieldError message={errors.email?.message} />
        </div>
        <div>
          <Label htmlFor="password">Password</Label>
          <Input id="password" type="password" autoComplete="new-password" className="mt-1.5" aria-invalid={Boolean(errors.password)} {...form.register("password")} />
          <FieldError message={errors.password?.message ?? undefined} />
          {!errors.password && <p className="mt-1 text-xs text-muted">At least 8 characters.</p>}
        </div>
        <div>
          <Label htmlFor="confirm">Confirm password</Label>
          <Input id="confirm" type="password" autoComplete="new-password" className="mt-1.5" aria-invalid={Boolean(errors.confirm)} {...form.register("confirm")} />
          <FieldError message={errors.confirm?.message} />
        </div>
        <Button type="submit" className="w-full" disabled={isSubmitting}>
          {isSubmitting && <Spinner />} Create account
        </Button>
      </form>
      <OrDivider />
      <GoogleButton label="Sign up with Google" />
      <p className="mt-6 text-center text-sm text-muted">
        Already have an account?{" "}
        <Link to="/login" className="font-semibold text-link hover:underline">
          Sign in
        </Link>
      </p>
    </AuthCard>
  );
}

export function ForgotPage() {
  const { data: config } = useConfig();
  const [sent, setSent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const schema = z.object({ email: emailField });
  const form = useForm<z.infer<typeof schema>>({ resolver: zodResolver(schema), defaultValues: { email: "" } });
  const { errors, isSubmitting } = form.formState;

  if (sent) {
    return (
      <AuthCard title="Check your email">
        <div className="flex gap-3 rounded-btn border bg-card-alt p-4 text-sm">
          <MailCheck className="h-5 w-5 shrink-0 text-green" />
          <p>
            If an account exists for <strong>{sent}</strong>, we sent a link to reset its password. The link expires in 1
            hour.
          </p>
        </div>
        <Button asChild variant="outline" className="mt-5 w-full">
          <Link to="/login">Back to sign in</Link>
        </Button>
      </AuthCard>
    );
  }
  return (
    <AuthCard title="Reset your password" subtitle="We'll email you a link to choose a new password.">
      {config && !config.email_enabled ? (
        <FormError message="Email isn't configured on this server, so passwords can't be reset by email." />
      ) : (
        <form
          noValidate
          className="space-y-4"
          onSubmit={form.handleSubmit(async ({ email }) => {
            setError(null);
            try {
              await forgotPassword(email);
              setSent(email);
            } catch (err) {
              setError(messageOf(err, "The email could not be sent."));
            }
          })}
        >
          <FormError message={error} />
          <div>
            <Label htmlFor="email">Email</Label>
            <Input id="email" type="email" autoComplete="email" autoFocus className="mt-1.5" aria-invalid={Boolean(errors.email)} {...form.register("email")} />
            <FieldError message={errors.email?.message} />
          </div>
          <Button type="submit" className="w-full" disabled={isSubmitting}>
            {isSubmitting && <Spinner />} Send reset link
          </Button>
        </form>
      )}
      <p className="mt-6 text-center text-sm">
        <Link to="/login" className="font-semibold text-link hover:underline">
          Back to sign in
        </Link>
      </p>
    </AuthCard>
  );
}

export function ResetPage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(token ? null : "This reset link is missing its token.");
  const form = useForm<z.infer<typeof resetSchema>>({ resolver: zodResolver(resetSchema), defaultValues: { password: "", confirm: "" } });
  const { errors, isSubmitting } = form.formState;
  return (
    <AuthCard title="Choose a new password" subtitle="Signing in again is required on every device afterwards.">
      <form
        noValidate
        className="space-y-4"
        onSubmit={form.handleSubmit(async ({ password }) => {
          setError(null);
          try {
            await resetPassword(token, password);
            markSignedOut(queryClient);
            toast.success("Password changed. Sign in with your new password.");
            navigate("/login");
          } catch (err) {
            setError(messageOf(err, "The password could not be changed."));
          }
        })}
      >
        <FormError message={error} />
        <div>
          <Label htmlFor="password">New password</Label>
          <Input id="password" type="password" autoComplete="new-password" autoFocus className="mt-1.5" aria-invalid={Boolean(errors.password)} {...form.register("password")} />
          <FieldError message={errors.password?.message} />
        </div>
        <div>
          <Label htmlFor="confirm">Confirm new password</Label>
          <Input id="confirm" type="password" autoComplete="new-password" className="mt-1.5" aria-invalid={Boolean(errors.confirm)} {...form.register("confirm")} />
          <FieldError message={errors.confirm?.message} />
        </div>
        <Button type="submit" className="w-full" disabled={isSubmitting || !token}>
          {isSubmitting && <Spinner />} Change password
        </Button>
      </form>
    </AuthCard>
  );
}

export function VerifyPage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const queryClient = useQueryClient();
  const [state, setState] = useState<"working" | "done" | "failed">(token ? "working" : "failed");
  const [error, setError] = useState<string>("This verification link is missing its token.");
  const started = useRef(false);

  useEffect(() => {
    if (!token || started.current) return;
    started.current = true;
    verifyEmail(token)
      .then(() => {
        setState("done");
        void queryClient.invalidateQueries({ queryKey: keys.me });
      })
      .catch((err) => {
        setError(messageOf(err, "This verification link is invalid or has expired."));
        setState("failed");
      });
  }, [token, queryClient]);

  return (
    <AuthCard title="Confirm your email">
      {state === "working" && (
        <p className="flex items-center gap-2 text-sm text-muted">
          <Spinner /> Confirming…
        </p>
      )}
      {state === "done" && (
        <div className="flex gap-3 rounded-btn border bg-card-alt p-4 text-sm">
          <CheckCircle2 className="h-5 w-5 shrink-0 text-green" />
          <p>Your email address is confirmed.</p>
        </div>
      )}
      {state === "failed" && <FormError message={error} />}
      <Button asChild className="mt-5 w-full">
        <Link to="/">Continue to ClassWizard</Link>
      </Button>
    </AuthCard>
  );
}

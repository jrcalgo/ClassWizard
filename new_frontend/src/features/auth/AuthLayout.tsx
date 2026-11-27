import { X } from "lucide-react";
import { useEffect } from "react";
import { useNavigate } from "react-router-dom";

import { cn } from "@/lib/utils";

/** Centred card over the app; Escape or the close button returns to the planner. */
export function Overlay({ children, wide = false, label }: { children: React.ReactNode; wide?: boolean; label: string }) {
  const navigate = useNavigate();
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && navigate("/");
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [navigate]);
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={label}
      className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-bg/80 p-4 backdrop-blur-sm animate-in fade-in-0"
      onMouseDown={(e) => e.target === e.currentTarget && navigate("/")}
    >
      <div
        className={cn(
          "relative my-auto w-full rounded-card border bg-card shadow-xl animate-in zoom-in-95",
          wide ? "max-w-3xl" : "max-w-md",
        )}
      >
        <button
          type="button"
          aria-label="Close"
          onClick={() => navigate("/")}
          className="absolute right-4 top-4 rounded-btn p-1 text-muted hover:bg-card-alt hover:text-text"
        >
          <X className="h-4 w-4" />
        </button>
        {children}
      </div>
    </div>
  );
}

export function AuthCard({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <Overlay label={title}>
      <div className="p-7 sm:p-8">
        <img src="/classwizard-logo.png" alt="" className="mb-3 h-11 w-11" />
        <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
        <div className="mt-6">{children}</div>
      </div>
    </Overlay>
  );
}

export function FieldError({ message }: { message?: string }) {
  if (!message) return null;
  return <p className="mt-1 text-xs text-danger">{message}</p>;
}

export function FormError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p role="alert" className="rounded-btn border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
      {message}
    </p>
  );
}

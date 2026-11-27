import { FileText, History, Search, Upload, X } from "lucide-react";
import { useRef, useState } from "react";
import { Link } from "react-router-dom";

import { useConfig, useMe, useOccupations, useSavedAudits, useSearches } from "@/api/queries";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioPill } from "@/components/ui/radio-group";
import { Slider } from "@/components/ui/slider";
import { Spinner } from "@/components/ui/spinner";
import { useLoadSavedAudit, useRestoreSearch } from "@/features/history/useRestore";
import { MAX_CAREERS, auditSummary } from "@/lib/plan";
import { cn, formatDateTime } from "@/lib/utils";
import { usePlanStore } from "@/state/planStore";
import type { Priority } from "@/api/types";

import { useRunSearch } from "./useRunSearch";

function Step({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2.5">
      <h3 className="text-sm font-bold">
        <span className="text-green">{n}</span> · {title}
      </h3>
      {children}
    </section>
  );
}

function AuditUpload() {
  const { data: user } = useMe();
  const { data: config } = useConfig();
  const saved = Boolean(user && config?.audit_persistence);
  const pendingFile = usePlanStore((s) => s.pendingFile);
  const filename = usePlanStore((s) => s.filename);
  const setPendingFile = usePlanStore((s) => s.setPendingFile);
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const accept = (file: File | undefined) => {
    if (!file) return;
    if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) return;
    setPendingFile(file);
  };

  const shown = pendingFile?.name ?? filename;
  return (
    <div>
      <div
        role="button"
        tabIndex={0}
        aria-label="DegreeWorks audit (PDF)"
        onClick={() => input.current?.click()}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && input.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          accept(e.dataTransfer.files[0]);
        }}
        className={cn(
          "flex cursor-pointer flex-col items-center gap-1.5 rounded-zone border-2 border-dashed bg-card-alt px-3 py-4 text-center text-sm transition-colors hover:border-green",
          dragging && "border-green bg-green/10",
        )}
      >
        <Upload className="h-5 w-5 text-green" />
        <span className="font-semibold">Drop your DegreeWorks PDF or browse</span>
        <span className="text-xs text-muted">
          {saved
            ? "Saved to your account, encrypted. Delete it any time from Account."
            : "Kept for this page only. A refresh discards the parsed audit."}
        </span>
        <input
          ref={input}
          type="file"
          accept="application/pdf,.pdf"
          className="hidden"
          onChange={(e) => {
            accept(e.target.files?.[0]);
            e.target.value = "";
          }}
        />
      </div>
      {shown && (
        <div className="mt-2 flex items-center gap-2 rounded-btn border bg-card px-2.5 py-1.5 text-xs">
          <FileText className="h-3.5 w-3.5 shrink-0 text-green" />
          <span className="truncate font-medium">{shown}</span>
          <span className="ml-auto shrink-0 text-muted">{pendingFile ? "ready" : "loaded"}</span>
          {pendingFile && (
            <button
              type="button"
              aria-label="Remove file"
              className="shrink-0 text-muted hover:text-text"
              onClick={() => setPendingFile(null)}
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function SavedAuditPicker() {
  const { data: user } = useMe();
  const { data: audits } = useSavedAudits(Boolean(user));
  const auditId = usePlanStore((s) => s.auditId);
  const pendingFile = usePlanStore((s) => s.pendingFile);
  const load = useLoadSavedAudit();
  if (!user || !audits?.length) return null;
  return (
    <details className="group rounded-btn border bg-card-alt text-sm">
      <summary className="cursor-pointer select-none px-3 py-2 font-semibold">Or use a saved audit ({audits.length})</summary>
      <ul className="max-h-40 space-y-1 overflow-y-auto px-2 pb-2">
        {audits.map((a) => {
          const active = a.id === auditId && !pendingFile;
          return (
            <li key={a.id}>
              <button
                type="button"
                onClick={() => load(a.id, a.filename)}
                className={cn(
                  "w-full rounded-md px-2 py-1.5 text-left hover:bg-card",
                  active && "bg-selection text-on-selection hover:bg-selection",
                )}
              >
                <span className="block truncate font-medium">{a.filename ?? "Audit"}</span>
                <span className={cn("block text-xs", active ? "opacity-80" : "text-muted")}>
                  {a.summary.major ?? "Audit"} · {formatDateTime(a.created_at)}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </details>
  );
}

function CareerMenu() {
  const { data, isLoading, error } = useOccupations();
  const selected = usePlanStore((s) => s.selectedCareers);
  const toggleCareer = usePlanStore((s) => s.toggleCareer);
  const count = Object.keys(selected).length;
  const full = count >= MAX_CAREERS;

  if (isLoading)
    return (
      <div className="flex items-center gap-2 text-sm text-muted">
        <Spinner /> Loading careers…
      </div>
    );
  if (error || !data) return <p className="text-sm text-danger">Occupations are unavailable.</p>;

  return (
    <div className="space-y-2">
      <Accordion type="multiple" className="space-y-1.5">
        {data.categories.map((category) => {
          const picked = category.occupations.filter((o) => selected[o.soc_code]).length;
          return (
            <AccordionItem key={category.name} value={category.name}>
              <AccordionTrigger>
                <span>
                  {category.name} ({category.occupations.length})
                  {picked > 0 && <span className="ml-1.5 text-xs font-bold text-green">· {picked} selected</span>}
                </span>
              </AccordionTrigger>
              <AccordionContent className="space-y-1">
                {category.occupations.map((occupation) => {
                  const checked = Boolean(selected[occupation.soc_code]);
                  const id = `occ_${occupation.soc_code}`;
                  return (
                    <div
                      key={occupation.soc_code}
                      className={cn(
                        "flex items-start gap-2 rounded-md px-1.5 py-1",
                        checked && "bg-selection/15",
                      )}
                    >
                      <Checkbox
                        id={id}
                        checked={checked}
                        disabled={!checked && full}
                        onCheckedChange={(v) => toggleCareer(occupation, v === true)}
                        className="mt-0.5"
                      />
                      <label htmlFor={id} className={cn("cursor-pointer text-sm leading-5", !checked && full && "opacity-50")}>
                        {occupation.title}
                      </label>
                    </div>
                  );
                })}
              </AccordionContent>
            </AccordionItem>
          );
        })}
      </Accordion>
      <p className="text-xs text-muted">
        {count} career(s) selected{full ? ` · up to ${MAX_CAREERS}` : ""}
      </p>
    </div>
  );
}

function Preferences() {
  const credits = usePlanStore((s) => s.credits);
  const includeSummer = usePlanStore((s) => s.includeSummer);
  const priority = usePlanStore((s) => s.priority);
  const setCredits = usePlanStore((s) => s.setCredits);
  const setIncludeSummer = usePlanStore((s) => s.setIncludeSummer);
  const setPriority = usePlanStore((s) => s.setPriority);
  return (
    <div className="space-y-4">
      <div>
        <div className="flex items-center justify-between">
          <Label htmlFor="credits">Credits per semester</Label>
          <span className="text-sm font-bold tabular-nums text-green">{credits}</span>
        </div>
        <Slider
          id="credits"
          aria-label="Credits per semester"
          min={3}
          max={18}
          step={1}
          value={[credits]}
          onValueChange={([v]) => setCredits(v)}
        />
        <div className="flex justify-between text-[11px] text-muted">
          <span>3</span>
          <span>18</span>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <Checkbox id="summer" checked={includeSummer} onCheckedChange={(v) => setIncludeSummer(v === true)} />
        <Label htmlFor="summer" className="cursor-pointer font-medium">
          Include summer terms
        </Label>
      </div>
      <div className="space-y-2">
        <Label>Priority</Label>
        <RadioGroup
          value={priority}
          onValueChange={(v) => setPriority(v as Priority)}
          className="flex flex-wrap gap-2"
          aria-label="Priority"
        >
          <RadioPill value="Finish sooner">Finish sooner</RadioPill>
          <RadioPill value="Close skill gaps">Close skill gaps</RadioPill>
        </RadioGroup>
      </div>
    </div>
  );
}

function RecentSearches() {
  const { data: user } = useMe();
  const { data: searches } = useSearches(Boolean(user), 5);
  const restore = useRestoreSearch();
  const [busy, setBusy] = useState<string | null>(null);
  if (!user) return null;
  return (
    <section className="space-y-2 border-t pt-4">
      <div className="flex items-center justify-between">
        <h3 className="flex items-center gap-1.5 text-sm font-bold">
          <History className="h-4 w-4 text-green" /> Recent searches
        </h3>
        <Link to="/account/history" className="text-xs font-semibold text-link hover:underline">
          View all
        </Link>
      </div>
      {!searches?.length ? (
        <p className="text-xs text-muted">Your searches will appear here.</p>
      ) : (
        <ul className="space-y-1">
          {searches.map((s) => (
            <li key={s.id}>
              <button
                type="button"
                disabled={busy !== null}
                onClick={async () => {
                  setBusy(s.id);
                  await restore(s.id);
                  setBusy(null);
                }}
                className="flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-card-alt disabled:opacity-60"
              >
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium">
                    {(s.prefs.careers ?? []).map((c) => c.title).join(", ") || s.soc_codes.join(", ")}
                  </span>
                  <span className="block text-xs text-muted">{formatDateTime(s.created_at)}</span>
                </span>
                {busy === s.id && <Spinner className="mt-0.5" />}
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function SearchMenu() {
  const open = usePlanStore((s) => s.menuOpen);
  const audit = usePlanStore((s) => s.audit);
  const searching = usePlanStore((s) => s.searching);
  const runSearch = useRunSearch();

  return (
    <aside
      id="search-menu"
      aria-label="Search preferences"
      aria-hidden={!open}
      className={cn(
        "h-full shrink-0 overflow-hidden border-r bg-card transition-[width] duration-200 ease-out",
        open ? "w-full sm:w-[340px]" : "w-0 border-r-0",
        // On phones the menu covers the canvas instead of squeezing it.
        "absolute inset-y-0 left-0 z-30 sm:static",
      )}
    >
      <div className={cn("flex h-full w-full flex-col sm:w-[340px]", !open && "invisible")}>
        <div className="min-h-0 flex-1 space-y-5 overflow-y-auto p-4">
          <Step n={1} title="Upload your audit">
            <AuditUpload />
            <SavedAuditPicker />
          </Step>
          <Step n={2} title="Choose target careers">
            <CareerMenu />
          </Step>
          <Step n={3} title="Set your preferences">
            <Preferences />
          </Step>
          {audit && <p className="rounded-btn border border-green/40 bg-green/10 p-3 text-xs leading-5">{auditSummary(audit)}</p>}
          <RecentSearches />
        </div>
        <div className="shrink-0 border-t bg-card p-4">
          <Button className="w-full" size="lg" onClick={() => void runSearch()} disabled={searching}>
            {searching ? <Spinner /> : <Search />}
            {searching ? "Searching…" : "Search"}
          </Button>
        </div>
      </div>
    </aside>
  );
}

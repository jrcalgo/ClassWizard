import { PanelRightClose } from "lucide-react";

import { useConceptMapCourses } from "@/api/queries";
import type { Audit, AuditCourse } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { SKILL_GAPS, TERMS, auditSummary, bestOccupation, matchLabel, scoreCaption } from "@/lib/plan";
import { mapKey } from "@/lib/utils";
import { usePlanStore } from "@/state/planStore";

function SampleNote({ children }: { children: string }) {
  return <p className="mb-3 text-xs text-muted">{children}</p>;
}

function Recommended() {
  const plan = usePlanStore((s) => s.plan);
  const openConceptMap = usePlanStore((s) => s.openConceptMap);
  const { data: mapCourses = [] } = useConceptMapCourses();
  const available = new Set(mapCourses);
  if (!plan) return null;
  if (plan.recommendError) {
    return <p className="rounded-btn border bg-card-alt p-3 text-sm">{plan.recommendError}</p>;
  }
  const result = plan.recommendation;
  const rows = result?.recommendations ?? [];
  if (!result || !rows.length) {
    return <p className="text-sm text-muted">No still-needed courses with a named course code were found in this audit.</p>;
  }
  const titles = Object.fromEntries(result.occupations.map((o) => [o.soc_code, o.title]));
  const top = rows[0].score;
  const unmatched = result.unmatched.map((u) => u.code);
  return (
    <div className="space-y-3">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted">{scoreCaption(result)}</p>
      <ol className="space-y-2.5">
        {rows.map((row) => {
          const best = bestOccupation(row);
          const hasMap = available.has(mapKey(row.code));
          const unmet = (row.prerequisites ?? []).filter((p) => !p.met).map((p) => p.code);
          return (
            <li key={row.code} className="rounded-btn border bg-card-alt p-3 text-sm">
              <div className="flex flex-wrap items-baseline gap-x-2">
                {hasMap ? (
                  <Button
                    variant="tertiary"
                    title="Show this course's concept map"
                    onClick={() => openConceptMap(mapKey(row.code))}
                  >
                    {row.code}
                  </Button>
                ) : (
                  <strong>{row.code}</strong>
                )}
                <span>
                  {row.title} · {row.credits} cr
                </span>
              </div>
              <p className="mt-1 text-muted">
                {matchLabel(row.score, top)} for {best ? (titles[best] ?? best) : "selected careers"} · satisfies{" "}
                {row.requirement_blocks.length ? row.requirement_blocks.join(", ") : "a listed requirement"}
              </p>
              {unmet.length > 0 && (
                <p className="mt-1 text-xs text-muted">
                  Prerequisites not found in your audit: {unmet.join(", ")}. An alternative course may already satisfy
                  them.
                </p>
              )}
            </li>
          );
        })}
      </ol>
      {unmatched.length > 0 && (
        <p className="text-xs text-muted">
          Not in the {result.catalog ?? "loaded"} catalog: {unmatched.join(", ")}
        </p>
      )}
    </div>
  );
}

function Sequence() {
  return (
    <div>
      <SampleNote>Sample sequence; not yet generated from your audit.</SampleNote>
      <div className="grid gap-2.5 sm:grid-cols-2">
        {TERMS.map((term) => (
          <article key={term.term} className="rounded-btn border bg-card-alt p-3">
            <h4 className="mb-1.5 text-sm font-bold">{term.term}</h4>
            {term.courses.map(([code, title, credits]) => (
              <p key={code} className="mb-1 text-sm">
                <strong className="block">{code}</strong>
                <span className="text-muted">
                  {title} · {credits} cr
                </span>
              </p>
            ))}
          </article>
        ))}
      </div>
    </div>
  );
}

function SkillGaps() {
  return (
    <div>
      <SampleNote>Sample data: not yet computed from your audit.</SampleNote>
      <div className="space-y-2">
        {SKILL_GAPS.map((gap) => (
          <div key={gap.skill} className="grid grid-cols-3 gap-2 rounded-btn border bg-card-alt p-3 text-sm">
            <div>
              <span className="block text-[11px] font-semibold uppercase tracking-wide text-muted">Skill</span>
              {gap.skill}
            </div>
            <div>
              <span className="block text-[11px] font-semibold uppercase tracking-wide text-muted">Level</span>
              {gap.current} → {gap.target}
            </div>
            <div>
              <span className="block text-[11px] font-semibold uppercase tracking-wide text-muted">Course</span>
              {gap.course}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function CourseList({ title, courses }: { title: string; courses: AuditCourse[] }) {
  if (!courses.length) return null;
  return (
    <section>
      <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">
        {title} ({courses.length})
      </h4>
      <ul className="divide-y rounded-btn border bg-card-alt text-sm">
        {courses.map((c, i) => (
          <li key={`${c.code}-${i}`} className="flex gap-2 px-3 py-1.5">
            <strong className="shrink-0">{c.code}</strong>
            <span className="truncate text-muted">{c.title}</span>
            {c.grade && <span className="ml-auto shrink-0 text-xs text-muted">{c.grade}</span>}
          </li>
        ))}
      </ul>
    </section>
  );
}

function AuditTab({ audit }: { audit: Audit | null }) {
  if (!audit) return <p className="text-sm text-muted">No audit loaded.</p>;
  return (
    <div className="space-y-3">
      <p className="rounded-btn border bg-card-alt p-3 text-sm">{auditSummary(audit)}</p>
      <CourseList title="In progress" courses={audit.courses_in_progress ?? []} />
      <CourseList title="Preregistered" courses={audit.courses_preregistered ?? []} />
      <CourseList title="Completed" courses={audit.courses_completed ?? []} />
      {(audit.courses_not_taken ?? []).length > 0 && (
        <section>
          <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">
            Still needed ({audit.courses_not_taken.length})
          </h4>
          <ul className="divide-y rounded-btn border bg-card-alt text-sm">
            {audit.courses_not_taken.map((r, i) => (
              <li key={i} className="px-3 py-1.5">
                <span className="font-semibold">{r.block}</span>
                {r.course_codes?.length ? <span className="text-muted"> · {r.course_codes.join(", ")}</span> : null}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

export function ResultsPanel() {
  const audit = usePlanStore((s) => s.audit);
  const setResultsOpen = usePlanStore((s) => s.setResultsOpen);
  return (
    <aside
      aria-label="Plan results"
      className="flex h-full w-full flex-col border-l bg-card lg:w-[400px]"
    >
      <Tabs defaultValue="recommended" className="flex min-h-0 flex-1 flex-col">
        <div className="flex items-center gap-2 border-b px-3 py-2">
          <TabsList className="flex-1 justify-start overflow-x-auto">
            <TabsTrigger value="recommended">Recommended</TabsTrigger>
            <TabsTrigger value="sequence">Sequence</TabsTrigger>
            <TabsTrigger value="gaps">Skill gaps</TabsTrigger>
            <TabsTrigger value="audit">Audit</TabsTrigger>
          </TabsList>
          <Button variant="ghost" size="icon" aria-label="Hide results" title="Hide results" onClick={() => setResultsOpen(false)}>
            <PanelRightClose />
          </Button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          <TabsContent value="recommended">
            <Recommended />
          </TabsContent>
          <TabsContent value="sequence">
            <Sequence />
          </TabsContent>
          <TabsContent value="gaps">
            <SkillGaps />
          </TabsContent>
          <TabsContent value="audit">
            <AuditTab audit={audit} />
          </TabsContent>
        </div>
      </Tabs>
    </aside>
  );
}

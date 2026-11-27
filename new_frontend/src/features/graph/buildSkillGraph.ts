// Port of _graph_data (frontend/src/app.py): three columns, current courses ->
// courses needed -> careers. A current->needed edge is drawn only where the
// catalog lists the current course as a prerequisite; every needed course
// links to the careers, weighted by how well it scores for each.
import type { Audit, Occupation, Recommendation, RecommendResponse } from "@/api/types";
import { SAMPLE_CURRENT, SAMPLE_NEEDED, matchLabel, occupationScores } from "@/lib/plan";

export type SkillNodeKind = "current" | "needed" | "career";

export interface SkillNodeData extends Record<string, unknown> {
  kind: SkillNodeKind;
  code?: string; // course code, for course nodes
  label: string;
  subtitle?: string;
  detail?: string;
  sample?: boolean;
}

export interface SkillGraphNode {
  id: string;
  column: 0 | 1 | 2;
  row: number;
  data: SkillNodeData;
}

export interface SkillGraphEdge {
  id: string;
  source: string;
  target: string;
  weight: number; // 0..1, drawn as stroke width/opacity
  kind: "prerequisite" | "career";
}

export interface SkillGraph {
  nodes: SkillGraphNode[];
  edges: SkillGraphEdge[];
  sample: boolean;
}

export const DEFAULT_NEEDED = 5;

const nodeId = (kind: SkillNodeKind, key: string) => `${kind}:${key}`;

export function buildSkillGraph(
  result: RecommendResponse | null,
  audit: Audit | null,
  careers: Occupation[],
  neededCount = DEFAULT_NEEDED,
): SkillGraph {
  const rows: Recommendation[] = (result?.recommendations ?? []).slice(0, neededCount);
  const careerNodes: SkillGraphNode[] = careers.map((career, i) => ({
    id: nodeId("career", career.soc_code),
    column: 2,
    row: i,
    data: { kind: "career", label: career.title, subtitle: career.soc_code },
  }));

  if (!rows.length || !audit) {
    return sampleGraph(careerNodes);
  }

  const taken: { code: string; title?: string; status: string }[] = [];
  for (const course of audit.courses_in_progress ?? []) taken.push({ ...course, status: "In progress" });
  for (const course of audit.courses_completed ?? []) taken.push({ ...course, status: "Completed" });
  const prereqCodes = new Set(rows.flatMap((r) => (r.prerequisites ?? []).map((p) => p.code)));
  const maxCurrent = Math.max(3, neededCount);
  const current = taken.filter((c) => prereqCodes.has(c.code)).slice(0, maxCurrent);
  for (const course of taken) {
    if (current.length >= maxCurrent) break;
    if (!current.some((c) => c.code === course.code)) current.push(course);
  }

  const top = rows[0]?.score ?? 0;
  const nodes: SkillGraphNode[] = [
    ...current.map((course, i) => ({
      id: nodeId("current", course.code),
      column: 0 as const,
      row: i,
      data: {
        kind: "current" as const,
        code: course.code,
        label: course.code,
        subtitle: course.title,
        detail: course.status,
      },
    })),
    ...rows.map((row, i) => ({
      id: nodeId("needed", row.code),
      column: 1 as const,
      row: i,
      data: {
        kind: "needed" as const,
        code: row.code,
        label: row.code,
        subtitle: row.title,
        detail: `${matchLabel(row.score, top)} · ${row.credits} cr`,
      },
    })),
    ...careerNodes,
  ];

  const edges: SkillGraphEdge[] = [];
  for (const row of rows) {
    for (const prereq of row.prerequisites ?? []) {
      if (current.some((c) => c.code === prereq.code)) {
        edges.push({
          id: `p:${prereq.code}->${row.code}`,
          source: nodeId("current", prereq.code),
          target: nodeId("needed", row.code),
          weight: 1,
          kind: "prerequisite",
        });
      }
    }
    const scores = occupationScores(row);
    const best = Math.max(0, ...careers.map((c) => scores[c.soc_code] ?? 0));
    for (const career of careers) {
      const score = scores[career.soc_code];
      edges.push({
        id: `c:${row.code}->${career.soc_code}`,
        source: nodeId("needed", row.code),
        target: nodeId("career", career.soc_code),
        weight: best > 0 && score !== undefined ? Math.max(0.15, score / best) : 0.5,
        kind: "career",
      });
    }
  }
  return { nodes, edges, sample: false };
}

function sampleGraph(careerNodes: SkillGraphNode[]): SkillGraph {
  const careers = careerNodes.length
    ? careerNodes
    : [{ id: "career:sample", column: 2 as const, row: 0, data: { kind: "career" as const, label: "Your careers" } }];
  const nodes: SkillGraphNode[] = [
    ...SAMPLE_CURRENT.map((code, i) => ({
      id: nodeId("current", code),
      column: 0 as const,
      row: i,
      data: { kind: "current" as const, code, label: code, sample: true },
    })),
    ...SAMPLE_NEEDED.map((code, i) => ({
      id: nodeId("needed", code),
      column: 1 as const,
      row: i,
      data: { kind: "needed" as const, code, label: code, sample: true },
    })),
    ...careers,
  ];
  const edges: SkillGraphEdge[] = SAMPLE_CURRENT.map((code, i) => ({
    id: `p:${code}->${SAMPLE_NEEDED[i]}`,
    source: nodeId("current", code),
    target: nodeId("needed", SAMPLE_NEEDED[i]),
    weight: 1,
    kind: "prerequisite" as const,
  }));
  for (const needed of SAMPLE_NEEDED) {
    for (const career of careers) {
      edges.push({ id: `c:${needed}->${career.id}`, source: nodeId("needed", needed), target: career.id, weight: 1, kind: "career" });
    }
  }
  return { nodes, edges, sample: true };
}

export const COLUMN_X = [0, 360, 720] as const;
export const ROW_GAP = 96;

/** Columns are centred vertically against the tallest one. */
export function positionFor(node: SkillGraphNode, columnSizes: [number, number, number]): { x: number; y: number } {
  const tallest = Math.max(...columnSizes, 1);
  const offset = ((tallest - columnSizes[node.column]) * ROW_GAP) / 2;
  return { x: COLUMN_X[node.column], y: offset + node.row * ROW_GAP };
}

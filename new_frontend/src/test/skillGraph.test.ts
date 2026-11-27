import type { Recommendation, RecommendResponse } from "@/api/types";
import { buildSkillGraph } from "@/features/graph/buildSkillGraph";

import { audit } from "./fixtures";

const careers = [
  { soc_code: "15-1252.00", title: "Software Developers" },
  { soc_code: "15-2051.00", title: "Data Scientists" },
];

function rec(code: string, score: number, prereqs: string[] = []): Recommendation {
  return {
    code,
    title: code,
    credits: 3,
    requirement_blocks: [],
    score,
    score_by_occupation: { "15-1252.00": score, "15-2051.00": score / 2 },
    prerequisites: prereqs.map((p) => ({ code: p, met: true })),
  };
}

const result = {
  recommendations: [rec("ITSC 3155", 4, ["ITSC 2214"]), rec("ITSC 3160", 3), rec("ITSC 3688", 2)],
  occupations: careers,
  unmatched: [],
} as unknown as RecommendResponse;

describe("buildSkillGraph", () => {
  it("builds three columns from real data", () => {
    const graph = buildSkillGraph(result, audit, careers, 2);
    expect(graph.sample).toBe(false);
    const byColumn = [0, 1, 2].map((c) => graph.nodes.filter((n) => n.column === c).map((n) => n.data.label));
    expect(byColumn[1]).toEqual(["ITSC 3155", "ITSC 3160"]);
    expect(byColumn[2]).toEqual(["Software Developers", "Data Scientists"]);
    // Prerequisites are preferred in the current column.
    expect(byColumn[0][0]).toBe("ITSC 2214");
  });

  it("draws prerequisite edges only where listed, and career edges for every needed course", () => {
    const graph = buildSkillGraph(result, audit, careers, 3);
    const prereq = graph.edges.filter((e) => e.kind === "prerequisite");
    expect(prereq.map((e) => [e.source, e.target])).toEqual([["current:ITSC 2214", "needed:ITSC 3155"]]);
    const career = graph.edges.filter((e) => e.kind === "career");
    expect(career).toHaveLength(3 * careers.length);
    const strongest = career.find((e) => e.id === "c:ITSC 3155->15-1252.00");
    const weaker = career.find((e) => e.id === "c:ITSC 3155->15-2051.00");
    expect(strongest?.weight).toBe(1);
    expect(weaker?.weight).toBeCloseTo(0.5);
  });

  it("falls back to labelled sample data without recommendations", () => {
    const graph = buildSkillGraph(null, audit, careers);
    expect(graph.sample).toBe(true);
    expect(graph.nodes.filter((n) => n.column === 1).map((n) => n.data.label)).toEqual([
      "ITSC 3160",
      "STAT 2122",
      "COMM 2100",
    ]);
  });
});

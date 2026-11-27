import { ApiError } from "@/api/client";
import type { ExplainResponse, PlanPrefs, RecommendResponse } from "@/api/types";
import {
  FALLBACK_SOURCES,
  auditSummary,
  careerLabel,
  chatErrorMessage,
  defaultConceptCourse,
  explainErrorMessage,
  explainMessage,
  matchLabel,
  recommendError,
  recommendationSeed,
  scoreCaption,
  uploadErrorMessage,
} from "@/lib/plan";

import { audit } from "./fixtures";



const prefs: PlanPrefs = {
  filename: "audit.pdf",
  careers: [
    { soc_code: "15-1252.00", title: "Software Developers" },
    { soc_code: "15-2051.00", title: "Data Scientists" },
  ],
  credits: 15,
  include_summer: true,
  priority: "Finish sooner",
};

describe("matchLabel", () => {
  it("uses the 0.85 / 0.6 thresholds relative to the top score", () => {
    expect(matchLabel(4, 4)).toBe("Strong match");
    expect(matchLabel(3.4, 4)).toBe("Strong match");
    expect(matchLabel(3.39, 4)).toBe("Moderate match");
    expect(matchLabel(2.4, 4)).toBe("Moderate match");
    expect(matchLabel(2.39, 4)).toBe("Weaker match");
    expect(matchLabel(1, 0)).toBe("Match");
  });
});

describe("text helpers", () => {
  it("summarises the audit exactly like the Streamlit app", () => {
    expect(auditSummary(audit)).toBe(
      "Computer Science (2024-2025): 60 of 120 credits applied. 1 completed, 1 in progress, 0 preregistered, 1 still needed.",
    );
  });

  it("joins career titles", () => {
    expect(careerLabel({ careers: [prefs.careers[0]] })).toBe("Software Developers");
    expect(careerLabel(prefs)).toBe("Software Developers and Data Scientists");
    expect(careerLabel({ careers: [...prefs.careers, { soc_code: "x", title: "DBAs" }] })).toBe(
      "Software Developers, Data Scientists, and DBAs",
    );
  });

  it("captions the score by scoring method", () => {
    expect(scoreCaption({ scoring_method: "spark_blended" })).toBe("Career rating (0–5)");
    expect(scoreCaption({ scoring_method: "cosine_similarity" })).toBe("Description similarity");
  });

  it("seeds the chat from the top three recommendations", () => {
    const result = {
      recommendations: [
        { code: "A 1", title: "One" },
        { code: "B 2", title: "Two" },
        { code: "C 3", title: "Three" },
        { code: "D 4", title: "Four" },
      ],
    } as RecommendResponse;
    const seed = recommendationSeed(prefs, audit, result);
    expect(seed).toContain("A 1 One, B 2 Two, C 3 Three.");
    expect(seed).not.toContain("D 4");
    expect(recommendationSeed(prefs, audit, null)).toBe(`Parsed audit.pdf. ${auditSummary(audit)}`);
  });
});

describe("error mapping", () => {
  it("maps /recommend failures", () => {
    expect(recommendError(new ApiError(404, "audit not found"))).toBe("The audit expired. Upload it again.");
    expect(recommendError(new ApiError(409, "x"))).toBe("Recommendations are unavailable: course data is still loading.");
    expect(recommendError(new ApiError(422, "the Graduate catalog is not loaded yet"))).toBe(
      "Recommendations are unavailable for this audit: the Graduate catalog is not loaded yet.",
    );
    expect(recommendError(new ApiError(503, "database unavailable"))).toBe(
      "Recommendations are unavailable. database unavailable",
    );
  });

  it("maps upload failures", () => {
    expect(uploadErrorMessage(new ApiError(422, "x"))).toBe("That PDF could not be read as a DegreeWorks audit.");
    expect(uploadErrorMessage(new ApiError(503, "x"))).toBe("The audit could not be saved.");
  });

  it("falls back to evidence when the model is down", () => {
    const evidence = [1, 2, 3, 4].map((i) => ({ id: `e${i}`, kind: "course", text: `t${i}` }));
    const message = explainErrorMessage(new ApiError(503, "language model unavailable", { evidence }));
    expect(message.content).toMatch(/language model is unavailable/);
    expect(message.sources).toHaveLength(FALLBACK_SOURCES);
  });

  it("maps 404 and timeouts for both chat modes", () => {
    for (const map of [explainErrorMessage, chatErrorMessage]) {
      expect(map(new ApiError(404, "audit not found")).content).toBe(
        "The audit is gone. Upload the DegreeWorks PDF again.",
      );
      expect(map(new ApiError(0, "timed out")).content).toBe("The reply timed out.");
      expect(map(new ApiError(500, "boom")).content).toBe("The reply could not be generated. boom");
    }
  });
});

describe("explainMessage", () => {
  const evidence = [
    { id: "c1", kind: "course", text: "course fact" },
    { id: "k1", kind: "career", text: "career fact" },
    { id: "n1", kind: "note", text: "note" },
    { id: "n2", kind: "note", text: "note 2" },
  ];
  it("keeps only cited sources when grounded", () => {
    const payload = { answer: "Because [c1].", citations: ["c1", "zz"], grounded: true, evidence } as ExplainResponse;
    const message = explainMessage(payload);
    expect(message.content).toBe("Because [c1].");
    expect(message.sources?.map((s) => s.id)).toEqual(["c1"]);
  });
  it("replaces ungrounded answers with the top evidence", () => {
    const payload = { answer: "Made up.", citations: [], grounded: false, evidence } as unknown as ExplainResponse;
    const message = explainMessage(payload);
    expect(message.content).toMatch(/could not be checked/);
    expect(message.sources).toHaveLength(FALLBACK_SOURCES);
  });
});

describe("defaultConceptCourse", () => {
  const courses = ["AAHP_3701", "ITSC_2214", "ITSC_3160", "ITSC_3155"];
  it("prefers recommendations, then audit courses, then ITSC 3160", () => {
    expect(defaultConceptCourse(courses, { recommendations: [{ code: "ITSC 3155" }] } as RecommendResponse, audit)).toBe(
      "ITSC_3155",
    );
    expect(defaultConceptCourse(courses, null, audit)).toBe("ITSC_2214");
    expect(defaultConceptCourse(courses, null, null)).toBe("ITSC_3160");
    expect(defaultConceptCourse(["AAHP_3701"], null, null)).toBe("AAHP_3701");
    expect(defaultConceptCourse([], null, null)).toBeNull();
  });
});

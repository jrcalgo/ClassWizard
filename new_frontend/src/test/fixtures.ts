import type { Audit } from "@/api/types";

export const audit: Audit = {
  major: "Computer Science",
  catalog_year: "2024-2025",
  credits_applied: 60,
  credits_required: 120,
  courses_completed: [{ code: "ITSC 1212", title: "Intro to Computer Science I" }],
  courses_in_progress: [{ code: "ITSC 2214", title: "Data Structures" }],
  courses_preregistered: [],
  courses_not_taken: [{ block: "Major", text: "", course_codes: ["ITSC 3155"] }],
};

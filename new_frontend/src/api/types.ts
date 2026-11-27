// Shapes returned by the FastAPI backend (backend/main.py, ai/recommendations/ranking.py,
// data/degreeworks/parser.py, backend/accounts/routes.py).

export interface AuditCourse {
  code: string;
  title?: string;
  grade?: string;
  credits?: number | string;
  term?: string;
}

export interface AuditRequirement {
  block: string;
  text: string;
  course_codes: string[];
}

export interface Audit {
  degree?: string;
  audit_date?: string;
  level?: string;
  classification?: string;
  program?: string;
  major: string;
  college?: string;
  catalog_year: string;
  credits_required: number | string;
  credits_applied: number | string;
  courses_completed: AuditCourse[];
  courses_in_progress: AuditCourse[];
  courses_preregistered: AuditCourse[];
  courses_not_taken: AuditRequirement[];
}

export interface AuditResponse {
  session_id: string;
  audit: Audit;
  audit_id?: string | null;
}

export interface Occupation {
  soc_code: string;
  title: string;
}

export interface OccupationsResponse {
  categories: { name: string; occupations: Occupation[] }[];
}

export type ScoringMethod = "cosine_similarity" | "spark_hybrid" | "spark_blended";

export interface Recommendation {
  code: string;
  title: string;
  credits: number | string;
  requirement_blocks: string[];
  score: number;
  score_by_occupation?: Record<string, number>;
  similarity_by_occupation?: Record<string, number>;
  scoring_method?: ScoringMethod;
  prerequisites?: { code: string; met: boolean }[];
}

export interface RecommendResponse {
  session_id: string;
  search_id?: string | null;
  catalog?: string;
  model?: string;
  scoring_method?: ScoringMethod;
  occupations: Occupation[];
  recommendations: Recommendation[];
  unmatched: { code: string; requirement_blocks?: string[] }[];
  candidate_count?: number;
}

export interface Evidence {
  id: string;
  kind: "course" | "career" | "note" | "skill_match" | string;
  text: string;
  label?: string;
  course_code?: string;
  soc_code?: string;
}

export interface ExplainResponse {
  session_id: string;
  answer: string;
  citations: string[];
  unknown_citations: string[];
  grounded: boolean;
  evidence: Evidence[];
  model?: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  sources?: Evidence[] | null;
}

export type Priority = "Finish sooner" | "Close skill gaps";

/** The preferences captured when Search was pressed (same shape as the Streamlit prefs). */
export interface PlanPrefs {
  filename: string;
  careers: Occupation[];
  credits: number;
  include_summer: boolean;
  priority: Priority;
}

export interface AppConfig {
  chat_mode: "explain" | "chat";
  google_enabled: boolean;
  email_enabled: boolean;
  audit_persistence: boolean;
}

export interface User {
  id: string;
  email: string;
  display_name: string | null;
  email_verified: boolean;
  has_password: boolean;
  google_linked: boolean;
  created_at: string | null;
}

export interface AuditSummary {
  major?: string;
  catalog_year?: string;
  credits_applied?: number | string;
  credits_required?: number | string;
  courses_completed_count?: number;
  courses_in_progress_count?: number;
  courses_preregistered_count?: number;
  courses_not_taken_count?: number;
}

export interface SavedAudit {
  id: string;
  filename: string | null;
  summary: AuditSummary;
  created_at: string;
}

export interface SavedSearch {
  id: string;
  audit_id: string | null;
  soc_codes: string[];
  prefs: Partial<PlanPrefs>;
  audit_summary: AuditSummary | null;
  message_count: number;
  created_at: string;
  recommendation?: RecommendResponse | null;
}

export interface RestoreResponse {
  session_id: string;
  audit: Audit;
  audit_id: string;
  search: SavedSearch & { recommendation: RecommendResponse | null };
  messages: ChatMessage[];
}

export interface ActivityEvent {
  id: number;
  event: string;
  detail: Record<string, unknown>;
  ip: string | null;
  user_agent: string | null;
  created_at: string;
}

export interface ConceptNode {
  id: string;
  label: string;
  type: string;
  status: "verified" | "inferred" | string;
  occurrences: number;
}

export interface ConceptEdge {
  id: string;
  source: string;
  target: string;
  predicate: string;
  order_evidence: string | null;
  flags: string | null;
}

export interface ConceptMap {
  course: string;
  nodes: ConceptNode[];
  edges: ConceptEdge[];
}

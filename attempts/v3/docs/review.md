# V3 final deep review

Reassessed the preserved V1 and V2 reviews, their measured failures, source preparation,
normalized schema, import transactions, query plans, Redis scripts, solver, AI calls,
frontend inputs and Docker operation. Reviewed V3's changes and final verification artifacts.
V1's 59 and V2's 68 checksummed files still match their preservation manifests.

## Final scope and data verification

- Active public dataset: `388774660f9cc53ac1c8`; the prepared transformation hash and all
  nine raw-source SHA-256 values verify. There are 3,729 course records, four occupations,
  68 skill/knowledge elements and 306 active public embedding chunks.
- Program evidence points to PDF pages 203–204, printed pages 190–191. The selected
  concentration follows the catalog's official name. Unknown conditions are preserved,
  including the ITSC 3990 punctuation case and unresolved ITSC 4155 references.
- A final source comparison caught variable technical electives satisfying course count
  without the six-credit minimum. V3 now enforces technical electives (two/six credits),
  concentration electives (three/nine credits) and three capstone credits. The qualification
  begun before that correction was stopped and excluded from the final reports.
- Science choices require two lectures and a matching or integrated laboratory. Requirement
  allocations cannot double-count a course. The GPA confirmation covers the lower of overall
  and major GPA; in-progress credits are added separately from earned applied credits.
- There are 2,703 unresolved rules and two quarantined references. These are limitations of
  the source review scope, not hidden eligible records. Real worksheet validation remains zero.

## Functional and operational evidence

- **36 backend tests passed** against PostgreSQL and memory-only Redis: prerequisite/grade/
  corequisite cases, pins, deadlines, credit choices, allocation, independent plan verification,
  parser ambiguity, invalid AI output, privacy/isolation, deletion races, rollback, idempotency,
  source activation and cache-generation invalidation.
- **Four browser tests passed**, covering the complete synthetic academic-to-plan workflow, responsive search,
  reload/session restoration, unsaved-edit protection and canonical variable-credit entry.
  Frontend production builds passed. Semester cards expose prerequisite and requirement
  rationale with page-linked evidence; upload feedback lists unresolved and remaining candidates.
- Redis restart discarded a synthetic ephemeral probe, and the worker reconnected. PostgreSQL
  restart recovered through connection-pool health checks. A synthetic interrupted explanation
  claim was requeued and completed in local-LLM mode, then its session/job was deleted.
- Public and private work use separate workers. Explanation claims are bounded, revision-checked
  and recoverable. Student state, private caches and job results remain exclusively in volatile
  Redis; uploads and proxy request/response buffers remain in memory. Access logs are disabled.
- Source-update checks record public release metadata but require reviewed activation for new
  academic rules. Dependencies, main/transient image digests and model identities are recorded.
  Hosted CI execution is unverified; its local equivalent checks passed.

## Database and AI measurements

The final cold public hydration was 58.1 ms; subsequent warm reads were 0.32–0.50 ms.
Ten calls used 17 instrumented application statements. Driver health pings are additional;
request-latency measurements include their overhead. Final SQL execution plans measured
approximately 0.96 ms for versioned course reads, 2.60 ms for skill joins and 1.18 ms for
small-corpus exact retrieval. Immutable public caches and direct serialized private responses
remove repeated hydration and generic encoding while preserving version/revision checks.

The 10,000-course/100,000-chunk synthetic benchmark measured exact search at 118.8 ms and
HNSW at 12.4 ms, recall@10 and filtered recall@10 of 0.995, and indexed joins at 3.64 ms.
Rare filters used validated exact fallback. These results qualify that synthetic workload;
they do not establish arbitrary real-corpus recall. Current small-corpus production retrieval
remains exact, with larger ANN retrieval explicitly opt-in.

The final local explanation run completed in 4.04 seconds with a warm model, including
retrieval, and validated its public excerpt/citations. Deterministic private reasoning remains
separate from generated public highlights. Invalid citations, wrong JSON shapes, unavailable
services and unrecognized model identities fall back to deterministic explanations.

## Sustained qualification

Each of three repetitions used twenty isolated synthetic sessions, 120 seconds of warmup
and 600 seconds of measurement, alternating recommendations and plans. Five-minute cache
expiry/regeneration was included. Application limits were six CPUs and 7.75 GiB; the load
generator was a separate tools container. No ingestion, service restarts, model generation
or vector-index construction ran during qualification.

| Run | Recommendation p95 | Plan p95 | Requests/s | Measured requests | Errors / invalid plans |
|---|---:|---:|---:|---:|---|
| 1 | 124.0 ms | 123.1 ms | 326.3 | 195,806 | 0 / 0 |
| 2 | 166.8 ms | 167.2 ms | 229.1 | 137,430 | 0 / 0 |
| 3 | 164.7 ms | 163.0 ms | 229.3 | 137,596 | 0 / 0 |

All targets passed: recommendation p95 ≤500 ms, planning p95 ≤2,000 ms, zero errors and
zero invalid successful plans. Total measured requests: **470,832**. Raw reports, summaries,
environment details, SQL plans, vector results and AI evidence are retained in this directory.
V1/V2's shorter exploratory tests are not presented as full-duration certifications.

## Practical limits

Only the selected 2026–2027 Computer Science path and four careers are in scope. Real
DegreeWorks layouts, actual offerings, skill-proficiency accuracy, residency/attempt-limit
verification and broader academic paths require further validation. The bounded solver does
not claim globally optimal graduation timing. Advisor confirmations remain explicit inputs.
All academic test data is synthetic; no real worksheets or Git mutation commands were used.
V3 remains available on localhost:8083; V1/V2 remain preserved separately.

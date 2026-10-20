# Three sequential ClassWizard MVP attempts

## Shared scope and completion criteria

Each attempt implements the same end-to-end workflow: acquired public catalog and O*NET data;
profiled, normalized and versioned public storage; synthetic/user-supplied worksheet parsing;
manual academic review; career and planning preferences; constraint-first recommendations and
semester planning; public evidence retrieval; asynchronous explanations; session deletion; a
usable frontend; repeatable local Docker deployment; and measured database operations.

The supported initial academic path is Computer Science BS, Web/Mobile Development and Software
Engineering. Four O*NET occupations provide the initial career scope. Real DegreeWorks validation
requires a user-provided worksheet and remains explicitly unverified until then. No university-login
automation or persistent student data is included.

Public ingestion must be transactional, idempotent and source-versioned. Prerequisites, grades,
corequisites, standing, requirement allocations, pins and semester load limits are hard constraints.
Ambiguity must block planning or require an explicit confirmation. Generated explanations cannot
change eligibility or schedules. Local pretrained embeddings and a local language model provide
AI support; deterministic explanations are available when generation fails validation.

Performance qualification uses twenty independent synthetic sessions, recommendations and plans,
two minutes of warmup and ten minutes of measurement per repetition, repeated three times for the
final attempt. Targets are recommendation p95 ≤500 ms and planning p95 ≤2,000 ms, with zero failed
requests and zero invalid successful plans. AI latency is separate. Synthetic vector qualification
uses 10,000 courses and 100,000 384-dimensional chunks, comparing exact and HNSW latency and recall.
Current small-corpus retrieval remains exact; synthetic recall does not establish real-world quality.

## Attempt 1 — establish the complete baseline

1. Acquire source snapshots and retain URLs, versions, hashes, page evidence and attribution.
2. Parse course headings, credits and selected-path rules; retain unresolved references and profile
   actual counts, distributions, duplicates, missing metadata and irregular text.
3. Implement normalized PostgreSQL/pgvector storage, Alembic migrations and atomic activation.
4. Implement memory-only PDF parsing, reviewable session state, constraints, recommendations,
   semester planning, public embeddings, async explanations and the complete React workflow.
5. Test real database/cache behavior and browser workflows; measure hydration, query plans,
   concurrency and local AI behavior. Record capacity failures as failures.
6. Deeply review the entire attempt, write `docs/review.md`, checksum its contents, then create V2.

## Attempt 2 — apply evidence from V1

Reassess V1 code, data, schema, solver, lifecycle, UI and measurements before any successor changes.
Retain the complete shared workflow and improve the measured bottlenecks:

1. Replace repeated link scans with indexed grouping and immutable public snapshots keyed by version.
2. Add revision/version-aware private result caching and atomic Redis state, result and deletion logic.
3. Use PostgreSQL COPY staging while retaining integrity checks, rollback and atomic activation.
4. Reuse public embeddings by model/content identity and publish provenance-bearing semantic estimates.
5. Improve elective inputs, ranking semantics, bounded-search outcomes and worker reconnection.
6. Measure cold/warm SQL operations, repeated exploratory traffic and synthetic vector scale/recall.
7. Deeply review V2, distinguish unresolved defects from verified improvements, checksum and create V3.

## Attempt 3 — validate and complete the final MVP

Reassess V1 and V2 findings, especially response encoding, ambiguous source rules, science allocation,
LLM evidence failures and missing operational checks. Retain the workflow and implement:

1. Direct serialized cache responses, bounded previews, explicit totals and paginated review endpoints.
2. Conservative condition extraction, correct page provenance, science/laboratory constraints and a
   separate validator for every successfully generated semester plan.
3. Thread-bounded embeddings, isolated public/private workers, recoverable bounded explanation queues,
   constrained cited language-model output and useful deterministic reasoning.
4. Locked Python/npm dependencies, container-image digests, model identity checks, health/readiness,
   privacy-safe metrics, source-update checks, documented migrations and public-version rollback.
5. Prevent unsaved frontend edits from generating stale results, restore saved sessions after reload,
   verify responsive workflows and disable proxy disk buffering for private traffic.
6. Validate source activation/invalidation, deletion races, rollback, restart recovery, query plans,
   vector scale and real local AI. Then run the three full sustained benchmark repetitions.
7. Document measured results, remaining limitations and the final review; checksum V3. Preserve all
   attempts separately and leave V3 available on localhost. Do not run Git mutation commands.

Source updates are checked daily; annual catalog and quarterly O*NET releases are acquired in batches.
New academic rules require review before transactional activation. This review gate is a deliberate
refinement of automatic ETL: schedule public checks without automatically changing degree rules.

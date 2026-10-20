# V2 deep review — gate before V3

Reassessed V1 and reviewed all V2 source, schema/import changes, Redis scripts, caching,
solver changes, frontend changes, worker recovery, AI calls and measurement artifacts.

## Verified improvements

- 24 backend tests passed, including atomic stale-write rejection, final session deletion,
  job registration preserving JSON arrays, single-query warm snapshots, correct degree-
  progress ranking, multiple unrestricted electives and invalid AI citations.
- Both browser tests passed: desktop workflow in 1.4 seconds and mobile search in 0.5 seconds.
- Warm public snapshots now take approximately 0.7–1.8 ms; cold hydration took 126–146 ms.
  Ten calls need 17 queries rather than 70. Course-skill hydration is linear rather than
  scanning the entire link collection for each course.
- Three 20-session exploratory runs produced no failures or invalid plans. Recommendation
  p95 was 908–1,185 ms, and planning p95 was 839–1,034 ms. Planning meets its target;
  recommendations still exceed 500 ms. These 30-second runs are not full-duration certification.
- Public vectors and semantic links are recoverable and idempotent. 306 chunks are available;
  two threshold-qualified semantic estimates supplement 2,414 lexical/alias links.
- Synthetic 10,000-course/100,000-vector benchmark: HNSW mean 11.0 ms versus exact 113.1 ms,
  recall@10 1.0 and filtered recall@10 1.0 on twenty seeded clustered queries. Highly selective
  filters use a validated exact fallback. This does not establish recall on arbitrary corpora.
- COPY staging retains transactional activation and rollback. Redis remains memory-only.

## Remaining defects and exact V3 decisions

1. **Response processing dominates warm requests.** A recommendation response is 252,415
   bytes with 2,606 blocked entries, and generic encoding alone averages 23.5 ms. Return
   serialized JSON directly on cache hits; limit blocked previews and provide indexed,
   paginated rule-review retrieval. Preserve explicit totals and source evidence.
2. **Local explanations still fall back.** The short local LLM call returned after 82 seconds
   but failed output validation. Use constrained JSON output selecting grounded excerpts,
   limit prompt/output further, configure real Torch thread limits, and isolate public
   embedding work from private explanation jobs. Keep deterministic explanations useful.
3. **Source condition extraction misses punctuation variants.** ITSC 3990 has a semicolon
   after its prerequisite heading and was incorrectly treated as unrestricted. Detect
   prerequisite/corequisite/permission conditions conservatively. Correct program PDF-page
   evidence using actual source positions rather than fixed offsets.
4. **Natural-science allocation needs structural validation.** Enforce two approved lecture
   choices plus a matching laboratory, allowing catalog-defined integrated-lab alternatives.
   Add an independent output validator that checks every emitted semester and allocation.
5. **Scale optimization needs bounded deployment.** Keep exact retrieval for the current
   306-chunk corpus. Provide HNSW for larger, explicitly qualified corpora with iterative
   scans and exact fallback; do not equate synthetic recall with real semantic quality.
6. **Complete operations and observability.** Add pinned dependency/model/image manifests,
   health/readiness, public source-update checks, bounded queues and job recovery, documented
   migrations and rollback, and privacy-safe request/database counters.
7. **Certify the final implementation.** Run three full 120-second-warmup/600-second
   measurement repetitions, cold/warm checks, recovery tests, source-version invalidation,
   independent schedule verification and final browser tests. Report limitations explicitly.

An interrupted public mapping pass exposed a PostgreSQL parameter-type issue; explicit
text casting and idempotent mapping retries fixed it before preservation. The first synthetic
HNSW build exceeded its useful in-memory graph budget and was canceled; at 256 MB maintenance
memory the replacement build completed in 90.8 seconds. Both findings informed the final design.

Retain the normalized/versioned public schema, reviewed rule expressions, anonymous ephemeral
sessions, immutable public cache, atomic Redis lifecycle, constraint-first planning and full
browser workflow. No user worksheets or Git mutation commands were used.

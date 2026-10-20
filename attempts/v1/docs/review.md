# V1 deep review — gate before V2

Reviewed the complete API, SQLAlchemy schema and migration, atomic importer, public-source
preparation scripts, constraint solver, PDF parser, session lifecycle, local AI worker,
React views, Docker configuration, test suite, database execution plans and real-service runs.

## Evidence and retained behavior

- Backend: 18 unit/integration tests passed against actual PostgreSQL and Redis.
- Browser: both desktop academic workflow/valid plan and mobile catalog search passed.
- Public data: 3,729 versioned records, four O*NET careers, 68 skills/knowledge elements;
  306 local MiniLM embedding chunks populated in pgvector.
- Database profile: ten snapshots took 813–967 ms; 70 SQL queries took 234 ms in total.
  SQL plans show approximately 1.7 ms course scans, 5 ms skill joins and 2.7 ms exact retrieval.
  The dominant cost is Python hydration and repeatedly scanning all links per course.
- Synthetic degree plan is valid and allocation/credit constraints are exercised. Unknown
  printed prerequisites, transfer thresholds, term offerings and real worksheet compatibility
  are deliberately unresolved rather than guessed.
- Local LLM loaded the 3B model but the 400-token explanation timed out at 90 seconds;
  retrieval returned five public evidence chunks and deterministic fallback worked.

## Findings and next-attempt decisions

1. **High: public snapshots are rebuilt for every operation.** Replace nested link scans
   with keyed grouping, cache immutable public snapshots by active dataset version, and
   keep active-version checking inexpensive. Retain bulk SQL and transaction boundaries.
2. **High: baseline concurrent setup encountered 503 pool-pressure errors.** The original
   load harness also aborted on request errors. Correct the harness to serialize unmeasured
   setup and account for failures; do not disguise baseline capacity failure as a pass.
   Cache student results in Redis with session/version/revision keys and expiry.
3. **High: get/check/save sequences have concurrency gaps.** Use Redis Lua compare-and-set
   for academic changes, result writes and explanation completion; reject stale results.
   Deletion must remain final even when an AI job is finishing.
4. **Medium: worker exits if Redis is restarted.** Add reconnection/backoff and service restart
   policy. Recreating Redis must discard academic state while the application recovers.
5. **Medium: local AI prompt/output bounds exceed the CPU latency budget.** Reduce public
   evidence and generation size; retain async jobs and deterministic fallbacks. Add semantic
   mapping provenance and incremental embedding reuse rather than rerunning unchanged texts.
6. **Medium: elective selection UI exposes only external categories.** Expose multi-option
   groups and preferred courses; preserve manual corrections and prevent stale displayed results.
7. **Medium: bulk import uses individual ORM objects.** Stage public rows with COPY, validate
   references and publish a complete version atomically; keep rollback and idempotency tests.
8. **Medium: solver candidate enumeration has a bound but may report an incomplete bounded
   search as infeasible.** Preserve explicit search-limit outcomes and independently verify
   every emitted schedule. Improve constraint pruning without changing hard constraints.

Startup migration discovery and Nginx root errors were fixed before the browser gate.
Frontend dependencies were updated to patched Vite/Playwright versions; npm audit reports
zero vulnerabilities. No private worksheets were used and no Git mutation commands ran.

V1 is the functional baseline, not a performance-certified release. Baseline concurrency
and AI timeout limitations are explained here and become explicit V2 work items.

# ClassWizard

A local academic and career planning MVP for UNC Charlotte's 2026–2027 Computer Science
BS, Web/Mobile Development and Software Engineering concentration. Three complete attempts
were implemented sequentially, with a written review and preservation gate before each successor.

## Run the final attempt

```bash
cd attempts/v3
docker compose up --build -d
```

Open **http://localhost:8083** and choose **Explore a demo**. The academic profile is synthetic;
the catalog and O*NET snapshots are public, acquired source data. Initial startup may download
the local models. If Docker uses an unavailable Desktop context on this workstation, prefix
commands with `docker -H unix:///var/run/docker.sock`.

The application supports memory-only worksheet upload, manual correction and review, career
selection, preferences and elective choices, eligible course recommendations, semester planning,
estimated skill gaps, cited explanations, catalog search, and session deletion. PostgreSQL and
pgvector hold public information. Redis contains only temporary session information with persistence
disabled. The proxy and parser do not spool private requests or responses to disk.

## The three attempts

| Attempt | Focus | Location | Local port |
|---|---|---|---|
| V1 | Complete functional baseline and measured bottlenecks | [V1](attempts/v1/README.md) | 8081 |
| V2 | Version-aware public cache, atomic Redis lifecycle, COPY ingestion and incremental embeddings | [V2](attempts/v2/README.md) | 8082 |
| V3 | Faster response handling, stricter source rules, independent plan validation and operational verification | [V3](attempts/v3/README.md) | 8083 |

V1 and V2 are preserved and stopped; V3 is the final running implementation. Each has isolated
Compose services, public volumes, source snapshots, prepared data, frontend, backend, tests and
documentation. Earlier attempts are retained for comparison and contain limitations corrected
in later attempts. Checksums establish that the predecessor contents were preserved.

- [Implementation plan](IMPLEMENTATION_PLAN.md)
- [Attempt comparison](attempts/COMPARISON.md)
- [Sprint 1 exploration report](attempts/v3/docs/sprint1.md)
- [Architecture and schema](attempts/v3/docs/architecture.md)
- [V1 review before V2](attempts/v1/docs/review.md)
- [V2 review before V3](attempts/v2/docs/review.md)
- [V3 final review](attempts/v3/docs/review.md)
- [Three-run performance results](attempts/v3/docs/performance.md)

V3 passed three full twenty-session qualification runs: **470,832 measured requests**,
zero errors or invalid plans, recommendation p95 124–167 ms and planning p95 123–168 ms.
The synthetic scale test measured 100,000 vector chunks with recall@10 0.995; real semantic
quality remains a separate validation question. Database, AI and operational evidence are
preserved with the final review.

Run backend checks with `docker compose run --rm --no-deps tests` after initialization. Frontend
checks use `npm ci`, `npm run build`, and Playwright; see the final attempt's README for commands.
The GitHub workflow validates the final attempt's backend, build and browser flow without requiring
AI model downloads. Local benchmarks use actual PostgreSQL/Redis and synthetic student sessions.

Real DegreeWorks layout compatibility and actual semester offerings remain **unverified**. Unknown
catalog rules require review and cannot silently satisfy prerequisites. Plans are proposals for
advisor review; skill mappings describe coursework exposure, not proven proficiency. No Git staging,
commit or push operations are part of this implementation.

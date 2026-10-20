# ClassWizard V3 — final validated MVP

Local academic and career planning for the 2026–2027 Computer Science BS,
Web/Mobile Development and Software Engineering concentration.

Three full qualification runs passed with 470,832 measured requests and no errors/invalid
plans. Recommendation p95 was 124–167 ms and planning p95 123–168 ms. See
`docs/performance.md` and `docs/review.md` for measurements and their scope.

V3 builds on V2's public snapshots, atomic Redis lifecycle, COPY staging and incremental
embeddings. It adds direct serialized responses, bounded/paginated blocked-course output,
indexed catalog lookup, stricter prerequisite extraction, science/lab checks, independent
schedule verification, bounded recoverable explanation jobs, validated local model output,
dependency/model/image locks, source checks and request/database metrics. Its predecessor
review is preserved in `docs/predecessor-review.md`.

## Run

```bash
cd attempts/v3
docker compose up --build -d
```

Open http://localhost:8083. The first run downloads the local embedding and Qwen models.
Click **Explore a demo** for a synthetic student with reviewed elective selections.
For your own profile, upload a text PDF or enter courses manually, review every field,
save the profile and preferences, then generate recommendations and a semester plan.
Public catalog data is real; the demo academic state is synthetic.

PostgreSQL stores public data only. Redis has persistence disabled and no volume;
sessions expire after 60 minutes of inactivity or eight hours total. End-session deletes
academic state and explanation results. PDFs are read in memory without upload spooling.
Use the application on localhost; credentials in Compose are local demonstration defaults.

## Validate

```bash
docker compose run --rm --no-deps tests
docker compose run --rm tests python tools/benchmark.py --seconds 600 --warmup 120 --output /reports/benchmark.json
cd frontend
npm ci
PLAYWRIGHT_BROWSERS_PATH=/tmp/classwizard-browsers npx playwright install chromium
PLAYWRIGHT_BROWSERS_PATH=/tmp/classwizard-browsers npm test
```

The benchmark creates twenty isolated synthetic sessions. Run three repetitions and
compare the reports on the same hardware. AI generation is measured separately using
`docker compose run --rm --no-deps tests python tools/validate_ai.py`.
`tools/profile_db.py` records cold/warm snapshots and `EXPLAIN (ANALYZE, BUFFERS)`.
SQL counters measure instrumented application statements; connection-pool health pings
are additional database operations and are included in end-to-end request latency.
`tools/vector_benchmark.py` uses temporary synthetic scale tables that disappear after
the connection closes. Never run restarts, ingestion or scale-index construction during
latency qualification; those operations change the measured environment.

## Sources and re-ingestion

`data/raw` contains public source snapshots. `data/prepared/dataset.json` is a
versioned, normalized import; `profile.json` records actual profiling results.

```bash
python tools/acquire.py                 # download pinned public sources, requires pdftotext
python tools/prepare.py                 # profile and normalize; stdlib only
docker compose run --rm init            # migrate and transactionally activate new public data
```

To use a locally downloaded public catalog PDF:
`python tools/acquire.py --catalog /path/to/catalog.pdf`.
Review catalog-year and program rules before replacing source releases. The prepared
dataset ID hashes source content and transformations; repeating the import is idempotent.
Unknown prerequisites block planning. Departmental confirmations are explicit inputs.

## API

The FastAPI OpenAPI schema is `/openapi.json` on port 8000 inside the Compose network.
Public endpoints: `GET /api/v1/{status,program,careers,catalog}`.
Private endpoints: `POST /sessions`, `GET|DELETE /session`, `POST /worksheet`,
`PUT /academic-state`, `PUT /preferences`, `POST /recommendations`, `POST /plans`,
`POST /explanations`, and `GET /explanations/{job_id}`, all under `/api/v1`.
Anonymous HttpOnly cookies identify sessions; private API responses use `no-store`.
`GET /api/v1/blocked-courses?offset=100&limit=100` requires a reviewed session and exposes
the remainder of the bounded blocked preview. `GET /api/v1/rule-review` pages public
unresolved rules. `GET /api/v1/health`, `/readiness` and `/metrics` expose service status
and counters without student identifiers. Readiness distinguishes core availability,
public-vector availability and the explanation-worker heartbeat.

The optional external explanation adapter accepts `{ "evidence": [...] }` and returns
`{ "text": "...", "citations": ["ITSC 1212"] }`. Set `EXTERNAL_EXPLANATION_URL`
and `EXTERNAL_EXPLANATION_TOKEN` in the worker environment. It receives public
course evidence only, with no academic state, user preferences, or student identifiers.
The returned text must exactly match an offered public excerpt and cite its course ID;
otherwise the deterministic explanation is used. The local model follows the same rule.
Constraint-based explanation text is built separately from verified recommendation inputs.

## Operations and rollback

The nine running services have a combined limit of **6 CPUs and 7.75 GiB RAM**. Build,
initialization, model download and benchmark containers are separate transient workloads.
Local AI jobs do not hold request database connections while generating. One explanation
worker uses Redis claim/ack lists, requeues interrupted claims on startup, and caps jobs at
five per session and 100 across queued/claimed work. Completed/deleted job writes cannot
recreate expired or revised academic state. Public embedding work has its own worker.

The source checker polls public release metadata daily and records a public ingestion audit.
It does not automatically replace reviewed academic rules. Acquire, prepare and review
new source releases before running `init`; source identities include transformation hashes.
PostgreSQL activation is one transaction protected by an advisory lock. An intentionally
failed import leaves the previous version active, and active-version changes invalidate
public snapshots and private result caches on their next request.

To roll back public data, choose a previously imported dataset ID and, in one PostgreSQL
transaction, run `UPDATE datasets SET active=false WHERE active=true` followed by
`UPDATE datasets SET active=true WHERE id='<reviewed previous ID>'`. Verify that exactly
one target row exists before committing. Public embeddings for that version can be reused;
private Redis state is never restored from database backups. Schema rollback uses Alembic
`downgrade` only after checking that the selected application's schema is compatible.

Resolved Python dependencies are in `backend/requirements.lock.txt` and
`backend/embedding-requirements.lock.txt`; npm dependencies use `package-lock.json`.
Service base images are pinned by digest. `backend/models.lock.json` records the embedding
revision and local language-model identity; unrecognized local model digests trigger the
template fallback. Review source and model license terms before redistribution.

PostgreSQL/model volumes contain public data. Redis has no persistent volume, snapshot or
append-only file. PDF bytes, parser text and private request/response buffering stay in
memory; API and proxy access logs are disabled. Ending a session removes private state,
result caches, jobs and queued identifiers. Redis recreation/restart drops all private state.

## Limits

- Real DegreeWorks layout compatibility is **unverified**; only synthetic fixtures are tested.
- Term offerings are unknown. Plans are constraint-valid proposals, not registration schedules.
- Capstone permissions, outside-discipline electives and unrestricted credits require review;
  selected natural-science choices must satisfy the implemented lecture/lab pairing rule.
- The catalog itself has unresolved references (including MATH 1165); they are quarantined.
- Skill mappings describe estimated coursework exposure, not verified student proficiency.
- No claim of globally optimal graduation timing: the solver is deterministic and bounded.
- Local LLM failure returns deterministic explanations rather than blocking recommendations.

`docker compose stop` preserves public database/model volumes; Redis session state is
lost on recreation. Never include private student data in fixtures, reports, or logs.

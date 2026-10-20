# ClassWizard V2 — reviewed database and session optimization

Local academic and career planning for the 2026–2027 Computer Science BS,
Web/Mobile Development and Software Engineering concentration.

V2 retains the complete V1 workflow and adds cached public snapshots, linear skill-link
assembly, Redis revision-aware result caches and atomic lifecycle operations, COPY staging,
incremental embeddings, and provenance-bearing semantic skill estimates. The predecessor
review is preserved in `docs/predecessor-review.md`.

## Run

```bash
cd attempts/v2
docker compose up --build -d
```

Open http://localhost:8082. The first run downloads the local embedding and Qwen models.
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
docker compose run --rm tests
docker compose run --rm tests python tools/benchmark.py --seconds 600 --warmup 120 --output /reports/benchmark.json
cd frontend
npm ci
PLAYWRIGHT_BROWSERS_PATH=/tmp/classwizard-browsers npx playwright install chromium
PLAYWRIGHT_BROWSERS_PATH=/tmp/classwizard-browsers npm test
```

The benchmark creates twenty isolated synthetic sessions. Run three repetitions and
compare the reports on the same hardware. AI generation is measured separately.

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

The optional external explanation adapter accepts `{ "evidence": [...] }` and returns
`{ "text": "...", "citations": ["ITSC 1212"] }`. Set `EXTERNAL_EXPLANATION_URL`
and `EXTERNAL_EXPLANATION_TOKEN` in the worker environment. It receives public
course evidence only, with no academic state, user preferences, or student identifiers.

## Limits

- Real DegreeWorks layout compatibility is **unverified**; only synthetic fixtures are tested.
- Term offerings are unknown. Plans are constraint-valid proposals, not registration schedules.
- Capstone, science pairing, outside-discipline electives, and unrestricted credits require review.
- The catalog itself has unresolved references (including MATH 1165); they are quarantined.
- Skill mappings describe estimated coursework exposure, not verified student proficiency.
- No claim of globally optimal graduation timing: the solver is deterministic and bounded.
- Local LLM failure returns deterministic explanations rather than blocking recommendations.

`docker compose stop` preserves public database/model volumes; Redis session state is
lost on recreation. Never include private student data in fixtures, reports, or logs.

# ClassWizard
AI-Assisted Class Suggestor

## Contributors
* Scott Do (Reshlynt)
* Jackson Redman (jrcalgo)
* Caleb Richardson (CalebRichardson0307)
* Akshat Kumar (akshuoo7)

# Overview
With the diverse classes offered at the university, college students struggle to find which classes best align with their career goals. Current tools like DegreeWorks track graduation requirements, but fail to guide students on which electives best align with their career path. Classwizard provides a solution through a career-aware, prerequisite-focused planning system. It achieves measurable business impact by improving student job readiness by suggesting the classes that teach the career-specific skills.

# How to Start

```bash
cp .env.example .env
docker compose up
```

The API is at http://127.0.0.1:8000/health. The web app is at http://localhost:8501 (use the address in `PUBLIC_BASE_URL`, so Google sign-in and email links match), and the development mail inbox (account verification and password-reset emails) is at http://127.0.0.1:8025.

### Web app

The frontend is a React + TypeScript single-page app in `new_frontend/` (Vite, Tailwind, Radix/shadcn-style components, React Flow, TanStack Query). In Docker it is built and served by nginx, which also proxies `/api/*` to the backend, so the page and API share one origin. The original Streamlit MVP is still in `frontend/` but is no longer started.

- The search preferences (audit upload, target careers, credits, summer terms, priority) are in the menu on the left, opened by the hamburger button.
- **Search** fills the canvas with the skill graph (current courses → courses needed → careers). Click a course to open its interactive concept map. The plan assistant chat sits under the graph; drag the divider to resize it. Recommendations, the sample sequence, skill gaps and the audit are in the collapsible results panel.
- The theme menu (Light, Dark, System default) is next to **Sign in** in the top right.
- Signing in is optional. Without an account, the app works as before: the audit lives in Redis for the page session only. With an account (email and password, or Google), uploaded audits are saved encrypted in Postgres, and searches, conversations and an activity log are kept. Reopen them from **Recent searches** or the account menu. Accounts can be deleted along with all of their data.

To work on the frontend with hot reload, run the stack with `docker compose up`, then:

```bash
cd new_frontend
npm install
npm run dev          # http://localhost:5173, proxies /api to the backend on :8000
npm test             # vitest
npm run lint && npm run typecheck
```

Accounts need `AUDIT_ENCRYPTION_KEY` (to save audits) and, for Google, `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` in `.env`; see `.env.example` for how to generate keys and the Google redirect URI.

The first boot unzips every catalog zip in `data/_datasets/uncc-courses/catalog/dataset/`, builds catalog JSON, and loads PostgreSQL. Zips are named `undergraduate-catalog-YYYY-YYYY.zip` and `graduate-catalog-YYYY-YYYY.zip`; each becomes its own catalog (`Undergraduate 2026-2027`, `Graduate 2026-2027`), and each DegreeWorks audit is ranked against the catalog for its level. Only the undergraduate zip is in the repo today, so graduate audits get a "Graduate 2026-2027 catalog is not loaded yet" message until a graduate zip is added. The directory inside that zip is spelled `undegraduate-catalog-2026-2027` (missing an r). Extracted PDFs and JSON stay in `data/catalog_out` and are not committed.

The first boot also embeds the syllabus triples from `data/uncc-courses/syllabi/valid_triples_for_postgres.csv` and loads the structured syllabus records from `data/_datasets/uncc-courses/syllabi/syllabus-records.zip` (course summaries, units, concepts, and learning objectives). Embedding both takes several minutes on CPU, and the whole first boot can take 15-20 minutes. The syllabus records reload when the zip's SHA-256 changes.

After loading, the backend starts the Spark pipeline in the background (see below), so the API is usable right away and the career-course scores arrive about 7-10 minutes later. The frontend waits until the backend reports healthy.

Postgres, Redis and Mailpit run in their own containers. The database is kept in the `pgdata` Docker volume: `docker compose down` keeps it, and `docker compose down -v` drops it so the next boot loads everything again. A later boot skips the catalog, O*NET, and programs when each source's SHA-256 is already stored in `ingest_runs`. Syllabi reload only when `SYLLABI_RELEASE` in `backend/storage/database/postgres.py` changes, and only rows without a vector are embedded. Redis is empty until a student uploads a PDF.

Postgres stores courses, requisite links, programs, and O*NET occupations and skills. O*NET is read from `data/_datasets/onet`. For anonymous visitors, DegreeWorks uploads stay in Redis for the session only and are not written to Postgres. For signed-in users, the parsed audit is also stored Fernet-encrypted in `saved_audits` (`backend/accounts_schema.sql`), and is deleted with the account.

### Rebuilds

The first build takes about 15-20 minutes: the backend image includes PyTorch, Java 17, and PySpark. If `docker compose down` was run before, the next `docker compose up` reuses the cached build layers and the persisted Postgres data, so a rebuild is much faster.

To clear the image and build cache, run:

```bash
docker compose down --rmi local
docker builder prune --all
```

This keeps the database. To also drop the database, run `docker compose down -v`; the next boot reloads the catalog, O*NET, programs, and syllabi.

## Chatbot (RAG)

The chat panel answers from retrieved evidence instead of the model's memory. Questions and stored text are embedded with `all-MiniLM-L6-v2` (384 dimensions) and searched in pgvector by cosine similarity (HNSW index). `CHAT_MODE` in `.env` picks one of two paths:

- `explain` (default): `/explain` retrieves courses that match the question through their syllabus summaries, learning objectives, and catalog descriptions, plus related courses from the student's remaining requirements and the chosen careers. Then a local Ollama model (`EXPLAIN_MODEL`) answers in at most four sentences and cites evidence IDs in brackets, such as `[ITSC 3160]`. Every citation is checked against the retrieved evidence, and the sources are shown under the answer. When the evidence does not answer the question, the reply is "not found in the data". Ollama runs in the `ollama` container, which downloads the model on the first start, so nothing needs installing on your machine. See [DEPLOYMENT.md](DEPLOYMENT.md#chatbot-model) for smaller models, GPU use, and using an Ollama you already run on the host.
- `chat`: `/chat` retrieves the five syllabus triples closest to the question, at the student's level, and answers through the provider set by `LLM_MODE` and `LLM_MODEL`.

### Optional: hosted model (OpenRouter)

By default `/explain` only uses a local Ollama model. To use a hosted model for both modes instead, set these in `.env` and restart with `docker compose up -d`:

```bash
LLM_MODEL=openrouter/meta-llama/llama-3.1-70b-instruct
LLM_API_KEY=<your OpenRouter key>
EXPLAIN_MODEL=openrouter/meta-llama/llama-3.1-70b-instruct
EXPLAIN_ALLOW_REMOTE=1
```

Prompts then leave your machine. Setting `EXPLAIN_ALLOW_REMOTE=0` returns `/explain` to Ollama only.

Student names, IDs, and advisor names are removed when the DegreeWorks PDF is parsed, so they never reach either model.


## Spark pipeline (ALS recommender)

`ai/recommendations/spark_jobs/` is a batch job that rates how well every course fits every career, then trains a Spark MLlib ALS recommender on those ratings. The backend publishes hybrid ratings and evidence in a background refresh process. A separate ALS worker trains only when the canonical rating matrix or training version changes. Runtime depends on hardware and competing work; the verified local run spent about 19 minutes in Gold scoring alone. Follow it with `docker compose logs -f backend`. While it runs, the Spark UI is available at http://localhost:4041.

To run it again by hand:

```bash
docker compose exec backend sh -c "python3 -m ai.recommendations.spark_jobs.run_all | tee /data/lake/sprint4_results.txt"
```

| Step | What it does |
|:--|:--|
| bronze | Loads the catalog (from Postgres), the syllabus triples CSV, and 6 O*NET CSVs into Parquet as-is |
| silver | Cleans course codes, removes nulls and duplicates, joins catalog and syllabus courses, keeps careers that need a bachelor's degree |
| gold | Rates every career x course pair 0-5 from text similarity and matched O*NET skills |
| queries | Two temporary Spark SQL queries: best courses for Data Scientists, and subjects covering the most in-demand technologies |
| publish_hybrid | Atomically publishes Gold ratings independently of ALS |
| evidence | Publishes source-linked support for the hybrid component |

Run `python3 -m ai.recommendations.spark_jobs.worker --once` in the backend container for one-shot ALS training and publication. Startup runs its retrying supervisor automatically.

Tables are written to `data/lake/` and the printed results to `data/lake/sprint4_results.txt` (both git-ignored).

### Testing the Spark jobs

Once the run has finished, check the scores in Postgres:

```bash
docker compose exec backend psql -h postgres -U classwizard -d classwizard -c "SELECT course_code, als_score FROM course_career_scores WHERE soc_code = '13-2011.00' ORDER BY als_score DESC LIMIT 5;"
```

Try your own Spark SQL. Open Python in the container with `docker compose exec backend python3`, then:

```python
from ai.recommendations.spark_jobs.session import get_spark, read_table
spark = get_spark()
read_table(spark, "gold", "ratings").createOrReplaceTempView("ratings")
read_table(spark, "silver", "courses").createOrReplaceTempView("courses")
spark.sql("SELECT level, COUNT(*) FROM courses GROUP BY level").show()
spark.sql("""
    SELECT r.course_code, c.title, r.rating
    FROM ratings r JOIN courses c ON c.course_code = r.course_code
    WHERE r.soc_code = '15-1252.00'
    ORDER BY r.rating DESC LIMIT 10
""").show(truncate=False)
```

## catalog-scrape start

### Local
- Ensure the terminal is in `data/uncc-courses/catalog`
- Run the two commands.
```bash
pip install -e ".[dev]"            # needs Python 3.10+, and poppler's pdftotext on PATH
python -m catalog_pipeline build \
    --pdf-dir path/to/pdfs \
    --catalog "Undergraduate 2026-2027" \
    --out out/
```

Replace the path to where you stored the catalog PDFs. 

# Tools
catalog-scrape
- Turns the UNC Charlotte "Course Descriptions" catalog print-outs into validated JSON for ClassWizard. 

syllabi_pipeline
- Turns syllabus concept extractions into `data/uncc-courses/syllabi/valid_triples_for_postgres.csv`.

# Technologies
What the software uses are the following:

PostgreSQL, pgvector, Redis
Python, FastAPI
React, TypeScript, Vite, Tailwind CSS, React Flow, TanStack Query, nginx
sentence-transformers, spaCy, LLM providers (LiteLLM SDK wrapper & proxy)
pdfplumber, poppler
Docker
Apache Spark (PySpark 3.5, Spark SQL, MLlib ALS), Java 17

# Architecture
|       Layer      |                                                                      Components                                                                      |
|:----------------:|:----------------------------------------------------------------------------------------------------------------------------------------------------:|
| Data sources     | UNC Charlotte course catalog, course syllabi, DegreeWorks PDF, O*NET career database                                                                 |
| Storage          | PostgreSQL (courses, programs, requirements, careers, skills, career-course scores); pgvector (embeddings for semantic search); Redis (temporary DegreeWorks session data); user accounts, encrypted saved audits, searches and activity in PostgreSQL |
| Processing       | Spark: Bronze / Silver / Gold Parquet tables in `data/lake`                                                                                          |
| AI & planning    | Semantic skill matching, ALS career-course recommender, rule-based course recommender, constraint-based degree planner, LLM explanation layer       |
| User application | React web app: upload DegreeWorks, select career goals, set semester preferences, explore the skill graph and concept maps, chat, optional accounts |
| Outputs          | Recommended courses, skill-gap view, explanations                                                                         |

This software takes source data from the UNC- Charlotte course catalog, DegreeWorks PDfs submitted by the user, course syllabi, and the O*NET career database. PostgreSQL, pgvector, and Redis will be used for storage in their respective locations. Spark cleans and joins the data, and trains an ALS model that scores how well each course fits each career. AI will be used to match skills, and suggest courses between matching career pathways and produce recommended courses in a front-end.

### Recommendation scoring

`/recommend` ranks by `0.70 × hybrid_rating + 0.30 × normalized_als_score` when complete current blended scores are available, otherwise by complete current hybrid ratings, otherwise cosine similarity for the whole request. ALS normalization is `5 × PERCENT_RANK()` over each full catalog/career partition, preserving ties. Responses identify `scoring_method` (`spark_blended`, `spark_hybrid`, or `cosine_similarity`), the applicable scoring version, active `score_by_occupation`, and nullable `score_components_by_occupation`. The highest selected-career score determines rank. Scores are relative ranking signals, not probabilities or student skill measurements.

Spark keeps catalog identity through all layers. Publishing validates exact coverage of loaded catalog courses across its degree-level O*NET careers, rejects invalid batches, and atomically replaces scores and release metadata. Input-release or scoring-version changes trigger a rebuild. Partial runs require current upstream stage manifests; after a schema or scoring change, rebuild all stages:

```sh
docker compose exec backend python3 -m ai.recommendations.spark_jobs.run_all
```

Hybrid and ALS publishers reject missing, extra, duplicate, or non-finite scores. `/explain` includes the scoring method and career ratings in cited evidence.

### Cited syllabus-to-career skill matches

`/explain` can cite the individual syllabus concepts that contributed to Spark's skill-coverage signal, with the recorded source statement, filename, and page when available. These statements come from existing extraction records; they are not independently verified verbatim PDF quotes. Computed relationships are labeled separately from what the syllabus explicitly says. The rating formula, course ordering, and recommendation cards are unchanged.

Explanation evidence uses only traceable matches with confidence at least 0.80 and similarity at least 0.70. It includes at most three match items per answer and two per course, within the existing ten-item budget. For named-course questions, skill matches are limited to the named courses, while existing discovery facts remain available. Missing or weak evidence falls back to the existing syllabus and career facts; it does not imply that a course has no career relevance.

Refresh evidence from compatible, already-built artifacts without embeddings or ALS training:

```sh
docker compose exec backend python3 -m ai.recommendations.spark_jobs.run_all --steps evidence
```

The command checks saved term aggregates and Gold ratings before atomically replacing evidence. It rejects incompatible artifacts rather than silently retraining. Evidence has its own version and is tied to the hybrid publication timestamp; ALS publication preserves it. Startup refreshes evidence alone when scores are current; normal full pipeline runs publish it after scores.

Prepare six before/after explanation samples and the review rubric:

```sh
docker compose exec backend python3 -m ai.nlp.explanations.review_skill_matches --output /data/lake/skill_match_review.json
```

This review uses only the existing configured local Ollama model. If unavailable, it records the model review as pending and prepares evidence samples without starting Ollama, downloading a model, or switching providers. Generated samples require review against their sources; citation-ID validity alone does not establish factual support.

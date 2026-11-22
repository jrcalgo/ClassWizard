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

The API is at http://127.0.0.1:8000/health. The Streamlit page is at http://127.0.0.1:8501.

The first boot unzips every catalog zip in `data/_datasets/uncc-courses/catalog/dataset/`, builds catalog JSON, and loads PostgreSQL. Zips are named `undergraduate-catalog-YYYY-YYYY.zip` and `graduate-catalog-YYYY-YYYY.zip`; each becomes its own catalog (`Undergraduate 2026-2027`, `Graduate 2026-2027`), and each DegreeWorks audit is ranked against the catalog for its level. Only the undergraduate zip is in the repo today, so graduate audits get a "Graduate 2026-2027 catalog is not loaded yet" message until a graduate zip is added. The directory inside that zip is spelled `undegraduate-catalog-2026-2027` (missing an r). Extracted PDFs and JSON stay in `data/catalog_out` and are not committed.

The first boot also embeds the syllabus triples from `data/uncc-courses/syllabi/valid_triples_for_postgres.csv` and loads the structured syllabus records from `data/_datasets/uncc-courses/syllabi/syllabus-records.zip` (course summaries, units, concepts, and learning objectives). Embedding both takes several minutes on CPU, and the whole first boot can take 15-20 minutes. The syllabus records reload when the zip's SHA-256 changes.

After loading, the backend starts the Spark pipeline in the background (see below), so the API is usable right away and the career-course scores arrive about 7-10 minutes later. The frontend waits until the backend reports healthy.

Postgres and Redis run in their own containers. The database is kept in the `pgdata` Docker volume: `docker compose down` keeps it, and `docker compose down -v` drops it so the next boot loads everything again. A later boot skips the catalog, O*NET, and programs when each source's SHA-256 is already stored in `ingest_runs`. Syllabi reload only when `SYLLABI_RELEASE` in `backend/storage/database/postgres.py` changes, and only rows without a vector are embedded. Redis is empty until a student uploads a PDF.

Postgres stores courses, requisite links, programs, and O*NET occupations and skills. O*NET is read from `data/_datasets/onet`. DegreeWorks uploads stay in Redis for the session only and are not written to Postgres.

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

- `explain` (default): `/explain` retrieves courses that match the question through their syllabus summaries, learning objectives, and catalog descriptions, plus related courses from the student's remaining requirements and the chosen careers. Then a local Ollama model (`EXPLAIN_MODEL`) answers in at most four sentences and cites evidence IDs in brackets, such as `[ITSC 3160]`. Every citation is checked against the retrieved evidence, and the sources are shown under the answer. When the evidence does not answer the question, the reply is "not found in the data". This path needs Ollama running on the host with the model pulled.
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

`ai/recommendations/spark_jobs/` is a batch job that rates how well every course fits every career, then trains a Spark MLlib ALS recommender on those ratings. The backend runs it automatically in the background on the first boot, and again on any boot after the catalog, O*NET, or syllabi change. A full run takes about 7-10 minutes; follow it with `docker compose logs -f backend`. While it runs, the Spark UI is available at http://localhost:4041.

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
| model | Trains ALS (80/20 split, tuned on a validation split) and prints test RMSE next to two baselines |
| publish | Writes a score for every pair to the Postgres table `course_career_scores` |

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
Streamlit
sentence-transformers, spaCy, LLM providers (LiteLLM SDK wrapper & proxy)
pdfplumber, poppler
Docker
Apache Spark (PySpark 3.5, Spark SQL, MLlib ALS), Java 17

# Architecture
|       Layer      |                                                                      Components                                                                      |
|:----------------:|:----------------------------------------------------------------------------------------------------------------------------------------------------:|
| Data sources     | UNC Charlotte course catalog, course syllabi, DegreeWorks PDF, O*NET career database                                                                 |
| Storage          | PostgreSQL (courses, programs, requirements, careers, skills, career-course scores); pgvector (embeddings for semantic search); Redis (temporary DegreeWorks session data) |
| Processing       | Spark: Bronze / Silver / Gold Parquet tables in `data/lake`                                                                                          |
| AI & planning    | Semantic skill matching, ALS career-course recommender, rule-based course recommender, constraint-based degree planner, LLM explanation layer       |
| User application | Upload DegreeWorks, select career goal, set semester preferences, view results                                                                       |
| Outputs          | Recommended courses, skill-gap view, explanations                                                                         |

This software takes source data from the UNC- Charlotte course catalog, DegreeWorks PDfs submitted by the user, course syllabi, and the O*NET career database. PostgreSQL, pgvector, and Redis will be used for storage in their respective locations. Spark cleans and joins the data, and trains an ALS model that scores how well each course fits each career. AI will be used to match skills, and suggest courses between matching career pathways and produce recommended courses in a front-end.

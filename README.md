# ClassWizard
AI-Assisted Class Suggestor

## Contributors
* Scott Do (Reshlynt)
* Jackson Redman (jrcalgo)
* Caleb Richardson (CalebRichardson0307)
* Akshat Kumar

# Overview
With the diverse classes offered at the university, college students struggle to find which classes best align with their career goals. Current tools like DegreeWorks track graduation requirements, but fail to guide students on which electives best align with their career path. Classwizard provides a solution through a career-aware, prerequisite-focused planning system. It achieves measurable business impact by improving student job readiness by suggesting the classes that teach the career-specific skills.

# How to Start

```bash
cp .env.example .env
docker compose up
```

The first boot unzips every catalog zip in `data/_datasets/uncc-courses/catalog/dataset/`, builds catalog JSON, and loads PostgreSQL. Zips are named `undergraduate-catalog-YYYY-YYYY.zip` and `graduate-catalog-YYYY-YYYY.zip`; each becomes its own catalog (`Undergraduate 2026-2027`, `Graduate 2026-2027`), and each DegreeWorks audit is ranked against the catalog for its level. Only the undergraduate zip is in the repo today, so graduate audits get a "Graduate 2026-2027 catalog is not loaded yet" message until a graduate zip is added.

The first boot also embeds the syllabus triples from `data/uncc-courses/syllabi/valid_triples_for_postgres.csv`, which takes a few minutes on CPU. The database lives in the `pgdata` Docker volume, so later boots and rebuilds skip anything already loaded. To start over from an empty database, run `docker compose down -v`. The directory inside that zip is spelled `undegraduate-catalog-2026-2027` (missing an r). Extracted PDFs and JSON stay in `data/catalog_out` and are not committed. A later boot skips a catalog or O*NET release already recorded in `ingest_runs`.

Postgres stores courses, requisite links, programs, and O*NET occupations and skills. O*NET is read from `data/_datasets/onet`. DegreeWorks uploads stay in Redis for the session only and are not written to Postgres. Redis is empty until a student uploads a PDF.

The API is at http://127.0.0.1:8000/health. The Streamlit page is at http://127.0.0.1:8501.

## Chatbot (RAG)

The chat panel answers from retrieved evidence instead of the model's memory. Questions and stored text are embedded with `all-MiniLM-L6-v2` (384 dimensions) and searched in pgvector by cosine similarity (HNSW index). `CHAT_MODE` in `.env` picks one of two paths:

- `explain` (default): `/explain` retrieves catalog courses, O*NET careers, and the student's ranked recommendations, then a local Ollama model (`EXPLAIN_MODEL`) answers in at most four sentences and cites evidence IDs in brackets, such as `[ITSC 3160]`. Every citation is checked against the retrieved evidence, and the sources are shown under the answer. When the evidence does not answer the question, the reply is "not found in the data". This path needs Ollama running on the host with the model pulled.
- `chat`: `/chat` retrieves the five closest syllabus triples and answers through the provider set by `LLM_MODE` and `LLM_MODEL`.

Student names, IDs, and advisor names are removed when the DegreeWorks PDF is parsed, so they never reach either model.

## Restore the database

See [database_dump/README.MD](database_dump/README.MD). 

## catalog-scrape start

### Local
- Ensure the terminal is in `/catalog_pipeline`
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

# Technologies
What the software uses are the following:

PostgreSQL, pgvector, Redis
Python, FastAPI
Streamlit
sentence-transformers, spaCy, LLM providers (Ollama / OpenAI-style API)
pdfplumber, poppler
Docker

# Architecture
|       Layer      |                                                                      Components                                                                      |
|:----------------:|:----------------------------------------------------------------------------------------------------------------------------------------------------:|
| Data sources     | UNC Charlotte course catalog, DegreeWorks PDF, O*NET career database                                                                                 |
| Storage          | PostgreSQL (courses, programs, requirements, careers, skills); pgvector (embeddings for semantic search); Redis (temporary DegreeWorks session data) |
| AI & planning    | Semantic skill matching, rule-based course recommender, constraint-based degree planner, LLM explanation layer                                       |
| User application | Upload DegreeWorks, select career goal, set semester preferences, view results                                                                       |
| Outputs          | Recommended courses, skill-gap view, explanations                                                                         |

This software takes source data from the UNC- Charlotte course catalog, DegreeWorks PDfs submitted by the user, and the O*NET career database. PostgreSQL, pgvector, and Redis will be used for storage in their respective locations. AI will be used to match skills, and suggest courses between matching career pathways and produce recommended courses in a front-end.
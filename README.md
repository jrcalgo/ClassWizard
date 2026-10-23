# ClassWizard
AI-Assisted Class Suggestor

## Contributors
Scott Do (Reshlynt)
Jackson Redman (jrcalgo)
Caleb Richardson (CalebRichardson0307)
Akshat Kumar

# Overview
With the diverse classes offered at the university, college students struggle to find which classes best align with their career goals. Current tools like DegreeWorks track graduation requirements, but fail to guide students on which electives best align with their career path. Classwizard provides a solution through a career-aware, prerequisite-focused planning system. It achieves measurable business impact by improving student job readiness by suggesting the classes that teach the career-specific skills.

# How to Start

```bash
cp .env.example .env
docker compose up
```

The first boot unzips `data/_datasets/uncc-courses/catalog/dataset/undergraduate-catalog-2026-2027.zip`, builds catalog JSON, and loads PostgreSQL. The directory inside that zip is spelled `undegraduate-catalog-2026-2027` (missing an r). Extracted PDFs and JSON stay in `data/catalog_out` and are not committed. A later boot skips a catalog or O*NET release already recorded in `ingest_runs`.

Postgres stores courses, requisite links, programs, and O*NET occupations and skills. O*NET is read from `data/_datasets/onet`. DegreeWorks uploads stay in Redis for the session only and are not written to Postgres. Redis is empty until a student uploads a PDF.

The API is at http://127.0.0.1:8000/health. The Streamlit page is at http://127.0.0.1:8501.

## Restore the database

`data_dump/classwizard.sql` is a PostgreSQL dump of the loaded catalog, program, and O*NET tables, including the `vector` extension. Redis is not in the dump. It only holds a student's DegreeWorks session and starts empty.

Start the stack, then restore into the Postgres running inside the backend container. The dump drops and recreates those tables.

```bash
docker compose up -d
docker compose exec -T backend psql -h 127.0.0.1 -U classwizard -d classwizard -v ON_ERROR_STOP=1 < data_dump/classwizard.sql
```

If `.env` sets `POSTGRES_USER`, `POSTGRES_PASSWORD`, or `POSTGRES_DB`, use those values. The password must match the database that was created on first boot. Default user, password, and database name are `classwizard`. 


# Tools
catalog-scrape
- Turns the UNC Charlotte "Course Descriptions" catalog print-outs into validated JSON for
ClassWizard. 

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


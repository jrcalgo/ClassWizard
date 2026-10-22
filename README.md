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

## Quick Start
```bash
cp .\.env.example .\.env        # Copy environment
docker compose up -d            # Run db
```
## How to Start



## catalog-scrape start
The README under the `catalog_pipeline_tool` directory has most of the directions that you will need that does not merit rehashing in this README. Regardless, to use this tool:
- Unzip `catalog_pipeline.zip` to the root directory of the repo. The name **must** be `catalog_pipeline`or the Dockerfile will fail to find the needed files.

### Via Docker
- Put your PDFs from the University Catalog into `data/catalog_pdfs`.
- In the terminal, run `docker compose run --rm catalog-pipeline`. This will create a containter that will only exist to convert PDFs into the output files (read more in the README in the unzipped directory).

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


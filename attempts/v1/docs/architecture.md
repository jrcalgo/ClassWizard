# Architecture and data model

```mermaid
flowchart LR
  A[Public catalog + O*NET] --> B[Acquire / clean / profile / review]
  B --> C[(PostgreSQL public versions)]
  C --> D[Local embeddings worker]
  D --> V[(pgvector)]
  U[Student PDF / manual entry] --> P[Memory-only parser + student review]
  P --> R[(Redis ephemeral session)]
  C --> E[Constraint recommendations and semester solver]
  R --> E
  E --> F[React application]
  V --> L[Evidence-grounded local LLM]
  E --> L
  L --> F
```

```mermaid
erDiagram
  DATASET ||--o{ COURSE : versions
  DATASET ||--o{ PROGRAM : versions
  PROGRAM ||--o{ REQUIREMENT : defines
  PROGRAM ||--o{ PROGRAM_COURSE : includes
  COURSE ||--o{ PROGRAM_COURSE : belongs
  COURSE ||--o{ COURSE_SKILL : supports
  SKILL ||--o{ COURSE_SKILL : mapped
  OCCUPATION ||--o{ OCCUPATION_SKILL : requires
  SKILL ||--o{ OCCUPATION_SKILL : measured
  DATASET ||--o{ SOURCE_DOCUMENT : documents
  DATASET ||--o{ EMBEDDING : contains
```

Public tables have versioned identities. Rule expressions preserve AND/OR structure;
minimum-grade and concurrent conditions remain explicit. Requirement allocation prevents
elective double-counting; quantitative/data competency is fulfilled by required mathematics.
The active-version unique index and transaction ensure readers never see partially loaded data.
Representative operations: bulk course lookup by version, course–skill–occupation joins,
and filtered cosine retrieval. Sessions and student-derived results have no SQL tables.

Storage alternatives: relational integrity is useful for academic rules and source versions;
JSON payloads retain irregular document metadata; pgvector shares transactional public-data
storage; Redis fits deliberately short-lived session data. A separate graph or document
database would add operational cost without a demonstrated workload requirement.

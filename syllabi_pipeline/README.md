# syllabi_pipeline

Turns syllabus concept-map extractions (`*_triples.csv` + `*_concepts.csv`) into
`data/uncc-courses/syllabi/valid_triples_for_postgres.csv`, the file the backend
loads into the `syllabus_triples` table.

```
concept-map CSVs -> syllabi_pipeline -> valid_triples_for_postgres.csv (committed, ~15 MB)
                                   |                     |
                                   |                     v  backend first boot
                                   |        load_syllabi() + embed_syllabus_triples() -> Postgres
                                   +-> rejected_triples.csv, pipeline_report.json (git-ignored)
```

Only the CSV is committed. Vectors are computed by the backend on the first
boot of each release (a few minutes on CPU) and kept in the `pgdata` Docker
volume, so later boots skip it.

## Run

From the repo root:

```bash
python -m syllabi_pipeline --input path/to/syllabus_extractions
python -m pytest tests/test_syllabi_pipeline.py
```

The committed CSV was built from the November 2026 extraction (2,363 courses).
That extraction folder is not kept in the repo; rerun the pipeline when a new
release arrives.

```bash
# What the extraction folder looks like (any nesting works):
#   <COURSE>/<COURSE>_triples.csv
#   <COURSE>/<COURSE>_concepts.csv
```

After writing a new CSV, bump `SYLLABI_RELEASE` in
`backend/storage/database/postgres.py`; the next `docker compose up` reloads and
re-embeds it.

Input files are found recursively and grouped by their `course` column, so a
folder per course and one combined CSV pair both work.

| Option | Default | Purpose |
|---|---|---|
| `--output` | `data/uncc-courses/syllabi/valid_triples_for_postgres.csv` | Output CSV. Review files are written next to it. |
| `--catalog` | `data/catalog_out` | A `courses_flat.csv`, or a folder searched for them (one per catalog level). Adds course titles to the evidence text. Skipped if missing. |
| `--min-confidence` | `0.60` | Relations below this go to `rejected_triples.csv`. Use `0` to keep flagged rows. |
| `--no-inferred` | off | Drop `inferred` concepts entirely (the old behaviour). |
| `--include-inferred-pairs` | off | Keep relations whose two ends are both inferred (capped at 0.60). |
| `--include-unverified` | off | Keep concepts whose `status` is neither `verified` nor `inferred`. |
| `--no-covers` | off | Skip the course-covers-concept rows. |

## Inferred concepts

The extractor marks each concept `verified` (found in the syllabus text) or
`inferred`. In the November 2026 extraction, 48% of concepts are inferred.
They are not spread evenly: 1,308 courses are fully verified, while the
~1,050 courses that have inferred concepts are usually ~90% inferred and list
about twice as many concepts (median 23 vs 11). Inferred terms are paraphrases
("Flight Pioneers' Achievements", "Application Writing Tips"), always have
`occurrences = 1`, and match the catalog description far less often (3.6% vs
21.8% full word overlap). The course link is real; the exact wording is not.

| Case | Handling |
|---|---|
| Inferred concept | `covers` row kept at 0.60, evidence says "inferred from the syllabus, not quoted from it" (165 courses have only inferred concepts) |
| Relation with one inferred end | Kept, capped at 0.65, evidence names the inferred term |
| Relation with two inferred ends | Rejected (`both_endpoints_inferred`), since nothing ties it to the syllabus text |

## Mapping

| Concept map | Postgres |
|---|---|
| `PREREQUISITE_OF` | `prerequisite_for` |
| `PART_OF` | `part_of` |
| `SUBTYPE_OF` | `is_subclass_of` |
| `USED_FOR` | `used_for` |
| (each verified concept) | `<course> covers <concept>`, `subject_type = Course` |
| `concept` / `topic` / `method` / `measure` / `work` | `Concept` / `Topic` / `Method` / `Measure` / `Work` |
| `tool` | `Technology` |

- `subject_canonical_id` / `object_canonical_id`: `<type>_<md5(lowercased term)[:8]>`,
  the same scheme as the existing rows, so one term gets the same id in every course.
- `triple_id`: `md5(course|subject_id|predicate|object_id)[:12]`. Re-running gives the same ids.
- `filename`: `<COURSE>.pdf`. `page_num` and `section_heading` are empty (not in the source).
- `evidence`: a generated sentence with the course code, title and syllabus order, e.g.
  *"In ACCT 2121 (Principles of Accounting I), Journal Entries is a prerequisite for
  T-Accounts (Journal Entries is taught earlier in the course)."*

## Confidence

| Row | Confidence |
|---|---|
| `prerequisite_for`, A taught first | 0.90 |
| `prerequisite_for`, A mentioned first | 0.80 |
| `prerequisite_for`, same unit | 0.75 |
| `prerequisite_for`, unknown or blank order | 0.70 |
| `prerequisite_for`, B mentioned first | 0.60 |
| `prerequisite_for`, B taught first | 0.50 |
| `is_subclass_of` | 0.90 |
| `part_of`, `used_for` | 0.85 |
| any row with a `... - check` flag | capped at 0.50 |
| relation with one inferred end | capped at 0.65 |
| `covers`, verified concept appears 2+ times | 0.90 |
| `covers`, verified concept appears once | 0.80 |
| `covers`, inferred concept | 0.60 |

## Rejected rows

Every dropped row goes to `rejected_triples.csv` with one of these reasons:
`flagged_for_review`, `low_confidence`, `both_endpoints_inferred`,
`endpoint_inferred` / `concept_inferred` (only with `--no-inferred`),
`endpoint_not_in_concepts`, `endpoint_unverified`, `concept_unverified`,
`self_loop`, `duplicate`,
`unknown_predicate:<X>`, `unknown_type`, `bad_course_code`, `bad_term`,
`missing_subject_or_object`, `term_too_long`.

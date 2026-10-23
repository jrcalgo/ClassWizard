# catalog_pipeline

Turns the UNC Charlotte "Course Descriptions" catalog print-outs into validated JSON for
ClassWizard. It was built and tested on the 2026–27 Undergraduate Catalog: 38 PDFs, 3,794
courses.

The output has three layers, and every derived value keeps the catalog's raw text next to it:

| Layer | What it holds | Trust |
|---|---|---|
| **A: raw** | Title, section, description and the exact text of every field, with source file and page | Verified word-for-word against a second PDF extractor |
| **B: normalized** | Credit range and attributes, gen ed labels, repeatability, grading method, cross-listed codes, restriction gates | Rule-based; anything that doesn't fit a pattern is flagged |
| **C: structured** | Requisite logic trees, plus cross-list, exclusion and requisite edges | `status` and `review` say how far each item can be trusted |

Loading into PostgreSQL (layer D) is not part of this package yet. The edge lists are already
shaped like link tables.

## Quick start

```bash
pip install -e ".[dev]"            # needs Python 3.10+, and poppler's pdftotext on PATH
python -m catalog_pipeline build \
    --pdf-dir path/to/pdfs \
    --catalog "Undergraduate 2026-2027" \
    --out out/
```

To install poppler: `apt install poppler-utils` on Debian/Ubuntu, `brew install poppler` on
macOS, or on Windows add the poppler `bin` folder to PATH.

`python -m catalog_pipeline validate ...` runs only the checks.

**Exit codes:**
- `0`: success
- `1`: validation failed; no course data is written, only `validation_report.json`
- `2`: bad arguments

## Input: how the PDFs must be printed

The parser is fitted to Microsoft Print to PDF print-outs of the catalog's course listing:

- Portrait, all pages, Letter, fit to page width, default margins, headers and footers on
  (the parser strips them).
- **Every course must be expanded before printing.** A collapsed listing prints about 10 sheets
  instead of about 50, has no course text, and the build refuses it. That is exactly what
  happened to the first print of page 18.
- One PDF per listing page, with a file name ending in `pgN.pdf`, for example
  `Undergraduate_Catalog_2026-2027_pg18.pdf`. The number must match the listing page; the
  build checks it against the pagination bar printed on the page.
- Start from one documented catalog URL. The 2026–27 prints came from three URL forms; the
  content matched, but one starting URL makes re-printing repeatable.

## Output files

| File | Contents |
|---|---|
| `courses.json` | One document: `sources` (each PDF's producer, print time and printed URL) plus `courses`, one object per course with all three layers. Schema: `catalog_pipeline/schema/courses.schema.json` |
| `edges.json` | Course-to-course links. Schema: `catalog_pipeline/schema/edges.schema.json` |
| `review_queue.csv` | Every item a person should check, high severity first |
| `validation_report.json` | Per-page results of every check |
| `hyphen_fixes.json` | Audit log of the hyphens restored (see Stage 3) |
| `courses_flat.csv` | Layer A only, one row per course, for spreadsheets |

Both JSON files are checked against their schemas before they are written.

### A course, abridged

```json
{
 "code": "CJUS 3354",
 "credit_hours": {"raw": "(3)", "min": 3, "max": 3, "options": null, "variable": false,
                  "attributes": [], "status": "ok"},
 "requisites": {
  "prerequisite": {
   "raw": "CJUS 1511 and CJUS 2340, both with grade of C or above",
   "timing": "before", "status": "parsed",
   "tree": {"op": "and", "items": [
     {"type": "course", "code": "CJUS 1511", "min_grade": "C", "timing": "before"},
     {"type": "course", "code": "CJUS 2340", "min_grade": "C", "timing": "before"}]},
   "advisory": [], "courses_mentioned": ["CJUS 1511", "CJUS 2340"], "review": []},
  "corequisite": null, "pre_or_corequisite": null},
 "cross_listed": {"raw": "HONR 3700 -H01 and LEGL 3354",
                  "courses": [{"code": "HONR 3700", "section": "H01"},
                              {"code": "LEGL 3354", "section": null}], "status": "ok"}
}
```

- **Key:** `(catalog, code)` is unique. A suffix such as `L` is part of the code, so `BIOL 2120L` is its own course.
- **Requisite nodes:** `and`, `or`, or `n_of` (with `n`).
- **Requisite leaves:**
  - `course`: `code`, `min_grade`, `timing`, and optionally `or_higher` and `max_attempts`
  - `level`: e.g. "two SPAN 3000-level courses" or "MUPF 32xx"
  - `permission`, `placement`, `standing`, `equivalent`
  - `other`: a known non-course requirement, e.g. "an approved principal ensemble"
  - `text`: not understood, and always flagged
- **Timing:** comes from the field the requisite sits in:
  - Prerequisite(s): `before`
  - Corequisite(s): `same_term`
  - Pre- or Corequisite(s): `before_or_same_term`

## How far to trust a requisite

| `status` | Meaning | 2026–27 count (all 3 requisite fields) |
|---|---|---|
| `parsed` | Every grouping decision was forced by the text | 1,845 |
| `proposed` | A tree is given, but some decision was an inference or some text wasn't understood. Each one is listed in `review` with a severity | 391 |
| `unparsed` | The grouping is ambiguous, e.g. "A or B and C" with no punctuation. No tree; `courses_mentioned` is still filled | 98 |
| `advisory_only` | The field only recommends ("SPAN 2105 is recommended") | 8 |

What the review severities mean:

- **`low`:** the usual catalog convention was applied. Examples:
  - a comma list with no "and"/"or" is read as AND
  - "A or B with a grade of C" gives the grade to each alternative
  - grouping is taken from comma placement
- **`high`:** a real guess, or a gap. Examples:
  - text that wasn't understood
  - "A and B with grade of C", where the grade may apply only to B
  - a conditional remark such as "(for the B.A. in Chemistry program)"
  - and/or mixed without punctuation (status `unparsed`)

**Hand-checking** means a person reads the raw text of a `high` or `unparsed` item, decides
the intended reading (asking the department or checking DegreeWorks if needed), and records
the corrected tree. Start with the courses in the MVP majors' prerequisite chains; that list
is not decided yet.

Two random samples of 40 and 30 `parsed` trees were all correct against the source text, but
that is a sample check, not proof.

## Pipeline stages (one module each)

| Stage | Module | Why it exists |
|---|---|---|
| 1. Extract | `extract.py` | Reads each PDF with **pdftotext** (the parser's input) and with **pdfplumber** (an independent reference). It also reads producer, print time, sheet count and printed URL. |
| 2. Parse | `parse.py` | A line-by-line state machine: heading → course header → description → labelled fields. It rejoins wrapped titles and tells department headings apart from wrapped field text. This is the logic of the validated `catalog_parse.py`; on the 38 PDFs its output is identical. |
| 3. Repair | `repair.py` | pdftotext deletes a '-' at the end of a line ("three-dimensional" becomes "threedimensional"). A fix is applied only if the fixed value then matches pdfplumber's text for the same file. This makes 92 fixes. An earlier blind version put fixes on the wrong course, which the content check caught. |
| 4. Validate | `validate.py` | Refuses bad input (see the next section). |
| 5. Normalize | `normalize.py` | Layer B. |
| 6. Structure | `requisites.py`, `relations.py` | Layer C. The requisite parser follows punctuation from loosest to tightest: sentence > `;` > `,` > and/or words. |
| 7. Build | `build.py`, `cli.py` | Runs the stages, checks the schemas and writes the files. |

## Validation checks

**Errors** (these block output):

- The text layer is missing, or holds fewer than 5,000 characters.
- A page doesn't have exactly `--page-size` courses (default 100); the last page may have fewer.
- A field label appears a different number of times in the raw text than in the parsed records, or than in pdfplumber's text.
- The course codes, or their order, differ from pdfplumber's.
- A title, description or field value is not found word-for-word in pdfplumber's text.
- The pagination bar doesn't include the page number taken from the file name.
- A listing page is missing, or a course code appears twice.

**Warnings:**

- course numbers going backwards within a prefix
- pages made by different PDF producers
- pages printed from different URL forms
- empty field values in the source

**2026–27 result:** all 16,919 values were verified, with no errors. There were 2 warnings: three URL forms, and 10 empty fields that are empty in the source too.

## Tests and lint

```bash
pytest                                        # unit tests; the integration tests are skipped
CATALOG_PDF_DIR=path/to/pdfs pytest           # adds the end-to-end run (~90 s)
pylint catalog_pipeline tests                 # 10.00/10 with the settings in pyproject.toml
```

- **Requisite tests:** the expected trees were written by reading the catalog text, not by copying parser output.
- **Golden sample:** `tests/golden/raw_records.json` holds 30 hard records: wrapped titles, page boundaries, repaired hyphens, the misplaced CHEM 4090, empty and invalid source values, and page 18 records. Their raw text was checked against pdfplumber, and ITCS 3120, CHEM 4090 and the page 18 records were also checked against the rendered page images.

### The repo's pylint GitHub Action

The Action fails because it lints incomplete assignment code. Point it at this package instead.
In the workflow file, change the step that runs pylint, typically

```yaml
- run: pylint $(git ls-files '*.py')
```

to

```yaml
- run: pylint catalog_pipeline tests
```

or, if the package sits in a subfolder, `pylint path/to/catalog_pipeline`. To keep linting
everything except the assignment folder, use `pylint --ignore=<assignment folder> ...`.

## Known limits

- **Restrictions** are keyword-tagged (program, standing, GPA and so on), not parsed into
  logic. Program names stay as text until a program list exists.
- **Exclusions** ("no credit if…") are found by sentence templates: 76 edges, 54 of them
  printed on both courses. The 8 that cover a range ("…or higher") are flagged.
- **References to courses not in the catalog:** 20 codes are named in requisites but don't
  exist in this catalog (retired ETME numbers, ITIS 5270 and others), and 194 cross-list
  edges point to graduate course numbers. They are kept with `target_resolved: false`.
- **Offering terms:** the catalog has no reliable data on which terms a course is offered.
- **Graduate catalog:** pass `--catalog "Graduate 2026-2027"`. Check one printed page first,
  because headings or field labels may differ.

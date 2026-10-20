# Sprint 1 — exploration and preparation evidence

This report accompanies executable acquisition and preparation scripts and
`data/prepared/profile.json`. Counts are measured from the acquired snapshots,
not inferred from document size. The implemented concentration follows the catalog's
official title: Computer Science BS, Web/Mobile Development and Software Engineering.

## Inventory and relevance

| Source | Access / provider | Format, measured or estimated size, cadence | Role and restrictions |
|---|---|---|---|
| Charlotte 2026–2027 undergraduate catalog | [Catalog PDF](https://catalog.charlotte.edu/mime/media/view/10/5658/2026-2027-Undergraduate-Catalog.pdf), [catalog website](https://catalog.charlotte.edu/); UNC Charlotte | PDF → extracted text; PDF content length 22,987,044 bytes; two text representations total 11,748,570 bytes; annual publication | Course eligibility and degree requirements; publicly accessible, source/page provenance retained |
| DegreeWorks worksheet | [DegreeWorks](https://degreeworks.charlotte.edu/); student-provided file, Charlotte/NinerNet | PDF; approximately 15 KB per student is the project estimate, not a measured real-file size; changes with the academic record | Completed/in-progress work and remaining requirements; requires user provision, memory-only handling and manual review |
| O*NET 31.0 | [Database downloads](https://www.onetcenter.org/database.html); US Department of Labor/Employment and Training Administration | Six selected CSV tables total 22,233,913 bytes; quarterly release cadence | Occupations, skill ratings, technologies and education; retain [database attribution/license](https://www.onetcenter.org/license_db.html) |

Actual source byte sizes and SHA-256 values are in `dataset.json`'s manifest.
The catalog was successfully acquired from the supplied URL during implementation.

## Structure and profiling

The normalized catalog contains 3,729 records, including two quarantined references
with no matching course-description entry. Courses and programs have many-to-many
relationships. Prerequisites are logical expressions, not just edges. Program requirements
include alternatives, minimum grades, standing, credit totals, and permission conditions.
No geospatial or time-series observations are required for the MVP; catalog years and
O*NET rating dates are version metadata rather than measurements of enrollment demand.
The nine course attributes are canonical code, title, numeric credit value, numeric credit
range, description text, logical rule object, quarantine flag, review reason and source
evidence object. Stable codes connect course/program membership and many-to-many
course–skill and occupation–skill mappings. Requirement groups retain nested alternatives,
counts, credit minimums and completion/grade conditions.

Measured catalog profiling: 2,798 courses have a three-credit default, 562 one-credit,
219 two-credit, 77 four-credit and 43 zero-credit entries; remaining defaults are 6–15 credits.
There are 275 variable-credit courses and 21 duplicate heading codes. These unusual credits
are preserved as catalog values rather than automatically removed as outliers. Two
quarantined entries have placeholder descriptions sourced from requirement references;
the other records have extracted text. **2,703 rules remain unresolved**, reflecting
conservative detection of conditions and the limited manually reviewed planning path.

O*NET raw selected tables have 45,500 transferable-skill rating records, 18,200 essential-
skill records, and 60,060 knowledge records. The MVP filters four occupations and 68
distinct skill/knowledge elements. Importance and level ratings are preserved separately.
Null confidence/statistical fields are not converted into zero skill importance.
Each of the three profiled rating tables has 15 attributes. Empty-cell counts are 22,750
for transferable skills, 9,100 for essential skills and 99,416 for knowledge. These counts
include optional statistics and are not counts of missing career identities. SOC/element
codes are strings; ratings are numeric; scale IDs/categories and rating dates are retained
as metadata. The source files and their hashes allow deeper column-level profiling.

DegreeWorks has no real student records in this repository. Unit tests generate synthetic
PDF layouts in memory. Real worksheet accuracy cannot be claimed from these fixtures.

## Quality and remediation

| Finding | Impact | Implemented response |
|---|---|---|
| Duplicate catalog headings | Medium: repeated headings can attach wrong descriptions | Deduplicate by code and retain duplicate-code report for review |
| Irregular PDF whitespace and wrapping | High for rules; lower for display | Normalize whitespace, parse anchored headings, retain source page evidence |
| MATH 1165 and CHEM 1112 lack matching descriptions | High if selected | Preserve sourced title/credits as quarantined references |
| Most prerequisite descriptions need structured review | High | Encode reviewed selected-path rules; unresolved rules block automated scheduling |
| ITSC 4155 cites ITCS prerequisite prefixes | High | Retain unresolved condition; require departmental confirmation |
| Term offering data absent | High for registration certainty | Mark every plan as an unverified offering proposal |
| Broad O*NET skills and mixed measurement scales | Medium | Preserve scale/date metadata; supplement skill interpretation with technology examples |
| Worksheet layout and transfer-grade uncertainty | High | Require manual review, offer manual entry, refuse unknown minimum-grade assumptions |
| Variable technical electives can meet a course count without six credits | High | Enforce two technical electives **and six credits**, three concentration electives **and nine credits**, and three capstone credits |
| Catalog degree summary and general-education details require cross-reference | Medium | Encode the actual theme, communication, quantitative and science sections rather than inferring requirements from the summary credit label |

## Transformations and AI readiness

Acquisition → source checksums → text extraction → heading parsing → canonical course
codes and credit ranges → rule review → O*NET occupation filtering and scale-preserving
joins → lexical skill aliases with provenance → normalized versioned dataset → transactional
ingestion → local public-text embeddings.

Prepared descriptions and identifiers support semantic retrieval and evidence-based
explanations. Rules support eligibility filtering and constraint planning without supervised
training. There are no validated skill-proficiency labels or recommendation outcomes;
future evaluation needs advisor-reviewed mappings and real, user-supplied worksheet checks.
Importance ratings are normalized from the O*NET 1–5 scale to 0–1; original importance,
level and date values remain in the occupation–skill payload. Suppressed ratings are excluded.
Whitespace is normalized and heading boundaries separate code/title/description; titles are
not split indiscriminately on hyphens. Stable slug identifiers serve programs and requirements,
while human-facing names retain the official catalog terminology. Duplicate codes are reported,
missing references are quarantined, and permission alternatives are never assumed approved.

The prepared data supports eligibility, ranking, bounded sequencing, public-text retrieval and
cited explanations. No outcome labels or validated student skill assessments exist. The local
model selects a source-grounded public highlight; deterministic explanations connect verified
degree progress and estimated skills. Neither generation nor semantic similarity decides whether
a prerequisite is satisfied. Natural-science options are a curated initial set; additional approved
options, residency/attempt-limit checks and real worksheet layouts need further review before a
broader advising deployment. The GPA confirmation represents the lower of overall and major GPA.

The MVP performs batch ingestion with transactional activation, checks public release metadata
daily and refreshes embeddings after version changes. Public-source updates require review before
activation. Student inputs enter through file upload/manual review and never enter the public ETL.

The architecture and ER diagram are in `architecture.md`. Team-member contributions are
not fabricated; the team should add names and responsibility assignments to its report.

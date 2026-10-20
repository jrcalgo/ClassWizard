# Sprint 1 — exploration and preparation evidence

This report accompanies executable acquisition and preparation scripts and
`data/prepared/profile.json`. Counts are measured from the acquired snapshots,
not inferred from document size. The implemented concentration follows the catalog's
official title: Computer Science BS, Web/Mobile Development and Software Engineering.

## Inventory and relevance

| Source | Access / provider | Format and cadence | Role and restrictions |
|---|---|---|---|
| Charlotte 2026–2027 undergraduate catalog | Public catalog PDF, UNC Charlotte | PDF → extracted text; annual publication | Courses, credits and degree rules; public-source provenance preserved |
| DegreeWorks worksheet | Student-supplied upload; Charlotte/NinerNet | PDF; changes with academic record | Individual progress; no login scraping, no persistent student data |
| O*NET 31.0 | onetcenter.org public download; US DOL/ETA | Selected CSV tables; quarterly release cadence | Career descriptions, skill ratings, technologies and education; attribution/license retained |

Actual source byte sizes and SHA-256 values are in `dataset.json`'s manifest.
The catalog was successfully acquired from the supplied URL during implementation.

## Structure and profiling

The normalized catalog contains 3,729 records, including two quarantined references
with no matching course-description entry. Courses and programs have many-to-many
relationships. Prerequisites are logical expressions, not just edges. Program requirements
include alternatives, minimum grades, standing, credit totals, and permission conditions.
No geospatial or time-series observations are required for the MVP; catalog years and
O*NET rating dates are version metadata rather than measurements of enrollment demand.

O*NET raw selected tables have 45,500 transferable-skill rating records, 18,200 essential-
skill records, and 60,060 knowledge records. The MVP filters four occupations and 68
distinct skill/knowledge elements. Importance and level ratings are preserved separately.
Null confidence/statistical fields are not converted into zero skill importance.

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

## Transformations and AI readiness

Acquisition → source checksums → text extraction → heading parsing → canonical course
codes and credit ranges → rule review → O*NET occupation filtering and scale-preserving
joins → lexical skill aliases with provenance → normalized versioned dataset → transactional
ingestion → local public-text embeddings.

Prepared descriptions and identifiers support semantic retrieval and evidence-based
explanations. Rules support eligibility filtering and constraint planning without supervised
training. There are no validated skill-proficiency labels or recommendation outcomes;
future evaluation needs advisor-reviewed mappings and real, user-supplied worksheet checks.

The architecture and ER diagram are in `architecture.md`. Team-member contributions are
not fabricated; the team should add names and responsibility assignments to its report.

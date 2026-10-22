"""ClassWizard catalog pipeline.

Turns UNC Charlotte Acalog "Course Descriptions" print-outs (Microsoft Print to PDF)
into validated JSON in three layers:

* raw         - the exact catalog text per field, with provenance (layer A)
* normalized  - typed values derived from the raw text: credit range, gen ed labels, ... (layer B)
* structured  - requisite trees, cross-list / exclusion edges, reference resolution (layer C)

Every derived value keeps the raw text next to it, and anything that could not be
derived with certainty is flagged ``needs_review`` instead of guessed.
"""

__version__ = "0.1.0"
SCHEMA_VERSION = "1.0.0"

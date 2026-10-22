"""End-to-end run on the real print-outs.

Needs the 38 PDFs. Point CATALOG_PDF_DIR at the folder holding ..._pg1.pdf ... _pg38.pdf;
without it these tests are skipped (so CI without the PDFs still passes the unit tests).
A full run takes about 90 seconds.
"""
# pylint: disable=missing-function-docstring,redefined-outer-name
import json
import os
from collections import Counter
from pathlib import Path

import pytest

from catalog_pipeline.build import build

PDF_DIR = os.environ.get("CATALOG_PDF_DIR")
GOLDEN = Path(__file__).parent / "golden" / "raw_records.json"

pytestmark = pytest.mark.skipif(not PDF_DIR, reason="set CATALOG_PDF_DIR to run on the real PDFs")


@pytest.fixture(scope="module")
def result():
    return build(Path(PDF_DIR), "Undergraduate 2026-2027")


def test_validation_passes(result):
    assert result.report.ok, result.report.all_errors()[:10]
    assert result.report.values_checked == 16919


def test_counts(result):
    courses = result.courses["courses"]
    assert len(courses) == 3794
    assert len({c["code"] for c in courses}) == 3794
    per_page = Counter(c["provenance"]["listing_page"] for c in courses)
    assert all(n == 100 for p, n in per_page.items() if p != 38) and per_page[38] == 94


def test_field_totals(result):
    totals = Counter(k for c in result.courses["courses"] for k in c["raw_fields"])
    assert totals == {"Credit Hours": 3794, "Prerequisite(s)": 1822, "Restriction(s)": 1582,
                      "Repeatability": 808, "Cross-listed Course(s)": 513,
                      "Pre- or Corequisite(s)": 226,
                      "General Education Requirement(s) Satisfied": 170,
                      "Corequisite(s)": 302, "Grading Method": 124}


def test_golden_records(result):
    """30 hard cases: wrapped titles, page boundaries, repaired hyphens, misplaced CHEM 4090,
    empty and invalid source values. Raw text verified against pdfplumber and, for ITCS 3120,
    CHEM 4090 and the page 18 records, against the rendered page images."""
    by_code = {c["code"]: c for c in result.courses["courses"]}
    for gold in json.loads(GOLDEN.read_text(encoding="utf-8")):
        got = by_code[gold["code"]]
        for key in ("title", "section", "description", "raw_fields"):
            assert got[key] == gold[key], (gold["code"], key)
        assert got["provenance"]["listing_page"] == gold["listing_page"]


def test_hyphen_repairs(result):
    assert len(result.fixes) == 92
    assert not any(f.code == "BINF 4171" for f in result.fixes)   # source spelling kept


def test_edges(result):
    edges = result.edges["edges"]
    excl = [e for e in edges if e["type"] == "exclusion"]
    assert len(excl) == 76 and sum(e["reciprocal"] for e in excl) == 54
    unresolved = {e["target"] for e in edges if e["type"] == "requisite" and not e["target_resolved"]}
    assert len(unresolved) == 20 and "ITIS 5270" in unresolved

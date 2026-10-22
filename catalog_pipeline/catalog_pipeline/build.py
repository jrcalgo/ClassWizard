"""Stage 7: run every stage in order and assemble the output documents.

    PDFs -> extract -> parse -> repair -> validate -> normalize/structure -> schema check

The build refuses to write course data if validation finds errors (unless explicitly told
to continue), because a silently wrong page is worse than no output.
"""
from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from importlib import resources
from pathlib import Path

import jsonschema

from . import SCHEMA_VERSION, __version__
from . import normalize as norm
from .constants import FIELDS
from .extract import PageSource, discover, read_page
from .parse import RawCourse, parse_pages
from .relations import crosslist_edges, exclusion_edges, finish_edges, requisite_edges
from .repair import Fix, repair_page
from .requisites import parse_requisite
from .validate import ValidationReport, check_catalog, check_page

REQ_KEYS = {"Prerequisite(s)": "prerequisite", "Corequisite(s)": "corequisite",
            "Pre- or Corequisite(s)": "pre_or_corequisite"}


class BuildRefused(RuntimeError):
    """Validation found errors; output was not written."""

    def __init__(self, report: ValidationReport):
        super().__init__("validation failed:\n  " + "\n  ".join(report.all_errors()[:40]))
        self.report = report


@dataclass
class BuildResult:
    """Everything a build produces, before it is written to disk."""

    courses: dict
    edges: dict
    review: list[dict]
    report: ValidationReport
    fixes: list[Fix] = field(default_factory=list)


# ------------------------------------------------------------------ per-course assembly

def review_item(code: str, field_name: str, reason: str, severity: str, raw: str = "") -> dict:
    """One row of the review queue."""
    return {"code": code, "field": field_name, "severity": severity, "reason": reason, "raw": raw}


def structure_course(rec: RawCourse, catalog: str, src: PageSource,
                     order: int) -> tuple[dict, list[dict], list[dict]]:
    """Layers B and C for one course. Returns (course document, edges, review items)."""
    f = rec.fields
    review: list[dict] = []
    edges: list[dict] = []

    def flag(field_name: str, reason: str, severity: str) -> None:
        review.append(review_item(rec.code, field_name, reason, severity, f.get(field_name, "")))

    for name, value in f.items():
        if not value:
            flag(name, "field is empty in the source", "high")

    credit = norm.credit_hours(f["Credit Hours"]) if "Credit Hours" in f else None
    if credit and credit["status"] != "ok":
        flag("Credit Hours", f"credit value not understood: {credit['raw']!r}", "high")

    requisites = {}
    for label, key in REQ_KEYS.items():
        if not f.get(label):
            requisites[key] = None
            continue
        parsed = parse_requisite(f[label], label)
        requisites[key] = parsed
        for item in parsed["review"]:
            flag(label, item["reason"], item["severity"])
        if parsed["status"] == "unparsed" and not parsed["review"]:
            flag(label, "no requirement could be read", "high")
        edges += requisite_edges(rec.code, label, parsed)

    restriction = norm.restrictions(f["Restriction(s)"]) if f.get("Restriction(s)") else None
    if restriction is not None and not restriction["gates"]:
        flag("Restriction(s)", "no known kind of gate detected", "low")

    repeat = norm.repeatability(f["Repeatability"]) if f.get("Repeatability") else None
    if repeat is not None and repeat["repeatable"] is None:
        flag("Repeatability", "text does not say plainly whether the course is repeatable", "low")

    grading = norm.grading_method(f["Grading Method"]) if f.get("Grading Method") else None
    if grading is not None and grading["status"] != "ok":
        flag("Grading Method", grading["status"].replace("_", " "), "low")

    xlist = norm.cross_listed(f["Cross-listed Course(s)"]) if f.get("Cross-listed Course(s)") else None
    if xlist is not None:
        if xlist["status"] != "ok":
            flag("Cross-listed Course(s)", "text besides course codes in the field", "high")
        edges += crosslist_edges(rec.code, xlist)

    edges += exclusion_edges(rec.code, [("description", rec.description),
                                        ("Restriction(s)", f.get("Restriction(s)", ""))])
    gened = norm.gen_ed(f["General Education Requirement(s) Satisfied"]) \
        if f.get("General Education Requirement(s) Satisfied") else None

    doc = {
        "catalog": catalog,
        "code": rec.code,
        "subject": rec.subject,
        "number": rec.number,
        "number_parts": norm.course_number(rec.number),
        "title": rec.title,
        "section": rec.section,
        "description": rec.description,
        "raw_fields": {k: f[k] for k in FIELDS if k in f},
        "credit_hours": credit,
        "requisites": requisites,
        "restrictions": restriction,
        "repeatability": repeat,
        "cross_listed": xlist,
        "gen_ed": gened,
        "grading": grading,
        "review": [{k: r[k] for k in ("field", "severity", "reason")} for r in review],
        "provenance": {"listing_page": rec.page, "order": order, "source_file": src.path.name,
                       "printed_at": src.printed_at, "producer": src.producer},
    }
    return doc, edges, review


# ------------------------------------------------------------------ pipeline

def load_schema(name: str) -> dict:
    """A JSON Schema shipped inside the package."""
    return json.loads(resources.files("catalog_pipeline").joinpath("schema", name).read_text("utf-8"))


def repair_and_validate(sources: list[PageSource], by_page: dict[int, list[RawCourse]],
                        raw: list[RawCourse], page_size: int) -> tuple[list[Fix], ValidationReport]:
    """Repair hyphens page by page, then run every validation check."""
    fixes: list[Fix] = []
    report = ValidationReport()
    last = sources[-1].page
    for src in sources:
        recs = by_page.get(src.page, [])
        fixes += repair_page(recs, src.reference)
        page_rep, checked = check_page(src, recs, is_last=src.page == last, page_size=page_size)
        report.pages.append(page_rep)
        report.values_checked += checked
    check_catalog(report, raw)
    return fixes, report


def build(pdf_dir: Path, catalog: str, *, page_size: int = 100,
          allow_errors: bool = False) -> BuildResult:
    """Run the whole pipeline on a folder of pgN.pdf files."""
    sources = [read_page(p) for p in discover(pdf_dir)]
    if not sources:
        raise FileNotFoundError(f"no pgN.pdf files in {pdf_dir}")
    raw = parse_pages([(s.page, s.text) for s in sources])
    by_page: dict[int, list[RawCourse]] = {}
    for rec in raw:
        by_page.setdefault(rec.page, []).append(rec)

    fixes, report = repair_and_validate(sources, by_page, raw, page_size)
    if not report.ok and not allow_errors:
        raise BuildRefused(report)

    src_by_page = {s.page: s for s in sources}
    courses, edges, review = [], [], []
    for order, rec in enumerate(raw, start=1):
        doc, rec_edges, rec_review = structure_course(rec, catalog, src_by_page[rec.page], order)
        courses.append(doc)
        edges += rec_edges
        review += rec_review
    known = {c["code"] for c in courses}
    edges = finish_edges(edges, known)
    for edge in edges:
        if edge["type"] == "requisite" and edge["in_tree"] and not edge["target_resolved"]:
            review.append(review_item(edge["source"], edge["field"],
                                      f"requires {edge['target']}, which is not in this catalog",
                                      "low", edge["target"]))
        if edge["type"] == "exclusion" and edge["needs_review"]:
            review.append(review_item(edge["source"], edge["field"],
                                      f"exclusion may cover a range of courses, not only "
                                      f"{edge['target']}", "high", edge["evidence"]))

    courses_doc = {
        "schema_version": SCHEMA_VERSION,
        "generator": f"catalog_pipeline {__version__}",
        "catalog": catalog,
        "sources": [{"listing_page": s.page, "file": s.path.name, "pdf_pages": s.pdf_pages,
                     "producer": s.producer, "printed_at": s.printed_at,
                     "printed_url": s.printed_url} for s in sources],
        "courses": courses,
    }
    edges_doc = {"schema_version": SCHEMA_VERSION, "catalog": catalog, "edges": edges}
    jsonschema.validate(courses_doc, load_schema("courses.schema.json"))
    jsonschema.validate(edges_doc, load_schema("edges.schema.json"))
    return BuildResult(courses_doc, edges_doc, review, report, fixes)


# ------------------------------------------------------------------ writing

def write_outputs(result: BuildResult, out_dir: Path) -> list[Path]:
    """Write all output files; returns their paths."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []

    def dump(name: str, obj) -> None:
        path = out_dir / name
        path.write_text(json.dumps(obj, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        written.append(path)

    dump("courses.json", result.courses)
    dump("edges.json", result.edges)
    dump("hyphen_fixes.json", [asdict(f) for f in result.fixes])
    dump("validation_report.json", report_dict(result.report))

    path = out_dir / "review_queue.csv"
    order = {"high": 0, "low": 1}
    rows = sorted(result.review, key=lambda r: (order[r["severity"]], r["code"], r["field"]))
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, ["severity", "code", "field", "reason", "raw"])
        writer.writeheader()
        writer.writerows({k: r[k] for k in writer.fieldnames} for r in rows)
    written.append(path)

    path = out_dir / "courses_flat.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(["code", "subject", "number", "title", "section", "description",
                         *FIELDS, "listing_page", "order", "source_file"])
        for c in result.courses["courses"]:
            writer.writerow([c["code"], c["subject"], c["number"], c["title"], c["section"],
                             c["description"], *(c["raw_fields"].get(k, "") for k in FIELDS),
                             c["provenance"]["listing_page"], c["provenance"]["order"],
                             c["provenance"]["source_file"]])
    written.append(path)
    return written


def report_dict(report: ValidationReport) -> dict:
    """Validation report as plain data."""
    return {"ok": report.ok, "values_checked": report.values_checked,
            "errors": report.all_errors(), "warnings": report.warnings,
            "pages": [asdict(p) for p in report.pages]}


def requisite_summary(courses: list[dict]) -> dict:
    """Count requisite statuses per field (for the console summary and README)."""
    out: dict[str, dict[str, int]] = {}
    for label, key in REQ_KEYS.items():
        counts: dict[str, int] = {}
        for c in courses:
            req = c["requisites"][key]
            if req is not None:
                counts[req["status"]] = counts.get(req["status"], 0) + 1
        out[label] = counts
    return out


__all__ = ["build", "write_outputs", "BuildRefused", "BuildResult", "requisite_summary"]

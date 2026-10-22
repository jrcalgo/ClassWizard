"""Stage 4: decide whether the extracted pages can be trusted.

Every check here is one that caught, or would have caught, a real defect in this data:

* no text layer / too few courses  -> the first page 18, printed with courses collapsed
                                      and its text drawn as shapes
* label counts raw != parsed       -> a field label swallowed into another field
* pdfplumber disagrees on codes    -> a course header lost or invented by one extractor
* value not verbatim in reference  -> a wrapped line attached to the wrong course, or a
                                      bad repair (two wrong-course hyphen fixes were caught)
* pagination bar / page sequence   -> a file saved under the wrong page number, or a gap

Errors make the build refuse to write output. Warnings are reported but don't block it.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from .constants import FIELDS, label_count_re
from .extract import PageSource
from .parse import RawCourse
from .repair import norm

MIN_TEXT_CHARS = 5000          # a real 100-course page has ~40,000; the broken page 18 had ~0
REF_HEADER_RE = re.compile(r"^([A-Z]{3,5}) (\d{4}[A-Z]{0,2}) - ", re.MULTILINE)
NAV_RE = re.compile(r"Page: (.*)")


@dataclass
class PageReport:
    """Result of all checks for one listing page."""

    page: int
    file: str
    courses: int
    pdf_pages: int
    producer: str | None
    printed_at: str | None
    printed_url: str | None
    label_counts: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class ValidationReport:
    """All page reports plus catalog-wide findings."""

    pages: list[PageReport] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    values_checked: int = 0

    @property
    def ok(self) -> bool:
        """True when nothing blocks the build."""
        return not self.errors and not any(p.errors for p in self.pages)

    def all_errors(self) -> list[str]:
        """Catalog errors followed by page errors, each prefixed with its page."""
        return self.errors + [f"pg{p.page}: {e}" for p in self.pages for e in p.errors]


def _field_counts(text: str) -> dict[str, int]:
    return {f: len(label_count_re(f).findall(text)) for f in FIELDS}


def check_page(src: PageSource, recs: list[RawCourse], *, is_last: bool,
               page_size: int) -> tuple[PageReport, int]:
    """Run every per-page check. Returns the report and the number of values compared."""
    rep = PageReport(src.page, src.path.name, len(recs), src.pdf_pages, src.producer,
                     src.printed_at, src.printed_url)
    if src.char_count < MIN_TEXT_CHARS:
        rep.errors.append(f"no usable text layer ({src.char_count} characters); re-print "
                          "the page with all courses expanded")
        return rep, 0
    if (len(recs) != page_size) if not is_last else not 0 < len(recs) <= page_size:
        rep.errors.append(f"{len(recs)} courses, expected {page_size}"
                          f"{' or fewer (last page)' if is_last else ''}; was the course "
                          "list expanded when printed?")

    raw = _field_counts(src.text)
    parsed = {f: sum(f in r.fields for r in recs) for f in FIELDS}
    ref = _field_counts(src.reference)
    rep.label_counts = parsed
    for f in FIELDS:
        if raw[f] != parsed[f]:
            rep.errors.append(f"'{f}' appears {raw[f]}x in the text but {parsed[f]}x in records")
        if ref[f] != parsed[f]:
            rep.errors.append(f"'{f}': pdfplumber finds {ref[f]}, parser {parsed[f]}")

    ref_codes = [f"{a} {b}" for a, b in REF_HEADER_RE.findall(src.reference)]
    if ref_codes != [r.code for r in recs]:
        missing = sorted(set(ref_codes) - {r.code for r in recs})
        extra = sorted({r.code for r in recs} - set(ref_codes))
        rep.errors.append(f"course list differs from pdfplumber (only pdfplumber: {missing}; "
                          f"only parser: {extra}; or order differs)")

    nav = NAV_RE.search(src.text)
    if not nav:
        rep.warnings.append("no pagination bar found; page number not cross-checked")
    elif str(src.page) not in re.findall(r"\d+", nav.group(1)):
        rep.errors.append(f"pagination bar '{nav.group(1)[:60]}' does not include page "
                          f"{src.page}; is the file named after the right page?")

    ref_norm, checked = norm(src.reference), 0
    for rec in recs:
        for name, value in [("title", rec.title), ("description", rec.description),
                            *rec.fields.items()]:
            if not value:
                continue
            checked += 1
            if norm(value) not in ref_norm:
                rep.errors.append(f"{rec.code} {name} not found verbatim in pdfplumber text: "
                                  f"{value[:80]!r}")
    return rep, checked


def check_catalog(report: ValidationReport, recs: list[RawCourse]) -> None:
    """Checks that need all pages at once."""
    pages = sorted({p.page for p in report.pages})
    expected = list(range(1, pages[-1] + 1)) if pages else []
    if pages != expected:
        report.errors.append(f"listing pages missing: {sorted(set(expected) - set(pages))}")

    dupes = [c for c, n in Counter(r.code for r in recs).items() if n > 1]
    if dupes:
        report.errors.append(f"duplicate course codes: {dupes}")

    def num_key(num: str) -> tuple[int, str]:
        return int(num[:4]), num[4:]

    for prev, nxt in zip(recs, recs[1:]):
        if (prev.section == nxt.section and prev.subject == nxt.subject
                and num_key(nxt.number) <= num_key(prev.number)):
            report.warnings.append(f"order break within {prev.section}: {prev.code} "
                                   f"(pg{prev.page}) -> {nxt.code} (pg{nxt.page})")

    producers = Counter(p.producer for p in report.pages)
    if len(producers) > 1:
        report.warnings.append(f"pages produced by different programs: {dict(producers)}")
    urls = Counter(p.printed_url or "" for p in report.pages)
    if len(urls) > 1:
        report.warnings.append(f"pages printed from {len(urls)} different URL forms: "
                               f"{dict(urls)}")
    empty = [f"{r.code} {k}" for r in recs for k, v in r.fields.items() if not v]
    if empty:
        report.warnings.append(f"{len(empty)} empty field values in the source: {empty}")

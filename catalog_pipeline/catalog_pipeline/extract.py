"""Stage 1: read each listing PDF with two independent text extractors.

* ``pdftotext`` (poppler) gives the primary text the parser works on. Its reading order
  is reliable for these print-outs, but it deletes a '-' at the end of a line.
* ``pdfplumber`` (pdfminer) gives a reference text. It keeps line-end hyphens, so it is
  used to repair them and to cross-check every parsed value (see validate.py).

Using two unrelated extractors means a defect in one of them shows up as a disagreement
instead of silently entering the data.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pdfplumber

# Running header/footer lines that "Print headers and footers" adds to every printed page.
FURNITURE_RES = [re.compile(p) for p in (
    r"^\d+ of \d+ \d{1,2}/\d{1,2}/\d{4}, \d{1,2}:\d{2} [AP]M$",   # "12 of 47 10/1/2026, 9:56 AM"
    r"^\d{1,2}/\d{1,2}/\d{4}, \d{1,2}:\d{2} [AP]M$",              # date on its own line
    r"^\d+ of \d+$",                                             # page counter on its own line
    r"^Course Descriptions - University of North Carolina at Charlotte.*$",  # page title (+URL)
    r"^https://catalog\.charlotte\.edu\S*$",                     # truncated URL
    r"^Schedule of Classes$",                                    # link printed after each course
)]
PAGE_FILE_RE = re.compile(r"pg(\d+)\.pdf$", re.IGNORECASE)
PRINTED_URL_RE = re.compile(r"https://catalog\.charlotte\.edu/\S+")


class ExtractionError(RuntimeError):
    """Raised when a PDF cannot be read at all (missing tool, unreadable file)."""


@dataclass
class PageSource:
    """Everything later stages need to know about one listing page (one PDF file)."""

    path: Path
    page: int                      # listing page number, taken from the file name (pgN.pdf)
    text: str                      # pdftotext output, the parser's input
    reference: str                 # pdfplumber output with page furniture removed
    pdf_pages: int                 # number of printed sheets in the PDF
    producer: str | None
    printed_at: str | None         # ISO-8601 from the PDF CreationDate
    printed_url: str | None        # truncated URL from the printed header
    char_count: int = 0            # characters in the text layer; 0 means no usable text
    notes: list[str] = field(default_factory=list)


def page_number(path: Path) -> int:
    """Listing page number from a file name such as 'Undergraduate_Catalog_2026-2027_pg18.pdf'."""
    match = PAGE_FILE_RE.search(path.name)
    if not match:
        raise ExtractionError(f"{path.name}: file name must end in pgN.pdf")
    return int(match.group(1))


def run_pdftotext(path: Path) -> str:
    """Plain (non-layout) pdftotext output; non-layout mode keeps one text column per line."""
    exe = shutil.which("pdftotext")
    if exe is None:
        raise ExtractionError("pdftotext not found; install poppler-utils")
    result = subprocess.run([exe, str(path), "-"], capture_output=True, text=True,
                            encoding="utf-8", check=False)
    if result.returncode != 0:
        raise ExtractionError(f"{path.name}: pdftotext failed: {result.stderr.strip()}")
    return result.stdout


def parse_pdf_date(value: str | None) -> str | None:
    """Convert a PDF date ("D:20261001094420-04'00'") to ISO-8601, or None if absent/odd."""
    if not value:
        return None
    match = re.match(r"D:(\d{14})([+-])(\d{2})'?(\d{2})", value)
    if not match:
        return None
    stamp = datetime.strptime(match.group(1), "%Y%m%d%H%M%S")
    sign = 1 if match.group(2) == "+" else -1
    offset = timedelta(hours=int(match.group(3)), minutes=int(match.group(4))) * sign
    return stamp.replace(tzinfo=timezone(offset)).isoformat()


def strip_furniture(lines: list[str]) -> list[str]:
    """Drop the running header/footer lines added by the print dialog."""
    return [ln for ln in lines if not any(r.match(ln.strip()) for r in FURNITURE_RES)]


def read_page(path: Path) -> PageSource:
    """Extract one PDF with both extractors and collect its print metadata."""
    path = Path(path)
    text = run_pdftotext(path)
    with pdfplumber.open(path) as pdf:
        meta = pdf.metadata or {}
        plumber_text = "\n".join((pg.extract_text() or "") for pg in pdf.pages)
        sheets = len(pdf.pages)
    url = PRINTED_URL_RE.search(text)
    return PageSource(
        path=path,
        page=page_number(path),
        text=text,
        reference="\n".join(strip_furniture(plumber_text.split("\n"))),
        pdf_pages=sheets,
        producer=meta.get("Producer"),
        printed_at=parse_pdf_date(meta.get("CreationDate")),
        printed_url=url.group(0) if url else None,
        char_count=len(re.sub(r"\s", "", text)),
    )


def discover(pdf_dir: Path) -> list[Path]:
    """All pgN.pdf files in a folder, ordered by listing page number."""
    files = [p for p in Path(pdf_dir).iterdir() if PAGE_FILE_RE.search(p.name)]
    return sorted(files, key=page_number)

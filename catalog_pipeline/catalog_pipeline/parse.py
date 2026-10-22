"""Stage 2: turn pdftotext output into one raw record per course (layer A).

The listing is a flat stream of lines: an optional department heading, then for each course
a header line ("ITSC 1212 - Title"), description lines, and labelled fields
("Credit Hours: (3)", "Prerequisite(s): ...") whose values can wrap over many lines.
The parser walks that stream once with a small state machine:

    heading -> header -> description -> field -> field ... -> header | heading

This is the logic of the validated ``catalog_parse.py``, restructured so that the set of
known headings is per-run state instead of a module global.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .constants import FIELDS, HEADER_RE

LABEL_ALT = "|".join(re.escape(f) for f in sorted(FIELDS, key=len, reverse=True))
# A label at the start of a line ("Pre- or Corequisite(s)" is tried before "Corequisite(s)").
FIELD_AT_START = re.compile(r"^(" + LABEL_ALT + r"):\s*(.*)$")
# A label glued into the middle of a line (".Credit Hours: (3)"); split the line there.
FIELD_ANYWHERE = re.compile(r"(?<!^)(?<![\w-])(?<!Pre- or )(" + LABEL_ALT + r"):")

# Page furniture lines, as pdftotext prints them.
NOISE_LINE = [re.compile(p) for p in (
    r"^\d{1,2}/\d{1,2}/\d{4}, \d{1,2}:\d{2} [AP]M$",
    r"^\d+ of \d+( \d{1,2}/\d{1,2}/\d{4}, \d{1,2}:\d{2} [AP]M)?$",
    r"^Course Descriptions - University of North Carolina at Charlotte",
    r"^https://catalog\.charlotte\.edu",
    r"^Contract All Courses( \|)?( Print this Page)?$",
    r"^Print this Page$",
    r"^Page: \d",
    r"^(Undergraduate|Graduate) Catalog \| \d{4}-\d{4}$",
)]
INLINE_NOISE = re.compile(r"\s*Schedule of Classes\s*")
# The fixed preamble at the top of every listing page (filter box, helpful links) ends here.
PREAMBLE_END = "DegreeWorks"
# Occasionally the running header is glued onto a body line; cut it out.
GLUED_HEADER = re.compile(
    r"\s*Course Descriptions - University of North Carolina at Charlotte\s+"
    r"https://catalog\.charlotte\.edu/\S*\s*")
# Words a wrapped title line commonly ends on: the next line continues the title.
CONNECTOR_END = re.compile(r"((?<=\s)(and|of|the|in|for|to|with|on|from|through|&)|[:,\-–/])$")
# Lines that look like a heading but are the wrapped tail of a field value.
NOT_HEADINGS = {"Reasoning"}


def normalise_lines(text: str) -> list[str]:
    """Clean pdftotext output into content lines: no furniture, no blank lines,
    and one field label per line."""
    text = (text.replace("\r\n", "\n").replace("\x02", "-").replace("\f", "\n")
            .replace("&nbsp;", " "))
    lines = text.split("\n")
    if PREAMBLE_END in lines[:60]:
        lines = lines[lines.index(PREAMBLE_END) + 1:]
    out: list[str] = []
    for raw in lines:
        line = raw.strip()
        if line and not line.startswith("Course Descriptions - University"):
            line = GLUED_HEADER.sub(" ", line).strip()
        if not line or any(p.search(line) for p in NOISE_LINE):
            continue
        line = INLINE_NOISE.sub(" ", line).strip()
        if not line:
            continue
        parts, last = [], 0
        for match in FIELD_ANYWHERE.finditer(line):
            parts.append(line[last:match.start()].strip())
            last = match.start()
        parts.append(line[last:].strip())
        out.extend(p for p in parts if p)
    return out


def looks_like_heading(line: str) -> bool:
    """A department heading: short, capitalised, no digits, no closing punctuation."""
    if re.search(r"\d", re.sub(r"\bK-12\b", "", line)) or line.endswith((".", ",", ";", ":")):
        return False
    if not line[0].isupper() or len(line.split()) > 9:
        return False
    return not FIELD_AT_START.match(line)


@dataclass
class RawCourse:
    """One course exactly as printed (layer A)."""

    page: int
    subject: str
    number: str
    title: str
    section: str | None
    description: str = ""
    fields: dict[str, str] = field(default_factory=dict)

    @property
    def code(self) -> str:
        """Course code as printed, e.g. 'BIOL 2120L'."""
        return f"{self.subject} {self.number}"


@dataclass
class Parser:
    """Parses pages in order. Run :meth:`learn_headings` over all pages first, so headings
    seen unambiguously anywhere help decide ambiguous lines everywhere."""

    known_headings: set[str] = field(default_factory=set)

    def learn_headings(self, texts: list[tuple[int, str]]) -> None:
        """Pass 1: collect headings that appear where nothing else could appear."""
        for page, text in texts:
            self.parse_page(page, text)

    @staticmethod
    def _join_wrapped_title(lines: list[str], i: int, title: str) -> tuple[str, int]:
        """If a long title wrapped onto the next line, append that line; return (title, i)."""
        if i + 1 >= len(lines) or FIELD_AT_START.match(lines[i + 1]) or HEADER_RE.match(lines[i + 1]):
            return title, i
        nxt, line = lines[i + 1], lines[i]
        wrapped = (len(line) >= 58 and len(nxt) <= 45 and not nxt.endswith(".")
                   and not re.search(r"[A-Z]{3,5} \d{4}", nxt)
                   and nxt[:1].isupper() and len(nxt.split()) <= 5)
        if CONNECTOR_END.search(title) or wrapped:
            return f"{title} {nxt}", i + 1
        return title, i

    def parse_page(self, page: int, text: str) -> list[RawCourse]:  # pylint: disable=too-many-branches
        """Parse one page's text into raw course records."""
        lines = normalise_lines(text)
        recs: list[RawCourse] = []
        cur: RawCourse | None = None
        fld: str | None = None
        heading: str | None = None
        i = 0
        while i < len(lines):
            line = lines[i]
            header = HEADER_RE.match(line)
            if header:
                title, i = self._join_wrapped_title(lines, i, header.group(3))
                cur = RawCourse(page, header.group(1), header.group(2), title.strip(), heading)
                recs.append(cur)
                fld = None
            elif (labelled := FIELD_AT_START.match(line)) and cur is not None:
                fld = labelled.group(1)
                old = cur.fields.get(fld)
                cur.fields[fld] = f"{old} {labelled.group(2)}".strip() if old is not None \
                    else labelled.group(2)
            elif cur is None:                       # text before the first course = heading
                heading = line
                self.known_headings.add(line)
            elif fld is None:                       # still inside the description
                cur.description = f"{cur.description} {line}".strip()
            elif self._is_heading(lines, i, cur, fld):
                heading, fld, cur = line, None, None
            else:                                   # wrapped continuation of the field
                cur.fields[fld] = f"{cur.fields[fld]} {line}".strip()
            i += 1
        for rec in recs:
            rec.fields = {k: tidy(v) for k, v in rec.fields.items()}
            rec.description = re.sub(r"\s+", " ", rec.description).strip()
        return recs

    def _is_heading(self, lines: list[str], i: int, cur: RawCourse, fld: str) -> bool:
        """Is lines[i] a department heading sitting right above the next course header?"""
        line = lines[i]
        nxt = HEADER_RE.match(lines[i + 1]) if i + 1 < len(lines) else None
        if not nxt or not looks_like_heading(line) or line in NOT_HEADINGS:
            return False
        same_prefix_unfinished = (nxt.group(1) == cur.subject
                                  and not cur.fields[fld].rstrip().endswith("."))
        return not same_prefix_unfinished or line in self.known_headings


def tidy(value: str) -> str:
    """Collapse whitespace and remove the space pdftotext leaves before punctuation."""
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"\s+([,.;)])", r"\1", value)
    return value.strip()


def parse_pages(texts: list[tuple[int, str]]) -> list[RawCourse]:
    """Two-pass parse of (page number, pdftotext text) pairs, in page order."""
    parser = Parser()
    parser.learn_headings(texts)
    out: list[RawCourse] = []
    for page, text in texts:
        out.extend(parser.parse_page(page, text))
    return out

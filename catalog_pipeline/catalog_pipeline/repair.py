"""Stage 3: restore the hyphens and dashes pdftotext deletes at line ends.

pdftotext treats a '-' at the end of a line as soft hyphenation and removes it, gluing the
two halves ("three-\\ndimensional" -> "threedimensional", "fences -\\nare" -> "fences are").
The catalog never soft-hyphenates (the browser only wraps at real hyphens), so every such '-'
is real text. pdfplumber keeps them, so its text is the reference.

Safety rule: a candidate fix is applied to a value only if the fixed value then matches the
pdfplumber text of the same file further than before. A fix therefore cannot land on the
wrong course, which a blind "first occurrence on the page" replacement did in testing
(BINF 4171 instead of BINF 4191, MATH 1340 instead of MATH 1341).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .parse import RawCourse


def norm(text: str) -> str:
    """Comparable form of a text: entities as spaces, line-break hyphens joined, whitespace
    collapsed. Applied to both sides of every comparison so layout differences don't count."""
    text = text.replace("&nbsp;", " ")
    text = re.sub(r"(\w)-\n(\w)", r"\1-\2", text)
    text = text.replace("Schedule of Classes", " ")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([,.;)])", r"\1", text)
    return text.strip()


def candidates(reference: str) -> set[tuple[str, str]]:
    """(damaged form, correct form) pairs implied by line-end hyphens in the reference text."""
    pairs: set[tuple[str, str]] = set()
    for m in re.finditer(r"(\w+)-\n(\w+)", reference):        # word-\nword
        pairs.add((m.group(1) + m.group(2), f"{m.group(1)}-{m.group(2)}"))   # glued by pdftotext
        pairs.add((f"{m.group(1)}- {m.group(2)}", f"{m.group(1)}-{m.group(2)}"))  # page break
    for m in re.finditer(r"(\w+) -\n(\w+)", reference):       # word -\nword (a spaced dash)
        pairs.add((f"{m.group(1)} {m.group(2)}", f"{m.group(1)} - {m.group(2)}"))
    return pairs


def longest_prefix(value: str, target: str) -> int:
    """Length of the longest prefix of ``value`` that occurs in ``target`` (binary search;
    valid because a prefix of an occurring string also occurs)."""
    lo, hi = 0, len(value)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if value[:mid] in target:
            lo = mid
        else:
            hi = mid - 1
    return lo


@dataclass
class Fix:
    """One applied repair, kept for the audit log."""

    page: int
    code: str
    field: str
    damaged: str
    restored: str


def repair_value(value: str, ref_norm: str, pairs: set[tuple[str, str]],
                 max_rounds: int = 6) -> tuple[str, list[tuple[str, str]]]:
    """Apply verified fixes to one value until it matches the reference (or nothing helps)."""
    applied: list[tuple[str, str]] = []
    for _ in range(max_rounds):
        if norm(value) in ref_norm:
            break
        best = longest_prefix(norm(value), ref_norm)
        improved = False
        for bad, good in sorted(pairs):                     # sorted: deterministic order
            for m in re.finditer(r"(?<!\w)" + re.escape(bad) + r"(?!\w)", value):
                trial = value[:m.start()] + good + value[m.end():]
                if longest_prefix(norm(trial), ref_norm) > best:
                    value, improved = trial, True
                    applied.append((bad, good))
                    break
            if improved:
                break
        if not improved:
            break
    return value, applied


def repair_page(records: list[RawCourse], reference: str) -> list[Fix]:
    """Repair every value of the records from one page in place; return the fixes made."""
    ref_norm, pairs = norm(reference), candidates(reference)
    fixes: list[Fix] = []
    if not pairs:
        return fixes
    for rec in records:
        targets = [("title", rec.title), ("description", rec.description), *rec.fields.items()]
        for name, value in targets:
            if not value or norm(value) in ref_norm:
                continue
            new, applied = repair_value(value, ref_norm, pairs)
            if not applied:
                continue
            if name == "title":
                rec.title = new
            elif name == "description":
                rec.description = new
            else:
                rec.fields[name] = new
            fixes.extend(Fix(rec.page, rec.code, name, bad, good) for bad, good in applied)
    return fixes

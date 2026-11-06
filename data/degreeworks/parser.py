"""Parse a Degree Works audit PDF into structured fields."""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple, Union

import pdfplumber


_COURSE_RE = re.compile(
    r"\b([A-Z]{2,5})\s+(\d{4})\s+"
    r"((?:(?![A-Z]{2,5}\s+\d{4}\b)(?!Still needed\b).)+?)\s+"
    r"(\*[A-Z]+|[A-F][+-]?|S|P|CR|TR)\s+"
    r"\((\d+(?:\.\d+)?)\)\s+"
    r"((?:Fall|Spring|Summer|Winter)\s+\d{4})"
)
_REQ_KIND = re.compile(r"\b(?:Classes in|Class in|Credits in)\b")
_CODE_TOKEN = re.compile(r"[A-Z]{2,5}|@|\d{4}")
_IN_PROGRESS = {"*IP", "IP"}
_PREREGISTERED = {"*REG", "REG", "*PR", "PR"}
_COMPLETED = re.compile(r"[A-F][+-]?|S|P|CR|TR")


@dataclass
class Course:
    """One course row from the audit."""

    code: str
    title: str
    grade: str
    credits: Union[int, float]
    term: str


@dataclass
class UnmetRequirement:
    """A Still needed rule that names classes or credits."""

    block: str
    text: str
    course_codes: List[str]


@dataclass
class Audit:
    """Fields read from one Degree Works audit.

    The student ID printed on the audit is not stored.
    """

    # A parsed audit is one record; pylint's attribute cap is for service objects.
    # pylint: disable=too-many-instance-attributes

    student_name: str
    degree: str
    audit_date: str
    level: str
    classification: str
    program: str
    major: str
    college: str
    advisors: List[str]
    catalog_year: str
    credits_required: Union[int, float]
    credits_applied: Union[int, float]
    courses_completed: List[Course]
    courses_in_progress: List[Course]
    courses_preregistered: List[Course]
    courses_not_taken: List[UnmetRequirement]


def parse_audit(source: Union[str, Path, bytes]) -> Audit:
    """Read a Degree Works PDF and return the audit fields."""
    raw = _extract_text(source)
    flat = _flatten(raw)
    header = _header(flat)
    credits_required, credits_applied = _credits(flat)
    completed, in_progress, preregistered = _classify(_courses(flat))
    return Audit(
        student_name=header["student_name"],
        degree=header["degree"],
        audit_date=header["audit_date"],
        level=header["level"],
        classification=header["classification"],
        program=header["program"],
        major=header["major"],
        college=header["college"],
        advisors=header["advisors"],
        catalog_year=_first(flat, r"Catalog year:\s*(\d{4}-\d{4})", "catalog year"),
        credits_required=credits_required,
        credits_applied=credits_applied,
        courses_completed=completed,
        courses_in_progress=in_progress,
        courses_preregistered=preregistered,
        courses_not_taken=_unmet(raw),
    )


def _extract_text(source: Union[str, Path, bytes]) -> str:
    handle = io.BytesIO(source) if isinstance(source, bytes) else source
    with pdfplumber.open(handle) as pdf:
        pages = [page.extract_text() or "" for page in pdf.pages]
    return "\n".join(pages)


def _flatten(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _header(flat: str) -> dict:
    """Labeled header values. Student ID is skipped on purpose."""
    match = re.search(
        r"Student name\s+(.+?)\s+(?:Overall GPA|Student ID)\s+"
        r".+?\s+Degree\s+(?!progress\b)(.+?)\s+Audit date\s+"
        r"(\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}\s*[AP]M)\s+"
        r".*?\s+Level\s+(.+?)\s+Classification\s+(.+?)\s+"
        r"Program\s+(.+?)\s+Major\s+(.+?)\s+College\s+(.+?)\s+"
        r"Advisors\s+(.+?)\s+Degree in\b",
        flat,
    )
    if match is None:
        raise ValueError("degree audit header could not be read")
    return {
        "student_name": match.group(1).strip(),
        "degree": match.group(2).strip(),
        "audit_date": re.sub(r"\s+", " ", match.group(3).strip()),
        "level": match.group(4).strip(),
        "classification": match.group(5).strip(),
        "program": match.group(6).strip(),
        "major": match.group(7).strip(),
        "college": match.group(8).strip(),
        "advisors": _advisors(match.group(9)),
    }


def _advisors(raw: str) -> List[str]:
    parts = re.split(r"\s*;\s*|\s+and\s+", raw.strip())
    return [part.strip() for part in parts if part.strip()]


def _first(flat: str, pattern: str, label: str) -> str:
    match = re.search(pattern, flat)
    if match is None:
        raise ValueError(f"degree audit {label} could not be read")
    return match.group(1).strip()


def _credits(flat: str) -> Tuple[Union[int, float], Union[int, float]]:
    """Major-block pair. Ignores the in-progress section's applied total."""
    match = re.search(
        r"Credits required:\s*(\d+(?:\.\d+)?)\s+Credits applied:\s*(\d+(?:\.\d+)?)",
        flat,
    )
    if match is None:
        raise ValueError("degree audit credits could not be read")
    return _number(match.group(1)), _number(match.group(2))


def _number(value: str) -> Union[int, float]:
    number = float(value)
    if number.is_integer():
        return int(number)
    return number


def _courses(flat: str) -> List[Course]:
    found = []
    seen = set()
    for match in _COURSE_RE.finditer(flat):
        code = f"{match.group(1)} {match.group(2)}"
        grade = match.group(4)
        term = match.group(6)
        key = (code, grade, term)
        if key in seen:
            continue
        seen.add(key)
        found.append(
            Course(
                code=code,
                title=match.group(3).strip(),
                grade=grade,
                credits=_number(match.group(5)),
                term=term,
            )
        )
    return found


def _classify(
    courses: List[Course],
) -> Tuple[List[Course], List[Course], List[Course]]:
    completed: List[Course] = []
    in_progress: List[Course] = []
    preregistered: List[Course] = []
    for course in courses:
        grade = course.grade.upper()
        if grade in _IN_PROGRESS:
            in_progress.append(course)
        elif grade in _PREREGISTERED:
            preregistered.append(course)
        elif _COMPLETED.fullmatch(grade):
            completed.append(course)
    return completed, in_progress, preregistered


def _unmet(raw: str) -> List[UnmetRequirement]:
    """Still needed rules that name classes or credits, one block per line."""
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in raw.splitlines()]
    lines = [line for line in lines if line]
    unmet: List[UnmetRequirement] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if "Still needed:" not in line:
            index += 1
            continue
        block, _, rest = line.partition("Still needed:")
        parts = [rest.strip()]
        index += 1
        while index < len(lines) and _continues_requirement(lines[index]):
            parts.append(lines[index])
            index += 1
        text = " ".join(part for part in parts if part).strip()
        if _REQ_KIND.search(text) is None:
            continue
        unmet.append(
            UnmetRequirement(
                block=block.strip(),
                text=text,
                course_codes=_course_codes(text),
            )
        )
    return unmet


def _continues_requirement(line: str) -> bool:
    if "Still needed:" in line:
        return False
    return line.startswith("or ") or line[:1].islower() or bool(re.match(r"\d{4}\b", line))


def _course_codes(text: str) -> List[str]:
    match = re.search(r"(?:Classes in|Class in|Credits in)\s+(.+)$", text)
    if match is None:
        return []
    codes: List[str] = []
    subject: Optional[str] = None
    for token in _CODE_TOKEN.findall(match.group(1)):
        if token == "@":
            continue
        if token.isalpha():
            subject = token
            continue
        if subject is not None:
            codes.append(f"{subject} {token}")
    return codes

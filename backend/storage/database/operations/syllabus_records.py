"""Turn structured syllabus JSON records into rows for the syllabus_* tables."""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

CODE = re.compile(r"\b([A-Z]{2,5}) ?(\d{4}[A-Z]?)\b")
NOT_SUBJECTS = {"CRN", "TBD", "SEC", "ROOM"}  # registration numbers etc. that look like codes
CREDITS_SUFFIX = re.compile(
    r"[\s,|(-]*(?<![A-Za-z0-9])\d+(?:\.\d+)?(?:\s*-\s*\d+)?\s*credit(?:s|\s+hours?)\b.*$", re.IGNORECASE
)
MAX_CHUNK = 1500
MAX_TITLE = 120
NOT_TITLE = re.compile(r"[|\[\]{}@#;]")  # characters real titles do not use
# Bump when parse_record() output changes, so existing databases reload the records.
PARSER_VERSION = 4

# Staff, contact and meeting details (times, rooms) in syllabus text. They are not course content, and
# feeding them to /explain let the model "answer" who teaches a course from an
# unrelated syllabus. Sentences matching any of these are dropped.
_STAFF = re.compile(
    r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"                     # e-mail address
    r"|\boffice hours?\b"
    r"|\bteaching assistants?\b"
    r"|\binstructors?\s*(?::|\bo\b)"                  # "Instructor:" / "Instructors o ..."
    r"|^\s*(?:dr\.|prof\.|professor)\s+[A-Z]"
    r"|\(?\b\d{3}\)?[-. ]\d{3}-\d{4}\b"               # phone number
    r"|\bcanvas page\b"
    r"|\b\d{1,2}:\d{2}\s*(?:-\s*\d{1,2}:\d{2}\s*)?[ap]\.?m\b"  # class time "5:30-8:15PM"
    r"|\b(?:room|rm\.?|bldg\.?)\s*#?\s*\d{2,4}[a-z]?\b",
    re.IGNORECASE,
)
_TA = re.compile(r"\bTAs?\b")                         # "TA" only in capitals
_SENTENCES = re.compile(r"(?<=[.!?;])\s+")


def is_staff_text(text: str | None) -> bool:
    return bool(text) and bool(_STAFF.search(text) or _TA.search(text))


def without_staff(text: str | None) -> str | None:
    """The text minus sentences that hold staff or contact details."""
    if not text:
        return text
    kept = [part for part in _SENTENCES.split(text) if not is_staff_text(part)]
    return " ".join(kept).strip() or None


def course_code_from_name(name: str) -> str:
    """'ADMN_8171.json' -> 'ADMN 8171'. The file name, not the record's own code,
    names the course: one syllabus can be shared by 6171 and 8171."""
    return Path(name).stem.replace("_", " ").strip().upper()


def codes_in(text: str | None, exclude: str) -> list[str]:
    found = []
    for subject, number in CODE.findall(text or ""):
        code = f"{subject} {number}"
        if subject not in NOT_SUBJECTS and code != exclude and code not in found:
            found.append(code)
    return found


def clean_title(title: str | None) -> str | None:
    """Drop a trailing credit-hours note such as ' (3 credit hours)' or '- 3 Credit Hours | Fall 2026'."""
    text = CREDITS_SUFFIX.sub("", " ".join((title or "").split())).rstrip(" -|,(")
    if text.count("(") > text.count(")"):
        text = text[: text.rfind("(")].rstrip(" -|,(")
    # Some extractions put body text in the title (e.g. AFRS 1100); drop those.
    if len(text) > MAX_TITLE or NOT_TITLE.search(text):
        return None
    return text or None


def level_of(record: dict, code: str) -> str:
    level = (record.get("level") or "").strip().lower()
    if level in ("undergraduate", "graduate"):
        return level
    number = re.search(r"\d{4}", code)
    return "graduate" if number and int(number.group()) >= 5000 else "undergraduate"


def parse_record(name: str, record: dict) -> dict:
    """Rows for one syllabus file: course, units, concepts, objectives, prerequisites, chunks."""
    code = course_code_from_name(name)
    title = clean_title(record.get("title"))
    if is_staff_text(title):
        title = None
    description = without_staff(" ".join((record.get("description") or "").split()) or None)
    level = level_of(record, code)
    prerequisites = " ".join((record.get("prerequisites") or "").split()) or None
    cross_listed = codes_in(" ".join(record.get("cross_listed") or []), code)

    units, concepts, seen_units = [], [], set()
    for unit in record.get("units") or []:
        number = unit.get("number")
        if not isinstance(number, int) or number in seen_units or not (unit.get("title") or "").strip():
            continue
        seen_units.add(number)
        units.append((code, number, unit["title"].strip(), unit.get("source") == "llm-inferred"))
        labels = []
        for concept in unit.get("concepts") or []:
            label = (concept.get("label") or "").strip()
            if label and label not in labels:
                labels.append(label)
                concepts.append((code, number, label))

    objectives, seen_ids = [], set()
    for i, objective in enumerate(record.get("objectives") or [], start=1):
        text = " ".join((objective.get("text") or "").split())
        if not text or is_staff_text(text):
            continue
        objective_id = (objective.get("id") or f"O{i}").strip()
        if objective_id in seen_ids:
            objective_id = f"{objective_id}-{i}"
        seen_ids.add(objective_id)
        objectives.append((code, objective_id, text, objective.get("bloom")))

    heading = f"{code} {title}" if title else code
    unit_text = "; ".join(
        f"{u[2]} ({', '.join(c[2] for c in concepts if c[1] == u[1])})" for u in units
    )
    body = ". ".join(part for part in (heading, description, f"Units: {unit_text}" if units else "") if part)
    metadata = json.dumps({"code": code, "level": level})
    chunks = [("syllabus_course", code, body[:MAX_CHUNK], metadata)]
    chunks += [
        ("syllabus_objective", f"{code}#{objective_id}", f"{heading}: {text}", metadata)
        for _, objective_id, text, _ in objectives
    ]
    return {
        "course": (code, title, description, level, prerequisites, cross_listed, name),
        "units": units,
        "concepts": concepts,
        "objectives": objectives,
        "prerequisites": [(code, target) for target in codes_in(prerequisites, code)],
        "chunks": chunks,
    }


def read_zip(path: Path) -> list[dict]:
    """Parse every .json record in the zip. A file that is not valid JSON is skipped."""
    parsed = []
    with zipfile.ZipFile(path) as archive:
        for name in sorted(archive.namelist()):
            if not name.endswith(".json"):
                continue
            try:
                record = json.loads(archive.read(name).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                print(f"skipping unreadable syllabus record {name}")
                continue
            parsed.append(parse_record(name, record))
    return parsed

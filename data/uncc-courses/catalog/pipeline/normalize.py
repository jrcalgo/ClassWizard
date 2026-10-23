"""Stage 5: typed values derived from the raw text (layer B).

Each function takes one raw field value and returns a small dict that always includes the
raw text. When the text doesn't fit a known pattern the function says so (``status`` or a
``None`` value) and the caller adds a review item; nothing is guessed.
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------- course number

def course_number(number: str) -> dict:
    """'1241L' -> base 1241, suffix 'L', level 1000."""
    base, suffix = int(number[:4]), number[4:]
    return {"base": base, "suffix": suffix or None, "level": (base // 1000) * 1000}


# ---------------------------------------------------------------- credit hours

CREDIT_RE = re.compile(r"^\((\d+)(?:\s+(to|or)\s+(\d+))?\)((?:\s*\([A-Z]{1,2}(?:,\s*[A-Z]{1,2})*\))*)$")


def credit_hours(raw: str) -> dict:
    """'(3)' | '(1 to 3)' | '(3 or 6)' | '(3) (O,W)' -> min/max/options plus attributes.

    Course attributes (SL service learning, W writing, O oral) are printed inside the
    credit value; they are split out into ``attributes``.
    """
    out = {"raw": raw, "min": None, "max": None, "options": None, "variable": None,
           "attributes": [], "status": "invalid"}
    match = CREDIT_RE.match(raw.strip())
    if not match:
        return out                      # e.g. '(!)', '(1 ro 3)', '' -> left for review
    low, kind, high, attrs = match.groups()
    low_i = int(low)
    high_i = int(high) if high else low_i
    if high_i < low_i:
        return out
    out.update(min=low_i, max=high_i, variable=high_i != low_i, status="ok")
    if kind == "or":                    # '(3 or 6)': only the listed values are allowed
        out["options"] = [low_i, high_i]
    out["attributes"] = re.findall(r"[A-Z]{1,2}", attrs or "")
    return out


# ---------------------------------------------------------------- gen ed labels

def gen_ed(raw: str) -> dict:
    """Split the gen ed value into labels, and each label into its ' - ' components.

    'Oral Communication (O), Writing in the Disciplines (W)' is two labels.
    'Local Arts/Humanities - Western Tradition' is one label whose components come from
    two different gen ed systems; mapping components to one canonical list is a later,
    separate decision, so components are only split, never interpreted.
    """
    labels = [p.strip() for p in re.split(r",\s+(?=[A-Z])", raw) if p.strip()]
    return {"raw": raw,
            "labels": [{"label": lab, "components": [c.strip() for c in lab.split(" - ")]}
                       for lab in labels]}


# ---------------------------------------------------------------- repeatability

NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "once": 1, "twice": 2}


def repeatability(raw: str) -> dict:
    """Whether a course may be repeated for credit, and under which conditions.

    ``repeatable`` is True/False only when the text says so plainly; otherwise None.
    """
    text = raw.lower().strip().rstrip(".")
    out = {"raw": raw, "repeatable": None, "change_of_topic": False, "permission_of": None,
           "max_credit_hours": None, "max_repeats": None, "max_attempts": None}
    if re.fullmatch(r"no", text) or re.search(
            r"may not be repeated(?! for grade replacement)|only be taken once for credit"
            r"|cannot be repeated", text):
        out["repeatable"] = False
    elif re.fullmatch(r"yes", text) or re.search(
            r"\bmay be (?:repeated|repated)\b|\bcan be repeated\b|course may be repeated", text):
        out["repeatable"] = True    # 'repated' is a typo in the source (one course)
    if re.search(r"change (?:of|in) topic", text):
        out["change_of_topic"] = True
    if who := re.search(r"permission (?:of|from) (?:the )?(\w+)", text):
        out["permission_of"] = who.group(1)
    if hours := re.search(r"up to (?:a (?:maximum|total) of )?(\d+) (?:credit )?hours", text):
        out["max_credit_hours"] = int(hours.group(1))
    if times := re.search(r"repeated(?: for credit)? (one|two|three|four|five) times?", text):
        out["max_repeats"] = NUMBER_WORDS[times.group(1)]
    if attempts := re.search(r"(?:attempted|taken) more than (once|twice)", text):
        out["max_attempts"] = NUMBER_WORDS[attempts.group(1)]
    elif attempts := re.search(r"maximum of (one|two|three|four|five) (?:attempts|times)", text):
        out["max_attempts"] = NUMBER_WORDS[attempts.group(1)]
    return out


# ---------------------------------------------------------------- grading method

GRADING = (
    (r"pass/no credit", "pass_no_credit"),
    (r"satisfactory/unsatisfactory", "satisfactory_unsatisfactory"),
    (r"pass/unsatisfactory", "pass_unsatisfactory"),
)
DELIVERY = re.compile(r"^(face-to-face|online|hybrid)", re.IGNORECASE)


def grading_method(raw: str) -> dict:
    """Grading basis. Delivery modes found in this field (a source defect: 32 courses) are
    moved to ``delivery_mode`` and the method left unknown."""
    out = {"raw": raw, "method": None, "delivery_mode": None, "status": "unrecognized"}
    if DELIVERY.match(raw.strip()):
        out.update(delivery_mode=raw.strip(), status="delivery_mode_in_grading_field")
        return out
    for pattern, name in GRADING:
        if re.search(pattern, raw, re.IGNORECASE):
            out.update(method=name, status="ok")
            break
    return out


# ---------------------------------------------------------------- cross-listed courses

XLIST_RE = re.compile(r"\b([A-Z]{3,5} \d{4}[A-Z]{0,2})(?:\s?-([A-Z]\d{2}))?\b")


def cross_listed(raw: str) -> dict:
    """Course codes in the cross-list field. A section suffix ('HONR 3700-H01') means the
    cross-listing applies to that section only."""
    refs = [{"code": c, "section": s or None} for c, s in XLIST_RE.findall(raw)]
    leftover = XLIST_RE.sub("", raw)
    leftover = re.sub(r"[\s,.;]|\b(and|or)\b", "", leftover)
    return {"raw": raw, "courses": refs, "status": "ok" if refs and not leftover else "check"}


# ---------------------------------------------------------------- restrictions

STANDING_WORDS = ("freshman", "sophomore", "junior", "senior")
GATE_PATTERNS = (
    ("program", r"\bmajors?\b|\bminors?\b|\bprogram\b|\bconcentration\b|\bcertificate\b|\bdegree\b"),
    ("admission", r"\badmission\b|\badmitted\b|\bacceptance\b|\baccepted\b|\badmittance\b"),
    ("standing", r"\b(?:freshman|sophomore|junior|senior|graduate)\b(?:[\w ,]*?)\bstanding\b"),
    ("permission", r"\bpermission\b|\bconsent\b|\bapproval\b|\bapproved\b"),
    ("gpa", r"\bGPA\b|grade point average"),
    ("honors", r"\bhonors\b"),
    ("credit_hours", r"\bcredit hours\b|\bhours of credit\b"),
    ("exclusion", r"\bnot open to\b|\bmay not\b|\bexcept\b|\bexcluded\b"),
    ("background_check", r"background check|\bPraxis\b"),
)


def restrictions(raw: str) -> dict:
    """Which kinds of student-state gate a restriction mentions (keyword detection).

    This is NOT a logic tree: a restriction such as 'Criminal Justice major or minor; and
    Junior or Senior standing' is tagged program + standing, with the standing levels and
    any GPA thresholds pulled out. Program names stay in the raw text until a program list
    (catalog program pages or DegreeWorks) exists to resolve them against.
    """
    gates = [name for name, pat in GATE_PATTERNS if re.search(pat, raw, re.IGNORECASE)]
    standing = []
    for match in re.finditer(r"((?:(?:freshman|sophomore|junior|senior)"
                             r"(?:,\s*or\s+|,\s*|\s+or\s+|\s+and\s+)?)+)\s*standing",
                             raw, re.IGNORECASE):
        standing += [w.lower() for w in re.findall(r"freshman|sophomore|junior|senior",
                                                   match.group(1), re.IGNORECASE)]
    gpas = [float(g) for g in re.findall(r"GPA (?:of )?(?:at least |a minimum of )?(\d\.\d+)|"
                                         r"(\d\.\d+)\s*(?:overall |cumulative )?GPA", raw)
            for g in g if g]
    return {"raw": raw, "gates": gates, "standing_levels": list(dict.fromkeys(standing)),
            "min_gpa_values": gpas, "method": "keyword"}

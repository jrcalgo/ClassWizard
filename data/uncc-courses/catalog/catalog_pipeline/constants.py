"""Fixed vocabulary of the Acalog print-outs, shared by every stage."""
import re

# The nine field labels Acalog prints under a course, in the order they are usually printed.
FIELDS = (
    "Credit Hours",
    "Prerequisite(s)",
    "Restriction(s)",
    "Repeatability",
    "Cross-listed Course(s)",
    "Pre- or Corequisite(s)",
    "General Education Requirement(s) Satisfied",
    "Corequisite(s)",
    "Grading Method",
)

# Requisite fields and the timing each one implies for the courses it names.
REQUISITE_FIELDS = {
    "Prerequisite(s)": "before",                  # must be completed in an earlier term
    "Corequisite(s)": "same_term",                # must be taken in the same term
    "Pre- or Corequisite(s)": "before_or_same_term",
}

# A course code: 3-5 capital letters, a space, 4 digits, optional letter suffix (L, H, ...).
COURSE_CODE = r"[A-Z]{3,5} \d{4}[A-Z]{0,2}"
COURSE_CODE_RE = re.compile(r"\b(" + COURSE_CODE + r")\b")

# A course header line: "ITSC 1212 - Introduction to Computer Science I".
HEADER_RE = re.compile(r"^([A-Z]{3,5}) (\d{4}[A-Z]{0,2}) - (.+)$")


def label_count_re(label: str) -> re.Pattern:
    """Regex that counts a field label in raw text.

    'Corequisite(s):' also occurs inside 'Pre- or Corequisite(s):', so the
    negative look-behind keeps the two labels from being double counted.
    """
    return re.compile(r"(?<!Pre- or )" + re.escape(label) + ":")

"""Term split for registered DegreeWorks courses. No student audits.

Run from the repo root:
    python -m pytest tests/test_degreeworks_parser.py
"""

import pytest

from data.degreeworks.parser import Course, _classify, _courses, _header


def _course(code: str, grade: str, term: str) -> Course:
    return Course(code=code, title="Title", grade=grade, credits=3, term=term)


def test_header_checks_name_in_banner_when_label_is_blank():
    common = (
        "Overall GPA Student ID 12345 70% 3.0 Degree Bachelor of Science "
        "Audit date 10/26/2026 8:46 PM Requirements Level Undergraduate "
        "Classification Junior Programs Computer Science Majors Computing "
        "College Computing and Informatics Advisors Faculty"
    )
    header = _header(
        f"UNC Charlotte Example Student - 12345 UNC Charlotte Degree progress "
        f"Student name {common}"
    )

    assert header["degree"] == "Bachelor of Science"
    assert header["level"] == "Undergraduate"
    assert header["program"] == "Computer Science"
    assert header["major"] == "Computing"
    assert "student_name" not in header


def test_header_rejects_missing_name_in_banner_and_labeled_field():
    common = (
        "Overall GPA Student ID 12345 70% 3.0 Degree Bachelor of Science "
        "Audit date 10/26/2026 8:46 PM Requirements Level Undergraduate "
        "Classification Junior Programs Computer Science Majors Computing "
        "College Computing and Informatics Advisors Faculty"
    )

    with pytest.raises(ValueError, match="student name"):
        _header(f"Student name   {common}")


def test_course_rows_allow_bare_credits_labs_and_transfer_grades():
    text = (
        "ITSC 1212 Intro to Computer Science I A 4 Fall 2025 "
        "BIOL 2120L General Biology I Lab TA 1 Fall 2024 "
        "MATH 1ELE Math Elective TB 2 Spring 2024 "
        "ITSC 2214 Data Structures *REG (4) Fall 2026"
    )
    found = {(course.code, course.grade, course.credits, course.term) for course in _courses(text)}
    assert found == {
        ("ITSC 1212", "A", 4, "Fall 2025"),
        ("BIOL 2120L", "TA", 1, "Fall 2024"),
        ("MATH 1ELE", "TB", 2, "Spring 2024"),
        ("ITSC 2214", "*REG", 4, "Fall 2026"),
    }


def test_registered_current_term_is_in_progress_and_later_term_is_preregistered():
    courses = [
        _course("ITSC 2214", "*REG", "Fall 2026"),
        _course("ITSC 3155", "REG", "Spring 2027"),
        _course("ITSC 1212", "A", "Fall 2025"),
        _course("ITSC 2181", "*IP", "Fall 2026"),
        _course("ITSC 3146", "*PR", "Fall 2026"),
    ]
    completed, in_progress, preregistered = _classify(courses, "10/26/2026 11:31 AM")
    assert [course.code for course in completed] == ["ITSC 1212"]
    assert [course.code for course in in_progress] == ["ITSC 2214", "ITSC 2181"]
    assert [course.code for course in preregistered] == ["ITSC 3155", "ITSC 3146"]

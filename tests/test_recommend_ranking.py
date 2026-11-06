"""Unit tests for the database-free parts of ai/recommendations/ranking.py.

Uses a made-up audit (no real student data). Run from the repo root:
    python -m pytest tests/test_recommend_ranking.py
"""

from ai.recommendations.ranking import (
    candidate_courses,
    is_supported,
    satisfied_codes,
    taken_codes,
)

AUDIT = {
    "level": "Undergraduate",
    "courses_completed": [{"code": "ITSC 2214"}],
    "courses_in_progress": [{"code": "ITSC 2181"}],
    "courses_preregistered": [{"code": "ITSC 3146"}],
    "courses_not_taken": [
        {"block": "Major", "course_codes": ["ITSC 3160", "ITSC 3155", "ITSC 3146"]},
        {"block": "Electives", "course_codes": ["ITSC 3160", "ITIS 3135"]},
        {"block": "Elective pool", "course_codes": []},
    ],
}


def test_taken_includes_completed_in_progress_and_preregistered():
    assert taken_codes(AUDIT) == {"ITSC 2214", "ITSC 2181", "ITSC 3146"}


def test_preregistered_does_not_satisfy_prerequisites():
    assert satisfied_codes(AUDIT) == {"ITSC 2214", "ITSC 2181"}


def test_candidates_drop_taken_and_keep_every_block():
    assert candidate_courses(AUDIT) == {
        "ITSC 3160": ["Major", "Electives"],
        "ITSC 3155": ["Major"],
        "ITIS 3135": ["Electives"],
    }


def test_only_undergraduate_audits_are_supported():
    assert is_supported(AUDIT)
    assert not is_supported({**AUDIT, "level": "Graduate"})
    assert not is_supported({**AUDIT, "level": ""})


def test_empty_audit_has_no_candidates():
    assert candidate_courses({"level": "Undergraduate"}) == {}

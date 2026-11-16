"""Unit tests for the database-free parts of ai/recommendations/ranking.py.

Uses a made-up audit (no real student data). Run from the repo root:
    python -m pytest tests/test_recommend_ranking.py
"""

import pytest

from ai.recommendations.ranking import (
    UnsupportedAudit,
    candidate_courses,
    catalog_for,
    is_supported,
    recommend,
    satisfied_codes,
    taken_codes,
)
from backend.storage.database.postgres import discover_catalogs

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


def test_each_level_maps_to_its_catalog():
    assert catalog_for(AUDIT) == "Undergraduate 2026-2027"
    assert catalog_for({**AUDIT, "level": "Graduate"}) == "Graduate 2026-2027"
    assert catalog_for({**AUDIT, "level": "Doctoral"}) == "Graduate 2026-2027"
    assert is_supported(AUDIT) and is_supported({**AUDIT, "level": "Graduate"})
    assert not is_supported({**AUDIT, "level": ""})


class _NoCoursesConn:
    """Stands in for psycopg: every query returns no rows."""

    def execute(self, *_args):
        return self

    def fetchone(self):
        return None


def test_missing_catalog_names_the_catalog():
    with pytest.raises(UnsupportedAudit, match="Graduate 2026-2027 catalog is not loaded"):
        recommend(_NoCoursesConn(), {**AUDIT, "level": "Graduate"}, ["15-1252.00"])
    with pytest.raises(UnsupportedAudit, match="not recognised"):
        recommend(_NoCoursesConn(), {**AUDIT, "level": "Certificate"}, ["15-1252.00"])


def test_empty_audit_has_no_candidates():
    assert candidate_courses({"level": "Undergraduate"}) == {}


def test_loader_finds_both_catalog_zips(tmp_path):
    for name in ("graduate-catalog-2026-2027.zip", "undergraduate-catalog-2026-2027.zip", "notes.zip"):
        (tmp_path / name).write_bytes(b"")
    sources = discover_catalogs(tmp_path)
    assert [s.release for s in sources] == ["Undergraduate 2026-2027", "Graduate 2026-2027"]
    assert sources[1].slug == "graduate-2026-2027"

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


class ScoreConn:
    def __init__(self, *, stale=False, incomplete=False, vectors=True, blended=False, invalid=False):
        self.blended, self.invalid = blended, invalid
        self.stale, self.incomplete, self.vectors = stale, incomplete, vectors
        self.rows = []

    def execute(self, sql, params=None):
        if sql.strip().startswith('SELECT 1 FROM courses'):
            self.rows = [(1,)]
        elif 'SELECT soc_code, title' in sql:
            self.rows = [('career1', 'Career One'), ('career2', 'Career Two')]
        elif 'SELECT code, title' in sql:
            self.rows = [r for r in [('ITSC 3155', 'A', 3, 3, '3'), ('ITSC 3160', 'B', 3, 3, '3')] if r[0] in params[1]]
        elif 'SELECT release FROM ingest_runs WHERE source=%s' in sql:
            from ai.recommendations.scoring import SCORING_VERSION, BLEND_VERSION, training_identity
            values = {'spark_hybrid': 'old' if self.stale else SCORING_VERSION + ':inputs',
                      'spark_training_fingerprint': 'fp', 'spark_als': training_identity('fp') if self.blended else None,
                      'spark_blend': BLEND_VERSION}
            value = values.get(params[0])
            self.rows = [(value,)] if value else []
        elif 'string_agg' in sql:
            self.rows = [('inputs',)]
        elif 'SELECT count(*) FROM courses' in sql:
            self.rows = [(2,)]
        elif 'SELECT course_code,soc_code,hybrid_rating' in sql:
            assert params[0] == 'Undergraduate 2026-2027'
            self.rows = [('ITSC 3155','career1',2,1,0,1.4), ('ITSC 3155','career2',5,1,0,3.5),
                         ('ITSC 3160','career1',4,2,5,4.3), ('ITSC 3160','career2',1,2,5,2.2)]
            if self.incomplete:
                self.rows.pop()
            if self.invalid:
                self.rows[0] = (*self.rows[0][:5], float('nan'))
        elif "source_type = 'occupation'" in sql and 'SELECT source_key' in sql:
            self.rows = [('career1',), ('career2',)] if self.vectors else []
        elif 'SELECT c.source_key' in sql:
            self.rows = [('ITSC 3155', 'career1', .1), ('ITSC 3155', 'career2', .2),
                         ('ITSC 3160', 'career1', .9), ('ITSC 3160', 'career2', .3)]
        elif 'SELECT course_code, target_code' in sql:
            self.rows = [('ITSC 3155', 'ITSC 2214'), ('ITSC 3160', 'ITSC 9999')]
        else:
            raise AssertionError(sql)
        return self

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


def test_spark_ranks_without_vectors_and_keeps_audit_flags():
    result = recommend(ScoreConn(vectors=False), AUDIT, ['career1', 'career2'])
    assert result['scoring_method'] == 'spark_hybrid'
    first, second = result['recommendations']
    assert first['code'] == 'ITSC 3155' and first['score'] == 5
    assert first['score_by_occupation']['career2'] == 5
    assert 'similarity_by_occupation' not in first
    assert first['prerequisites'] == [{'code': 'ITSC 2214', 'met': True}]
    assert second['requirement_blocks'] == ['Major', 'Electives']
    assert second['prerequisites'] == [{'code': 'ITSC 9999', 'met': False}]


@pytest.mark.parametrize('options', [{'stale': True}, {'incomplete': True}])
def test_spark_falls_back_for_entire_request(options):
    result = recommend(ScoreConn(**options), AUDIT, ['career1', 'career2'])
    assert result['scoring_method'] == 'cosine_similarity'
    assert result['recommendations'][0]['code'] == 'ITSC 3160'
    assert all(r['score'] <= 1 for r in result['recommendations'])


def test_blended_ranking_and_components():
    result = recommend(ScoreConn(blended=True), AUDIT, ['career1','career2'])
    assert result['scoring_method'] == 'spark_blended'
    first = result['recommendations'][0]
    assert first['code'] == 'ITSC 3160'
    assert first['score'] == 4.3
    assert first['score_components_by_occupation']['career1']['hybrid_rating'] == 4


def test_invalid_blend_uses_hybrid_for_entire_request():
    result = recommend(ScoreConn(blended=True, invalid=True), AUDIT, ['career1','career2'])
    assert result['scoring_method'] == 'spark_hybrid'
    assert result['recommendations'][0]['score'] == 5


def test_candidate_subset_does_not_change_blended_values():
    whole=recommend(ScoreConn(blended=True),AUDIT,['career1','career2'])
    subset=recommend(ScoreConn(blended=True),{**AUDIT,'courses_not_taken':[{'course_codes':['ITSC 3160']}]},['career1','career2'])
    assert subset['scoring_method']=='spark_blended'
    assert subset['recommendations'][0]['score_by_occupation']==whole['recommendations'][0]['score_by_occupation']

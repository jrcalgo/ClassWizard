"""Tests for spark_jobs on a few made-up rows. Skipped without PySpark.

Run inside the backend container:
    docker compose cp tests backend:/app/tests
    docker compose exec backend sh -c "pip install -q --break-system-packages pytest && python3 -m pytest /app/tests/test_spark_jobs.py"
"""

import pytest

pytest.importorskip("pyspark")

from ai.recommendations.spark_jobs.medallion import gold, silver  # noqa: E402
from ai.recommendations.spark_jobs.session import get_spark  # noqa: E402


@pytest.fixture(scope="module")
def spark():
    session = get_spark("ClassWizard_Tests")
    yield session
    session.stop()


def test_course_concepts_keep_covers_rows_only(spark):
    triples = spark.createDataFrame(
        [
            ("ITSC 3160", "covers", "SQL", "0.90"),
            ("ITSC 3160", "covers", "sql", "0.80"),         # same concept, different case
            ("itsc_3160", "covers", "Query Tips", "0.60"),  # code needs cleaning
            ("SQL", "part_of", "Databases", "0.85"),        # not a covers row
            ("Not A Course", "covers", "Thing", "0.90"),    # bad course code
        ],
        "subject string, predicate string, object string, confidence string",
    )
    rows = silver.clean_course_concepts(triples).collect()
    assert sorted(r.term_key for r in rows) == ["query tips", "sql"]
    assert {r.course_code for r in rows} == {"ITSC 3160"}


def test_courses_combine_catalog_and_syllabus(spark):
    catalog = spark.createDataFrame(
        [("ITSC 3160", "Database Design", "Relational schemas.", 3, 1)],
        "course_code string, title string, description string, credits int, n_prereqs long",
    )
    concepts = spark.createDataFrame(
        [("ITSC 3160", "sql"), ("ITCS 6160", "query optimization")], "course_code string, term_key string")
    rows = {r.course_code: r for r in silver.build_courses(catalog, concepts).collect()}
    assert rows["ITSC 3160"].in_catalog and rows["ITSC 3160"].has_syllabus
    assert rows["ITSC 3160"].level == "undergraduate"
    assert not rows["ITCS 6160"].in_catalog and rows["ITCS 6160"].level == "graduate"
    assert rows["ITCS 6160"].n_prereqs == 0


def test_careers_keep_degree_level_job_zones(spark):
    occupations = spark.createDataFrame(
        [("15-2051.00", "Data Scientists", "Analyze data."), ("41-2011.00", "Cashiers", "Take payments.")],
        "o_net_soc_code string, title string, description string",
    )
    zones = spark.createDataFrame([("15-2051.00", "5"), ("41-2011.00", "1")], "o_net_soc_code string, job_zone string")
    assert [r.soc_code for r in silver.clean_careers(occupations, zones).collect()] == ["15-2051.00"]


def test_career_terms_weights(spark):
    skills = spark.createDataFrame(
        [("15-2051.00", "programming", "Programming", "skill", 4.5),
         ("13-2011.00", "programming", "Programming", "skill", 2.0)],  # not important enough
        "soc_code string, term_key string, term string, kind string, importance double",
    )
    technologies = spark.createDataFrame(
        [("15-2051.00", "python", "Python", True, True)],
        "soc_code string, term_key string, term string, hot boolean, in_demand boolean",
    )
    rows = {(r.soc_code, r.term_key): r.weight for r in gold.build_career_terms(skills, technologies).collect()}
    assert ("13-2011.00", "programming") not in rows
    assert rows[("15-2051.00", "programming")] == pytest.approx(0.875)  # (4.5 - 1) / 4
    assert rows[("15-2051.00", "python")] == pytest.approx(1.0)         # 0.4 + hot + in demand

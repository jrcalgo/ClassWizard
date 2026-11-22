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
        [("Undergraduate 2026-2027", "ITSC 3160", "Database Design", "Relational schemas.", 3, 1)],
        "catalog_name string, course_code string, title string, description string, credits int, n_prereqs long",
    )
    concepts = spark.createDataFrame(
        [("ITSC 3160", "sql"), ("ITCS 6160", "query optimization")], "course_code string, term_key string")
    rows = {r.course_code: r for r in silver.build_courses(catalog, concepts).collect()}
    assert rows["ITSC 3160"].in_catalog and rows["ITSC 3160"].has_syllabus
    assert rows["ITSC 3160"].level == "undergraduate"
    assert "ITCS 6160" not in rows


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


def test_als_items_separate_catalogs(spark):
    ratings = spark.createDataFrame(
        [("Undergraduate 2026-2027", "ITSC 5000", "career"),
         ("Graduate 2026-2027", "ITSC 5000", "career")],
        "catalog_name string, course_code string, soc_code string")
    rows = gold.add_als_ids(ratings).collect()
    assert len({r.item_id for r in rows}) == 2
    assert len({r.user_id for r in rows}) == 1


def test_catalog_cleaning_preserves_same_code_and_prerequisite_scope(spark):
    courses = spark.createDataFrame(
        [('Undergraduate', 'ITSC 5000', 'First', 'One', 3),
         ('Graduate', 'ITSC 5000', 'Second', 'Two', 4)],
        'catalog_name string, code string, title string, description string, credit_min int')
    links = spark.createDataFrame([('Graduate', 'ITSC 5000', 'ITSC 4000', 'prerequisite')],
        'catalog_name string, course_code string, target_code string, kind string')
    rows = {r.catalog_name: r for r in silver.clean_catalog_courses(courses, links).collect()}
    assert len(rows) == 2
    assert rows['Graduate'].n_prereqs == 1
    assert rows['Undergraduate'].n_prereqs is None


def test_ratings_partition_by_catalog(spark):
    spark.createDataFrame(
        [('Undergraduate', 'career', 'A', .1), ('Undergraduate', 'career', 'B', .2),
         ('Graduate', 'career', 'A', .8), ('Graduate', 'career', 'B', .9)],
        'catalog_name string, soc_code string, course_code string, doc_sim double'
    ).createOrReplaceTempView('doc_similarity')
    spark.createDataFrame(
        [('Undergraduate', 'A', False), ('Undergraduate', 'B', False),
         ('Graduate', 'A', False), ('Graduate', 'B', False)],
        'catalog_name string, course_code string, has_syllabus boolean'
    ).createOrReplaceTempView('courses')
    spark.createDataFrame([], 'catalog_name string, soc_code string, course_code string, term_score double, n_matches long').createOrReplaceTempView('evidence')
    rows = spark.sql(gold.RATING_SQL).collect()
    assert len(rows) == 4
    assert {(r.catalog_name, r.course_code, r.rating) for r in rows} == {
        ('Undergraduate', 'A', 0), ('Undergraduate', 'B', 5),
        ('Graduate', 'A', 0), ('Graduate', 'B', 5)}


def test_full_data_als_covers_all_catalog_pairs(spark):
    from ai.recommendations.spark_jobs.model import make_als
    ratings = spark.createDataFrame(
        [('UG', 'A', 'career1', 1.0), ('GR', 'A', 'career1', 4.0),
         ('UG', 'A', 'career2', 3.0), ('GR', 'A', 'career2', 2.0)],
        'catalog_name string, course_code string, soc_code string, rating double')
    indexed = gold.add_als_ids(ratings)
    predictions = make_als(2, .1).fit(indexed).transform(indexed)
    assert predictions.count() == 4
    assert predictions.select('catalog_name', 'course_code', 'soc_code').distinct().count() == 4

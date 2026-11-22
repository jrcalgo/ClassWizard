"""Copy gold.predictions into the Postgres table course_career_scores."""

import os

import psycopg

from spark_jobs.session import LAKE_DIR, read_table, section

EXPORT_DIR = LAKE_DIR / "export" / "course_career_scores"
COPY_SQL = "COPY course_career_scores (soc_code, course_code, als_score, hybrid_rating) FROM STDIN WITH (FORMAT csv)"

# The data the pipeline reads, as recorded by the backend loader.
INPUTS_SQL = """
    SELECT COALESCE(string_agg(source || '=' || release, ';' ORDER BY source), '')
    FROM ingest_runs
    WHERE source LIKE 'catalog:%' OR source IN ('onet', 'syllabi')
"""


def inputs_key(conn):
    return conn.execute(INPUTS_SQL).fetchone()[0]


def is_current():
    """True when the published scores were built from the data loaded now."""
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        has_scores = conn.execute("SELECT EXISTS (SELECT 1 FROM course_career_scores)").fetchone()[0]
        recorded = conn.execute(
            "SELECT release FROM ingest_runs WHERE source = 'spark_als'"
        ).fetchone()
        return has_scores and recorded is not None and recorded[0] == inputs_key(conn)


def run(spark):
    section("Step 6: Publish predictions to Postgres (course_career_scores)")
    predictions = read_table(spark, "gold", "predictions")
    predictions.select("soc_code", "course_code", "als_score", "hybrid_rating") \
        .write.mode("overwrite").csv(str(EXPORT_DIR))

    # One transaction: the app never sees a half-loaded table.
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        conn.execute("TRUNCATE course_career_scores")
        with conn.cursor() as cur:
            with cur.copy(COPY_SQL) as copy:
                for path in sorted(EXPORT_DIR.glob("part-*.csv")):
                    copy.write(path.read_bytes())
        conn.execute("DELETE FROM ingest_runs WHERE source = 'spark_als'")
        conn.execute("INSERT INTO ingest_runs (source, release) VALUES ('spark_als', %s)", (inputs_key(conn),))
        loaded = conn.execute("SELECT count(*) FROM course_career_scores").fetchone()[0]
    print(f"  postgres.course_career_scores  {loaded:>10,} rows")

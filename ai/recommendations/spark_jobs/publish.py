"""Validate and atomically publish catalog-qualified Spark predictions."""
import json
import os

import psycopg

from ai.recommendations.scoring import release_key, SCORING_VERSION
from ai.recommendations.spark_jobs.session import LAKE_DIR, read_table, section

EXPORT_DIR = LAKE_DIR / "export" / "course_career_scores"
MANIFEST = LAKE_DIR / "scoring_manifest.json"
COLUMNS = "catalog_name, soc_code, course_code, als_score, hybrid_rating"


def inputs_key(conn):
    return release_key(conn)


def is_current():
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        recorded = conn.execute("SELECT release FROM ingest_runs WHERE source = 'spark_als'").fetchone()
        count = conn.execute("SELECT count(*) FROM course_career_scores").fetchone()[0]
        expected = conn.execute("SELECT release FROM ingest_runs WHERE source = 'spark_als_count'").fetchone()
        return bool(recorded and recorded[0] == inputs_key(conn) and count > 0
                    and expected and expected[0] == str(count))


def run(spark):
    section("Step 6: Validate and publish predictions")
    manifest = json.loads((LAKE_DIR / "model_manifest.json").read_text())
    predictions = read_table(spark, "gold", "predictions")
    predictions.select(*[c.strip() for c in COLUMNS.split(",")]).write.mode("overwrite").csv(str(EXPORT_DIR))
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        # Block ingest metadata changes and concurrent publication until commit.
        conn.execute("LOCK TABLE ingest_runs IN SHARE ROW EXCLUSIVE MODE")
        conn.execute("LOCK TABLE courses IN SHARE MODE")
        if manifest != {"release": inputs_key(conn), "scoring_version": SCORING_VERSION}:
            raise ValueError("Spark artifacts are stale; rebuild from Bronze")
        conn.execute("CREATE TEMP TABLE score_stage (LIKE course_career_scores INCLUDING ALL) ON COMMIT DROP")
        with conn.cursor() as cur:
            with cur.copy(f"COPY score_stage ({COLUMNS}) FROM STDIN WITH (FORMAT csv)") as copy:
                for path in sorted(EXPORT_DIR.glob("part-*.csv")):
                    copy.write(path.read_bytes())
        invalid = conn.execute("""SELECT count(*) FROM score_stage
            WHERE hybrid_rating NOT BETWEEN 0 AND 5 OR als_score IN ('NaN'::real, 'Infinity'::real, '-Infinity'::real)""").fetchone()[0]
        # Spark deliberately serves O*NET job zones 4 and 5. Compare with its
        # saved career set, and require every loaded catalog course for each.
        careers = [r.soc_code for r in read_table(spark, "silver", "careers").select("soc_code").collect()]
        if not careers:
            raise ValueError("No careers in Spark output")
        missing, extra = conn.execute("""WITH expected AS (
            SELECT catalog_name, code AS course_code, unnest(%s::text[]) AS soc_code FROM courses
        ) SELECT
          (SELECT count(*) FROM (SELECT * FROM expected EXCEPT SELECT catalog_name, course_code, soc_code FROM score_stage) x),
          (SELECT count(*) FROM (SELECT catalog_name, course_code, soc_code FROM score_stage EXCEPT SELECT * FROM expected) x)
        """, (careers,)).fetchone()
        if invalid or missing or extra:
            raise ValueError(f"Invalid score batch: invalid={invalid}, missing={missing}, extra={extra}")
        conn.execute("DELETE FROM course_career_scores")
        conn.execute(f"INSERT INTO course_career_scores ({COLUMNS}) SELECT {COLUMNS} FROM score_stage")
        loaded = conn.execute("SELECT count(*) FROM score_stage").fetchone()[0]
        conn.execute("DELETE FROM ingest_runs WHERE source IN ('spark_als', 'spark_als_count')")
        conn.execute("INSERT INTO ingest_runs (source, release) VALUES ('spark_als', %s), ('spark_als_count', %s)",
                     (manifest["release"], str(loaded)))
    print(f"Published {loaded} verified scores ({SCORING_VERSION})")

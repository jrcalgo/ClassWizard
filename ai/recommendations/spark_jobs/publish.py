"""Validate and atomically publish catalog-qualified Spark predictions."""
import json
import os

import psycopg

from ai.recommendations.scoring import release_key, SCORING_VERSION, marker
from ai.recommendations.spark_jobs.session import LAKE_DIR, read_table

MANIFEST = LAKE_DIR / "scoring_manifest.json"


def inputs_key(conn):
    return release_key(conn)


def record(conn, source, value):
    conn.execute("DELETE FROM ingest_runs WHERE source=%s", (source,))
    conn.execute("INSERT INTO ingest_runs(source, release) VALUES (%s,%s)", (source, value))


def is_current():
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        count = conn.execute("SELECT count(*) FROM course_career_scores").fetchone()[0]
        invalid = conn.execute('SELECT EXISTS (SELECT 1 FROM course_career_scores WHERE hybrid_rating IS NULL OR hybrid_rating NOT BETWEEN 0 AND 5)').fetchone()[0]
        return bool(count and not invalid and marker(conn, 'spark_hybrid') == inputs_key(conn)
                    and marker(conn, 'spark_hybrid_count') == str(count))


def validate(conn, table, careers):
    if not careers:
        raise ValueError('No careers in score batch')
    missing, extra = conn.execute(f"""WITH expected AS (
        SELECT catalog_name, code AS course_code, unnest(%s::text[]) AS soc_code FROM courses
    ) SELECT
      (SELECT count(*) FROM (SELECT * FROM expected EXCEPT SELECT catalog_name, course_code, soc_code FROM {table}) x),
      (SELECT count(*) FROM (SELECT catalog_name, course_code, soc_code FROM {table} EXCEPT SELECT * FROM expected) x)
    """, (careers,)).fetchone()
    invalid = conn.execute(f"""SELECT count(*) FROM {table} WHERE hybrid_rating IS NULL
        OR hybrid_rating NOT BETWEEN 0 AND 5 OR als_score IN ('NaN'::float8,'Infinity'::float8,'-Infinity'::float8)""").fetchone()[0]
    if invalid or missing or extra:
        raise ValueError(f'Invalid score batch: invalid={invalid}, missing={missing}, extra={extra}')


def load_export(conn, directory, columns):
    conn.execute('CREATE TEMP TABLE score_stage (LIKE course_career_scores INCLUDING ALL) ON COMMIT DROP')
    with conn.cursor() as cur:
        with cur.copy(f'COPY score_stage ({columns}) FROM STDIN WITH (FORMAT csv)') as copy:
            for path in sorted(directory.glob('part-*.csv')):
                with path.open('rb') as handle:
                    while chunk := handle.read(1024 * 1024):
                        copy.write(chunk)


def publish_hybrid(spark):
    from ai.recommendations.scoring import training_fingerprint
    manifest = json.loads((LAKE_DIR / 'gold_manifest.json').read_text())
    directory = LAKE_DIR / 'export' / 'hybrid'
    read_table(spark, 'gold', 'ratings').selectExpr('catalog_name', 'soc_code', 'course_code',
        'rating AS hybrid_rating').write.mode('overwrite').csv(str(directory))
    careers = [r.soc_code for r in read_table(spark, 'silver', 'careers').select('soc_code').collect()]
    with psycopg.connect(os.environ['DATABASE_URL']) as conn:
        conn.execute('LOCK TABLE ingest_runs IN SHARE ROW EXCLUSIVE MODE')
        conn.execute('LOCK TABLE courses IN SHARE MODE')
        if manifest != {'release': inputs_key(conn), 'scoring_version': SCORING_VERSION}:
            raise ValueError('Stale Gold artifacts')
        load_export(conn, directory, 'catalog_name, soc_code, course_code, hybrid_rating')
        validate(conn, 'score_stage', careers)
        rows = conn.execute('SELECT catalog_name,soc_code,course_code,hybrid_rating FROM score_stage').fetchall()
        if not rows:
            raise ValueError("Empty hybrid score batch")
        fingerprint = training_fingerprint(rows)
        if marker(conn, 'spark_training_fingerprint') == fingerprint:
            conn.execute("""UPDATE score_stage s SET als_score=c.als_score,
                normalized_als_score=c.normalized_als_score, blended_rating=c.blended_rating
                FROM course_career_scores c WHERE s.catalog_name=c.catalog_name
                AND s.soc_code=c.soc_code AND s.course_code=c.course_code""")
        else:
            conn.execute("DELETE FROM ingest_runs WHERE source IN ('spark_als','spark_als_count','spark_blend')")
        conn.execute('DELETE FROM course_career_scores')
        conn.execute('INSERT INTO course_career_scores SELECT * FROM score_stage')
        record(conn, 'spark_hybrid', manifest['release'])
        record(conn, 'spark_hybrid_count', str(len(rows)))
        record(conn, 'spark_training_fingerprint', fingerprint)


def recompute_blend(conn):
    from ai.recommendations.scoring import HYBRID_WEIGHT, BLEND_VERSION
    conn.execute("""WITH normalized AS (
        SELECT catalog_name,soc_code,course_code,
          5 * percent_rank() OVER (PARTITION BY catalog_name,soc_code ORDER BY als_score) AS value
        FROM course_career_scores
    ) UPDATE course_career_scores c SET normalized_als_score=n.value,
        blended_rating=%s*c.hybrid_rating + %s*n.value FROM normalized n
        WHERE c.catalog_name=n.catalog_name AND c.soc_code=n.soc_code AND c.course_code=n.course_code
    """, (HYBRID_WEIGHT, 1-HYBRID_WEIGHT))
    record(conn, 'spark_blend', BLEND_VERSION)


def publish_predictions(conn, rows, identity):
    from ai.recommendations.scoring import training_identity
    conn.execute('LOCK TABLE ingest_runs IN SHARE ROW EXCLUSIVE MODE')
    if training_identity(marker(conn, 'spark_training_fingerprint') or '') != identity:
        return False
    conn.execute('CREATE TEMP TABLE prediction_stage (catalog_name text, soc_code text, course_code text, als_score double precision NOT NULL, PRIMARY KEY(catalog_name,soc_code,course_code)) ON COMMIT DROP')
    with conn.cursor() as cur:
        with cur.copy('COPY prediction_stage FROM STDIN') as copy:
            for row in rows:
                copy.write_row(row)
    bad = conn.execute("""SELECT EXISTS (
        (SELECT catalog_name,soc_code,course_code FROM course_career_scores EXCEPT SELECT catalog_name,soc_code,course_code FROM prediction_stage)
        UNION ALL (SELECT catalog_name,soc_code,course_code FROM prediction_stage EXCEPT SELECT catalog_name,soc_code,course_code FROM course_career_scores))
        OR EXISTS (SELECT 1 FROM prediction_stage WHERE als_score IN ('NaN'::float8,'Infinity'::float8,'-Infinity'::float8))""").fetchone()[0]
    if bad:
        raise ValueError('Incomplete or invalid predictions')
    conn.execute('UPDATE course_career_scores c SET als_score=p.als_score FROM prediction_stage p WHERE c.catalog_name=p.catalog_name AND c.soc_code=p.soc_code AND c.course_code=p.course_code')
    record(conn, 'spark_als', identity)
    record(conn, 'spark_als_count', str(conn.execute('SELECT count(*) FROM prediction_stage').fetchone()[0]))
    recompute_blend(conn)
    return True

"""Independent ALS supervisor; immutable per-job artifacts and bounded retries."""
import argparse
import json
import fcntl
import logging
import os
from pathlib import Path
import signal
import threading
import uuid

import psycopg

from ai.recommendations.scoring import training_identity, BLEND_VERSION
from ai.recommendations.spark_jobs.publish import marker, publish_predictions, recompute_blend
from ai.recommendations.spark_jobs.session import LAKE_DIR, get_spark

log = logging.getLogger(__name__)
stop = threading.Event()


def retry_delay(attempt):
    return min(30 * 2 ** min(attempt, 5), 900)


def attempt():
    with psycopg.connect(os.environ['DATABASE_URL']) as conn:
        with conn.transaction():
            conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
            fingerprint = marker(conn, 'spark_training_fingerprint')
            if not fingerprint:
                return
            identity = training_identity(fingerprint)
            count, invalid, invalid_blend = conn.execute("""SELECT count(*),
                count(*) FILTER (WHERE als_score IS NULL OR als_score IN ('NaN'::float8,'Infinity'::float8,'-Infinity'::float8)),
                count(*) FILTER (WHERE blended_rating IS NULL OR blended_rating NOT BETWEEN 0 AND 5
                    OR normalized_als_score IS NULL OR normalized_als_score NOT BETWEEN 0 AND 5)
                FROM course_career_scores""").fetchone()
            if (marker(conn, 'spark_als') == identity and count > 0 and not invalid
                    and marker(conn, 'spark_als_count') == str(count)):
                if marker(conn, 'spark_blend') != BLEND_VERSION or invalid_blend:
                    conn.execute('LOCK TABLE ingest_runs IN SHARE ROW EXCLUSIVE MODE')
                    recompute_blend(conn)
                return
            rows = conn.execute('SELECT catalog_name,soc_code,course_code,hybrid_rating FROM course_career_scores ORDER BY catalog_name,soc_code,course_code').fetchall()
    # A completed prediction artifact survives publication failures and restarts.
    saved = None
    for manifest in sorted((LAKE_DIR / 'jobs').glob('*/manifest.json')):
        try:
            compatible = json.loads(manifest.read_text()).get('training_identity') == identity
        except (OSError, ValueError):
            continue
        if compatible and (manifest.parent / 'predictions' / '_SUCCESS').exists():
            saved = manifest.parent
            break
    spark = get_spark()
    try:
        if saved:
            log.info('Reusing saved predictions for %s from %s', identity, saved)
            predictions = spark.read.parquet(str(saved / 'predictions'))
        else:
            job = LAKE_DIR / 'jobs' / uuid.uuid4().hex
            job.mkdir(parents=True)
            (job / 'manifest.json').write_text(json.dumps({'training_identity': identity}))
            log.info('Training %s in %s', identity, job)
            from pyspark.sql import Window, functions as F
            from ai.recommendations.spark_jobs.model import run
            ratings = spark.createDataFrame(rows, 'catalog_name string,soc_code string,course_code string,rating double')
            ratings = ratings.withColumn('user_id', (F.dense_rank().over(Window.orderBy('soc_code'))-1).cast('int'))
            ratings = ratings.withColumn('item_id', (F.dense_rank().over(Window.orderBy('catalog_name','course_code'))-1).cast('int'))
            ratings.write.parquet(str(job / 'ratings'))
            predictions = run(spark, spark.read.parquet(str(job / 'ratings')), job)
        with psycopg.connect(os.environ['DATABASE_URL']) as conn:
            published = publish_predictions(conn, predictions.select('catalog_name','soc_code','course_code','als_score').toLocalIterator(), identity)
        if not published:
            log.info('Discarded superseded job %s', identity)
    except Exception:
        log.exception("Training/publication failed for %s", identity)
        raise
    finally:
        spark.stop()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--once', action='store_true', help='train/publish once without retry')
    parser.add_argument('--publish-job', type=Path, help='publish saved predictions from a job directory')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    LAKE_DIR.mkdir(parents=True, exist_ok=True)
    with (LAKE_DIR / '.als.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        if args.publish_job:
            spark = get_spark()
            try:
                identity = json.loads((args.publish_job / 'manifest.json').read_text())['training_identity']
                rows = spark.read.parquet(str(args.publish_job / 'predictions')).select('catalog_name','soc_code','course_code','als_score').toLocalIterator()
                with psycopg.connect(os.environ['DATABASE_URL']) as conn:
                    if not publish_predictions(conn, rows, identity):
                        raise ValueError('Superseded training job')
            finally:
                spark.stop()
            return
        if args.once:
            attempt()
            return
        failures = 0
        while not stop.is_set():
            try:
                attempt()
                failures = 0
                stop.wait(30)
            except Exception:
                delay = retry_delay(failures)
                failures += 1
                log.exception('ALS failed; rechecking training identity and retrying in %ss', delay)
                stop.wait(delay)


if __name__ == '__main__':
    main()

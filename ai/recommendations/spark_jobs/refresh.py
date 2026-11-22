"""Retry hybrid/evidence publication independently of the ALS worker."""
import json
import logging
import os
import signal
import subprocess
import sys
import threading

import psycopg
from ai.recommendations.spark_jobs import publish
from ai.recommendations.spark_jobs.session import LAKE_DIR
from ai.recommendations.spark_jobs.worker import retry_delay
from ai.recommendations.skill_evidence import publication_current


def main():
    logging.basicConfig(level=logging.INFO)
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    failures = 0
    while not stop.is_set():
        try:
            if not publish.is_current():
                with psycopg.connect(os.environ['DATABASE_URL']) as conn:
                    expected = {'release': publish.inputs_key(conn), 'scoring_version': publish.SCORING_VERSION}
                path = LAKE_DIR / 'gold_manifest.json'
                saved = json.loads(path.read_text()) if path.exists() else None
                steps = 'publish_hybrid' if saved == expected else 'bronze,silver,gold,publish_hybrid'
                subprocess.run([sys.executable, '-m', 'ai.recommendations.spark_jobs.run_all', '--steps', steps], check=True)
            with psycopg.connect(os.environ['DATABASE_URL']) as conn:
                evidence_current = publication_current(conn)
            if not evidence_current:
                subprocess.run([sys.executable, '-m', 'ai.recommendations.spark_jobs.run_all', '--steps', 'evidence'], check=True)
            failures = 0
            stop.wait(30)
        except Exception:
            delay = retry_delay(failures)
            failures += 1
            logging.exception('Hybrid/evidence refresh failed; retry in %ss', delay)
            stop.wait(delay)


if __name__ == '__main__':
    main()

"""Transactional publishing checks against an isolated PostgreSQL schema.

Run in the backend container with DATABASE_URL set; no Spark JVM is needed.
"""
import csv
import json
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest

psycopg = pytest.importorskip('psycopg')
from ai.recommendations.spark_jobs import publish
from ai.recommendations.scoring import SCORING_VERSION


@pytest.fixture
def database(monkeypatch, tmp_path):
    if not os.environ.get('DATABASE_URL'):
        pytest.skip('DATABASE_URL required')
    connect = psycopg.connect
    schema = 'test_scores_' + uuid4().hex
    with connect(os.environ['DATABASE_URL'], autocommit=True) as admin:
        admin.execute(f'CREATE SCHEMA {schema}')
        def scoped(*args, **kwargs):
            return connect(*args, **kwargs, options=f'-c search_path={schema}')
        monkeypatch.setattr(publish.psycopg, 'connect', scoped)
        monkeypatch.setattr(publish, 'LAKE_DIR', tmp_path)
        monkeypatch.setattr(publish, 'EXPORT_DIR', tmp_path / 'export')
        with scoped(os.environ['DATABASE_URL']) as conn:
            conn.execute('CREATE TABLE ingest_runs (source text, release text, loaded_at timestamptz DEFAULT now(), PRIMARY KEY(source, release))')
            conn.execute('CREATE TABLE courses (catalog_name text, code text)')
            conn.execute('CREATE TABLE course_career_scores (catalog_name text NOT NULL, soc_code text NOT NULL, course_code text NOT NULL, als_score real NOT NULL, hybrid_rating real NOT NULL, PRIMARY KEY(catalog_name,soc_code,course_code))')
            conn.execute("INSERT INTO courses VALUES ('UG','A'), ('GR','A')")
            conn.execute("INSERT INTO course_career_scores VALUES ('UG','career','old',1,1)")
            conn.execute("INSERT INTO ingest_runs(source,release) VALUES ('catalog:UG','input'), ('spark_als','old')")
            key = publish.inputs_key(conn)
        (tmp_path / 'model_manifest.json').write_text(json.dumps({'release': key, 'scoring_version': SCORING_VERSION}))
        yield scoped, key
        admin.execute(f'DROP SCHEMA {schema} CASCADE')


class Predictions:
    def __init__(self, rows):
        self.rows = rows
        self.write = self
    def select(self, *columns):
        return self
    def mode(self, mode):
        return self
    def csv(self, path):
        from pathlib import Path
        target = Path(path)
        target.mkdir(parents=True, exist_ok=True)
        with (target / 'part-000.csv').open('w') as handle:
            csv.writer(handle).writerows(self.rows)


def prepare(monkeypatch, rows):
    class Careers:
        def select(self, *args): return self
        def collect(self): return [SimpleNamespace(soc_code='career')]
    monkeypatch.setattr(publish, 'read_table', lambda spark, layer, table: Predictions(rows) if table == 'predictions' else Careers())


def test_publish_complete_catalog_batch(database, monkeypatch):
    connect, key = database
    prepare(monkeypatch, [('UG','career','A',1,2), ('GR','career','A',3,4)])
    publish.run(None)
    with connect(os.environ['DATABASE_URL']) as conn:
        assert conn.execute('SELECT count(*) FROM course_career_scores').fetchone()[0] == 2
        assert conn.execute("SELECT release FROM ingest_runs WHERE source='spark_als'").fetchone()[0] == key
    assert publish.is_current()


@pytest.mark.parametrize('rows', [
    [('UG','career','A',1,2)],  # missing graduate identity
    [('UG','career','A',1,2), ('GR','career','A',3,6)],  # invalid rating
    [('UG','career','A',1,2), ('GR','career','A',float('nan'),4)],
    [('UG','career','A',1,2), ('GR','career','A',3,4), ('GR','career','A',3,4)],
    [('UG','career','A',1,2), ('GR','career','A',3,4), ('GR','career','extra',3,4)],
])
def test_invalid_batch_preserves_previous_scores(database, monkeypatch, rows):
    connect, _ = database
    prepare(monkeypatch, rows)
    with pytest.raises((ValueError, psycopg.Error)):
        publish.run(None)
    with connect(os.environ['DATABASE_URL']) as conn:
        assert conn.execute('SELECT course_code FROM course_career_scores').fetchall() == [('old',)]
        assert conn.execute("SELECT release FROM ingest_runs WHERE source='spark_als'").fetchone()[0] == 'old'


def test_changed_inputs_reject_artifacts(database, monkeypatch):
    connect, _ = database
    prepare(monkeypatch, [('UG','career','A',1,2), ('GR','career','A',3,4)])
    with connect(os.environ['DATABASE_URL']) as conn:
        conn.execute("UPDATE ingest_runs SET release='changed' WHERE source='catalog:UG'")
    with pytest.raises(ValueError, match='stale'):
        publish.run(None)
    assert not publish.is_current()


def test_scoring_version_change_rejects_artifacts(database, monkeypatch):
    prepare(monkeypatch, [('UG','career','A',1,2), ('GR','career','A',3,4)])
    monkeypatch.setattr(publish, 'SCORING_VERSION', 'next-version')
    with pytest.raises(ValueError, match='stale'):
        publish.run(None)


def test_missing_published_row_marks_batch_not_current(database, monkeypatch):
    connect, _ = database
    prepare(monkeypatch, [('UG','career','A',1,2), ('GR','career','A',3,4)])
    publish.run(None)
    with connect(os.environ['DATABASE_URL']) as conn:
        conn.execute("DELETE FROM course_career_scores WHERE catalog_name='GR'")
    assert not publish.is_current()


def test_release_sql_can_be_embedded_in_parameterized_score_query(database):
    from ai.recommendations.scoring import INPUTS_SQL
    connect, key = database
    with connect(os.environ['DATABASE_URL']) as conn:
        row = conn.execute("SELECT %s || ':' || (" + INPUTS_SQL + ")", (SCORING_VERSION,)).fetchone()
        assert row[0] == key

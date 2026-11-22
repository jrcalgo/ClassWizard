"""Transactional hybrid/ALS publishing in an isolated PostgreSQL schema."""
import csv
import json
import os
from types import SimpleNamespace
from uuid import uuid4
import pytest

psycopg = pytest.importorskip('psycopg')
pytest.importorskip('pyspark')
from ai.recommendations.spark_jobs import publish
from ai.recommendations.scoring import SCORING_VERSION, training_identity, training_fingerprint


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
        try:
            with scoped(os.environ['DATABASE_URL']) as conn:
                conn.execute('CREATE TABLE ingest_runs (source text, release text, loaded_at timestamptz DEFAULT now(), PRIMARY KEY(source, release))')
                conn.execute('CREATE TABLE courses (catalog_name text, code text)')
                conn.execute('CREATE TABLE course_career_scores (catalog_name text NOT NULL, soc_code text NOT NULL, course_code text NOT NULL, als_score double precision, hybrid_rating real NOT NULL, normalized_als_score double precision, blended_rating double precision, PRIMARY KEY(catalog_name,soc_code,course_code))')
                conn.execute("INSERT INTO courses VALUES ('UG','A'),('UG','B'),('UG','C'),('GR','A')")
                conn.execute("INSERT INTO ingest_runs(source,release) VALUES ('catalog:UG','input')")
                key = publish.inputs_key(conn)
            (tmp_path / 'gold_manifest.json').write_text(json.dumps({'release':key,'scoring_version':SCORING_VERSION}))
            yield scoped, tmp_path
        finally:
            admin.execute(f'DROP SCHEMA {schema} CASCADE')


RATINGS = [('UG','career','A',2),('UG','career','B',3),('UG','career','C',4),('GR','career','A',5)]


def hybrid(monkeypatch, rows=RATINGS):
    class Frame:
        write = property(lambda self:self)
        def selectExpr(self,*args): return self
        def select(self,*args): return self
        def collect(self): return [SimpleNamespace(soc_code='career')]
        def mode(self,*args): return self
        def csv(self, path):
            from pathlib import Path
            target = Path(path); target.mkdir(parents=True,exist_ok=True)
            with (target/'part-0.csv').open('w') as handle:
                csv.writer(handle).writerows(rows)
    monkeypatch.setattr(publish,'read_table',lambda *args:Frame())
    publish.publish_hybrid(None)


def test_hybrid_independent_then_als_percentiles(database, monkeypatch):
    connect,_=database
    hybrid(monkeypatch)
    assert publish.is_current()
    with connect(os.environ['DATABASE_URL']) as conn:
        batch=conn.execute("SELECT release,loaded_at FROM ingest_runs WHERE source='spark_hybrid'").fetchone()
        fp=publish.marker(conn,'spark_training_fingerprint')
        assert publish.publish_predictions(conn,[(*r[:3],p) for r,p in zip(RATINGS,[1.123456789,1.123456789,9,3])],training_identity(fp))
        values=conn.execute('SELECT catalog_name,course_code,als_score,normalized_als_score,blended_rating FROM course_career_scores ORDER BY catalog_name,course_code').fetchall()
        assert [r[3] for r in values] == [0,0,0,5]
        assert values[1][2] == 1.123456789
        assert values[-1][4] == pytest.approx(.7*4+.3*5)
        assert batch==conn.execute("SELECT release,loaded_at FROM ingest_runs WHERE source='spark_hybrid'").fetchone()
    hybrid(monkeypatch)
    with connect(os.environ['DATABASE_URL']) as conn:
        assert conn.execute('SELECT count(*) FROM course_career_scores WHERE als_score IS NOT NULL').fetchone()[0]==4
    hybrid(monkeypatch,[(*r[:3],1) for r in RATINGS])
    with connect(os.environ['DATABASE_URL']) as conn:
        assert conn.execute('SELECT count(*) FROM course_career_scores WHERE als_score IS NOT NULL').fetchone()[0]==0
        assert not publish.publish_predictions(conn,[(*r[:3],2) for r in RATINGS],training_identity(fp))


@pytest.mark.parametrize('rows',[RATINGS[:-1],[(*RATINGS[0][:3],float('nan')),*RATINGS[1:]],RATINGS+[RATINGS[0]]])
def test_invalid_hybrid_rolls_back(database,monkeypatch,rows):
    connect,_=database
    hybrid(monkeypatch)
    with pytest.raises((ValueError,psycopg.Error)):
        hybrid(monkeypatch,rows)
    with connect(os.environ['DATABASE_URL']) as conn:
        assert conn.execute('SELECT count(*) FROM course_career_scores').fetchone()[0]==4
        assert publish.marker(conn,'spark_training_fingerprint')==training_fingerprint(RATINGS)


def test_invalid_predictions_roll_back(database,monkeypatch):
    connect,_=database
    hybrid(monkeypatch)
    with pytest.raises(ValueError):
        with connect(os.environ['DATABASE_URL']) as conn:
            publish.publish_predictions(conn,[('UG','career','A',float('inf'))],training_identity(publish.marker(conn,'spark_training_fingerprint')))
    with connect(os.environ['DATABASE_URL']) as conn:
        assert conn.execute('SELECT count(*) FROM course_career_scores WHERE als_score IS NOT NULL').fetchone()[0]==0


def test_migration_idempotent(database):
    from backend.storage.database.postgres import migrate_course_career_scores
    connect,_=database
    with connect(os.environ['DATABASE_URL']) as conn:
        migrate_course_career_scores(conn)
        migrate_course_career_scores(conn)


def test_all_tied_and_career_isolation(database,monkeypatch):
    connect,_=database
    hybrid(monkeypatch)
    with connect(os.environ['DATABASE_URL']) as conn:
        identity=training_identity(publish.marker(conn,'spark_training_fingerprint'))
        publish.publish_predictions(conn,[(*r[:3],5) for r in RATINGS],identity)
        assert conn.execute('SELECT DISTINCT normalized_als_score FROM course_career_scores').fetchall()==[(0,)]
        conn.execute("INSERT INTO course_career_scores(catalog_name,soc_code,course_code,hybrid_rating,als_score) VALUES ('UG','other','A',1,-20),('UG','other','B',1,-10)")
        publish.recompute_blend(conn)
        assert conn.execute("SELECT normalized_als_score FROM course_career_scores WHERE soc_code='other' ORDER BY course_code").fetchall()==[(0,),(5,)]
        assert conn.execute("SELECT DISTINCT normalized_als_score FROM course_career_scores WHERE soc_code='career'").fetchall()==[(0,)]


def test_blend_version_change_reuses_predictions(database,monkeypatch):
    from ai.recommendations.spark_jobs import worker
    from ai.recommendations import scoring
    connect,_=database
    hybrid(monkeypatch)
    with connect(os.environ['DATABASE_URL']) as conn:
        identity=training_identity(publish.marker(conn,'spark_training_fingerprint'))
        publish.publish_predictions(conn,[(*r[:3],i) for i,r in enumerate(RATINGS)],identity)
        conn.execute("DELETE FROM ingest_runs WHERE source='spark_blend'")
    monkeypatch.setattr(worker,'get_spark',lambda:pytest.fail('blend-only update trained'))
    worker.attempt()
    with connect(os.environ['DATABASE_URL']) as conn:
        assert publish.marker(conn,'spark_als')==identity
        assert publish.marker(conn,'spark_blend')==scoring.BLEND_VERSION


def test_immutable_snapshot_and_superseded_job(database,monkeypatch,tmp_path):
    from ai.recommendations.spark_jobs import worker, model
    from ai.recommendations.spark_jobs.session import get_spark
    connect,_=database
    hybrid(monkeypatch)
    monkeypatch.setattr(worker,'LAKE_DIR',tmp_path)
    monkeypatch.setattr(worker,'get_spark',lambda:get_spark('SnapshotTest'))
    def delayed_model(spark,ratings,job):
        assert sorted((r.catalog_name,r.soc_code,r.course_code,r.rating) for r in ratings.collect())==sorted(RATINGS)
        with connect(os.environ['DATABASE_URL']) as conn:
            conn.execute('UPDATE course_career_scores SET hybrid_rating=1')
            publish.record(conn,'spark_training_fingerprint','new-matrix')
        # The job's materialized snapshot remains unchanged after publication changes.
        assert sorted(r.rating for r in spark.read.parquet(str(job/'ratings')).collect())==[2,3,4,5]
        return ratings.selectExpr('catalog_name','soc_code','course_code','rating AS als_score')
    monkeypatch.setattr(model,'run',delayed_model)
    worker.attempt()
    with connect(os.environ['DATABASE_URL']) as conn:
        assert publish.marker(conn,'spark_als') is None
        assert conn.execute('SELECT count(*) FROM course_career_scores WHERE als_score IS NOT NULL').fetchone()[0]==0


def test_api_serves_hybrid_while_separate_worker_is_delayed_and_fails(database,monkeypatch,tmp_path):
    import subprocess
    import sys
    import time
    from backend import main
    connect,_=database
    hybrid(monkeypatch)
    with connect(os.environ['DATABASE_URL']) as conn:
        conn.execute('ALTER TABLE courses ADD COLUMN title text, ADD COLUMN credit_min real, ADD COLUMN credit_max real, ADD COLUMN credit_raw text')
        conn.execute('CREATE TABLE occupations(soc_code text,title text)')
        conn.execute("INSERT INTO occupations VALUES ('career','Career')")
        conn.execute('CREATE TABLE course_links(catalog_name text,course_code text,target_code text,kind text)')
    audit={'level':'Undergraduate','courses_not_taken':[{'block':'Major','course_codes':['A','B']}]}
    monkeypatch.setattr(main,'_session_and_careers',lambda *_:('token',['career'],audit))
    monkeypatch.setattr(main,'recommend',lambda conn,audit,socs,limit:__import__('ai.recommendations.ranking',fromlist=['recommend']).recommend(conn,audit,socs,limit,catalog='UG'))
    ready=tmp_path/'ready'
    script="""import sys,time
from pathlib import Path
from ai.recommendations.spark_jobs import worker
worker.LAKE_DIR=Path(sys.argv[1])
def delayed_failure():
    (worker.LAKE_DIR/'ready').touch()
    time.sleep(10)
    raise RuntimeError('deliberate ALS failure')
worker.attempt=delayed_failure
sys.argv=['worker','--once']
worker.main()
"""
    process=subprocess.Popen([sys.executable,'-c',script,str(tmp_path)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        deadline=time.monotonic()+20
        while not ready.exists() and process.poll() is None and time.monotonic()<deadline:
            time.sleep(.05)
        assert ready.exists()
        response=main.post_recommend(main.RecommendRequest(session_id='test',soc_codes=['career'],limit=10))
        assert response['scoring_method']=='spark_hybrid'
        assert process.poll() is None
        assert process.wait(timeout=15)!=0
        response=main.post_recommend(main.RecommendRequest(session_id='test',soc_codes=['career'],limit=10))
        assert response['scoring_method']=='spark_hybrid'
    finally:
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=10)


def test_saved_predictions_retry_without_training(database,monkeypatch,tmp_path):
    from ai.recommendations.spark_jobs import worker,model
    connect,_=database
    hybrid(monkeypatch)
    with connect(os.environ['DATABASE_URL']) as conn:
        identity=training_identity(publish.marker(conn,'spark_training_fingerprint'))
    job=tmp_path/'jobs'/'saved'; (job/'predictions').mkdir(parents=True)
    (job/'manifest.json').write_text(json.dumps({'training_identity':identity}))
    (job/'predictions'/'_SUCCESS').touch()
    class Predictions:
        def select(self,*args): return self
        def toLocalIterator(self): return iter([(*r[:3],2) for r in RATINGS])
    class Spark:
        read=property(lambda self:self)
        def parquet(self,path): return Predictions()
        def stop(self): pass
    monkeypatch.setattr(worker,'LAKE_DIR',tmp_path)
    monkeypatch.setattr(worker,'get_spark',Spark)
    monkeypatch.setattr(model,'run',lambda *args:pytest.fail('compatible artifacts retrained'))
    worker.attempt()
    with connect(os.environ['DATABASE_URL']) as conn:
        assert publish.marker(conn,'spark_als')==identity

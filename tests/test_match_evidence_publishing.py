"""Real PostgreSQL checks, isolated from the application's catalog and scores."""
import csv
import os
from uuid import uuid4

import pytest

psycopg=pytest.importorskip('psycopg')
pytest.importorskip('pyspark')
from ai.recommendations.skill_evidence import SCHEMA_SQL, publication_current
from ai.recommendations.spark_jobs.match_evidence import COLUMNS, publish_exports, score_batch
from ai.recommendations.scoring import release_key


@pytest.fixture
def database(tmp_path):
    if not os.environ.get('DATABASE_URL'):
        pytest.skip('DATABASE_URL required')
    schema='test_matches_'+uuid4().hex
    with psycopg.connect(os.environ['DATABASE_URL'],autocommit=True) as admin:
        admin.execute(f'CREATE SCHEMA {schema}')
        def connect():
            return psycopg.connect(os.environ['DATABASE_URL'],options=f'-c search_path={schema}')
        try:
            with connect() as conn:
                conn.execute('CREATE TABLE ingest_runs (source text, release text, loaded_at timestamptz DEFAULT now(), PRIMARY KEY(source,release))')
                conn.execute('CREATE TABLE course_career_scores (catalog_name text, soc_code text, course_code text, als_score real, hybrid_rating real, PRIMARY KEY(catalog_name,soc_code,course_code))')
                conn.execute('''CREATE TABLE syllabus_triples (triple_id text, filename text, evidence text,
                    predicate text, object text, subject text, confidence numeric(3,2), page_num int, section_heading text)''')
                conn.execute("INSERT INTO ingest_runs(source,release) VALUES ('catalog:UG','input')")
                key=release_key(conn)
                conn.execute("INSERT INTO ingest_runs(source,release) VALUES ('spark_als',%s)",(key,))
                conn.execute("INSERT INTO course_career_scores VALUES ('UG','career','ITSC 3160',1,2),('GR','career','ITSC 3160',3,4)")
                conn.execute("INSERT INTO syllabus_triples VALUES ('a','source.pdf','Programming is covered.','covers','Programming','ITSC 3160',.9,1,'Objectives')")
                conn.execute(SCHEMA_SQL)
                batch=score_batch(conn)
            evidence=tmp_path/'evidence'; evidence.mkdir()
            predictions=tmp_path/'predictions'; predictions.mkdir()
            with (predictions/'part-0.csv').open('w') as handle:
                csv.writer(handle).writerows([('UG','career','ITSC 3160',1,2),('GR','career','ITSC 3160',3,4)])
            def write(rows=None):
                values=[]
                for catalog in ('UG','GR'):
                    value=dict(zip(COLUMNS,[f'skill:{catalog}',catalog,'ITSC 3160','career','Programming','programming',
                        'Programming','programming','skill',.9,.8,.75,.54,.27,1,'a','source.pdf',1,'Objectives','Programming is covered.']))
                    values.append(value)
                if rows:
                    values=rows(values)
                with (evidence/'part-0.csv').open('w') as handle:
                    csv.writer(handle).writerows([[v[c] for c in COLUMNS] for v in values])
            write()
            yield connect,batch,evidence,predictions,write
        finally:
            admin.execute(f'DROP SCHEMA {schema} CASCADE')


def test_successful_evidence_publication_never_changes_scores(database):
    connect,batch,evidence,predictions,_=database
    with connect() as conn:
        before=conn.execute('SELECT * FROM course_career_scores ORDER BY catalog_name').fetchall()
        assert publish_exports(conn,evidence,predictions,batch)==2
        assert before==conn.execute('SELECT * FROM course_career_scores ORDER BY catalog_name').fetchall()
        assert score_batch(conn)==batch
        assert publication_current(conn)


@pytest.mark.parametrize('change', ['duplicate','source','nonfinite','foreign_pair','predictions','concurrent_batch'])
def test_invalid_export_rolls_back_old_evidence(database,change):
    connect,batch,evidence,predictions,write=database
    with connect() as conn:
        publish_exports(conn,evidence,predictions,batch)
        old=conn.execute('SELECT * FROM course_career_match_evidence ORDER BY id').fetchall()
    def mutate(values):
        if change=='duplicate': values.append(values[0])
        if change=='source': values[0]['source_text']='Invented statement'
        if change=='nonfinite': values[0]['contribution']=float('nan')
        if change=='foreign_pair': values[0]['soc_code']='unknown'
        return values
    write(mutate)
    if change=='predictions':
        (predictions/'part-0.csv').write_text('UG,career,ITSC 3160,1,2\n')
    if change=='concurrent_batch':
        with connect() as conn:
            conn.execute("UPDATE ingest_runs SET loaded_at=loaded_at+interval '1 second' WHERE source='spark_als'")
    with pytest.raises((ValueError,psycopg.Error)):
        with connect() as conn:
            publish_exports(conn,evidence,predictions,batch)
    with connect() as conn:
        assert old==conn.execute('SELECT * FROM course_career_match_evidence ORDER BY id').fetchall()
        assert conn.execute('SELECT count(*) FROM course_career_scores').fetchone()[0]==2


@pytest.mark.parametrize('change',['version','input','batch','missing_row'])
def test_evidence_freshness_tracks_its_own_version_and_score_batch(database,change):
    connect,batch,evidence,predictions,_=database
    with connect() as conn:
        publish_exports(conn,evidence,predictions,batch)
        if change=='version': conn.execute("UPDATE course_career_match_publication SET evidence_version='old'")
        if change=='input': conn.execute("UPDATE ingest_runs SET release='changed' WHERE source='catalog:UG'")
        if change=='batch': conn.execute("UPDATE ingest_runs SET loaded_at=loaded_at+interval '1 second' WHERE source='spark_als'")
        if change=='missing_row': conn.execute("DELETE FROM course_career_match_evidence WHERE catalog_name='GR'")
        assert not publication_current(conn)


def test_in_flight_score_publication_invalidates_evidence_attempt(database):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    connect,batch,evidence,predictions,_=database
    entered=Event()
    def attempt():
        entered.set()
        with connect() as conn:
            return publish_exports(conn,evidence,predictions,batch)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with connect() as writer:
            writer.execute('LOCK TABLE ingest_runs IN SHARE ROW EXCLUSIVE MODE')
            writer.execute("UPDATE ingest_runs SET loaded_at=loaded_at+interval '1 second' WHERE source='spark_als'")
            future=pool.submit(attempt)
            assert entered.wait(5)
        with pytest.raises(ValueError,match='changed'):
            future.result(timeout=30)
    with connect() as conn:
        assert conn.execute('SELECT count(*) FROM course_career_match_evidence').fetchone()[0]==0


def test_retrieval_is_catalog_scoped_and_rejects_stale_or_weak_matches(database):
    from ai.recommendations.skill_evidence import retrieve_match_items
    connect,batch,evidence,predictions,_=database
    with connect() as conn:
        publish_exports(conn,evidence,predictions,batch)
        def read(catalog='UG',careers=None):
            return retrieve_match_items(conn,catalog,['ITSC 3160'],careers or ['career'],{'career':'Developer'},str)
        assert [i['id'] for i in read()]==['skill:UG']
        assert [i['id'] for i in read('GR')]==['skill:GR']
        assert read(careers=['unknown'])==[]
        conn.execute("UPDATE course_career_match_evidence SET confidence=.79 WHERE catalog_name='UG'")
        assert read()==[]
        assert read('GR')
        conn.execute("UPDATE ingest_runs SET loaded_at=loaded_at+interval '1 second' WHERE source='spark_als'")
        assert read('GR')==[]


def test_float32_similarity_roundoff_preserves_actual_contribution(database):
    connect,batch,evidence,predictions,write=database
    def alter(values):
        values[0]['similarity']=1.0000001192092896
        values[0]['points']=.9*values[0]['similarity']*.75
        values[0]['contribution']=values[0]['points']/2
        return values
    write(alter)
    with connect() as conn:
        assert publish_exports(conn,evidence,predictions,batch)==2
        assert conn.execute("SELECT similarity FROM course_career_match_evidence WHERE catalog_name='UG'").fetchone()[0]>1

"""Merged /explain behavior against synthetic data in an isolated PostgreSQL schema.

No data loader, embedding model, Ollama service, or persisted Spark model runs.
"""
import os
import re
from pathlib import Path
from uuid import uuid4

import pytest

psycopg=pytest.importorskip('psycopg')
pytest.importorskip('fastapi')
from fastapi.testclient import TestClient


@pytest.fixture
def merged_api(monkeypatch):
    if not os.environ.get('DATABASE_URL'):
        pytest.skip('DATABASE_URL required')
    import backend.main as main
    import ai.nlp.explanations.retrieval as retrieval
    from ai.recommendations.scoring import release_key
    from ai.recommendations.skill_evidence import EVIDENCE_VERSION
    real_connect=psycopg.connect
    schema='test_merge_'+uuid4().hex
    with real_connect(os.environ['DATABASE_URL'],autocommit=True) as admin:
        admin.execute(f'CREATE SCHEMA {schema}')
        def scoped(*args,**kwargs):
            kwargs['options']=f'-c search_path={schema},public'
            return real_connect(*args,**kwargs)
        try:
            with scoped(os.environ['DATABASE_URL']) as conn:
                conn.execute(Path('backend/schema.sql').read_text())
                # Assert namespace isolation before inserting any fixture records.
                for table in ('courses','occupations','course_career_scores','ingest_runs','course_career_match_evidence'):
                    actual=conn.execute('SELECT n.nspname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.oid=%s::regclass',(table,)).fetchone()[0]
                    assert actual==schema
                conn.execute("INSERT INTO ingest_runs(source,release) VALUES ('catalog:Undergraduate 2026-2027','fixture')")
                conn.execute("INSERT INTO occupations VALUES ('15-2051.00','Data Scientists','Analyze data.')")
                conn.execute('''INSERT INTO courses(catalog_name,code,subject,number,title,description,
                    credit_min,credit_max,credit_raw,prerequisite_raw,restriction_raw)
                    VALUES ('Undergraduate 2026-2027','MATH 2112','MATH','2112','Linear Algebra',
                    'May not be taken for credit if credit has been received for both MATH 2164 and STAT 2122.',
                    3,3,'3','MATH 1100 or MATH 1103','Senior standing.')''')
                conn.execute("INSERT INTO course_career_scores VALUES ('Undergraduate 2026-2027','15-2051.00','MATH 2112',4.7,4.5)")
                conn.execute("INSERT INTO ingest_runs(source,release) VALUES ('spark_als',%s)",(release_key(conn),))
                release,stamp=conn.execute("SELECT release,loaded_at FROM ingest_runs WHERE source='spark_als'").fetchone()
                conn.execute('''INSERT INTO course_career_match_evidence VALUES
                    ('skill:merge','Undergraduate 2026-2027','MATH 2112','15-2051.00',
                    'Linear algebra','linear algebra','Mathematics','mathematics','knowledge',
                    .9,.8,.75,.54,.27,1,'fixture-source','fixture.pdf',1,'Objectives','Study linear algebra and matrix methods.')''')
                conn.execute('''INSERT INTO course_career_match_publication
                    (evidence_version,score_release,score_published_at,row_count) VALUES (%s,%s,%s,1)''',(EVIDENCE_VERSION,release,stamp))
            monkeypatch.setattr(main.psycopg,'connect',scoped)
            monkeypatch.setattr(retrieval,'encode',lambda texts:[[1.]+[0.]*383 for _ in texts])
            monkeypatch.setattr(main,'_load_encoder',lambda:None)
            audit={'level':'Undergraduate','classification':'Sophomore',
                   'courses_completed':[{'code':'MATH 2164'},{'code':'STAT 2122'}],
                   'courses_not_taken':[{'block':'Mathematics Elective','course_codes':['MATH 2112']}]}
            loads=[]
            def load_audit(token):
                loads.append(token)
                return audit
            monkeypatch.setattr(main,'load_audit',load_audit)
            yield main,TestClient(main.app),loads
        finally:
            admin.execute(f'DROP SCHEMA {schema} CASCADE')


def test_merged_api_preserves_restrictions_skills_citation_filter_and_renewal(merged_api,monkeypatch):
    main,client,loads=merged_api
    def generate(messages):
        prompt=messages[-1]['content']
        assert 'Credit restriction that applies' in prompt
        assert 'Catalog restriction' in prompt and 'Sophomore' in prompt
        assert 'Catalog prerequisite rule' in prompt
        assert '[skill:merge]' in prompt
        assert 'Spark hybrid career rating' in prompt
        return ('The catalog says you may not receive credit for this course [MATH 2112]. '
                'A recorded skill connection exists [skill:merge]. This guarantees a job.')
    monkeypatch.setattr(main,'generate',generate)
    body={'session_id':'a'*32,'soc_codes':['15-2051.00']}
    before=client.post('/recommend',json=body).json()
    response=client.post('/explain',json={**body,'question':'Why MATH 2112 for data science?'})
    assert response.status_code==200,response.text
    payload=response.json()
    assert 'guarantees' not in payload['answer']
    assert 'may not receive credit' in payload['answer']
    assert 'skill:merge' in payload['citations'] and payload['grounded']
    assert len(payload['evidence'])<=10
    assert loads.count('a'*32)>=3  # recommend, explain, and post-generation renewal
    assert before==client.post('/recommend',json=body).json()


def test_model_failure_returns_skill_evidence_and_renews_audit(merged_api,monkeypatch):
    main,client,loads=merged_api
    def unavailable(messages): raise RuntimeError('model unavailable')
    monkeypatch.setattr(main,'generate',unavailable)
    response=client.post('/explain',json={'session_id':'b'*32,'soc_codes':['15-2051.00'],'question':'Why MATH 2112?'})
    assert response.status_code==503,response.text
    assert any(i['kind']=='skill_match' for i in response.json()['evidence'])
    assert loads==['b'*32,'b'*32]

"""Regression coverage for measured optimizations and source/schedule boundaries."""
import copy
import json
import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from classwizard.api import app
from classwizard import sessions
from classwizard.db import engine,public_snapshot
from classwizard.models import Preferences
from classwizard.validator import verify

pytestmark=pytest.mark.skipif(os.getenv('INTEGRATION')!='1',reason='Requires isolated PostgreSQL/Redis')

def test_cache_invalidation_and_independent_real_catalog_validation():
    with TestClient(app) as client:
        client.post('/api/v1/sessions');token=client.cookies['cw_session']
        state=json.loads(Path('/demo-state.json').read_text());prefs=Preferences(min_courses=0,min_credits=0).model_dump()
        client.put('/api/v1/academic-state',json=state);client.put('/api/v1/preferences',json=prefs)
        first=client.post('/api/v1/plans');assert first.status_code==200
        assert first.json()['status']=='valid'
        assert not verify(public_snapshot(),state,prefs,first.json())
        assert client.post('/api/v1/plans').content==first.content
        public=public_snapshot();revision=sessions.get(token)['revision']
        assert sessions.cached(token,'plans',revision,public['cache_version'])
        assert sessions.cached(token,'plans',revision,'different-version') is None
        prefs['max_credits']=12;client.put('/api/v1/preferences',json=prefs)
        assert not sessions.store.exists('session:'+token+':plans')
        client.delete('/api/v1/session')

def test_mapping_generation_invalidates_public_snapshot():
    before=public_snapshot()
    with engine.begin() as conn:
        original=conn.execute(text('SELECT manifest FROM datasets WHERE id=:v'),{'v':before['version']}).scalar()
        changed={**original,'mapping_generation':before['mapping_generation']+1}
        conn.execute(text('UPDATE datasets SET manifest=CAST(:m AS json) WHERE id=:v'),{'m':json.dumps(changed),'v':before['version']})
    try:
        after=public_snapshot();assert before['cache_version']!=after['cache_version']
    finally:
        with engine.begin() as conn:
            conn.execute(text('UPDATE datasets SET manifest=CAST(:m AS json) WHERE id=:v'),{'m':json.dumps(original),'v':before['version']})

def test_job_registration_does_not_get_lost_in_stale_session_save():
    token=sessions.create();data=sessions.get(token);stale=copy.deepcopy(data)
    job={'owner':token,'revision':data['revision'],'status':'pending'}
    sessions.add_job(token,data,'synthetic-race',job)
    stale['state']={'reviewed':True};sessions.save(token,stale)
    assert 'synthetic-race' in sessions.get(token)['jobs']
    assert not sessions.complete_job(token,'synthetic-race',job['revision'],{**job,'status':'complete'})
    sessions.delete(token)
    assert 'synthetic-race' not in sessions.store.lrange('explanation_queue',0,-1)
    assert not sessions.store.exists('job:synthetic-race')

def test_oversized_or_invalid_worksheet_is_rejected():
    with TestClient(app) as client:
        client.post('/api/v1/sessions')
        assert client.post('/api/v1/worksheet',content=b'not a PDF',headers={'Content-Type':'application/pdf'}).status_code==422
        assert client.post('/api/v1/worksheet',content=b'x'*(10*1024*1024+65537),headers={'Content-Type':'application/pdf'}).status_code==413
        client.delete('/api/v1/session')

def test_source_conditions_and_pdf_provenance():
    prepared=json.loads(Path('/data/prepared/dataset.json').read_text())
    courses={c['code']:c for c in prepared['courses']}
    assert courses['ITSC 3990']['rule']['kind']=='unknown'
    assert prepared['program']['evidence']['pdf_pages']==[203,204]
    groups={g['id']:g for g in prepared['program']['groups']}
    assert groups['technical_electives']['credits']==6
    assert groups['concentration_electives']['credits']==9
    assert groups['capstone']['credits']==3

def test_atomic_new_version_activation_invalidates_results(tmp_path):
    from classwizard.ingest import load
    original=public_snapshot()['version']
    prepared=json.loads(Path('/data/prepared/dataset.json').read_text())
    prepared['version']='synthetic-version-activation'
    remove_public_fixture(prepared['version'])
    file=tmp_path/'new-public-version.json';file.write_text(json.dumps(prepared))
    with TestClient(app) as client:
        client.post('/api/v1/sessions')
        client.put('/api/v1/academic-state',json=json.loads(Path('/demo-state.json').read_text()))
        client.put('/api/v1/preferences',json=Preferences(min_courses=0,min_credits=0).model_dump())
        first=client.post('/api/v1/recommendations');assert first.json()['version']==original
        try:
            assert load(file)['status']=='activated'
            second=client.post('/api/v1/recommendations')
            assert second.status_code==200 and second.json()['version']==prepared['version']
        finally:
            with engine.begin() as conn:
                conn.execute(text('UPDATE datasets SET active=false WHERE active=true'))
                conn.execute(text('UPDATE datasets SET active=true WHERE id=:v'),{'v':original})
            client.delete('/api/v1/session')
            remove_public_fixture(prepared['version'])
    assert public_snapshot()['version']==original

def remove_public_fixture(version):
    assert version=='synthetic-version-activation'
    with engine.begin() as conn:
        for table,parent,key in [('program_courses','programs','program_id'),('requirements','programs','program_id'),
                                  ('course_skills','courses','course_id'),('occupation_skills','occupations','occupation_id')]:
            conn.execute(text(f'DELETE FROM {table} WHERE {key} IN (SELECT id FROM {parent} WHERE version=:v)'),{'v':version})
        for table in ['embeddings','source_documents','courses','programs','occupations','skills']:
            conn.execute(text(f'DELETE FROM {table} WHERE version=:v'),{'v':version})
        conn.execute(text('DELETE FROM datasets WHERE id=:v AND active=false'),{'v':version})

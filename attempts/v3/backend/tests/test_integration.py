"""Run only against disposable Docker test data; all student states are synthetic."""
import copy
import json
import os
import time
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from classwizard.api import app
from classwizard import sessions
from classwizard.db import engine, public_snapshot
from classwizard.ingest import load

pytestmark = pytest.mark.skipif(os.getenv('INTEGRATION') != '1', reason='Set INTEGRATION=1 with PostgreSQL/Redis running')

def test_api_flow_and_deletion():
    with TestClient(app) as client:
        assert client.post('/api/v1/plans').status_code == 401
        assert client.post('/api/v1/sessions').status_code == 200
        token = client.cookies['cw_session']
        assert client.post('/api/v1/plans').status_code == 409
        state = json.loads(Path('/demo-state.json').read_text())
        assert client.put('/api/v1/academic-state', json=state).status_code == 200
        from classwizard.models import Preferences
        prefs = Preferences(min_courses=0,min_credits=0).model_dump()
        assert client.put('/api/v1/preferences', json=prefs).status_code == 200
        recommendation = client.post('/api/v1/recommendations')
        assert recommendation.status_code == 200
        assert recommendation.json()['courses']
        response = client.post('/api/v1/plans')
        assert response.status_code == 200
        assert response.json()['status'] == 'valid', response.json()
        # Independent scheduling validator, separate from solver implementation.
        completed = set(state['completed'])
        seen = set()
        for semester in response.json()['semesters']:
            codes = {c['code'] for c in semester['courses']}
            assert not seen & codes
            assert semester['credits'] <= prefs['max_credits']
            assert len(codes) <= prefs['max_courses']
            seen |= codes
        assert response.json()['projected_credits'] >= 120
        job = client.post('/api/v1/explanations').json()['job_id']
        assert sessions.store.exists('job:' + job)
        assert client.delete('/api/v1/session').status_code == 200
        assert not sessions.store.exists('session:' + token)
        assert not sessions.store.exists('job:' + job)

def test_isolation_expiration_origin_and_privacy():
    with TestClient(app) as a, TestClient(app) as b:
        a.post('/api/v1/sessions'); b.post('/api/v1/sessions')
        token = a.cookies['cw_session']
        a.put('/api/v1/academic-state', json={'completed': {'ITSC 1212':'A'},'reviewed':True})
        assert b.get('/api/v1/session').json()['state'] is None
        assert a.put('/api/v1/academic-state',json={},headers={'Origin':'https://other.example'}).status_code == 403
        data = sessions.get(token); data['created'] = time.time() - 9*3600
        sessions.store.set('session:' + token, json.dumps(data))
        assert a.get('/api/v1/session').status_code == 401
        assert not sessions.store.exists('session:' + token)
        assert sessions.store.config_get('save')['save'] == ''
        assert sessions.store.config_get('appendonly')['appendonly'] == 'no'
        b.delete('/api/v1/session')
    with engine.connect() as conn:
        tables = conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'")).scalars().all()
        assert not any('student' in t or 'session' in t or 'worksheet' in t for t in tables)

def test_idempotent_and_atomic_ingestion(tmp_path):
    first = public_snapshot()['version']
    assert load()['status'] == 'already_loaded'
    data = json.loads(Path('/data/prepared/dataset.json').read_text())
    data['version'] = 'rollback-fixture'
    file = tmp_path/'rollback.json'; file.write_text(json.dumps(data))
    with pytest.raises(RuntimeError):
        load(file, fail_after=True)
    assert public_snapshot()['version'] == first
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM datasets WHERE id='rollback-fixture'")).scalar() == 0

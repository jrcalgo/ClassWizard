import json
import secrets
import time
from collections import Counter
from email.parser import BytesParser
from email.policy import default
from typing import Annotated
from fastapi import FastAPI, Request, Response, Cookie, HTTPException
from sqlalchemy import text
from . import sessions
from .config import ATTEMPT
from .db import engine, public_snapshot, metrics
from .models import AcademicState, Preferences
from .engine import recommend, plan
from .parser import parse_pdf

app = FastAPI(title='ClassWizard', version=ATTEMPT)
request_metrics={'requests':0,'statuses':Counter(),'seconds':0.0}
Token = Annotated[str | None, Cookie(alias='cw_session')]

@app.middleware('http')
async def protect(request: Request, call_next):
    started=time.perf_counter()
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        origin = request.headers.get('origin')
        if origin:
            from urllib.parse import urlparse
            if urlparse(origin).netloc != request.headers.get('host'):
                return Response('Origin mismatch', status_code=403)
    try:
        response = await call_next(request)
    except Exception:
        response=Response('Service unavailable; retry shortly.', status_code=503)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    request_metrics['requests']+=1
    request_metrics['statuses'][str(response.status_code)]+=1
    request_metrics['seconds']+=time.perf_counter()-started
    return response

def snapshot():
    data = public_snapshot()
    if not data:
        raise HTTPException(503, 'Public datasets are not loaded.')
    return data

def ready(token):
    data = sessions.get(token)
    if not data['state'] or not data['state']['reviewed']:
        raise HTTPException(409, 'Review and save your academic state first.')
    return data, data['state'], data['preferences'] or Preferences().model_dump()

@app.get('/api/v1/health')
def health():
    with engine.connect() as conn:
        conn.execute(text('SELECT 1'))
    sessions.store.ping()
    return {'status': 'ok', 'attempt': ATTEMPT}

@app.get('/api/v1/metrics')
def telemetry():
    return {'attempt':ATTEMPT,'requests':request_metrics['requests'],'statuses':dict(request_metrics['statuses']),
            'http_seconds':request_metrics['seconds'],'sql':dict(metrics),'queue_depth':sessions.store.llen('explanation_queue')}

@app.get('/api/v1/readiness')
def readiness():
    health()
    with engine.connect() as conn:
        version=conn.execute(text('SELECT id FROM datasets WHERE active=true')).scalar_one_or_none()
        count=conn.execute(text('SELECT count(*) FROM embeddings WHERE version=:v'),{'v':version}).scalar()
    return {'core_ready':bool(version),'embeddings_ready':bool(count),'explanation_worker_alive':bool(sessions.store.exists('worker:heartbeat')),
            'generation_optional':True,'worksheet_validation':'synthetic only'}

@app.get('/api/v1/status')
def status():
    public = snapshot()
    with engine.connect() as conn:
        embeddings = conn.execute(text('SELECT count(*) FROM embeddings WHERE version=:v'), {'v': public['version']}).scalar()
    return {'attempt': ATTEMPT, 'version': public['version'], 'courses': len(public['courses']),
            'embeddings': embeddings, 'worksheet_validation': 'synthetic only', 'offering_data': 'unverified'}

@app.post('/api/v1/sessions')
def new_session(response: Response):
    token = sessions.create()
    response.set_cookie('cw_session', token, httponly=True, samesite='strict', max_age=sessions.ABSOLUTE)
    return {'idle_minutes': 60, 'maximum_hours': 8}

@app.get('/api/v1/session')
def session(cw_session: Token = None):
    data = sessions.get(cw_session)
    return {k: data[k] for k in ['state', 'preferences', 'revision']}

@app.delete('/api/v1/session')
def end_session(response: Response, cw_session: Token = None):
    if cw_session:
        sessions.delete(cw_session)
    response.delete_cookie('cw_session')
    return {'deleted': True}

@app.post('/api/v1/worksheet')
async def worksheet(request: Request, cw_session: Token = None):
    sessions.get(cw_session)
    limit = 10 * 1024 * 1024
    # Read the body ourselves to prevent UploadFile spilling private bytes to disk.
    body = bytearray()
    async for part in request.stream():
        body.extend(part)
        if len(body) > limit + 65536:
            raise HTTPException(413, 'Worksheet exceeds 10 MB.')
    content = bytes(body)
    content_type = request.headers.get('content-type', '')
    if content_type.startswith('multipart/form-data'):
        msg = BytesParser(policy=default).parsebytes(('Content-Type: ' + content_type + '\r\nMIME-Version: 1.0\r\n\r\n').encode() + content)
        files = [p.get_payload(decode=True) for p in msg.iter_parts() if p.get_param('name', header='content-disposition') == 'file'] if msg.is_multipart() else []
        if len(files) != 1:
            raise HTTPException(400, 'Provide exactly one PDF file.')
        content = files[0]
    if len(content) > limit:
        raise HTTPException(413, 'Worksheet exceeds 10 MB.')
    try:
        return parse_pdf(content)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

@app.put('/api/v1/academic-state')
def academic_state(state: AcademicState, cw_session: Token = None):
    data = sessions.get(cw_session)
    data['state'] = state.model_dump()
    sessions.save(cw_session, data)
    return {'saved': True, 'revision': data['revision']}

@app.put('/api/v1/preferences')
def preferences(prefs: Preferences, cw_session: Token = None):
    data = sessions.get(cw_session)
    career_codes = {o['soc'] for o in snapshot()['careers']}
    if prefs.career not in career_codes:
        raise HTTPException(422, 'Unknown career.')
    data['preferences'] = prefs.model_dump()
    sessions.save(cw_session, data)
    return {'saved': True, 'revision': data['revision']}

@app.get('/api/v1/catalog')
def catalog(q: str = '', limit: int = 100):
    from .db import active_version
    version=active_version()
    params={'v':version,'q':'%'+q[:100].lower()+'%','n':max(1,min(limit,200))}
    with engine.connect() as conn:
        count=conn.execute(text("SELECT count(*) FROM courses WHERE version=:v AND lower(code||' '||title) LIKE :q"),params).scalar()
        rows=conn.execute(text("SELECT payload FROM courses WHERE version=:v AND lower(code||' '||title) LIKE :q ORDER BY code LIMIT :n"),params).scalars().all()
    return {'version':version,'total':count,'courses':rows}

@app.get('/api/v1/rule-review')
def rule_review(offset:int=0,limit:int=100):
    from .db import active_version
    version=active_version()
    params={'v':version,'offset':max(0,min(offset,20000)),'n':max(1,min(limit,100))}
    with engine.connect() as conn:
        rows=conn.execute(text("""SELECT code,title,payload->'rule' AS rule,payload->'evidence' AS evidence FROM courses
            WHERE version=:v AND (payload->'rule'->>'kind'='unknown' OR payload->>'quarantined'='true')
            ORDER BY code OFFSET :offset LIMIT :n"""),params).mappings().all()
    return {'version':version,'offset':params['offset'],'courses':[dict(r) for r in rows]}

@app.get('/api/v1/blocked-courses')
def blocked_courses(offset:int=0,limit:int=100,cw_session:Token=None):
    data,state,prefs=ready(cw_session)
    result=recommend(snapshot(),state,prefs,max(0,min(offset,20000)),max(1,min(limit,100)))
    return {k:result[k] for k in ['version','blocked','blocked_total','blocked_offset']}

@app.get('/api/v1/program')
def program():
    data = snapshot()
    return {'version': data['version'], **data['program']}

@app.get('/api/v1/careers')
def careers():
    data = snapshot()
    return {'version': data['version'], 'careers': data['careers']}

@app.post('/api/v1/recommendations')
def recommendations(cw_session: Token = None):
    data, state, prefs = ready(cw_session)
    try:
        public = snapshot()
        previous = sessions.cached(cw_session, 'recommendations', data['revision'], public['cache_version'],serialized=True)
        if previous is not None:
            return Response(previous,media_type='application/json')
        result = recommend(public, state, prefs)
        if not sessions.put_cache(cw_session, 'recommendations', data['revision'], public['cache_version'], result):
            raise HTTPException(409, 'Academic state changed while generating recommendations.')
        return Response(json.dumps(result,separators=(',',':')),media_type='application/json')
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

@app.post('/api/v1/plans')
def plans(cw_session: Token = None):
    data, state, prefs = ready(cw_session)
    try:
        public = snapshot()
        previous = sessions.cached(cw_session, 'plans', data['revision'], public['cache_version'],serialized=True)
        if previous is not None:
            return Response(previous,media_type='application/json')
        result = plan(public, state, prefs)
        from .validator import verify
        errors=verify(public,state,prefs,result)
        if errors:
            raise HTTPException(503,'Generated plan failed independent validation; retry after data review.')
        if not sessions.put_cache(cw_session, 'plans', data['revision'], public['cache_version'], result):
            raise HTTPException(409, 'Academic state changed while planning.')
        return Response(json.dumps(result,separators=(',',':')),media_type='application/json')
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

@app.post('/api/v1/explanations')
def explanations(cw_session: Token = None):
    data, state, prefs = ready(cw_session)
    public = snapshot()
    results = recommend(public, state, prefs)
    jobid = secrets.token_urlsafe(24)
    job = {'owner': cw_session, 'version': public['version'], 'codes': [c['code'] for c in results['courses'][:5]],
           'status': 'pending', 'revision': data['revision'],
           'reasons':{c['code']:c['score_components'] for c in results['courses'][:5]}}
    sessions.add_job(cw_session, data, jobid, job)
    return {'job_id': jobid, 'status': 'pending'}

@app.get('/api/v1/explanations/{jobid}')
def explanation(jobid: str, cw_session: Token = None):
    data = sessions.get(cw_session)
    if jobid not in data['jobs']:
        raise HTTPException(404, 'Explanation not found.')
    raw = sessions.store.get('job:' + jobid)
    if not raw:
        raise HTTPException(404, 'Explanation expired.')
    job = json.loads(raw)
    if job['revision'] != data['revision']:
        return {'status': 'stale', 'result': {'message': 'Academic state changed; regenerate the explanation.'}}
    return {k: v for k, v in job.items() if k != 'owner'}

import hashlib
import json
import os
import time
import re
from datetime import datetime, timezone
import httpx
from sqlalchemy import text
from .config import EMBEDDING_URL, OLLAMA_URL, OLLAMA_MODEL
from .db import engine, public_snapshot

MODEL = 'sentence-transformers/all-MiniLM-L6-v2@1110a243fdf4706b3f48f1d95db1a4f5529b4d41'

def encode(texts):
    with httpx.Client(timeout=120) as client:
        r = client.post(EMBEDDING_URL + '/encode', json={'texts': texts})
        r.raise_for_status()
        return r.json()['embeddings']

def chunks(value):
    # Conservative character budget; sidecar verifies actual wordpiece length.
    words = value.split()
    for start in range(0, len(words), 100):
        yield ' '.join(words[start:start+120])

def build_embeddings():
    snapshot = public_snapshot()
    if not snapshot:
        return 0
    version = snapshot['version']
    corpus = []
    for c in snapshot['courses'].values():
        # Embed CCI-related and selected program courses first; all public text remains available in SQL.
        if c['code'].startswith(('ITSC ', 'ITIS ', 'ITCS ', 'MATH ', 'STAT ', 'DTSC ')):
            corpus.append((c['code'], c['title'] + ' ' + c['description'], c['evidence']))
    for o in snapshot['careers']:
        corpus.append((o['soc'], o['title'] + ' ' + o['description'], o['evidence']))
    for s in snapshot['skills'].values():
        corpus.append((s['element'], s['name'] + ' ' + s['description'], s['evidence']))
    records = []
    for entity, content, evidence in corpus:
        for i, chunk in enumerate(chunks(content)):
            digest = hashlib.sha256(chunk.encode()).hexdigest()
            records.append({'id': f'{version}:{entity}:{i}', 'version': version, 'entity_id': entity,
                            'content_hash': digest, 'model': MODEL, 'content': chunk,
                            'evidence': json.dumps(evidence)})
    with engine.connect() as conn:
        existing = set(conn.execute(text('SELECT id FROM embeddings WHERE version=:v'), {'v': version}).scalars())
    records = [r for r in records if r['id'] not in existing]
    # Reuse embeddings by public content/model identity across catalog releases.
    with engine.begin() as conn:
        reusable = conn.execute(text('SELECT DISTINCT ON (content_hash,model) content_hash, model, embedding::text FROM embeddings ORDER BY content_hash,model,id')).all()
        by_hash = {(h,m):v for h,m,v in reusable}
        copied = []
        pending = []
        for record in records:
            vector = by_hash.get((record['content_hash'], MODEL))
            if vector:
                copied.append({**record,'embedding':vector})
            else:
                pending.append(record)
        if copied:
            conn.execute(text('''INSERT INTO embeddings(id,version,entity_id,content_hash,model,content,evidence,embedding)
                VALUES (:id,:version,:entity_id,:content_hash,:model,:content,CAST(:evidence AS jsonb),CAST(:embedding AS vector))
                ON CONFLICT(id) DO NOTHING'''),copied)
        records = pending
    count = 0
    for start in range(0, len(records), 32):
        batch = records[start:start+32]
        vectors = encode([r['content'] for r in batch])
        for record, vector in zip(batch, vectors):
            record['embedding'] = json.dumps(vector)
        with engine.begin() as conn:
            conn.execute(text('''INSERT INTO embeddings(id,version,entity_id,content_hash,model,content,evidence,embedding)
                VALUES (:id,:version,:entity_id,:content_hash,:model,:content,CAST(:evidence AS jsonb),CAST(:embedding AS vector))
                ON CONFLICT(id) DO NOTHING'''), batch)
        count += len(batch)
    # Always retry the idempotent mapping publication, including after an interrupted
    # vector pass whose rows were already committed before mapping failed.
    if snapshot:
        # Semantic matches supplement lexical links, retaining confidence/model/evidence.
        with engine.begin() as conn:
            inserted = conn.execute(text('''INSERT INTO course_skills(course_id,skill_id,confidence,payload)
                SELECT c.id, candidate.skill_id, candidate.similarity,
                  json_build_object('method','semantic-estimate','model',CAST(:model AS text),'confidence',candidate.similarity,
                    'evidence',c.payload->'evidence')
                FROM courses c JOIN embeddings ce ON ce.entity_id=c.code AND ce.version=c.version AND split_part(ce.id,chr(58),3)='0'
                CROSS JOIN LATERAL (
                  SELECT s.id AS skill_id, 1-(ce.embedding <=> se.embedding) AS similarity
                  FROM skills s JOIN embeddings se ON se.entity_id=s.element AND se.version=s.version AND split_part(se.id,chr(58),3)='0'
                  WHERE s.version=:v ORDER BY ce.embedding <=> se.embedding LIMIT 3
                ) candidate WHERE c.version=:v AND candidate.similarity>=0.55
                ON CONFLICT(course_id,skill_id) DO NOTHING RETURNING course_id'''),{'model':MODEL,'v':version}).all()
            if inserted:
                conn.execute(text('''UPDATE datasets SET manifest=jsonb_set(manifest::jsonb,'{mapping_generation}',
                    to_jsonb(COALESCE((manifest->>'mapping_generation')::int,0)+1))::json WHERE id=:v'''),{'v':version})
    return count

def retrieve_public(query, version, limit=5):
    vector = json.dumps(encode([query])[0])
    with engine.connect() as conn:
        count=conn.execute(text('SELECT count(*) FROM embeddings WHERE version=:v'),{'v':version}).scalar()
        # Synthetic qualification is documented; real-corpus ANN is opt-in and size-bounded.
        approximate=os.getenv('VECTOR_MODE','exact')=='qualified-ann' and count>=10000
        if approximate:
            conn.execute(text('SET LOCAL hnsw.ef_search=256'))
            conn.execute(text("SET LOCAL hnsw.iterative_scan='strict_order'"))
        else:
            conn.execute(text('SET LOCAL enable_indexscan=off'))
        ordering='embedding <=> CAST(:q AS vector)' + ('' if approximate else ', id')
        rows = conn.execute(text('''SELECT entity_id, content, evidence, embedding <=> CAST(:q AS vector) AS distance
                  FROM embeddings WHERE version=:v ORDER BY '''+ordering+' LIMIT :n'),
                            {'q': vector, 'v': version, 'n': limit}).mappings().all()
        return [dict(r) for r in rows]

def template(courses):
    output=[]
    for c in courses:
        degree=c.get('score_components',{}).get('degree_progress',0)>0
        reason='It supports a remaining degree requirement.' if degree else 'It offers additional learning relevant to your selected direction.'
        names=c.get('skill_names',[])[:4]
        skills=(' Its coursework is mapped to '+', '.join(names)+'.') if names else ''
        output.append({'code':c['code'],'text':f"{c['code']} — {c['title']}. {reason}{skills} Review prerequisite conditions and actual term availability.",'evidence':[c['evidence']]})
    return output

def evidence_options(courses):
    choices=[]
    for c in courses[:3]:
        sentences=re.split(r'(?<=[.!?])\s+',c['description'])
        candidates=[s for s in sentences if 6<=len(s.split())<=30 and not re.search(r'prerequisite|corequisite|permission|cross.listed|standing',s,re.I)]
        if not candidates:candidates=[c['title']]
        for sentence in candidates[:2]:
            choices.append({'id':c['code'],'text':sentence})
    return choices

def model_guard(client):
    expected=os.getenv('OLLAMA_MODEL_DIGEST','357c53fb659c5076de1d65ccb0b397446227b71a42be9d1603d46168015c9e4b')
    response=client.get(OLLAMA_URL+'/api/tags');response.raise_for_status()
    if not any(m.get('name')==OLLAMA_MODEL and m.get('digest')==expected for m in response.json().get('models',[])):
        raise ValueError('Local model artifact has not been validated.')

def explain(courses, version):
    explanations = template(courses)
    evidence=evidence_options(courses)
    retrieval = []
    try:
        if courses:
            retrieval = retrieve_public(courses[0]['title'], version)
    except (httpx.HTTPError, OSError):
        pass
    if not evidence:
        return {'mode': 'template', 'explanations': [], 'message': 'No eligible courses to explain.'}
    prompt=('Select one public course evidence highlight. Return JSON with text copied EXACTLY from an option '
            'and citations containing that option\'s course ID. Do not add claims. Options: '+json.dumps(evidence))
    schema={'type':'object','properties':{'text':{'type':'string','enum':[e['text'] for e in evidence]},
            'citations':{'type':'array','items':{'type':'string','enum':sorted({e['id'] for e in evidence})},'minItems':1,'maxItems':1}},
            'required':['text','citations'],'additionalProperties':False}
    started = time.perf_counter()
    try:
        external = os.getenv('EXTERNAL_EXPLANATION_URL')
        if external:
            # Only public evidence is transmitted; private state and results are excluded.
            with httpx.Client(timeout=90) as client:
                response = client.post(external, json={'evidence': evidence}, headers={'Authorization': 'Bearer ' + os.getenv('EXTERNAL_EXPLANATION_TOKEN', '')})
                response.raise_for_status()
                generated = response.json()
        else:
            with httpx.Client(timeout=90) as client:
                model_guard(client)
                response = client.post(OLLAMA_URL + '/api/generate', json={'model': OLLAMA_MODEL, 'prompt': prompt,
                    'stream': False, 'format': schema, 'keep_alive': '10m',
                    'options': {'temperature': 0, 'num_predict': 128, 'num_ctx': 1024, 'num_thread': 2}})
                response.raise_for_status()
                generated = json.loads(response.json()['response'])
        if not isinstance(generated,dict):
            raise ValueError('Explanation output must be an object')
        valid_ids = {e['id'] for e in evidence}
        citations = generated.get('citations', [])
        if not isinstance(generated.get('text'), str) or not citations or not set(citations) <= valid_ids or not any(e['id'] in citations and e['text']==generated['text'] for e in evidence):
            raise ValueError('Invalid evidence citations')
        return {'mode': 'llm', 'explanations': explanations, 'public_course_summary': generated['text'],
                'citations': citations, 'retrieval': retrieval, 'seconds': round(time.perf_counter()-started, 3)}
    except (httpx.HTTPError, ValueError, KeyError, TypeError, OSError):
        return {'mode': 'template', 'explanations': explanations, 'retrieval': retrieval,
                'message': 'AI service unavailable or output failed evidence validation; deterministic explanations supplied.',
                'seconds': round(time.perf_counter()-started, 3)}

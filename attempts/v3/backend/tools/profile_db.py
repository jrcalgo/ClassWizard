import json
import time
from pathlib import Path
from sqlalchemy import text
from classwizard.db import engine, metrics, public_snapshot

times=[];start_queries=metrics['queries']
for _ in range(10):
    start=time.perf_counter();public_snapshot();times.append((time.perf_counter()-start)*1000)
result={'snapshot_ms':times,'sql_queries':metrics['queries']-start_queries,'sql_seconds':metrics['sql_seconds']}
with engine.connect() as conn:
    result['query_plans']={}
    queries={
        'courses': "SELECT code, payload FROM courses WHERE version=(SELECT id FROM datasets WHERE active=true)",
        'skill_join': "SELECT c.code,s.element FROM courses c JOIN course_skills cs ON c.id=cs.course_id JOIN skills s ON s.id=cs.skill_id WHERE c.version=(SELECT id FROM datasets WHERE active=true)",
        'exact_vectors': "SELECT entity_id FROM embeddings WHERE version=(SELECT id FROM datasets WHERE active=true) ORDER BY embedding <=> (SELECT embedding FROM embeddings LIMIT 1) LIMIT 10"}
    for name,query in queries.items():
        result['query_plans'][name]=[r[0] for r in conn.execute(text('EXPLAIN (ANALYZE, BUFFERS) '+query))]
Path('/reports/database-profile.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))

"""Synthetic scale and filtered-recall benchmark in connection-local temporary tables."""
import json
import time
from pathlib import Path
import numpy as np
from sqlalchemy import text
from classwizard.db import engine

def run(n=100000):
    rng=np.random.default_rng(42)
    centers=rng.normal(size=(50,384)).astype('float32');centers/=np.linalg.norm(centers,axis=1,keepdims=True)
    queries=[]
    started=time.perf_counter()
    with engine.begin() as conn:
        conn.execute(text('CREATE TEMP TABLE bench_courses(id integer PRIMARY KEY,title text) ON COMMIT DROP'))
        conn.execute(text('INSERT INTO bench_courses SELECT i, concat(\'Synthetic course \',i) FROM generate_series(1,10000) i'))
        conn.execute(text('CREATE TEMP TABLE bench_vectors(id integer PRIMARY KEY, course_id integer, category integer, rare boolean, embedding vector(384)) ON COMMIT DROP'))
        raw=conn.connection.driver_connection
        with raw.cursor() as cursor:
            with cursor.copy('COPY bench_vectors(id,course_id,category,rare,embedding) FROM STDIN') as writer:
                for start in range(0,n,2000):
                    indices=np.arange(start,min(n,start+2000));clusters=indices%50
                    batch=centers[clusters]+rng.normal(scale=.025,size=(len(indices),384)).astype('float32')
                    batch/=np.linalg.norm(batch,axis=1,keepdims=True)
                    for idx,cluster,vector in zip(indices,clusters,batch):
                        writer.write_row((int(idx),int(idx%10000+1),int(cluster%4),bool(idx%100==0),json.dumps(vector.tolist())))
                        if idx<20:queries.append((json.dumps(vector.tolist()),int(cluster%4)))
        load_seconds=time.perf_counter()-started
        conn.execute(text('ANALYZE bench_courses'));conn.execute(text('ANALYZE bench_vectors'))
        conn.execute(text('CREATE INDEX bench_vectors_course ON bench_vectors(course_id)'))
        build=time.perf_counter()
        conn.execute(text("SET LOCAL maintenance_work_mem='256MB'"))
        conn.execute(text('CREATE INDEX bench_vectors_hnsw ON bench_vectors USING hnsw(embedding vector_cosine_ops) WITH (m=16,ef_construction=128)'))
        build_seconds=time.perf_counter()-build
        timings=[]
        recall=[]
        filtered_recall=[]
        for query,category in queries:
            params={'q':query,'category':category}
            conn.execute(text('SET LOCAL enable_indexscan=off'))
            start=time.perf_counter()
            exact=conn.execute(text('SELECT id FROM bench_vectors ORDER BY embedding <=> CAST(:q AS vector),id LIMIT 10'),params).scalars().all()
            exact_ms=(time.perf_counter()-start)*1000
            filtered=conn.execute(text('SELECT id FROM bench_vectors WHERE category=:category ORDER BY embedding <=> CAST(:q AS vector),id LIMIT 10'),params).scalars().all()
            rare=conn.execute(text('SELECT id FROM bench_vectors WHERE rare=true ORDER BY embedding <=> CAST(:q AS vector),id LIMIT 10'),params).scalars().all()
            conn.execute(text('SET LOCAL enable_indexscan=on'));conn.execute(text('SET LOCAL enable_seqscan=off'))
            conn.execute(text('SET LOCAL hnsw.ef_search=256'));conn.execute(text("SET LOCAL hnsw.iterative_scan='strict_order'"))
            conn.execute(text('SET LOCAL hnsw.max_scan_tuples=100000'))
            start=time.perf_counter()
            ann=conn.execute(text('SELECT id FROM bench_vectors ORDER BY embedding <=> CAST(:q AS vector) LIMIT 10'),params).scalars().all()
            ann_ms=(time.perf_counter()-start)*1000
            ann_filtered=conn.execute(text('SELECT id FROM bench_vectors WHERE category=:category ORDER BY embedding <=> CAST(:q AS vector) LIMIT 10'),params).scalars().all()
            # Highly selective filters use exact retrieval deliberately.
            conn.execute(text('SET LOCAL enable_indexscan=off'));conn.execute(text('SET LOCAL enable_seqscan=on'))
            rare_fallback=conn.execute(text('SELECT id FROM bench_vectors WHERE rare=true ORDER BY embedding <=> CAST(:q AS vector),id LIMIT 10'),params).scalars().all()
            recall.append(len(set(exact)&set(ann))/10);filtered_recall.append(len(set(filtered)&set(ann_filtered))/10)
            assert rare_fallback==rare
            timings.append({'exact_ms':exact_ms,'ann_ms':ann_ms})
        conn.execute(text('SET LOCAL enable_seqscan=on'));conn.execute(text('SET LOCAL enable_indexscan=on'))
        join_plan=[r[0] for r in conn.execute(text('EXPLAIN (ANALYZE, BUFFERS) SELECT c.id,count(*) FROM bench_courses c JOIN bench_vectors v ON v.course_id=c.id WHERE c.id BETWEEN 1 AND 100 GROUP BY c.id'))]
        report={'synthetic':True,'courses':10000,'chunks':n,'dimensions':384,'seed':42,'queries':len(queries),
                'load_seconds':load_seconds,'index_build_seconds':build_seconds,'recall_at_10':sum(recall)/len(recall),
                'filtered_recall_at_10':sum(filtered_recall)/len(filtered_recall),'high_selectivity_policy':'exact fallback (validated)',
                'mean_exact_ms':sum(t['exact_ms'] for t in timings)/len(timings),'mean_ann_ms':sum(t['ann_ms'] for t in timings)/len(timings),
                'join_plan':join_plan,'timings':timings}
        report['ann_qualifies']=report['recall_at_10']>=.95 and report['filtered_recall_at_10']>=.95 and report['mean_ann_ms']<report['mean_exact_ms']
    Path('/reports/vector-benchmark.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))

if __name__=='__main__':run()

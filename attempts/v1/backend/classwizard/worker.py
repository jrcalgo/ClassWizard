"""Public embedding jobs and Redis-only explanation jobs."""
import json
import time
from . import sessions
from .ai import build_embeddings, explain
from .db import public_snapshot

def run():
    next_embedding_attempt = 0
    while True:
        if time.monotonic() >= next_embedding_attempt:
            try:
                count = build_embeddings()
                print(f'Public embedding pass: {count} new chunks', flush=True)
                next_embedding_attempt = time.monotonic() + 3600
            except Exception:
                # No private exception data or request payloads in worker logs.
                print('Embedding service not ready; retry scheduled.', flush=True)
                next_embedding_attempt = time.monotonic() + 60
        queued = sessions.store.blpop('explanation_queue', timeout=2)
        if not queued:
            continue
        jobid = queued[1]
        raw = sessions.store.get('job:' + jobid)
        if not raw:
            continue
        job = json.loads(raw)
        token = job['owner']
        try:
            data = sessions.get(token)
            if job['revision'] != data['revision']:
                job.update(status='stale', result={'message': 'Academic state changed. Generate a new explanation.'})
            else:
                snapshot = public_snapshot()
                if snapshot['version'] != job['version']:
                    job.update(status='stale', result={'message': 'Public data changed. Refresh recommendations.'})
                else:
                    selected = [snapshot['courses'][c] for c in job['codes'] if c in snapshot['courses']]
                    job.update(status='complete', result=explain(selected, snapshot['version']))
            # Recheck after AI generation so deletion does not recreate student data.
            current = sessions.get(token)
            if sessions.store.exists('job:' + jobid):
                ttl = min(sessions.store.ttl('session:' + token), 3600)
                if ttl > 0:
                    sessions.store.setex('job:' + jobid, ttl, json.dumps(job))
        except Exception:
            sessions.store.delete('job:' + jobid)

if __name__ == '__main__':
    run()

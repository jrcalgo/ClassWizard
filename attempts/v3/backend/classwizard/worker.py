"""Public embedding jobs and Redis-only explanation jobs."""
import json
import time
import threading
from . import sessions
from .ai import explain
from .db import public_snapshot

def recover_claims():
    recovered=0
    while sessions.store.rpoplpush('explanation_processing','explanation_queue'):
        recovered+=1
    return recovered

def run():
    def heartbeat():
        while True:
            try:sessions.store.setex('worker:heartbeat',15,str(time.time()))
            except Exception:pass
            time.sleep(5)
    threading.Thread(target=heartbeat,daemon=True).start()
    # One explanation worker: recover claims left by an interrupted predecessor.
    recover_claims()
    while True:
        try:
            queued = sessions.store.execute_command('BLMOVE','explanation_queue','explanation_processing','LEFT','RIGHT',2)
        except Exception:
            print('Temporary cache unavailable; reconnecting.', flush=True)
            time.sleep(2)
            continue
        if not queued:
            continue
        jobid = queued
        raw = sessions.store.get('job:' + jobid)
        if not raw:
            sessions.store.lrem('explanation_processing',0,jobid)
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
                    selected=[{**snapshot['courses'][c],'score_components':job.get('reasons',{}).get(c,{}),
                               'skill_names':[snapshot['skills'][s]['name'] for s in snapshot['courses'][c]['skills']]} for c in job['codes'] if c in snapshot['courses']]
                    job.update(status='complete', result=explain(selected, snapshot['version']))
            # Recheck after AI generation so deletion does not recreate student data.
            sessions.complete_job(token, jobid, job['revision'], job)
        except Exception:
            sessions.store.delete('job:' + jobid)
        finally:
            sessions.store.lrem('explanation_processing',0,jobid)

if __name__ == '__main__':
    run()

"""Synthetic worker-claim recovery probe; run seed with worker stopped, then check after startup."""
import json
import sys
import time
from pathlib import Path
from classwizard import sessions
from classwizard.db import public_snapshot

jobid='synthetic-recovery-job'
if sys.argv[1]=='seed':
    token=sessions.create();data=sessions.get(token)
    job={'owner':token,'revision':data['revision'],'version':public_snapshot()['version'],
         'codes':['ITSC 3155'],'status':'pending','reasons':{'ITSC 3155':{'degree_progress':1}}}
    sessions.add_job(token,data,jobid,job)
    assert sessions.store.rpoplpush('explanation_queue','explanation_processing')==jobid
    print('Synthetic interrupted claim prepared; no session identifiers logged.')
else:
    started=time.monotonic();owner=None
    try:
        while time.monotonic()-started<150:
            raw=sessions.store.get('job:'+jobid)
            assert raw,'Recovery probe expired unexpectedly.'
            job=json.loads(raw);owner=job['owner']
            if job['status']=='complete':break
            time.sleep(1)
        assert job['status']=='complete',job['status']
        assert jobid not in sessions.store.lrange('explanation_processing',0,-1)
        report={'synthetic':True,'interrupted_claim_recovered':True,'elapsed_seconds':time.monotonic()-started,
                'explanation_mode':job['result']['mode'],'redis_persistence_disabled':sessions.store.config_get('save')['save']=='' and sessions.store.config_get('appendonly')['appendonly']=='no'}
        Path('/reports/worker-recovery.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
    finally:
        if owner:sessions.delete(owner)

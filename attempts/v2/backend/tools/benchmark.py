"""Repeatable real-service benchmark; synthetic sessions only."""
import argparse
import concurrent.futures
import json
import statistics
import time
import threading
from pathlib import Path
import httpx

def percentile(items, p):
    return sorted(items)[min(len(items)-1, int((len(items)-1)*p))] if items else None

def run(base, seconds, concurrency, warmup, output):
    state=json.loads(Path('/demo-state.json').read_text())
    from classwizard.models import Preferences
    prefs=Preferences(min_courses=0,min_credits=0).model_dump()
    barrier=threading.Barrier(concurrency)
    setup_lock=threading.Lock()
    def one(index):
        records=[]; failures=[]; invalid=0
        with httpx.Client(base_url=base,timeout=60) as client:
            # Setup is intentionally outside the measured workload. Serialize it so
            # a baseline's expensive preference validation does not mix with traffic.
            with setup_lock:
                client.post('/api/v1/sessions').raise_for_status()
                client.put('/api/v1/academic-state',json=state).raise_for_status()
                client.put('/api/v1/preferences',json=prefs).raise_for_status()
            barrier.wait(timeout=180)
            begin=time.monotonic(); deadline=begin+warmup+seconds
            while time.monotonic()<deadline:
                for endpoint in ['recommendations','plans']:
                    start=time.perf_counter()
                    try:
                        response=client.post('/api/v1/'+endpoint)
                    except httpx.HTTPError as exc:
                        if time.monotonic()-begin >= warmup:
                            failures.append(type(exc).__name__)
                        continue
                    elapsed=time.perf_counter()-start
                    if time.monotonic()-begin >= warmup:
                        records.append((endpoint,elapsed))
                        if response.status_code!=200:failures.append(response.status_code)
                        elif endpoint=='plans' and response.json()['status']!='valid':invalid+=1
            client.delete('/api/v1/session')
        return records,failures,invalid
    started=time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        outcomes=list(pool.map(one,range(concurrency)))
    result={'seconds':seconds,'warmup':warmup,'concurrency':concurrency,'elapsed':time.monotonic()-started,
            'failures':[e for o in outcomes for e in o[1]],'invalid_plans':sum(o[2] for o in outcomes)}
    for endpoint in ['recommendations','plans']:
        samples=[t for outcome in outcomes for e,t in outcome[0] if e==endpoint]
        result[endpoint]={'count':len(samples),'p50_ms':percentile(samples,.5)*1000 if samples else None,
                          'p95_ms':percentile(samples,.95)*1000 if samples else None,
                          'p99_ms':percentile(samples,.99)*1000 if samples else None}
    result['meets_latency_target']=bool(result['recommendations']['p95_ms'] is not None and result['recommendations']['p95_ms']<=500 and result['plans']['p95_ms']<=2000 and not result['failures'] and result['invalid_plans']==0)
    Path(output).write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--base',default='http://api:8000');parser.add_argument('--seconds',type=int,default=600);parser.add_argument('--warmup',type=int,default=120);parser.add_argument('--concurrency',type=int,default=20);parser.add_argument('--output',default='/tmp/benchmark.json')
    args=parser.parse_args();run(args.base,args.seconds,args.concurrency,args.warmup,args.output)

"""Summarize three complete reports without replacing failed or missing measurements."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def summarize():
    version=json.loads((ROOT/'data/prepared/dataset.json').read_text())['version']
    rows=[]
    for number in range(1,4):
        report=json.loads((ROOT/f'docs/benchmark-full-{number}.json').read_text())
        if (report['seconds'],report['warmup'],report['concurrency'])!=(600,120,20):
            raise ValueError('Reports must use the full declared qualification workload.')
        if report['public_status']['version']!=version:
            raise ValueError('Report uses a different prepared dataset version.')
        rec=report['recommendations'];plan=report['plans']
        passed=bool(rec['count'] and plan['count'] and rec['p95_ms']<=500 and plan['p95_ms']<=2000
                    and not report['failures'] and not report['invalid_plans'])
        rows.append({'run':number,'recommendation_p95_ms':rec['p95_ms'],'plan_p95_ms':plan['p95_ms'],
                     'recommendation_p99_ms':rec['p99_ms'],'plan_p99_ms':plan['p99_ms'],
                     'measured_requests':rec['count']+plan['count'],'requests_per_second':report['throughput_requests_per_second'],
                     'failures':len(report['failures']),'invalid_plans':report['invalid_plans'],'passed':passed})
    result={'version':version,'concurrency':20,'warmup_seconds_per_run':120,'measurement_seconds_per_run':600,
            'runs':rows,'all_passed':all(row['passed'] for row in rows),'total_measured_requests':sum(r['measured_requests'] for r in rows),
            'worst_recommendation_p95_ms':max(r['recommendation_p95_ms'] for r in rows),
            'worst_plan_p95_ms':max(r['plan_p95_ms'] for r in rows),
            'scope':'Warm API traffic with twenty identical synthetic profiles; real worksheets and offerings unverified.'}
    (ROOT/'docs/benchmark-summary.json').write_text(json.dumps(result,indent=2))
    lines=['# Final sustained API qualification','',
           'Each repetition uses twenty isolated synthetic sessions, 120 seconds of warmup and 600 seconds of measurement.',
           'The workload alternates recommendations and plans. Five-minute cache expiry is included.',
           'AI generation, build/download time and synthetic vector-index construction are measured separately.','',
           '| Run | Recommendation p95 | Plan p95 | Requests/s | Measured requests | Failures | Invalid plans | Result |',
           '|---|---:|---:|---:|---:|---:|---:|---|']
    for row in rows:
        lines.append(f"| {row['run']} | {row['recommendation_p95_ms']:.1f} ms | {row['plan_p95_ms']:.1f} ms | {row['requests_per_second']:.1f} | {row['measured_requests']:,} | {row['failures']} | {row['invalid_plans']} | {'PASS' if row['passed'] else 'FAIL'} |")
    lines+=['','Targets: recommendation p95 ≤500 ms; plan p95 ≤2,000 ms; zero errors and invalid successful plans.',
            f"Dataset: `{version}`. Total measured requests: {result['total_measured_requests']:,}.",'',
            'Environment and limits are recorded in `benchmark-environment.json`. Raw reports retain p50/p95/p99,',
            'HTTP statuses, instrumented SQL counters and timings, source version, duration and request counts.',
            'SQL counters exclude driver connection-health pings; end-to-end latency includes those operations.',
            'The load generator is a separate tools container. The app uses the declared 6-CPU/7.75-GiB service limits.','',
            'This qualifies the declared warm workload, not every student profile, cold model startup, arbitrary',
            'solver search or real-semester registration. V1/V2 exploratory runs are shorter and not certifications.','']
    (ROOT/'docs/performance.md').write_text('\n'.join(lines))
    print(json.dumps(result,indent=2))
    return result

if __name__=='__main__':
    if not summarize()['all_passed']:raise SystemExit(1)

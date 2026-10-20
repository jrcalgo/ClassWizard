# Final sustained API qualification

Each repetition uses twenty isolated synthetic sessions, 120 seconds of warmup and 600 seconds of measurement.
The workload alternates recommendations and plans. Five-minute cache expiry is included.
AI generation, build/download time and synthetic vector-index construction are measured separately.

| Run | Recommendation p95 | Plan p95 | Requests/s | Measured requests | Failures | Invalid plans | Result |
|---|---:|---:|---:|---:|---:|---:|---|
| 1 | 124.0 ms | 123.1 ms | 326.3 | 195,806 | 0 | 0 | PASS |
| 2 | 166.8 ms | 167.2 ms | 229.1 | 137,430 | 0 | 0 | PASS |
| 3 | 164.7 ms | 163.0 ms | 229.3 | 137,596 | 0 | 0 | PASS |

Targets: recommendation p95 ≤500 ms; plan p95 ≤2,000 ms; zero errors and invalid successful plans.
Dataset: `388774660f9cc53ac1c8`. Total measured requests: 470,832.

Environment and limits are recorded in `benchmark-environment.json`. Raw reports retain p50/p95/p99,
HTTP statuses, instrumented SQL counters and timings, source version, duration and request counts.
SQL counters exclude driver connection-health pings; end-to-end latency includes those operations.
The load generator is a separate tools container. The app uses the declared 6-CPU/7.75-GiB service limits.

This qualifies the declared warm workload, not every student profile, cold model startup, arbitrary
solver search or real-semester registration. V1/V2 exploratory runs are shorter and not certifications.

# Sequential attempt comparison

Each attempt implements the same end-to-end ClassWizard workflow. Written predecessor
reviews and checksummed preservation preceded the next attempt. V1 and V2 remain unchanged;
V3 incorporates their findings and final source/operational validation.

| Evidence | V1 baseline | V2 optimization | V3 final |
|---|---|---|---|
| Backend tests | 18 passed | 24 passed | 36 passed |
| Browser tests | 2 passed | 2 passed | 4 passed |
| Public snapshots | 813–967 ms, rebuilt each call | Cold 126–146 ms; warm 0.7–1.8 ms | Final cold 58.1 ms; warm 0.32–0.50 ms |
| Application SQL statements for ten snapshots | 70 | 17 | 17 |
| Recommendation p95 | 23,468 ms in initial stress run | 908–1,185 ms across exploratory runs | 124–167 ms across full runs |
| Planning p95 | 17,432 ms in initial stress run | 839–1,034 ms across exploratory runs | 123–168 ms across full runs |
| Errors / invalid successful plans | 18 HTTP 503 errors / 0 invalid successes | 0 / 0 in exploratory runs | 0 / 0 across 470,832 measured requests |
| Qualification duration | Initial 10-second requested stress interval; overruns/failures | Three 30-second exploratory runs, five-second warmup | Three 600-second measurements, each with 120-second warmup |
| Local AI | 90-second timeout with fallback | 82-second response failed evidence validation | Final warm run: 4.04 seconds, validated local-LLM result |
| Main retained improvement | Complete functional baseline | Public cache, linear hydration, COPY, atomic Redis, incremental embeddings | Serialized responses, bounded previews, stricter rules, independent validation, operational checks |

Durations, payloads, resource limits and warm/cold conditions differ. The exploratory runs
show the progression and defects; only V3 has the declared full-duration qualification.
Latency includes driver connection-health overhead, which is excluded from application SQL counters.

V3's synthetic 10,000-course/100,000-chunk scale test measured exact retrieval at 118.8 ms,
HNSW at 12.4 ms, recall@10 0.995, filtered recall@10 0.995 and indexed joins at 3.64 ms.
This qualifies the seeded synthetic queries, not arbitrary real-corpus semantic accuracy.
Current small-corpus retrieval stays exact.

All versions use public catalog/O*NET source snapshots and synthetic test academics. Real
DegreeWorks layouts and term offerings remain unverified. Earlier source/constraint limitations
are preserved for review and corrected in the final attempt rather than silently rewritten.

- [V1 review](v1/docs/review.md)
- [V2 review](v2/docs/review.md)
- [V3 final review](v3/docs/review.md)
- [Full V3 raw/summary measurements](v3/docs/performance.md)

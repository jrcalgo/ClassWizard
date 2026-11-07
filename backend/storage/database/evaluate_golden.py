"""Score raw vector search against the golden query set (read-only).

For each golden item it ranks ALL course vectors exactly (no HNSW index, so
the result is the true ranking, not an approximation) and reports where each
must_include course landed:

  occupation items: courses ranked by similarity to the occupation's vector
  text items:       courses ranked by similarity to the encoded query

Metrics (Manning et al., Introduction to Information Retrieval, ch. 8):
  Recall@k = share of an item's must_include courses ranked within its k,
             averaged over items
  MRR      = mean of 1 / (rank of the best-ranked must_include course)

Items marked with "expected_weakness" (e.g. a bare course code) are scored
and printed but kept out of the averages, so a known limitation does not
hide or distort the baseline.

Run from the repo root (PowerShell); the file is piped in, no rebuild needed:
    Get-Content -Raw data\\eval\\golden_queries.json |
        docker compose exec -T backend python3 -m backend.storage.database.evaluate_golden
Add --include-drafts to also score draft items that already have
must_include filled in (useful before anything is marked verified).
"""

from __future__ import annotations

import json
import os
import sys

from ai.nlp.embeddings.sentence_transformer import encode, to_pgvector

SHOW_TOP = 5

# Exact ranking of every course chunk against one query vector.
RANK_SQL = """
    SELECT source_key, 1 - (embedding <=> %s::vector) AS similarity
    FROM text_chunks
    WHERE source_type = 'course' AND embedding IS NOT NULL
    ORDER BY similarity DESC, source_key
"""


def ranked_courses(conn, vector_text: str) -> list[tuple[str, float]]:
    # Exact scan: the evaluation must measure the embeddings, not the
    # approximate index. SET LOCAL lasts only for this transaction.
    with conn.transaction():
        conn.execute("SET LOCAL enable_indexscan = off")
        return conn.execute(RANK_SQL, (vector_text,)).fetchall()


def occupation_vector(conn, soc_code: str) -> str | None:
    row = conn.execute(
        """
        SELECT embedding::text FROM text_chunks
        WHERE source_type = 'occupation' AND source_key = %s AND embedding IS NOT NULL
        """,
        (soc_code,),
    ).fetchone()
    return row[0] if row else None


def main(argv: list[str]) -> int:
    import psycopg

    include_drafts = "--include-drafts" in argv
    golden = json.load(sys.stdin)

    scored = []  # (item, recall, reciprocal_rank)
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        for item in golden["items"]:
            expected = item.get("must_include") or []
            if not expected:
                continue
            if item.get("status") != "verified" and not include_drafts:
                continue

            if item["kind"] == "occupation":
                vector = occupation_vector(conn, item["soc_code"])
                if vector is None:
                    print(f"{item['id']}: no vector for {item['soc_code']}, skipped")
                    continue
                label = f"{item['soc_code']} {item.get('occupation_title', '')}"
            else:
                vector = to_pgvector(encode([item["query"]])[0])
                label = repr(item["query"])

            ranking = ranked_courses(conn, vector)
            rank_of = {code: position for position, (code, _) in enumerate(ranking, start=1)}
            k = int(item.get("k", 5))

            ranks = {code: rank_of.get(code) for code in expected}
            found = [r for r in ranks.values() if r is not None]
            recall = sum(1 for r in found if r <= k) / len(expected)
            reciprocal = 1 / min(found) if found else 0.0
            scored.append((item, recall, reciprocal))

            verdict = "PASS" if recall == 1 else ("PART" if recall > 0 else "FAIL")
            weak = "  (known weakness, not averaged)" if item.get("expected_weakness") else ""
            print(f"\n{item['id']} [{item['kind']}] {label}  k={k}  {verdict}{weak}")
            for code, rank in ranks.items():
                where = f"rank {rank}" if rank is not None else "NOT EMBEDDED / not in catalog"
                print(f"  expected {code:<10} {where}")
            top = ", ".join(f"{code} ({sim:.3f})" for code, sim in ranking[:SHOW_TOP])
            print(f"  top {SHOW_TOP}: {top}")

    averaged = [(r, rr) for item, r, rr in scored if not item.get("expected_weakness")]
    if not averaged:
        print("\nno items scored (mark items verified, or pass --include-drafts)")
        return 1
    recall_avg = sum(r for r, _ in averaged) / len(averaged)
    mrr = sum(rr for _, rr in averaged) / len(averaged)
    passed = sum(1 for r, _ in averaged if r == 1)
    print(
        f"\nbaseline over {len(averaged)} items: Recall@k {recall_avg:.3f}, "
        f"MRR {mrr:.3f}, fully passed {passed}/{len(averaged)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

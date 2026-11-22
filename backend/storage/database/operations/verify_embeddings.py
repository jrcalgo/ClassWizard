"""Read-only checks that text_chunks embeddings are complete and searchable.

Gate G5 in the semantic-search spec: every chunk has a 384-dimension,
unit-length vector, and the HNSW index exists. Then a few spot searches
print their top results for a person to judge. Nothing is written.

Run inside the backend container:
    docker compose exec backend python3 -m backend.storage.database.verify_embeddings
Exit code 0 = all checks passed, 1 = at least one failed.
"""

from __future__ import annotations

import os
import sys

from ai.nlp.embeddings.sentence_transformer import EMBEDDING_DIM, encode
from backend.storage.database.pgvector import search_text_chunks

SPOT_QUERIES = [
    ("relational database design and SQL", "course"),
    ("machine learning and neural networks", "course"),
    ("software developer", "occupation"),
    ("analyzing data with statistics", "occupation"),
]


def main() -> int:
    import psycopg

    failures = []
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        # 1. Coverage: every chunk of every source type has a vector.
        rows = conn.execute(
            """
            SELECT source_type, count(*) AS total, count(embedding) AS embedded
            FROM text_chunks GROUP BY source_type ORDER BY source_type
            """
        ).fetchall()
        print("coverage:")
        for source_type, total, embedded in rows:
            print(f"  {source_type:<11} {embedded}/{total}")
            if embedded != total:
                failures.append(f"{source_type}: {total - embedded} rows without a vector")
        if not rows:
            failures.append("text_chunks is empty")

        # 2. Dimensions: every vector has exactly 384 numbers.
        dims = conn.execute(
            "SELECT DISTINCT vector_dims(embedding) FROM text_chunks WHERE embedding IS NOT NULL"
        ).fetchall()
        dims = sorted(d for (d,) in dims)
        print(f"dimensions: {dims}")
        if dims and dims != [EMBEDDING_DIM]:
            failures.append(f"unexpected dimensions {dims}, expected [{EMBEDDING_DIM}]")

        # 3. Length: normalized vectors have length 1 (small float error allowed).
        lo, hi = conn.execute(
            """
            SELECT min(vector_norm(embedding)), max(vector_norm(embedding))
            FROM text_chunks WHERE embedding IS NOT NULL
            """
        ).fetchone()
        if lo is not None:
            print(f"vector length: min {lo:.4f}, max {hi:.4f}")
            if abs(lo - 1) > 1e-3 or abs(hi - 1) > 1e-3:
                failures.append("vectors are not unit length")

        # 4. Index: the HNSW cosine index exists.
        index = conn.execute(
            "SELECT 1 FROM pg_indexes WHERE indexname = 'text_chunks_embedding_hnsw'"
        ).fetchone()
        print(f"hnsw index: {'present' if index else 'MISSING'}")
        if not index:
            failures.append("text_chunks_embedding_hnsw index missing")

        # 5. Spot searches: printed for a person to judge, not scored.
        for query, source_type in SPOT_QUERIES:
            vector = encode([query])[0]
            hits = search_text_chunks(conn, vector, top_k=5, source_type=source_type)
            print(f"\n{query!r} ({source_type}):")
            for hit in hits:
                print(f"  {hit['similarity']:.3f}  {hit['chunk_text'][:90]}")

    if failures:
        print("\nFAILED:\n  " + "\n  ".join(failures))
        return 1
    print("\nall checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())

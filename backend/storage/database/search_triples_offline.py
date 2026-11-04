"""Standalone semantic search over syllabus triples using precomputed embeddings.

Runs completely offline using valid_triples_with_embeddings.json.
Does NOT require a database connection.

Usage:
    python backend/storage/database/search_triples_offline.py "machine learning prerequisites"
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from sentence_transformers import SentenceTransformer

REPO_ROOT = Path(__file__).resolve().parents[3]
JSON_PATH = REPO_ROOT / "data" / "uncc-courses" / "syllabi" / "valid_triples_with_embeddings.json"
MODEL_NAME = "all-MiniLM-L6-v2"


def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


def search_offline(query: str, top_k: int = 5, predicate_filter: str | None = None) -> list[dict]:
    with JSON_PATH.open(encoding="utf-8") as fh:
        records = json.load(fh)

    model = SentenceTransformer(MODEL_NAME, local_files_only=True)
    query_emb = model.encode(query).tolist()

    results = []
    for r in records:
        if predicate_filter and r.get("predicate") != predicate_filter:
            continue
        sim = cosine_similarity(query_emb, r["embedding"])
        results.append({
            "triple_id": r.get("triple_id"),
            "subject": r.get("subject"),
            "predicate": r.get("predicate"),
            "object": r.get("object"),
            "confidence": r.get("confidence"),
            "evidence": r.get("evidence"),
            "filename": r.get("filename"),
            "similarity": round(sim, 4),
        })

    results.sort(key=lambda x: x["similarity"], reverse=True)
    return results[:top_k]


def main():
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "relational database design and sql"
    print(f"Query: {query!r}\n")
    matches = search_offline(query, top_k=5)
    for i, m in enumerate(matches, 1):
        print(f"{i}. [Similarity: {m['similarity']:.4f}]")
        print(f"   Triple: {m['subject']} --[{m['predicate']}]--> {m['object']}")
        print(f"   Evidence: {m['evidence']}")
        print(f"   Source file: {m['filename']} (Confidence: {m['confidence']})")
        print()


if __name__ == "__main__":
    main()


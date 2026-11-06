"""Shared sentence-embedding encoder for ClassWizard.

Every vector stored in Postgres (text_chunks, syllabus_triples) and every
query vector computed at search time must come from the same model, or the
cosine similarities between them are meaningless. This module is the one
place that names the model and produces vectors, so the ingest step and the
live search path cannot drift apart.

The model is loaded lazily, once per process. Inside the backend image it is
read from the build-time cache in HF_HOME, so no network access is needed.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Sequence

MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384  # must match vector(384) in backend/schema.sql


@lru_cache(maxsize=1)
def get_model():
    """Load the sentence-transformers model once and reuse it."""
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(MODEL_NAME)


def encode(texts: Sequence[str], batch_size: int = 64) -> list[list[float]]:
    """Encode texts into unit-length 384-dimensional vectors.

    normalize_embeddings=True makes every vector length 1, so cosine
    similarity equals the dot product and pgvector's <=> distance is
    consistent no matter which code path produced the vector.
    """
    if not texts:
        return []
    vectors = get_model().encode(
        list(texts),
        batch_size=batch_size,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    if vectors.ndim != 2 or vectors.shape[1] != EMBEDDING_DIM:
        raise RuntimeError(
            f"{MODEL_NAME} returned shape {vectors.shape}; expected (n, {EMBEDDING_DIM})"
        )
    return vectors.tolist()


def to_pgvector(vector: Sequence[float]) -> str:
    """Format a vector as pgvector's text input, e.g. '[0.1,-0.2,...]'."""
    return "[" + ",".join(repr(float(x)) for x in vector) + "]"

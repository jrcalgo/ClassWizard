"""pgvector database operations for semantic search across text_chunks and syllabus_triples."""

from __future__ import annotations

import os
from typing import Any, Optional


DEFAULT_DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://classwizard:classwizard@127.0.0.1:5432/classwizard",
)


def search_text_chunks(
    conn,
    query_vector: list[float] | str,
    top_k: int = 5,
    source_type: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Search text_chunks using cosine distance with pgvector.

    Parameters
    ----------
    conn : psycopg.Connection
        Active database connection.
    query_vector : list[float] or str
        Query embedding vector (384 dimensions).
    top_k : int
        Maximum results to return.
    source_type : str, optional
        Filter by 'course', 'occupation', or 'skill'.
    """
    vec_str = str(query_vector) if isinstance(query_vector, list) else query_vector
    conditions = ["embedding IS NOT NULL"]
    params: list[Any] = [vec_str]

    if source_type:
        conditions.append("source_type = %s")
        params.append(source_type)

    where_clause = " AND ".join(conditions)
    params.extend([vec_str, top_k])

    sql = f"""
        SELECT
            source_type,
            source_key,
            chunk_text,
            metadata,
            1 - (embedding <=> %s::vector) AS similarity
        FROM text_chunks
        WHERE {where_clause}
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """
    rows = conn.execute(sql, params).fetchall()
    return [
        {
            "source_type": r[0],
            "source_key": r[1],
            "chunk_text": r[2],
            "metadata": r[3],
            "similarity": float(r[4]),
        }
        for r in rows
    ]


def search_syllabus_triples(
    conn,
    query_vector: list[float] | str,
    top_k: int = 5,
    predicate: Optional[str] = None,
    filename: Optional[str] = None,
    level: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Search syllabus_triples using cosine distance with pgvector.

    Parameters
    ----------
    conn : psycopg.Connection
        Active database connection.
    query_vector : list[float] or str
        Query embedding vector (384 dimensions).
    top_k : int
        Maximum results to return.
    predicate : str, optional
        Filter by predicate, e.g. 'covers', 'prerequisite_for', 'has_objective'.
    filename : str, optional
        Filter by source PDF filename.
    level : str, optional
        'undergraduate' (course numbers below 5000) or 'graduate', read from the filename.
    """
    vec_str = str(query_vector) if isinstance(query_vector, list) else query_vector
    conditions = ["embedding IS NOT NULL"]
    params: list[Any] = [vec_str]

    if predicate:
        conditions.append("predicate = %s")
        params.append(predicate)
    if filename:
        conditions.append("filename = %s")
        params.append(filename)
    if level in ("undergraduate", "graduate"):
        conditions.append("filename ~ %s")
        params.append(r"_[0-4]\d{3}" if level == "undergraduate" else r"_[5-9]\d{3}")

    where_clause = " AND ".join(conditions)
    params.extend([vec_str, top_k])

    sql = f"""
        SELECT
            triple_id,
            subject,
            subject_type,
            predicate,
            object,
            object_type,
            confidence,
            evidence,
            filename,
            page_num,
            section_heading,
            1 - (embedding <=> %s::vector) AS similarity
        FROM syllabus_triples
        WHERE {where_clause}
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """
    rows = conn.execute(sql, params).fetchall()
    cols = [
        "triple_id", "subject", "subject_type", "predicate",
        "object", "object_type", "confidence", "evidence",
        "filename", "page_num", "section_heading", "similarity",
    ]
    return [dict(zip(cols, (r[0], r[1], r[2], r[3], r[4], r[5], float(r[6]), r[7], r[8], r[9], r[10], float(r[11])))) for r in rows]


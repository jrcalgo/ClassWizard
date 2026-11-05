"""Generate sentence embeddings for syllabus triples and prepare SQL & database import.

Input:
    data/uncc-courses/syllabi/valid_triples_for_postgres.csv

Outputs:
    data/uncc-courses/syllabi/valid_triples_with_embeddings.json
    data/uncc-courses/syllabi/valid_triples_inserts.sql

Can also import directly into Postgres if DATABASE_URL is accessible.
"""

from __future__ import annotations

import csv
import json
import os
import sys
from pathlib import Path
from sentence_transformers import SentenceTransformer

REPO_ROOT = Path(__file__).resolve().parents[3]
INPUT_CSV = REPO_ROOT / "data" / "uncc-courses" / "syllabi" / "valid_triples_for_postgres.csv"
OUTPUT_JSON = REPO_ROOT / "data" / "uncc-courses" / "syllabi" / "valid_triples_with_embeddings.json"
OUTPUT_SQL = REPO_ROOT / "data" / "uncc-courses" / "syllabi" / "valid_triples_inserts.sql"
SCHEMA_SQL = REPO_ROOT / "backend" / "syllabus_triples_schema.sql"

MODEL_NAME = "all-MiniLM-L6-v2"


def build_embed_text(row: dict) -> str:
    subject = row.get("subject", "").strip()
    predicate = row.get("predicate", "").strip().replace("_", " ")
    obj = row.get("object", "").strip()
    evidence = row.get("evidence", "").strip()
    triple_sentence = f"{subject} {predicate} {obj}"
    if evidence and evidence.lower() != triple_sentence.lower():
        return f"{triple_sentence}. {evidence}"
    return triple_sentence


def escape_sql_str(val: str | None) -> str:
    if val is None or val == "":
        return "NULL"
    escaped = val.replace("'", "''")
    return f"'{escaped}'"


def escape_sql_num(val: str | None, default: str = "NULL") -> str:
    if val is None or str(val).strip() == "":
        return default
    try:
        float(val)
        return str(val).strip()
    except ValueError:
        return default


def main():
    print(f"Reading {INPUT_CSV} ...")
    with INPUT_CSV.open(newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    print(f"Found {len(rows)} triples.")

    print(f"Loading embedding model '{MODEL_NAME}' ...")
    model = SentenceTransformer(MODEL_NAME, local_files_only=True)

    texts = [build_embed_text(r) for r in rows]
    print(f"Encoding {len(texts)} texts into 384-dimensional embeddings ...")
    embeddings = model.encode(texts, show_progress_bar=True, batch_size=64)

    # 1. Save JSON with embeddings
    records = []
    for row, emb in zip(rows, embeddings):
        rec = dict(row)
        rec["embedding"] = emb.tolist()
        rec["embed_text"] = build_embed_text(row)
        records.append(rec)

    with OUTPUT_JSON.open("w", encoding="utf-8") as fh:
        json.dump(records, fh, indent=2)
    print(f"Saved JSON with embeddings to {OUTPUT_JSON}")

    # 2. Generate SQL file
    print(f"Generating SQL file {OUTPUT_SQL} ...")
    sql_lines = [
        "-- Auto-generated syllabus triples with pgvector embeddings",
        "-- Model: " + MODEL_NAME + " (384-dimensional vectors)",
        "",
    ]
    # Include schema creation
    if SCHEMA_SQL.is_file():
        sql_lines.append(SCHEMA_SQL.read_text(encoding="utf-8"))
        sql_lines.append("")

    sql_lines.append("BEGIN;")
    sql_lines.append("DELETE FROM syllabus_triples;")

    for rec in records:
        emb_str = "[" + ",".join(f"{x:.6f}" for x in rec["embedding"]) + "]"
        line = (
            f"INSERT INTO syllabus_triples ("
            f"triple_id, subject, subject_type, subject_canonical_id, "
            f"predicate, object, object_type, object_canonical_id, "
            f"confidence, evidence, filename, page_num, section_heading, embedding"
            f") VALUES ("
            f"{escape_sql_str(rec.get('triple_id'))}, "
            f"{escape_sql_str(rec.get('subject'))}, "
            f"{escape_sql_str(rec.get('subject_type'))}, "
            f"{escape_sql_str(rec.get('subject_canonical_id'))}, "
            f"{escape_sql_str(rec.get('predicate'))}, "
            f"{escape_sql_str(rec.get('object'))}, "
            f"{escape_sql_str(rec.get('object_type'))}, "
            f"{escape_sql_str(rec.get('object_canonical_id'))}, "
            f"{escape_sql_num(rec.get('confidence'), '0.9')}, "
            f"{escape_sql_str(rec.get('evidence'))}, "
            f"{escape_sql_str(rec.get('filename'))}, "
            f"{escape_sql_num(rec.get('page_num'))}, "
            f"{escape_sql_str(rec.get('section_heading'))}, "
            f"'{emb_str}'::vector"
            f");"
        )
        sql_lines.append(line)

    sql_lines.append("COMMIT;")
    sql_lines.append("")

    with OUTPUT_SQL.open("w", encoding="utf-8") as fh:
        fh.write("\n".join(sql_lines))
    print(f"Saved SQL script ({len(records)} INSERTs) to {OUTPUT_SQL}")

    # 3. Optional: direct DB connection if available
    db_url = os.environ.get("DATABASE_URL")
    if db_url:
        try:
            import psycopg
            print(f"Attempting direct PostgreSQL import via {db_url} ...")
            with psycopg.connect(db_url) as conn:
                conn.autocommit = True
                conn.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
                with conn.transaction():
                    conn.execute("DELETE FROM syllabus_triples")
                    with conn.cursor() as cur:
                        copy_sql = """
                        COPY syllabus_triples (
                            triple_id, subject, subject_type, subject_canonical_id,
                            predicate, object, object_type, object_canonical_id,
                            confidence, evidence, filename, page_num, section_heading,
                            embedding
                        ) FROM STDIN
                        """
                        with cur.copy(copy_sql) as copy:
                            for rec in records:
                                copy.write_row((
                                    rec.get("triple_id", ""),
                                    rec.get("subject", ""),
                                    rec.get("subject_type", ""),
                                    rec.get("subject_canonical_id") or None,
                                    rec.get("predicate", ""),
                                    rec.get("object", ""),
                                    rec.get("object_type", ""),
                                    rec.get("object_canonical_id") or None,
                                    float(rec.get("confidence") or 0.9),
                                    rec.get("evidence", ""),
                                    rec.get("filename") or None,
                                    int(rec["page_num"]) if rec.get("page_num") else None,
                                    rec.get("section_heading") or None,
                                    str(rec["embedding"]),
                                ))
                print("Successfully loaded into PostgreSQL!")
        except Exception as e:
            print(f"Direct DB import skipped/failed: {e}")


if __name__ == "__main__":
    main()

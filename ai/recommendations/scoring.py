"""Shared scoring release identity; safe to import without Spark."""

# Bump when scoring rules, embeddings, or training behavior change.
SCORING_VERSION = "catalog-hybrid-v1"
INPUTS_SQL = """SELECT COALESCE(string_agg(source || '=' || release, ';' ORDER BY source, release), '')
FROM ingest_runs WHERE left(source, 8) = 'catalog:' OR source IN ('onet', 'syllabi', 'syllabus_records')"""

def release_key(conn):
    return SCORING_VERSION + ":" + conn.execute(INPUTS_SQL).fetchone()[0]

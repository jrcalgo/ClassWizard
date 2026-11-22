"""Shared scoring release identity; safe to import without Spark."""

# Bump when hybrid scoring rules or embeddings change.
SCORING_VERSION = "catalog-hybrid-v1"
INPUTS_SQL = """SELECT COALESCE(string_agg(source || '=' || release, ';' ORDER BY source, release), '')
FROM ingest_runs WHERE left(source, 8) = 'catalog:' OR source IN ('onet', 'syllabi', 'syllabus_records')"""

def release_key(conn):
    return SCORING_VERSION + ":" + conn.execute(INPUTS_SQL).fetchone()[0]

ALS_TRAINING_VERSION = "als-v1-seed42-ranks8,16,32-reg.01,.05,.1-iter10"
BLEND_VERSION = "blend-v1-70-30"
HYBRID_WEIGHT = 0.70


def training_fingerprint(rows):
    """Canonical identities and integer thousandths, independent of provenance."""
    import hashlib
    import json
    from decimal import Decimal, ROUND_HALF_UP
    canonical = sorted((catalog, soc, code, int((Decimal(str(rating)) * 1000)
        .quantize(Decimal('1'), rounding=ROUND_HALF_UP)))
        for catalog, soc, code, rating in rows)
    return hashlib.sha256(json.dumps(canonical, ensure_ascii=False,
        separators=(',', ':')).encode()).hexdigest()


def training_identity(fingerprint):
    return ALS_TRAINING_VERSION + ':' + fingerprint


def marker(conn, source):
    row = conn.execute("SELECT release FROM ingest_runs WHERE source=%s", (source,)).fetchone()
    return row[0] if row else None

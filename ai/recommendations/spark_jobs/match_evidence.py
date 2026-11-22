"""Recover source provenance for the exact concepts used by Spark scoring."""
from pyspark.sql import functions as F
from pyspark.sql.window import Window

from ai.recommendations.spark_jobs.medallion.gold import contributing_matches
from ai.recommendations.spark_jobs.medallion.silver import course_code
from ai.recommendations.spark_jobs.session import term_key

from ai.recommendations.skill_evidence import EVIDENCE_VERSION


def build_match_evidence(concepts, links, career_terms, courses, triples):
    # Match the selected Silver row exactly; never choose a different confidence
    # merely because another source is easier to explain.
    sources = (triples.filter(F.col('predicate') == 'covers')
        .withColumn('course_code', course_code(F.col('subject')))
        .withColumn('term', F.trim('object'))
        .withColumn('term_key', term_key(F.col('object')))
        .withColumn('confidence', F.col('confidence').cast('double')))
    keys = ['course_code', 'term', 'term_key', 'confidence']
    order = Window.partitionBy(*keys).orderBy(
        F.col('triple_id').asc_nulls_last(), F.col('filename').asc_nulls_last(),
        F.col('page_num').asc_nulls_last(), F.col('evidence').asc_nulls_last(),
        F.col('section_heading').asc_nulls_last())
    sources = (sources.withColumn('_source_rank', F.row_number().over(order))
        .filter(F.col('_source_rank') == 1)
        .select(*keys, 'triple_id', 'filename', 'page_num', 'section_heading', 'evidence'))
    selected = concepts.join(sources, keys, 'left')
    matches = contributing_matches(selected, links, career_terms)
    return (matches.join(courses.select('catalog_name', 'course_code', 'n_concepts'), 'course_code')
        .withColumn('contribution', F.col('points') / F.sqrt('n_concepts'))
        .select('catalog_name', 'course_code', 'soc_code', 'term', 'term_key',
                'onet_term', 'career_term', 'kind', 'confidence', 'similarity',
                'weight', 'points', 'contribution', 'triple_id', 'filename',
                'page_num', 'section_heading', 'evidence'))


COLUMNS = ['id', 'catalog_name', 'course_code', 'soc_code', 'concept', 'concept_key',
           'career_term', 'career_term_key', 'kind', 'confidence', 'similarity',
           'career_weight', 'points', 'contribution', 'multiplicity', 'triple_id',
           'filename', 'page_num', 'section_heading', 'source_text']


def publication_rows(raw):
    """Collapse identical contributions without losing their scoring multiplicity."""
    raw = raw.withColumn('page_num', F.col('page_num').cast('int'))
    keys = [c for c in raw.columns if c not in ('points', 'contribution')]
    grouped = raw.groupBy(*keys).agg(F.sum('points').alias('points'),
        F.sum('contribution').alias('contribution'), F.count('*').alias('multiplicity'))
    identity = F.to_json(F.struct(*[F.col(c) for c in sorted(keys)]), options={'ignoreNullFields':'false'})
    return (grouped.withColumn('id', F.concat(F.lit('skill:'), F.sha2(identity, 256)))
        .withColumnRenamed('term', 'concept').withColumnRenamed('term_key', 'concept_key')
        .withColumnRenamed('onet_term', 'career_term_key').withColumnRenamed('weight', 'career_weight')
        .withColumnRenamed('evidence', 'source_text').withColumn('page_num', F.col('page_num').cast('int'))
        .select(*COLUMNS))


def validate_aggregates(raw, ratings):
    """Require evidence to reproduce the saved scoring inputs, not just new matches."""
    keys = ['catalog_name', 'course_code', 'soc_code']
    derived = raw.groupBy(*keys).agg(F.sum('contribution').alias('derived_term_score'),
                                   F.count('*').alias('derived_count'))
    compared = derived.join(ratings.select(*keys, 'term_score', 'n_matches')
        .withColumn('_rating_present', F.lit(True)), keys, 'full')
    invalid = compared.filter(
        F.col('_rating_present').isNull() |
        (F.coalesce(F.col('derived_count'), F.lit(0)) != F.col('n_matches')) |
        (F.abs(F.coalesce(F.col('derived_term_score'), F.lit(0.0)) -
               F.coalesce(F.col('term_score'), F.lit(0.0))) > .000050001))
    if invalid.limit(1).count():
        raise ValueError('Evidence does not reproduce saved term aggregates; compatible artifacts required')


def score_batch(conn):
    from ai.recommendations.scoring import release_key
    row = conn.execute("SELECT release, loaded_at FROM ingest_runs WHERE source='spark_hybrid'").fetchone()
    if not row or row[0] != release_key(conn):
        raise ValueError('Current published scores required; no training was started')
    return row


def publish_exports(conn, evidence_dir, predictions_dir, expected_batch):
    """Validate exports and replace evidence only, in the caller's transaction."""
    from ai.recommendations.skill_evidence import SCHEMA_SQL
    SCORE_COLUMNS = 'catalog_name, soc_code, course_code, hybrid_rating'
    conn.execute(SCHEMA_SQL)
    conn.execute('LOCK TABLE ingest_runs IN SHARE ROW EXCLUSIVE MODE')
    if score_batch(conn) != expected_batch:
        raise ValueError('Score publication changed during evidence build; retry evidence-only export')
    conn.execute('CREATE TEMP TABLE match_stage (LIKE course_career_match_evidence INCLUDING ALL) ON COMMIT DROP')
    conn.execute('CREATE TEMP TABLE match_score_stage (LIKE course_career_scores INCLUDING ALL) ON COMMIT DROP')
    for directory, table, columns in ((evidence_dir, 'match_stage', ', '.join(COLUMNS)),
                                      (predictions_dir, 'match_score_stage', SCORE_COLUMNS)):
        with conn.cursor() as cur:
            with cur.copy(f'COPY {table} ({columns}) FROM STDIN WITH (FORMAT csv)') as copy:
                for path in sorted(directory.glob('part-*.csv')):
                    with path.open('rb') as handle:
                        while chunk := handle.read(1024 * 1024):
                            copy.write(chunk)
    different = conn.execute('''SELECT EXISTS (
        (SELECT catalog_name,soc_code,course_code,hybrid_rating FROM match_score_stage EXCEPT SELECT catalog_name,soc_code,course_code,hybrid_rating FROM course_career_scores)
        UNION ALL (SELECT catalog_name,soc_code,course_code,hybrid_rating FROM course_career_scores EXCEPT SELECT catalog_name,soc_code,course_code,hybrid_rating FROM match_score_stage))''').fetchone()[0]
    if different:
        raise ValueError('Saved predictions differ from published scores; incompatible artifacts')
    # Normalized float32 dot products can exceed 1 by a few ulps. Preserve
    # the original scoring values rather than clamping or rejecting them.
    invalid = conn.execute('''SELECT EXISTS (SELECT 1 FROM match_stage m
        LEFT JOIN course_career_scores s USING(catalog_name, soc_code, course_code)
        WHERE s.course_code IS NULL OR multiplicity < 1
        OR confidence NOT BETWEEN 0 AND 1 OR similarity NOT BETWEEN 0 AND 1.00001
        OR career_weight NOT BETWEEN 0 AND 1 OR points < 0 OR contribution < 0
        OR abs(points-confidence*similarity*career_weight*multiplicity) > 1e-8*greatest(1,abs(points))
        OR points IN ('NaN'::float8,'Infinity'::float8,'-Infinity'::float8)
        OR contribution IN ('NaN'::float8,'Infinity'::float8,'-Infinity'::float8)
        OR btrim(concept)='' OR btrim(career_term)='')''').fetchone()[0]
    if invalid:
        raise ValueError('Invalid match evidence; previous evidence retained')
    # Traceable source records must exist and agree with the exported statement.
    bad_sources = conn.execute('''SELECT EXISTS (SELECT 1 FROM match_stage m
        WHERE m.triple_id IS NOT NULL AND NOT EXISTS (
          SELECT 1 FROM syllabus_triples t WHERE t.triple_id=m.triple_id
          AND t.filename IS NOT DISTINCT FROM m.filename
          AND coalesce(t.evidence,'')=coalesce(m.source_text,'')
          AND t.predicate='covers' AND btrim(t.object)=m.concept
          AND upper(btrim(regexp_replace(t.subject, '[[:space:]_]+', ' ', 'g')))=m.course_code
          AND t.confidence=m.confidence::numeric(3,2)
          AND t.page_num IS NOT DISTINCT FROM m.page_num
          AND coalesce(t.section_heading,'')=coalesce(m.section_heading,'')))''').fetchone()[0]
    if bad_sources:
        raise ValueError('Unverifiable source reference; previous evidence retained')
    conn.execute('DELETE FROM course_career_match_evidence')
    conn.execute('INSERT INTO course_career_match_evidence SELECT * FROM match_stage')
    count = conn.execute('SELECT count(*) FROM match_stage').fetchone()[0]
    conn.execute('DELETE FROM course_career_match_publication')
    conn.execute('''INSERT INTO course_career_match_publication
        (evidence_version, score_release, score_published_at, row_count)
        VALUES (%s,%s,%s,%s)''', (EVIDENCE_VERSION, *expected_batch, count))
    return count


def run(spark):
    """Export and publish evidence using compatible artifacts; never fit a model."""
    import json
    import os
    import psycopg
    from ai.recommendations.scoring import SCORING_VERSION
    from ai.recommendations.spark_jobs.session import LAKE_DIR, read_table, write_table
    SCORE_COLUMNS = 'catalog_name, soc_code, course_code, hybrid_rating'
    print('Evidence-only: validating saved manifests and score publication', flush=True)
    with psycopg.connect(os.environ['DATABASE_URL']) as conn:
        batch = score_batch(conn)
    expected = {'release': batch[0], 'scoring_version': SCORING_VERSION}
    for stage in ('bronze', 'silver', 'gold'):
        path = LAKE_DIR / f'{stage}_manifest.json'
        if not path.exists() or json.loads(path.read_text()) != expected:
            raise ValueError(f'Compatible {stage} artifacts required; no training was started')
    print('Reconstructing contributions from existing artifacts; no embeddings or ALS', flush=True)
    read = lambda layer, table: read_table(spark, layer, table)
    raw = build_match_evidence(read('silver','course_concepts'), read('gold','term_links'),
        read('gold','career_terms'), read('silver','courses'), read('bronze','syllabus_triples')).cache()
    try:
        validate_aggregates(raw, read('gold','ratings'))
        print('Saved aggregate validation passed; exporting source-linked evidence', flush=True)
        evidence = write_table(publication_rows(raw), 'gold', 'match_evidence')
        directory = LAKE_DIR / 'export' / 'match_evidence'
        predictions_dir = LAKE_DIR / 'export' / 'match_evidence_scores'
        evidence.write.mode('overwrite').option('escape', '"').csv(str(directory))
        read('gold','ratings').selectExpr('catalog_name','soc_code','course_code','rating AS hybrid_rating') \
            .write.mode('overwrite').csv(str(predictions_dir))
        print('Validating source references and publishing evidence atomically', flush=True)
        with psycopg.connect(os.environ['DATABASE_URL']) as conn:
            count = publish_exports(conn, directory, predictions_dir, batch)
        print(f'Published {count:,} source-linked contributions ({EVIDENCE_VERSION}); scores unchanged')
    finally:
        raw.unpersist()

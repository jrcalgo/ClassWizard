"""Version and selection contract for cited Spark skill evidence (no Spark imports)."""
EVIDENCE_VERSION = 'skill-matches-v1'
MIN_CONFIDENCE = .80
MIN_SIMILARITY = .70
MAX_MATCH_ITEMS = 3
MAX_MATCHES_PER_COURSE = 2

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS course_career_match_evidence (
  id text PRIMARY KEY,
  catalog_name text NOT NULL, course_code text NOT NULL, soc_code text NOT NULL,
  concept text NOT NULL, concept_key text NOT NULL, career_term text NOT NULL,
  career_term_key text NOT NULL, kind text NOT NULL,
  confidence double precision NOT NULL, similarity double precision NOT NULL,
  career_weight double precision NOT NULL, points double precision NOT NULL,
  contribution double precision NOT NULL, multiplicity bigint NOT NULL,
  triple_id text, filename text, page_num integer, section_heading text, source_text text
);
CREATE INDEX IF NOT EXISTS course_career_match_lookup
  ON course_career_match_evidence (catalog_name, course_code, soc_code, contribution DESC);
CREATE TABLE IF NOT EXISTS course_career_match_publication (
  singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
  evidence_version text NOT NULL, score_release text NOT NULL,
  score_published_at timestamptz NOT NULL, row_count bigint NOT NULL,
  published_at timestamptz NOT NULL DEFAULT now()
);
"""


def select_match_items(rows, course_order, career_order, titles, clip):
    """Round-robin course/career pairs before taking another match for a pair."""
    from collections import defaultdict
    pairs = defaultdict(list)
    seen = set()
    for row in rows:
        (identifier, code, soc, concept, career_term, kind, confidence, similarity,
         contribution, triple_id, filename, page, heading, source_text) = row
        if (confidence < MIN_CONFIDENCE or similarity < MIN_SIMILARITY or
                not (filename or '').strip() or not (source_text or '').strip() or
                not (triple_id or '').strip()):
            continue
        duplicate = (code, soc, ' '.join(source_text.split()), career_term.casefold())
        if duplicate in seen:
            continue
        seen.add(duplicate)
        place = filename + (f', page {page}' if page is not None else '')
        method = 'exact technology-name match' if kind == 'technology' and similarity == 1 else 'computed semantic match'
        title = titles.get(soc, soc)
        pairs[(code, soc)].append({
            'id': identifier, 'kind': 'skill_match', 'course_code': code, 'soc_code': soc,
            'label': f'{code} → {title}: {career_term}',
            'concept': concept, 'career_term': career_term, 'match_type': method,
            'provenance': {'triple_id': triple_id, 'filename': filename, 'page_num': page,
                           'section_heading': heading, 'evidence_version': EVIDENCE_VERSION},
            'text': (f'{code}; selected career: {title}. Recorded syllabus evidence ({place}): '
                     f'"{clip(source_text)}". Extracted syllabus concept: {clip(concept)}. '
                     f'Computed connection to O*NET {kind} '
                     f'"{career_term}" ({method}). This match contributes to the '
                     'skill-coverage component; it does not fully explain the final hybrid rating '
                     'or prove that the syllabus explicitly names this career skill.')})
    selected, course_counts = [], defaultdict(int)
    for level in range(MAX_MATCHES_PER_COURSE):
        for code in course_order:
            for soc in career_order:
                values = pairs.get((code, soc), [])
                if level < len(values) and course_counts[code] < MAX_MATCHES_PER_COURSE:
                    selected.append(values[level])
                    course_counts[code] += 1
                    if len(selected) == MAX_MATCH_ITEMS:
                        return selected
    return selected


def retrieve_match_items(conn, catalog, course_order, career_order, titles, clip):
    """Read only current, associated evidence in the explanation's DB snapshot."""
    from ai.recommendations.scoring import SCORING_VERSION, INPUTS_SQL
    if not course_order or not career_order:
        return []
    # Rolling upgrades can serve normal RAG before the new tables are initialized.
    available = conn.execute("SELECT to_regclass('course_career_match_publication')").fetchone()[0]
    if available is None:
        return []
    rows = conn.execute('''SELECT m.id, m.course_code, m.soc_code, m.concept,
        m.career_term, m.kind, m.confidence, m.similarity, m.contribution,
        m.triple_id, m.filename, m.page_num, m.section_heading, m.source_text
        FROM course_career_match_evidence m
        JOIN course_career_match_publication p ON p.singleton
        JOIN ingest_runs r ON r.source='spark_als' AND r.release=p.score_release
          AND r.loaded_at=p.score_published_at
        WHERE p.evidence_version=%s AND p.score_release=%s || ':' || (''' + INPUTS_SQL + ''')
          AND m.catalog_name=%s AND m.course_code=ANY(%s) AND m.soc_code=ANY(%s)
          AND m.confidence >= %s AND m.similarity >= %s
          AND btrim(coalesce(m.filename,''))<>'' AND btrim(coalesce(m.source_text,''))<>''
        ORDER BY m.contribution DESC, m.id''',
        (EVIDENCE_VERSION, SCORING_VERSION, catalog, course_order, career_order,
         MIN_CONFIDENCE, MIN_SIMILARITY)).fetchall()
    return select_match_items(rows, course_order, career_order, titles, clip)


def merge_match_items(items, matches, named, limit):
    """Protect named-course facts; reserve match slots before optional discoveries."""
    protected = [item for item in items if item['id'] in named or
                 item['id'] in {f'catalog:{code}' for code in named}]
    optional = [item for item in items if item not in protected]
    protected = protected[:limit]
    matches = matches[:max(0, limit-len(protected))]
    return (protected + matches + optional)[:limit]


def publication_current(conn):
    """Evidence may legitimately be empty; freshness is independent of score validity."""
    from ai.recommendations.scoring import release_key
    if conn.execute("SELECT to_regclass('course_career_match_publication')").fetchone()[0] is None:
        return False
    row = conn.execute('''SELECT p.evidence_version, p.score_release, p.row_count,
        (SELECT count(*) FROM course_career_match_evidence)
        FROM course_career_match_publication p JOIN ingest_runs r
          ON r.source='spark_als' AND r.release=p.score_release
          AND r.loaded_at=p.score_published_at''').fetchone()
    return bool(row and row[0] == EVIDENCE_VERSION and row[1] == release_key(conn) and row[2] == row[3])

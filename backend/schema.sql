-- Relational catalog, program, and O*NET tables, plus one text chunk per
-- course, occupation, and skill name. Chunks are inserted without vectors;
-- embed_text_chunks() in postgres.py fills text_chunks.embedding afterwards.
-- Its HNSW cosine index is created right after the text_chunks table.

CREATE TABLE IF NOT EXISTS ingest_runs (
  source text NOT NULL,
  release text NOT NULL,
  loaded_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (source, release)
);

CREATE TABLE IF NOT EXISTS courses (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  catalog_name text NOT NULL,
  code text NOT NULL,
  subject text NOT NULL,
  number text NOT NULL,
  title text NOT NULL,
  section text,
  description text NOT NULL DEFAULT '',
  credit_min integer,
  credit_max integer,
  credit_raw text,
  prerequisite_raw text,
  corequisite_raw text,
  pre_or_corequisite_raw text,
  restriction_raw text,
  UNIQUE (catalog_name, code)
);
-- Added after the first release; existing databases get the column here.
ALTER TABLE courses ADD COLUMN IF NOT EXISTS restriction_raw text;

CREATE TABLE IF NOT EXISTS course_links (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  catalog_name text NOT NULL,
  course_code text NOT NULL,
  target_code text NOT NULL,
  kind text NOT NULL,
  timing text,
  evidence text,
  advisory_only boolean NOT NULL DEFAULT false,
  target_resolved boolean
);

CREATE INDEX IF NOT EXISTS course_links_course_code_idx
  ON course_links (catalog_name, course_code);

CREATE TABLE IF NOT EXISTS programs (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name text NOT NULL UNIQUE,
  min_gpa numeric(4, 2),
  credit_requirement integer
);

CREATE TABLE IF NOT EXISTS program_courses (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  program_name text NOT NULL,
  course_code text,
  course_title text NOT NULL,
  credits integer
);

CREATE INDEX IF NOT EXISTS program_courses_program_name_idx
  ON program_courses (program_name);

CREATE TABLE IF NOT EXISTS occupations (
  soc_code text PRIMARY KEY,
  title text NOT NULL,
  description text NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS occupation_skills (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  soc_code text NOT NULL REFERENCES occupations (soc_code),
  element_id text NOT NULL,
  element_name text NOT NULL,
  scale_id text NOT NULL,
  score numeric NOT NULL
);

CREATE INDEX IF NOT EXISTS occupation_skills_soc_idx
  ON occupation_skills (soc_code);

CREATE TABLE IF NOT EXISTS occupation_knowledge (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  soc_code text NOT NULL REFERENCES occupations (soc_code),
  element_id text NOT NULL,
  element_name text NOT NULL,
  scale_id text NOT NULL,
  score numeric NOT NULL
);

CREATE INDEX IF NOT EXISTS occupation_knowledge_soc_idx
  ON occupation_knowledge (soc_code);

CREATE TABLE IF NOT EXISTS occupation_education (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  soc_code text NOT NULL REFERENCES occupations (soc_code),
  element_id text NOT NULL,
  category text NOT NULL,
  percentage numeric NOT NULL
);

CREATE TABLE IF NOT EXISTS occupation_technologies (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  soc_code text NOT NULL REFERENCES occupations (soc_code),
  name text NOT NULL,
  hot_technology boolean NOT NULL
);

CREATE TABLE IF NOT EXISTS skill_terms (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name text NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS text_chunks (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  source_type text NOT NULL,
  source_key text NOT NULL,
  chunk_text text NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  embedding vector(384),
  UNIQUE (source_type, source_key)
);

-- Rows without a vector are simply left out of the index; each UPDATE that
-- fills a vector adds that row to it.
CREATE INDEX IF NOT EXISTS text_chunks_embedding_hnsw
  ON text_chunks USING hnsw (embedding vector_cosine_ops);


CREATE TABLE IF NOT EXISTS syllabus_triples (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  triple_id text NOT NULL,
  subject text NOT NULL,
  subject_type text NOT NULL,
  subject_canonical_id text,
  predicate text NOT NULL,
  object text NOT NULL,
  object_type text NOT NULL,
  object_canonical_id text,
  confidence numeric(3, 2) NOT NULL DEFAULT 0.9,
  evidence text NOT NULL DEFAULT '',
  filename text,
  page_num integer,
  section_heading text,
  embedding vector(384),
  UNIQUE (triple_id, filename)
);

CREATE INDEX IF NOT EXISTS syllabus_triples_subject_idx
  ON syllabus_triples (subject);

CREATE INDEX IF NOT EXISTS syllabus_triples_predicate_idx
  ON syllabus_triples (predicate);

CREATE INDEX IF NOT EXISTS syllabus_triples_object_idx
  ON syllabus_triples (object);

CREATE INDEX IF NOT EXISTS syllabus_triples_filename_idx
  ON syllabus_triples (filename);

CREATE INDEX IF NOT EXISTS syllabus_triples_embedding_hnsw
  ON syllabus_triples USING hnsw (embedding vector_cosine_ops);


-- Career x catalog course scores written by Spark (ALS). Empty until the pipeline runs.
-- als_score is the ALS prediction; hybrid_rating is the 0-5 rating it was trained on.
CREATE TABLE IF NOT EXISTS course_career_scores (
  catalog_name text NOT NULL,
  soc_code text NOT NULL,
  course_code text NOT NULL,
  als_score double precision,
  normalized_als_score double precision,
  blended_rating double precision,
  hybrid_rating real NOT NULL,
  PRIMARY KEY (catalog_name, soc_code, course_code)
);


-- Structured syllabus records (data/_datasets/uncc-courses/syllabi/syllabus-records.zip),
-- one per syllabus file. Units and concepts may be LLM-inferred (inferred = true).
-- Course and objective text is also embedded in text_chunks
-- (source_type 'syllabus_course' and 'syllabus_objective').
CREATE TABLE IF NOT EXISTS syllabus_courses (
  course_code text PRIMARY KEY,
  title text,
  description text,
  level text NOT NULL,
  prerequisites text,
  cross_listed text[] NOT NULL DEFAULT '{}',
  source_file text NOT NULL
);

CREATE TABLE IF NOT EXISTS syllabus_units (
  course_code text NOT NULL,
  unit_number integer NOT NULL,
  title text NOT NULL,
  inferred boolean NOT NULL,
  PRIMARY KEY (course_code, unit_number)
);

CREATE TABLE IF NOT EXISTS syllabus_concepts (
  course_code text NOT NULL,
  unit_number integer NOT NULL,
  label text NOT NULL
);

CREATE INDEX IF NOT EXISTS syllabus_concepts_course_idx
  ON syllabus_concepts (course_code);

CREATE TABLE IF NOT EXISTS syllabus_objectives (
  course_code text NOT NULL,
  objective_id text NOT NULL,
  text text NOT NULL,
  bloom text,
  PRIMARY KEY (course_code, objective_id)
);

-- Course codes named in a syllabus's prerequisite text.
CREATE TABLE IF NOT EXISTS syllabus_prerequisites (
  course_code text NOT NULL,
  target_code text NOT NULL,
  PRIMARY KEY (course_code, target_code)
);

-- Cited contributions to the published Spark score batch.

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

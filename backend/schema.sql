-- Relational catalog, program, and O*NET tables, plus one text chunk per
-- course, occupation, and skill name. Embeddings stay null until a later job.
-- After vectors exist, index cosine search with:
-- CREATE INDEX text_chunks_embedding_hnsw
--   ON text_chunks USING hnsw (embedding vector_cosine_ops);

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
  UNIQUE (catalog_name, code)
);

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

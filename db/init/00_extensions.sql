-- Runs first, once, when the database volume is created.
-- pgvector ships in the image but has to be enabled per database.
CREATE EXTENSION IF NOT EXISTS vector;

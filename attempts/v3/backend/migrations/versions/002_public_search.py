"""Public search and scalable vector retrieval; current small corpus uses exact search."""
from alembic import op

revision='002'
down_revision='001'

def upgrade():
    op.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm')
    op.execute("CREATE INDEX ix_courses_search ON courses USING gin(lower(code||' '||title) gin_trgm_ops)")
    op.execute("CREATE INDEX ix_courses_review ON courses(version,(payload->'rule'->>'kind'))")
    op.execute('CREATE INDEX ix_embeddings_identity ON embeddings(model,content_hash)')
    op.execute("CREATE INDEX ix_embeddings_hnsw ON embeddings USING hnsw(embedding vector_cosine_ops) WITH (m=16,ef_construction=128)")

def downgrade():
    for name in ['ix_embeddings_hnsw','ix_embeddings_identity','ix_courses_review','ix_courses_search']:
        op.execute('DROP INDEX IF EXISTS '+name)

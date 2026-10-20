"""Public-data schema and embedding store."""
from alembic import op
from classwizard.db import Base

revision = '001'
down_revision = None

def upgrade():
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')
    Base.metadata.create_all(op.get_bind())
    op.execute('CREATE UNIQUE INDEX one_active_dataset ON datasets (active) WHERE active = true')
    op.execute('''CREATE TABLE embeddings (
        id text PRIMARY KEY, version text NOT NULL REFERENCES datasets(id),
        entity_id text NOT NULL, content_hash text NOT NULL, model text NOT NULL,
        content text NOT NULL, evidence jsonb NOT NULL, embedding vector(384) NOT NULL,
        UNIQUE(version, entity_id, content_hash, model))''')
    op.execute('CREATE INDEX ix_embeddings_version ON embeddings(version)')

def downgrade():
    op.execute('DROP TABLE embeddings')
    Base.metadata.drop_all(op.get_bind())

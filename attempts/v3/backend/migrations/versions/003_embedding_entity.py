"""Indexed public course/skill chunk lookup."""
from alembic import op
revision='003'
down_revision='002'
def upgrade():
    op.execute('CREATE INDEX ix_embeddings_entity ON embeddings(version,entity_id)')
def downgrade():
    op.execute('DROP INDEX ix_embeddings_entity')

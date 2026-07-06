"""add pgvector extension and daily_log_embeddings table

Revision ID: fa17460add86
Revises: 7766aae7d98a
Create Date: 2026-07-06 18:39:15.344445

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector


# revision identifiers, used by Alembic.
revision: str = 'fa17460add86'
down_revision: Union[str, Sequence[str], None] = '7766aae7d98a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        'daily_log_embeddings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('daily_log_id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('content_text', sa.Text(), nullable=False),
        sa.Column('embedding', Vector(384), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['daily_log_id'], ['daily_logs.id'], ),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('daily_log_id'),
    )
    op.create_index('ix_daily_log_embeddings_project_id', 'daily_log_embeddings', ['project_id'])
    op.execute(
        "CREATE INDEX ix_daily_log_embeddings_embedding_hnsw "
        "ON daily_log_embeddings USING hnsw (embedding vector_cosine_ops)"
    )
    
def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP INDEX IF EXISTS ix_daily_log_embeddings_embedding_hnsw")
    op.drop_index('ix_daily_log_embeddings_project_id', table_name='daily_log_embeddings')
    op.drop_table('daily_log_embeddings')
    op.execute("DROP EXTENSION IF EXISTS vector")

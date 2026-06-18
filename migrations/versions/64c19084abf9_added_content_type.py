"""added content_type

Revision ID: 64c19084abf9
Revises: 6cb574383be3
Create Date: 2026-06-18 20:20:09.366015

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '64c19084abf9'
down_revision: Union[str, Sequence[str], None] = '6cb574383be3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('site_photos', sa.Column('content_type', sa.String(), nullable=False))


def downgrade() -> None:
    op.drop_column('site_photos', 'content_type')
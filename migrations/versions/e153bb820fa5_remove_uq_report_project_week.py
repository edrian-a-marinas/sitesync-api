"""remove_uq_report_project_week

Revision ID: e153bb820fa5
Revises: ec07330d110f
Create Date: 2026-06-29 17:10:12.702296

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e153bb820fa5'
down_revision: Union[str, Sequence[str], None] = 'ec07330d110f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint('uq_report_project_week', 'reports', type_='unique')


def downgrade() -> None:
    """Downgrade schema."""
    op.create_unique_constraint('uq_report_project_week', 'reports', ['project_id', 'week_start'])

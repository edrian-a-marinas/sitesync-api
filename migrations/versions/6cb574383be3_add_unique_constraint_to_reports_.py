"""add unique constraint to reports project_id week_start

Revision ID: 6cb574383be3
Revises: b1cb0ee342e9
Create Date: 2026-06-18 18:15:30.239134

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6cb574383be3'
down_revision: Union[str, Sequence[str], None] = 'b1cb0ee342e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        DELETE FROM reports
        WHERE id NOT IN (
            SELECT MAX(id)
            FROM reports
            GROUP BY project_id, week_start
        )
    """)

    op.create_unique_constraint(
        "uq_report_project_week",
        "reports",
        ["project_id", "week_start"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_report_project_week",
        "reports",
        type_="unique",
    )

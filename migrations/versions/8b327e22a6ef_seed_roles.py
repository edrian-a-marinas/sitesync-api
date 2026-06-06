"""seed_roles

Revision ID: 8b327e22a6ef
Revises: 2a177df8cc41
Create Date: 2026-06-07 01:55:44.539822

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8b327e22a6ef'
down_revision: Union[str, Sequence[str], None] = '2a177df8cc41'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("INSERT INTO roles (name) VALUES ('owner'), ('project_manager'), ('site_worker')")
    


def downgrade() -> None:
    op.execute("DELETE FROM roles WHERE name IN ('owner', 'project_manager', 'site_worker')")
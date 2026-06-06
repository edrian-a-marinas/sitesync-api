"""seed_users

Revision ID: df1a4e1b0d83
Revises: 8b327e22a6ef
Create Date: 2026-06-07 02:33:08.015625

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.core.security import hash_password


# revision identifiers, used by Alembic.
revision: str = 'df1a4e1b0d83'
down_revision: Union[str, Sequence[str], None] = '8b327e22a6ef'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(f"""
        INSERT INTO users (email, password_hash, first_name, last_name, role_id, is_active)
        VALUES
        ('seed.owner@gmail.com', '{hash_password("test1234")}', 'Seed', 'Owner', 1, true),
        ('seed.project_manager@gmail.com', '{hash_password("test1234")}', 'Seed', 'Manager', 2, true)
    """)


def downgrade() -> None:
    op.execute("DELETE FROM users WHERE email IN ('seed.owner@gmail.com', 'seed.project_manager@gmail.com')")

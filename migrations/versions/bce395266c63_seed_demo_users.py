"""seed demo users

Revision ID: bce395266c63
Revises: 0fa617c188fa
Create Date: 2026-07-01 12:54:00.814679

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from app.core.security import hash_password

# revision identifiers, used by Alembic.
revision: str = 'bce395266c63'
down_revision: Union[str, Sequence[str], None] = '0fa617c188fa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # DEMO FEATURE: remove this migration content if demo mode is retired
    op.execute(f"""
        INSERT INTO users (email, password_hash, first_name, last_name, role_id, is_active, is_demo)
        VALUES
        ('demo.owner@sitesync.com', '{hash_password("demo1234")}', 'Demo', 'Owner', 1, true, true),
        ('demo.pm@sitesync.com', '{hash_password("demo1234")}', 'Demo', 'Manager', 2, true, true),
        ('demo.worker@sitesync.com', '{hash_password("demo1234")}', 'Demo', 'Worker', 3, true, true)
    """)


def downgrade() -> None:
    op.execute("DELETE FROM users WHERE email IN ('demo.owner@sitesync.com', 'demo.pm@sitesync.com', 'demo.worker@sitesync.com')")
"""add_performance_indexes

Revision ID: b1cb0ee342e9
Revises: 418410a5b944
Create Date: 2026-06-12 18:58:50.795943

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1cb0ee342e9'
down_revision: Union[str, Sequence[str], None] = '418410a5b944'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_daily_logs_project_id", "daily_logs", ["project_id"])
    op.create_index("ix_materials_daily_log_id", "materials", ["daily_log_id"])
    op.create_index("ix_attendance_daily_log_id", "attendance", ["daily_log_id"])
    op.create_index("ix_attendance_worker_id", "attendance", ["worker_id"])
    op.create_index("ix_incidents_daily_log_id", "incidents", ["daily_log_id"])
    op.create_index("ix_project_assignments_user_id", "project_assignments", ["user_id"])
    op.create_index("ix_worker_assignments_user_id", "worker_assignments", ["user_id"])
    op.create_index("ix_ai_queries_user_id", "ai_queries", ["user_id"])
    op.create_index("ix_ai_queries_created_at", "ai_queries", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_daily_logs_project_id", "daily_logs")
    op.drop_index("ix_materials_daily_log_id", "materials")
    op.drop_index("ix_attendance_daily_log_id", "attendance")
    op.drop_index("ix_attendance_worker_id", "attendance")
    op.drop_index("ix_incidents_daily_log_id", "incidents")
    op.drop_index("ix_project_assignments_user_id", "project_assignments")
    op.drop_index("ix_worker_assignments_user_id", "worker_assignments")
    op.drop_index("ix_ai_queries_user_id", "ai_queries")
    op.drop_index("ix_ai_queries_created_at", "ai_queries")

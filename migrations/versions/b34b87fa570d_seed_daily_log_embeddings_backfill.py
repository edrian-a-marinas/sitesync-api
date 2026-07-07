"""seed daily log embeddings backfill

Revision ID: b34b87fa570d
Revises: fa17460add86
Create Date: 2026-07-07 00:05:59.498390

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sentence_transformers import SentenceTransformer

# revision identifiers, used by Alembic.
revision: str = 'b34b87fa570d'
down_revision: Union[str, Sequence[str], None] = 'fa17460add86'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _build_chunk_text(conn, daily_log_id, log_date, weather, work_accomplished, notes) -> str:
    lines = [
        f"Date: {log_date}",
        f"Weather: {weather or 'Not recorded'}",
        f"Work accomplished: {work_accomplished}",
    ]
    if notes:
        lines.append(f"Notes: {notes}")

    materials = conn.execute(
        sa.text("SELECT name, quantity, unit, unit_cost FROM materials WHERE daily_log_id = :id"),
        {"id": daily_log_id},
    ).fetchall()
    if materials:
        lines.append("Materials used:")
        for m in materials:
            lines.append(f"  - {m.name}: {float(m.quantity)} {m.unit} at ₱{float(m.unit_cost):,.2f} each")

    attendance = conn.execute(
        sa.text("SELECT hours_worked FROM attendance WHERE daily_log_id = :id"),
        {"id": daily_log_id},
    ).fetchall()
    if attendance:
        total_hours = sum(float(a.hours_worked) for a in attendance)
        lines.append(f"Attendance: {len(attendance)} workers, {total_hours:.1f} total hours")

    incidents = conn.execute(
        sa.text("SELECT severity, status, description FROM incidents WHERE daily_log_id = :id"),
        {"id": daily_log_id},
    ).fetchall()
    if incidents:
        lines.append("Incidents:")
        for i in incidents:
            lines.append(f"  - [{i.severity}/{i.status}] {i.description}")

    return "\n".join(lines)


def upgrade() -> None:
    """Backfill embeddings for all existing daily_logs that don't have one yet."""
    conn = op.get_bind()
    model = SentenceTransformer("all-MiniLM-L6-v2")

    daily_logs = conn.execute(
        sa.text(
            """
            SELECT dl.id, dl.project_id, dl.log_date, dl.weather_condition, dl.work_accomplished, dl.notes
            FROM daily_logs dl
            LEFT JOIN daily_log_embeddings dle ON dle.daily_log_id = dl.id
            WHERE dle.id IS NULL
            """
        )
    ).fetchall()

    for row in daily_logs:
        content_text = _build_chunk_text(
            conn, row.id, row.log_date, row.weather_condition, row.work_accomplished, row.notes
        )
        vector = model.encode(content_text, normalize_embeddings=True).tolist()

        conn.execute(
            sa.text(
                """
                INSERT INTO daily_log_embeddings (daily_log_id, project_id, content_text, embedding, created_at)
                VALUES (:daily_log_id, :project_id, :content_text, :embedding, now())
                ON CONFLICT (daily_log_id) DO UPDATE
                SET content_text = EXCLUDED.content_text, embedding = EXCLUDED.embedding
                """
            ),
            {
                "daily_log_id": row.id,
                "project_id": row.project_id,
                "content_text": content_text,
                "embedding": str(vector),
            },
        )


def downgrade() -> None:
    """Remove seeded embeddings (irreversible content-wise, safe to clear table)."""
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM daily_log_embeddings"))

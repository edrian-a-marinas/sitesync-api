"""regenerate_material_costs_realistic

Revision ID: 5df42c512b5f
Revises: b798069fbb4f
Create Date: 2026-06-22 17:47:12.811582

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5df42c512b5f'
down_revision: Union[str, Sequence[str], None] = 'b798069fbb4f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - scale material costs to 30% of project budget."""
    from sqlalchemy import text
    connection = op.get_bind()
    
    # Get all projects with their current material totals
    projects = connection.execute(text("""
        SELECT 
            p.id,
            p.total_budget,
            COALESCE(SUM(m.total_cost), 0) as current_material_total
        FROM projects p
        LEFT JOIN daily_logs dl ON dl.project_id = p.id
        LEFT JOIN materials m ON m.daily_log_id = dl.id
        GROUP BY p.id, p.total_budget
    """)).fetchall()
    
    # For each project, scale materials to 30% of budget
    for project_id, total_budget, current_material_total in projects:
        target_material_total = float(total_budget) * 0.30
        
        if current_material_total > 0:
            scale_factor = target_material_total / float(current_material_total)
            
            # Update unit_cost so the generated total_cost recomputes accordingly
            connection.execute(text("""
                UPDATE materials m
                SET unit_cost = ROUND(unit_cost * :scale_factor, 2)
                WHERE daily_log_id IN (
                    SELECT id FROM daily_logs WHERE project_id = :project_id
                )
            """), {"scale_factor": scale_factor, "project_id": project_id})
        
        connection.commit()

def downgrade() -> None:
    """Downgrade schema - cannot safely reverse material cost scaling without original data."""
    raise RuntimeError(
        "This migration is not reversible: original material costs were overwritten "
        "by scaling to 30% of project budget, and no snapshot/audit data exists."
    )
"""force_budget_overrun_for_ml_training

Revision ID: 9e375583feef
Revises: d108387733e8
Create Date: 2026-06-28 17:42:34.083684

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9e375583feef'
down_revision: Union[str, Sequence[str], None] = 'd108387733e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Push Sta. Mesa and Quezon Avenue over budget via realistic cost escalation:
    - Supplier price hikes mid-project
    - Typhoon damage requiring rework materials
    - Steel shortage causing emergency premium purchases
    - Scope creep on finishing phase
    - Pandacan kept under budget as control project
    """
    op.execute("""
        -- ============================================================
        -- STA. MESA: Full budget overrun (~115% of budget)
        -- Cause: Steel rebar shortage + typhoon rework + scope creep
        -- ============================================================

        -- Phase 1: Steel shortage in mid-2024, emergency supplier at premium
        UPDATE materials
        SET unit_cost = unit_cost * 2.85
        WHERE daily_log_id IN (
            SELECT dl.id FROM daily_logs dl
            JOIN projects p ON p.id = dl.project_id
            WHERE p.name = 'Sta. Mesa Mixed-Use Development'
              AND dl.log_date BETWEEN '2024-07-01' AND '2024-09-30'
        )
        AND name = 'Steel Rebar';

        -- Phase 2: Typhoon Carina rework — cement and gravel bulk reorder
        UPDATE materials
        SET unit_cost = unit_cost * 1.95, quantity = quantity * 1.40
        WHERE daily_log_id IN (
            SELECT dl.id FROM daily_logs dl
            JOIN projects p ON p.id = dl.project_id
            WHERE p.name = 'Sta. Mesa Mixed-Use Development'
              AND dl.log_date BETWEEN '2024-08-01' AND '2024-08-31'
        )
        AND name IN ('Cement', 'Gravel', 'Sand');

        -- Phase 3: Finishing scope creep — client added 2 floors mid-2025
        UPDATE materials
        SET unit_cost = unit_cost * 1.60, quantity = quantity * 1.80
        WHERE daily_log_id IN (
            SELECT dl.id FROM daily_logs dl
            JOIN projects p ON p.id = dl.project_id
            WHERE p.name = 'Sta. Mesa Mixed-Use Development'
              AND dl.log_date BETWEEN '2025-03-01' AND '2026-06-28'
        )
        AND name IN ('Plywood', 'Paint', 'Lumber', 'PVC Pipes', 'Hollow Blocks');

        -- Phase 4: General inflation escalation late project
        UPDATE materials
        SET unit_cost = unit_cost * 1.30
        WHERE daily_log_id IN (
            SELECT dl.id FROM daily_logs dl
            JOIN projects p ON p.id = dl.project_id
            WHERE p.name = 'Sta. Mesa Mixed-Use Development'
              AND dl.log_date BETWEEN '2025-10-01' AND '2026-06-28'
        );

        -- ============================================================
        -- QUEZON AVENUE: Moderate overrun (~108% of budget)
        -- Cause: Delayed foundation discovery of soft soil + re-engineering
        -- ============================================================

        -- Soft soil discovery — foundation had to be deepened, extra materials
        UPDATE materials
        SET unit_cost = unit_cost * 1.75, quantity = quantity * 1.55
        WHERE daily_log_id IN (
            SELECT dl.id FROM daily_logs dl
            JOIN projects p ON p.id = dl.project_id
            WHERE p.name = 'Quezon Avenue Commercial Tower'
              AND dl.log_date BETWEEN '2024-06-01' AND '2024-10-31'
        )
        AND name IN ('Cement', 'Gravel', 'Steel Rebar', 'GI Wire');

        -- Supplier contract dispute — forced spot market purchase at 2x price
        UPDATE materials
        SET unit_cost = unit_cost * 2.10
        WHERE daily_log_id IN (
            SELECT dl.id FROM daily_logs dl
            JOIN projects p ON p.id = dl.project_id
            WHERE p.name = 'Quezon Avenue Commercial Tower'
              AND dl.log_date BETWEEN '2025-01-01' AND '2025-04-30'
        )
        AND name IN ('Steel Rebar', 'Lumber', 'Plywood');

        -- Delayed delivery penalties + rush orders
        UPDATE materials
        SET unit_cost = unit_cost * 1.40
        WHERE daily_log_id IN (
            SELECT dl.id FROM daily_logs dl
            JOIN projects p ON p.id = dl.project_id
            WHERE p.name = 'Quezon Avenue Commercial Tower'
              AND dl.log_date BETWEEN '2025-06-01' AND '2026-06-28'
        );

        -- ============================================================
        -- MARIKINA RIVERBANK: Slight overrun (~102% of budget)
        -- Cause: Flood control work requires more material than estimated
        -- ============================================================

        -- Underestimated concrete volume for flood barriers
        UPDATE materials
        SET quantity = quantity * 2.20, unit_cost = unit_cost * 1.25
        WHERE daily_log_id IN (
            SELECT dl.id FROM daily_logs dl
            JOIN projects p ON p.id = dl.project_id
            WHERE p.name = 'Marikina Riverbank Flood Control'
              AND dl.log_date BETWEEN '2024-01-01' AND '2024-12-31'
        )
        AND name IN ('Cement', 'Gravel', 'Steel Rebar');

        -- Emergency flood event response — unplanned material deployment
        UPDATE materials
        SET unit_cost = unit_cost * 1.80, quantity = quantity * 1.30
        WHERE daily_log_id IN (
            SELECT dl.id FROM daily_logs dl
            JOIN projects p ON p.id = dl.project_id
            WHERE p.name = 'Marikina Riverbank Flood Control'
              AND dl.log_date BETWEEN '2025-08-01' AND '2025-10-31'
        );
    """)


def downgrade() -> None:
    """
    Cannot precisely reverse multiplied values — restore from backup or re-seed.
    This is a one-way data migration for ML training purposes.
    """
    raise NotImplementedError(
        "Downgrade not supported for this migration. "
        "Restore from database backup or re-run full seed."
    )

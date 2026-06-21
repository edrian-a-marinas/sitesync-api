"""seed_pm2_additional_projects

Revision ID: 183263cdcdfe
Revises: 755c774f4332
Create Date: 2026-06-21 18:43:32.252057

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '183263cdcdfe'
down_revision: Union[str, Sequence[str], None] = '755c774f4332'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("""
        INSERT INTO projects (owner_id, name, location, total_budget, start_date, target_end_date, status)
        SELECT id, 'Davao Riverside Residences', 'Riverside, Davao City',
               64000000.00, '2024-09-02', '2026-12-31', 'Active'
        FROM users WHERE email = 'seed.owner@gmail.com';
        INSERT INTO projects (owner_id, name, location, total_budget, start_date, target_end_date, status)
        SELECT id, 'Makati Avenue Office Retrofit', 'Makati Avenue, Makati City',
               41000000.00, '2025-02-10', '2026-12-31', 'Active'
        FROM users WHERE email = 'seed.owner@gmail.com';
        INSERT INTO projects (owner_id, name, location, total_budget, start_date, target_end_date, status)
        SELECT id, 'Marikina Riverbank Flood Control', 'Marikina City',
               29500000.00, '2024-03-04', '2025-08-31', 'Completed'
        FROM users WHERE email = 'seed.owner@gmail.com';
    """)
    op.execute("""
        INSERT INTO project_phases (project_id, name, allocated_budget, status)
        SELECT id, 'Foundation', 15000000.00, 'Completed'
        FROM projects WHERE name = 'Davao Riverside Residences';
        INSERT INTO project_phases (project_id, name, allocated_budget, status)
        SELECT id, 'Structure', 32000000.00, 'In Progress'
        FROM projects WHERE name = 'Davao Riverside Residences';
        INSERT INTO project_phases (project_id, name, allocated_budget, status)
        SELECT id, 'Finishing', 17000000.00, 'Not Started'
        FROM projects WHERE name = 'Davao Riverside Residences';
        INSERT INTO project_phases (project_id, name, allocated_budget, status)
        SELECT id, 'Foundation', 8000000.00, 'Completed'
        FROM projects WHERE name = 'Makati Avenue Office Retrofit';
        INSERT INTO project_phases (project_id, name, allocated_budget, status)
        SELECT id, 'Structure', 21000000.00, 'In Progress'
        FROM projects WHERE name = 'Makati Avenue Office Retrofit';
        INSERT INTO project_phases (project_id, name, allocated_budget, status)
        SELECT id, 'Finishing', 12000000.00, 'Not Started'
        FROM projects WHERE name = 'Makati Avenue Office Retrofit';
        INSERT INTO project_phases (project_id, name, allocated_budget, status)
        SELECT id, 'Foundation', 7000000.00, 'Completed'
        FROM projects WHERE name = 'Marikina Riverbank Flood Control';
        INSERT INTO project_phases (project_id, name, allocated_budget, status)
        SELECT id, 'Structure', 15500000.00, 'Completed'
        FROM projects WHERE name = 'Marikina Riverbank Flood Control';
        INSERT INTO project_phases (project_id, name, allocated_budget, status)
        SELECT id, 'Finishing', 7000000.00, 'Completed'
        FROM projects WHERE name = 'Marikina Riverbank Flood Control';
    """)
    op.execute("""
        INSERT INTO project_assignments (project_id, user_id)
        SELECT p.id, u.id FROM projects p, users u
        WHERE p.name = 'Davao Riverside Residences'
          AND u.email = 'seed.pm2@gmail.com';
        INSERT INTO project_assignments (project_id, user_id)
        SELECT p.id, u.id FROM projects p, users u
        WHERE p.name = 'Makati Avenue Office Retrofit'
          AND u.email = 'seed.pm2@gmail.com';
        INSERT INTO project_assignments (project_id, user_id)
        SELECT p.id, u.id FROM projects p, users u
        WHERE p.name = 'Marikina Riverbank Flood Control'
          AND u.email = 'seed.pm2@gmail.com';
    """)
    op.execute("""
        INSERT INTO worker_assignments (project_id, user_id)
        SELECT p.id, u.id FROM projects p, users u
        WHERE p.name = 'Davao Riverside Residences'
          AND u.email IN ('seed.worker1@gmail.com', 'seed.worker3@gmail.com');
        INSERT INTO worker_assignments (project_id, user_id)
        SELECT p.id, u.id FROM projects p, users u
        WHERE p.name = 'Makati Avenue Office Retrofit'
          AND u.email IN ('seed.worker2@gmail.com', 'seed.worker4@gmail.com');
        INSERT INTO worker_assignments (project_id, user_id)
        SELECT p.id, u.id FROM projects p, users u
        WHERE p.name = 'Marikina Riverbank Flood Control'
          AND u.email IN ('seed.worker2@gmail.com', 'seed.worker5@gmail.com');
    """)
def downgrade() -> None:
    """Downgrade schema."""
    op.execute("""
        DELETE FROM worker_assignments WHERE project_id IN (
            SELECT id FROM projects WHERE name IN (
                'Davao Riverside Residences',
                'Makati Avenue Office Retrofit',
                'Marikina Riverbank Flood Control'
            )
        );
        DELETE FROM project_assignments WHERE project_id IN (
            SELECT id FROM projects WHERE name IN (
                'Davao Riverside Residences',
                'Makati Avenue Office Retrofit',
                'Marikina Riverbank Flood Control'
            )
        );
        DELETE FROM project_phases WHERE project_id IN (
            SELECT id FROM projects WHERE name IN (
                'Davao Riverside Residences',
                'Makati Avenue Office Retrofit',
                'Marikina Riverbank Flood Control'
            )
        );
        DELETE FROM projects WHERE name IN (
            'Davao Riverside Residences',
            'Makati Avenue Office Retrofit',
            'Marikina Riverbank Flood Control'
        );
    """)

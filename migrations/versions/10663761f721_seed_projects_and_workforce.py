"""seed_projects_and_workforce
Revision ID: 10663761f721
Revises: eae5a78be3fc
Create Date: 2026-06-12 12:46:02.123858
"""
from typing import Sequence, Union
from alembic import op
from app.core.security import hash_password

revision: str = '10663761f721'
down_revision: Union[str, Sequence[str], None] = 'eae5a78be3fc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pm2_hash = hash_password("test1234")
    w_hash = hash_password("test1234")

    op.execute(f"""
        INSERT INTO users (email, password_hash, first_name, last_name, role_id, is_active)
        VALUES
        ('seed.pm2@sitesync.com',      '{pm2_hash}', 'Marco',   'Reyes',     2, true),
        ('seed.worker1@sitesync.com',  '{w_hash}',   'Jose',    'Santos',    3, true),
        ('seed.worker2@sitesync.com',  '{w_hash}',   'Ramon',   'Cruz',      3, true),
        ('seed.worker3@sitesync.com',  '{w_hash}',   'Andres',  'Lim',       3, true),
        ('seed.worker4@sitesync.com',  '{w_hash}',   'Eduardo', 'Garcia',    3, true),
        ('seed.worker5@sitesync.com',  '{w_hash}',   'Miguel',  'Dela Cruz', 3, true)
    """)

    op.execute("""
        INSERT INTO projects (owner_id, name, location, total_budget, start_date, target_end_date, status)
        SELECT id, 'Sta. Mesa Mixed-Use Development', 'Sta. Mesa, Manila',
               85000000.00, '2024-01-08', '2026-12-31', 'Active'
        FROM users WHERE email = 'seed.owner@sitesync.com';

        INSERT INTO projects (owner_id, name, location, total_budget, start_date, target_end_date, status)
        SELECT id, 'Quezon Avenue Commercial Tower', 'Quezon Avenue, Quezon City',
               72000000.00, '2024-06-03', '2026-12-31', 'Active'
        FROM users WHERE email = 'seed.owner@sitesync.com';

        INSERT INTO projects (owner_id, name, location, total_budget, start_date, target_end_date, status)
        SELECT id, 'Pandacan Warehouse Complex', 'Pandacan, Manila',
               38000000.00, '2024-01-08', '2025-03-31', 'Completed'
        FROM users WHERE email = 'seed.owner@sitesync.com';
    """)

    op.execute("""
        INSERT INTO project_phases (project_id, name, allocated_budget, status)
        SELECT id, 'Foundation', 20000000.00, 'Completed'
        FROM projects WHERE name = 'Sta. Mesa Mixed-Use Development';

        INSERT INTO project_phases (project_id, name, allocated_budget, status)
        SELECT id, 'Structure', 42000000.00, 'In Progress'
        FROM projects WHERE name = 'Sta. Mesa Mixed-Use Development';

        INSERT INTO project_phases (project_id, name, allocated_budget, status)
        SELECT id, 'Finishing', 18000000.00, 'Not Started'
        FROM projects WHERE name = 'Sta. Mesa Mixed-Use Development';

        INSERT INTO project_phases (project_id, name, allocated_budget, status)
        SELECT id, 'Foundation', 16000000.00, 'Completed'
        FROM projects WHERE name = 'Quezon Avenue Commercial Tower';

        INSERT INTO project_phases (project_id, name, allocated_budget, status)
        SELECT id, 'Structure', 36000000.00, 'In Progress'
        FROM projects WHERE name = 'Quezon Avenue Commercial Tower';

        INSERT INTO project_phases (project_id, name, allocated_budget, status)
        SELECT id, 'Finishing', 16000000.00, 'Not Started'
        FROM projects WHERE name = 'Quezon Avenue Commercial Tower';

        INSERT INTO project_phases (project_id, name, allocated_budget, status)
        SELECT id, 'Foundation', 9000000.00, 'Completed'
        FROM projects WHERE name = 'Pandacan Warehouse Complex';

        INSERT INTO project_phases (project_id, name, allocated_budget, status)
        SELECT id, 'Structure', 19000000.00, 'Completed'
        FROM projects WHERE name = 'Pandacan Warehouse Complex';

        INSERT INTO project_phases (project_id, name, allocated_budget, status)
        SELECT id, 'Finishing', 7500000.00, 'Completed'
        FROM projects WHERE name = 'Pandacan Warehouse Complex';
    """)

    op.execute("""
        INSERT INTO project_assignments (project_id, user_id)
        SELECT p.id, u.id FROM projects p, users u
        WHERE p.name = 'Sta. Mesa Mixed-Use Development'
          AND u.email = 'seed.project_manager@sitesync.com';

        INSERT INTO project_assignments (project_id, user_id)
        SELECT p.id, u.id FROM projects p, users u
        WHERE p.name = 'Pandacan Warehouse Complex'
          AND u.email = 'seed.project_manager@sitesync.com';

        INSERT INTO project_assignments (project_id, user_id)
        SELECT p.id, u.id FROM projects p, users u
        WHERE p.name = 'Quezon Avenue Commercial Tower'
          AND u.email = 'seed.pm2@sitesync.com';
    """)

    op.execute("""
        INSERT INTO worker_assignments (project_id, user_id)
        SELECT p.id, u.id FROM projects p, users u
        WHERE p.name = 'Sta. Mesa Mixed-Use Development'
          AND u.email IN ('seed.worker1@sitesync.com', 'seed.worker2@sitesync.com', 'seed.worker3@sitesync.com');

        INSERT INTO worker_assignments (project_id, user_id)
        SELECT p.id, u.id FROM projects p, users u
        WHERE p.name = 'Quezon Avenue Commercial Tower'
          AND u.email IN ('seed.worker3@sitesync.com', 'seed.worker4@sitesync.com', 'seed.worker5@sitesync.com');

        INSERT INTO worker_assignments (project_id, user_id)
        SELECT p.id, u.id FROM projects p, users u
        WHERE p.name = 'Pandacan Warehouse Complex'
          AND u.email IN ('seed.worker1@sitesync.com', 'seed.worker4@sitesync.com', 'seed.worker5@sitesync.com');
    """)


def downgrade() -> None:
    op.execute("""
        DELETE FROM worker_assignments WHERE project_id IN (
            SELECT id FROM projects WHERE name IN (
                'Sta. Mesa Mixed-Use Development',
                'Quezon Avenue Commercial Tower',
                'Pandacan Warehouse Complex'
            )
        );
        DELETE FROM project_assignments WHERE project_id IN (
            SELECT id FROM projects WHERE name IN (
                'Sta. Mesa Mixed-Use Development',
                'Quezon Avenue Commercial Tower',
                'Pandacan Warehouse Complex'
            )
        );
        DELETE FROM project_phases WHERE project_id IN (
            SELECT id FROM projects WHERE name IN (
                'Sta. Mesa Mixed-Use Development',
                'Quezon Avenue Commercial Tower',
                'Pandacan Warehouse Complex'
            )
        );
        DELETE FROM projects WHERE name IN (
            'Sta. Mesa Mixed-Use Development',
            'Quezon Avenue Commercial Tower',
            'Pandacan Warehouse Complex'
        );
        DELETE FROM users WHERE email IN (
            'seed.pm2@sitesync.com',
            'seed.worker1@sitesync.com', 'seed.worker2@sitesync.com',
            'seed.worker3@sitesync.com', 'seed.worker4@sitesync.com',
            'seed.worker5@sitesync.com'
        );
    """)
"""seed demo project data

Revision ID: 7766aae7d98a
Revises: bce395266c63
Create Date: 2026-07-01 13:38:58.851366

"""
import random
from datetime import date, timedelta
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = '7766aae7d98a'
down_revision: Union[str, Sequence[str], None] = 'bce395266c63'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# DEMO FEATURE: remove this migration file entirely if demo mode is retired
DEMO_OWNER_ID = 31
DEMO_PM_ID = 32
DEMO_WORKER_ID = 33

WEATHER_CONDITIONS = ['Partly Cloudy', 'Rainy', 'Stormy', 'Cloudy', 'Sunny']
WORK_ACCOMPLISHED_SAMPLES = [
    "Continued foundation excavation works",
    "Completed rebar installation for column C-12",
    "Poured concrete for ground floor slab",
    "Installed formworks for beam section B-4",
    "Conducted site clearing and leveling",
    "Completed masonry works for east wing",
    "Installed plumbing rough-ins for 2nd floor",
    "Applied waterproofing on rooftop deck",
    "Completed electrical conduit layout",
    "Conducted structural steel erection",
]
NOTES_SAMPLES = [
    None,
    "No major issues encountered",
    "Minor delay due to material delivery",
    "Coordination meeting held with subcontractor",
    "Weather affected outdoor works",
    None,
]
MATERIALS_CATALOG = [
    ("Lumber", "bd.ft", 45.25),
    ("Steel Rebar", "pc", 811.25),
    ("Hollow Blocks", "pc", 5.31),
    ("Paint", "gal", 126.83),
    ("Sand", "cu.m", 19.79),
    ("PVC Pipes", "length", 80.89),
    ("Plywood", "sheet", 181.16),
]
EQUIPMENT_CATALOG = [
    ("Excavator", "Good"),
    ("Welding Machine", "Good"),
    ("Scaffolding", "Good"),
    ("Compactor", "Good"),
    ("Concrete Mixer", "Needs Repair"),
    ("Dump Truck", "Good"),
]
INCIDENT_SAMPLES = [
    ("Low", "Resolved", "Safety harness not worn by worker"),
    ("Low", "Open", "Concrete mix quality issue"),
    ("Medium", "Open", "Worker reported minor hand injury"),
    ("Medium", "Resolved", "Electrical short circuit on site"),
    ("Low", "Resolved", "Minor equipment malfunction reported"),
]


def _weekdays_with_gaps(start: date, end: date, skip_probability: float = 0.35) -> list[date]:
    random.seed(42)  # deterministic output, safe to re-run in fresh environments
    days = []
    current = start
    while current <= end:
        if current.weekday() < 5 and random.random() > skip_probability:
            days.append(current)
        current += timedelta(days=1)
    return days


def upgrade() -> None:
    bind = op.get_bind()

    # --- 2 demo projects ---------------------------------------------------
    active_project_id = bind.execute(
        sa.text("""
            INSERT INTO projects (owner_id, name, location, total_budget, start_date, target_end_date, status)
            VALUES (:owner_id, 'Cavite Residential Complex', 'Cavite', 45000000.00, '2026-06-20', '2026-11-20', 'Active')
            RETURNING id
        """),
        {"owner_id": DEMO_OWNER_ID},
    ).scalar_one()

    completed_project_id = bind.execute(
        sa.text("""
            INSERT INTO projects (owner_id, name, location, total_budget, start_date, target_end_date, status)
            VALUES (:owner_id, 'Marikina Bridge Rehabilitation', 'Marikina City', 28000000.00, '2026-01-01', '2026-06-20', 'Completed')
            RETURNING id
        """),
        {"owner_id": DEMO_OWNER_ID},
    ).scalar_one()

    # --- Project phases -------------------------------------------------------
    bind.execute(
        sa.text("""
            INSERT INTO project_phases (project_id, name, allocated_budget, status)
            VALUES
            (:active_id, 'Foundation', :active_budget_1, 'Completed'),
            (:active_id, 'Structure', :active_budget_2, 'In Progress'),
            (:active_id, 'Finishing', :active_budget_3, 'Not Started'),
            (:completed_id, 'Foundation', :completed_budget_1, 'Completed'),
            (:completed_id, 'Structure', :completed_budget_2, 'Completed'),
            (:completed_id, 'Finishing', :completed_budget_3, 'Completed')
        """),
        {
            "active_id": active_project_id,
            "active_budget_1": 12000000.00,
            "active_budget_2": 23000000.00,
            "active_budget_3": 10000000.00,
            "completed_id": completed_project_id,
            "completed_budget_1": 8000000.00,
            "completed_budget_2": 14000000.00,
            "completed_budget_3": 6000000.00,
        },
    )

    # --- Assignments ---------------------------------------------------------
    bind.execute(
        sa.text("""
            INSERT INTO project_assignments (project_id, user_id)
            VALUES (:active_id, :pm_id), (:completed_id, :pm_id)
        """),
        {"active_id": active_project_id, "completed_id": completed_project_id, "pm_id": DEMO_PM_ID},
    )
    bind.execute(
        sa.text("""
            INSERT INTO worker_assignments (project_id, user_id)
            VALUES (:active_id, :worker_id)
        """),
        {"active_id": active_project_id, "worker_id": DEMO_WORKER_ID},
    )

    # --- Daily logs ------------------------------------------------------
    active_dates = _weekdays_with_gaps(date(2026, 6, 20), date(2026, 11, 20))
    completed_dates = _weekdays_with_gaps(date(2026, 1, 1), date(2026, 6, 20))

    def insert_daily_logs(project_id: int, dates: list[date]) -> list[int]:
        log_ids = []
        for log_date in dates:
            log_id = bind.execute(
                sa.text("""
                    INSERT INTO daily_logs (project_id, submitted_by, log_date, weather_condition, work_accomplished, notes)
                    VALUES (:project_id, :submitted_by, :log_date, :weather, :work, :note)
                    RETURNING id
                """),
                {
                    "project_id": project_id,
                    "submitted_by": DEMO_PM_ID,
                    "log_date": log_date,
                    "weather": random.choice(WEATHER_CONDITIONS),
                    "work": random.choice(WORK_ACCOMPLISHED_SAMPLES),
                    "note": random.choice(NOTES_SAMPLES),
                },
            ).scalar_one()
            log_ids.append(log_id)
        return log_ids

    active_log_ids = insert_daily_logs(active_project_id, active_dates)
    completed_log_ids = insert_daily_logs(completed_project_id, completed_dates)

    # --- Materials / Equipment (subset of logs, matching real data's irregular pattern) ---
    def insert_materials_equipment(log_ids: list[int]):
        for log_id in log_ids:
            if random.random() < 0.5:
                for name, unit, base_cost in random.sample(MATERIALS_CATALOG, k=random.randint(1, 2)):
                    bind.execute(
                        sa.text("""
                            INSERT INTO materials (daily_log_id, name, quantity, unit, unit_cost)
                            VALUES (:log_id, :name, :quantity, :unit, :unit_cost)
                        """),
                        {
                            "log_id": log_id,
                            "name": name,
                            "quantity": round(random.uniform(20, 100), 2),
                            "unit": unit,
                            "unit_cost": round(base_cost * random.uniform(0.9, 1.1), 2),
                        },
                    )
            if random.random() < 0.35:
                name, condition = random.choice(EQUIPMENT_CATALOG)
                bind.execute(
                    sa.text("""
                        INSERT INTO equipment (daily_log_id, name, quantity, condition)
                        VALUES (:log_id, :name, :quantity, :condition)
                    """),
                    {"log_id": log_id, "name": name, "quantity": random.randint(1, 3), "condition": condition},
                )

    insert_materials_equipment(active_log_ids)
    insert_materials_equipment(completed_log_ids)

    # --- Attendance (demo worker, Active project only — matches worker_assignments scope) ---
    for log_id in active_log_ids:
        if random.random() < 0.8:
            bind.execute(
                sa.text("""
                    INSERT INTO attendance (daily_log_id, worker_id, hours_worked)
                    VALUES (:log_id, :worker_id, :hours)
                """),
                {"log_id": log_id, "worker_id": DEMO_WORKER_ID, "hours": round(random.uniform(4.0, 8.5), 2)},
            )

    # --- AI Queries (hardcoded Q&A pairs, isolated to demo owner) ---
    demo_ai_queries = [
        (
            "highest budget overrun risk",
            "Cavite Residential Complex has the highest budget overrun risk with 42.3% budget_used_percent. "
            "Its actual spend is \u20b119,035,000.00. Its budget is \u20b145,000,000.00.",
            active_project_id,
        ),
        (
            "what equipment do we have?",
            "We have the following equipment: Excavator, Welding Machine, Scaffolding, Compactor, "
            "Concrete Mixer, and Dump Truck.",
            None,
        ),
        (
            "how many incidents are still open?",
            "There are 4 open incidents across your projects, mostly Low severity related to safety "
            "harness compliance and minor equipment issues.",
            None,
        ),
        (
            "what is the material cost trend?",
            "Material costs for Cavite Residential Complex show steady spending on Lumber, Steel Rebar, "
            "and Hollow Blocks, averaging around \u20b145,000 per week.",
            active_project_id,
        ),
        (
            "where is marikina bridge rehabilitation?",
            "Marikina Bridge Rehabilitation is located in Marikina City. It is currently marked as Completed.",
            completed_project_id,
        ),
    ]
    for question, answer, q_project_id in demo_ai_queries:
        bind.execute(
            sa.text("""
                INSERT INTO ai_queries (user_id, project_id, question, answer, status)
                VALUES (:user_id, :project_id, :question, :answer, 'Done')
            """),
            {"user_id": DEMO_OWNER_ID, "project_id": q_project_id, "question": question, "answer": answer},
        )

    # --- Incidents (~7 total, spread across both projects) ---
    all_log_ids = active_log_ids + completed_log_ids
    for log_id in random.sample(all_log_ids, k=min(7, len(all_log_ids))):
        severity, status, description = random.choice(INCIDENT_SAMPLES)
        bind.execute(
            sa.text("""
                INSERT INTO incidents (daily_log_id, reported_by, description, severity, status)
                VALUES (:log_id, :reported_by, :description, :severity, :status)
            """),
            {"log_id": log_id, "reported_by": DEMO_PM_ID, "description": description, "severity": severity, "status": status},
        )


def downgrade() -> None:
    bind = op.get_bind()
    project_ids = bind.execute(
        sa.text("""
            SELECT id FROM projects
            WHERE name IN ('Cavite Residential Complex', 'Marikina Bridge Rehabilitation')
        """)
    ).scalars().all()

    if not project_ids:
        return

    log_ids = bind.execute(
        sa.text("SELECT id FROM daily_logs WHERE project_id = ANY(:project_ids)"),
        {"project_ids": project_ids},
    ).scalars().all()

    if log_ids:
        bind.execute(sa.text("DELETE FROM attendance WHERE daily_log_id = ANY(:log_ids)"), {"log_ids": log_ids})
        bind.execute(sa.text("DELETE FROM materials WHERE daily_log_id = ANY(:log_ids)"), {"log_ids": log_ids})
        bind.execute(sa.text("DELETE FROM equipment WHERE daily_log_id = ANY(:log_ids)"), {"log_ids": log_ids})
        bind.execute(sa.text("DELETE FROM incidents WHERE daily_log_id = ANY(:log_ids)"), {"log_ids": log_ids})
        bind.execute(sa.text("DELETE FROM site_photos WHERE daily_log_id = ANY(:log_ids)"), {"log_ids": log_ids})

    bind.execute(sa.text("DELETE FROM daily_logs WHERE project_id = ANY(:project_ids)"), {"project_ids": project_ids})
    bind.execute(sa.text("DELETE FROM project_assignments WHERE project_id = ANY(:project_ids)"), {"project_ids": project_ids})
    bind.execute(sa.text("DELETE FROM worker_assignments WHERE project_id = ANY(:project_ids)"), {"project_ids": project_ids})
    bind.execute(sa.text("DELETE FROM reports WHERE project_id = ANY(:project_ids)"), {"project_ids": project_ids})
    bind.execute(sa.text("DELETE FROM project_phases WHERE project_id = ANY(:project_ids)"), {"project_ids": project_ids})
    bind.execute(sa.text("DELETE FROM ai_queries WHERE user_id = :demo_owner_id"), {"demo_owner_id": DEMO_OWNER_ID})
    bind.execute(sa.text("DELETE FROM projects WHERE id = ANY(:project_ids)"), {"project_ids": project_ids})
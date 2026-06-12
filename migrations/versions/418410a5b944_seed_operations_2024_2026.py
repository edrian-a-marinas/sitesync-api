"""seed_operations_2024_2026

Revision ID: 418410a5b944
Revises: 479f014141b5
Create Date: 2026-06-12 13:06:21.659027

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = '418410a5b944'
down_revision: Union[str, Sequence[str], None] = '479f014141b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


import random
from datetime import date


# ------------------------------------------------------------------ #
# Config                                                              #
# ------------------------------------------------------------------ #

TYPHOON_MONTHS = {7, 8, 9, 10}

MATERIAL_BASE_COSTS = {
    "Cement":        270.00,
    "Sand":           50.00,
    "Gravel":         60.00,
    "Steel Rebar":   850.00,
    "Lumber":        120.00,
    "Hollow Blocks":  14.00,
    "Paint":         350.00,
    "GI Wire":       180.00,
    "PVC Pipes":     220.00,
    "Plywood":       480.00,
}

MATERIAL_UNITS = {
    "Cement":        "bag",
    "Sand":          "cu.m",
    "Gravel":        "cu.m",
    "Steel Rebar":   "pc",
    "Lumber":        "bd.ft",
    "Hollow Blocks": "pc",
    "Paint":         "gal",
    "GI Wire":       "kg",
    "PVC Pipes":     "length",
    "Plywood":       "sheet",
}

EQUIPMENT_NAMES = [
    "Concrete Mixer", "Scaffolding", "Excavator",
    "Dump Truck", "Welding Machine", "Compactor",
]


def get_material_cost_multiplier(log_date: date) -> float:
    y, m = log_date.year, log_date.month
    if y == 2024 and m in {7, 8, 9}:      # Q3 2024 shortage
        return 1.0 + 0.25 + (0.15 * random.random())  # +25–40%
    if y == 2025 and m in {4, 5, 6}:      # Q2 2025 spike
        return 1.0 + 0.20 + (0.10 * random.random())  # +20–30%
    return 1.0


def get_phase(log_date: date, project_name: str) -> str:
    """Approximate phase based on date for quantity scaling."""
    if "Pandacan" in project_name:
        if log_date < date(2024, 5, 1):
            return "Foundation"
        if log_date < date(2025, 1, 1):
            return "Structure"
        return "Finishing"
    if "Quezon" in project_name:
        if log_date < date(2024, 10, 1):
            return "Foundation"
        if log_date < date(2026, 3, 1):
            return "Structure"
        return "Finishing"
    # Sta. Mesa
    if log_date < date(2024, 6, 1):
        return "Foundation"
    if log_date < date(2026, 6, 1):
        return "Structure"
    return "Finishing"


def get_quantity_multiplier(phase: str) -> float:
    return {"Foundation": 0.8, "Structure": 1.4, "Finishing": 0.7}.get(phase, 1.0)


def get_equipment_condition(log_date: date, project_name: str, rng: random.Random) -> str:
    is_project1 = "Sta. Mesa" in project_name
    year = log_date.year
    if year == 2024:
        weights = [0.85, 0.12, 0.03]
    elif year == 2025:
        weights = [0.65, 0.25, 0.10] if not is_project1 else [0.50, 0.30, 0.20]
    else:
        weights = [0.50, 0.30, 0.20] if not is_project1 else [0.35, 0.30, 0.35]
    return rng.choices(["Good", "Needs Repair", "Broken"], weights=weights)[0]


def upgrade() -> None:
    rng = random.Random(42)

    conn = op.get_bind()

    # Fetch all logs with project info
    logs = conn.execute(text("""
        SELECT dl.id, dl.log_date, dl.project_id, dl.submitted_by,
               p.name AS project_name
        FROM daily_logs dl
        JOIN projects p ON p.id = dl.project_id
        ORDER BY dl.id
    """)).fetchall()

    # Fetch worker assignments per project
    worker_map = {}
    rows = conn.execute(text("""
        SELECT wa.project_id, u.email
        FROM worker_assignments wa
        JOIN users u ON u.id = wa.user_id
    """)).fetchall()
    for row in rows:
        worker_map.setdefault(row.project_id, []).append(row.email)

    # Fetch user id by email
    user_rows = conn.execute(text("SELECT id, email FROM users")).fetchall()
    user_id_map = {r.email: r.id for r in user_rows}

    attendance_rows = []
    material_rows = []
    equipment_rows = []
    incident_rows = []

    for log in logs:
        log_id = log.id
        log_date = log.log_date
        project_id = log.project_id
        project_name = log.project_name
        submitted_by = log.submitted_by

        is_typhoon = log_date.month in TYPHOON_MONTHS
        is_project1 = "Sta. Mesa" in project_name
        is_project2 = "Quezon" in project_name
        is_project3 = "Pandacan" in project_name

        # ---------------------------------------------------------- #
        # Incidents — decide first, affects attendance                #
        # ---------------------------------------------------------- #
        has_incident = False
        incident_severity = None

        if is_project1:
            inc_rate = 0.15
        elif is_project2:
            inc_rate = 0.08
        else:
            inc_rate = 0.06

        if rng.random() < inc_rate:
            has_incident = True
            severity_roll = rng.random()
            if severity_roll < 0.70:
                incident_severity = "Low"
            elif severity_roll < 0.90:
                incident_severity = "Medium"
            else:
                incident_severity = "High"

            year = log_date.year
            if is_project3:
                status = "Resolved"
            elif year == 2024:
                status = "Resolved" if rng.random() < 0.85 else "Open"
            else:
                status = "Resolved" if rng.random() < 0.50 else "Open"

            descriptions = [
                "Worker slipped on wet surface",
                "Minor equipment malfunction reported",
                "Material delivery delayed causing work stoppage",
                "Worker reported minor hand injury",
                "Scaffolding instability detected",
                "Electrical short circuit on site",
                "Concrete mix quality issue",
                "Safety harness not worn by worker",
            ]
            incident_rows.append({
                "log_id": log_id,
                "reported_by": submitted_by,
                "description": rng.choice(descriptions),
                "severity": incident_severity,
                "status": status,
            })

        # ---------------------------------------------------------- #
        # Attendance                                                   #
        # ---------------------------------------------------------- #
        workers = worker_map.get(project_id, [])
        if not workers:
            continue

        # Base count
        if is_project3:
            base_count = rng.randint(2, 3)
        else:
            base_count = rng.randint(2, 4)

        # Drop on high severity incident or typhoon
        if has_incident and incident_severity == "High":
            base_count = max(1, int(base_count * rng.uniform(0.50, 0.70)))
        elif is_typhoon:
            base_count = max(1, int(base_count * 0.75))

        selected_workers = rng.sample(workers, min(base_count, len(workers)))

        for email in selected_workers:
            if is_typhoon or (has_incident and incident_severity == "High"):
                hours = round(rng.uniform(4.0, 6.0), 2)
            else:
                hours = round(rng.uniform(8.0, 10.0), 2)
            attendance_rows.append({
                "log_id": log_id,
                "worker_id": user_id_map[email],
                "hours": hours,
            })

        # ---------------------------------------------------------- #
        # Materials                                                    #
        # ---------------------------------------------------------- #
        phase = get_phase(log_date, project_name)
        qty_mult = get_quantity_multiplier(phase)
        cost_mult = get_material_cost_multiplier(log_date)

        # Budget overrun logic for Project 1
        if is_project1 and log_date >= date(2025, 6, 1):
            cost_mult *= 1.15  # extra spend pushes over budget

        material_count = rng.randint(2, 4)
        chosen_materials = rng.sample(list(MATERIAL_BASE_COSTS.keys()), material_count)

        for mat in chosen_materials:
            # Scale quantities to produce realistic budget consumption
            if is_project1:
                base_qty = rng.uniform(80.0, 200.0) * qty_mult
            elif is_project2:
                base_qty = rng.uniform(60.0, 150.0) * qty_mult
            else:
                base_qty = rng.uniform(50.0, 120.0) * qty_mult
            unit_cost = round(MATERIAL_BASE_COSTS[mat] * cost_mult * rng.uniform(0.95, 1.05), 2)
            material_rows.append({
                "log_id": log_id,
                "name": mat,
                "quantity": round(base_qty, 2),
                "unit": MATERIAL_UNITS[mat],
                "unit_cost": unit_cost,
            })

        # ---------------------------------------------------------- #
        # Equipment — 60% of logs                                     #
        # ---------------------------------------------------------- #
        if rng.random() < 0.60:
            equip_count = rng.randint(1, 2)
            chosen_equip = rng.sample(EQUIPMENT_NAMES, equip_count)
            for eq in chosen_equip:
                equipment_rows.append({
                    "log_id": log_id,
                    "name": eq,
                    "quantity": rng.randint(1, 3),
                    "condition": get_equipment_condition(log_date, project_name, rng),
                })

    # ---------------------------------------------------------- #
    # Bulk insert — batches of 100                               #
    # ---------------------------------------------------------- #
    def insert_batch(table, rows, value_fn, batch_size=100):
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i + batch_size]
            values = ", ".join([value_fn(r) for r in batch])
            op.execute(f"INSERT INTO {table} VALUES {values}")

    insert_batch(
        "attendance (daily_log_id, worker_id, hours_worked)",
        attendance_rows,
        lambda r: f"({r['log_id']}, {r['worker_id']}, {r['hours']})",
    )

    insert_batch(
        "materials (daily_log_id, name, quantity, unit, unit_cost)",
        material_rows,
        lambda r: f"({r['log_id']}, '{r['name']}', {r['quantity']}, '{r['unit']}', {r['unit_cost']})",
    )

    insert_batch(
        "equipment (daily_log_id, name, quantity, condition)",
        equipment_rows,
        lambda r: f"({r['log_id']}, '{r['name']}', {r['quantity']}, '{r['condition']}')",
    )

    insert_batch(
        "incidents (daily_log_id, reported_by, description, severity, status)",
        incident_rows,
        lambda r: f"({r['log_id']}, {r['reported_by']}, '{r['description']}', '{r['severity']}', '{r['status']}')",
    )


def downgrade() -> None:
    op.execute("""
        DELETE FROM incidents WHERE daily_log_id IN (
            SELECT id FROM daily_logs WHERE project_id IN (
                SELECT id FROM projects WHERE name IN (
                    'Sta. Mesa Mixed-Use Development',
                    'Quezon Avenue Commercial Tower',
                    'Pandacan Warehouse Complex'
                )
            )
        );
        DELETE FROM equipment WHERE daily_log_id IN (
            SELECT id FROM daily_logs WHERE project_id IN (
                SELECT id FROM projects WHERE name IN (
                    'Sta. Mesa Mixed-Use Development',
                    'Quezon Avenue Commercial Tower',
                    'Pandacan Warehouse Complex'
                )
            )
        );
        DELETE FROM materials WHERE daily_log_id IN (
            SELECT id FROM daily_logs WHERE project_id IN (
                SELECT id FROM projects WHERE name IN (
                    'Sta. Mesa Mixed-Use Development',
                    'Quezon Avenue Commercial Tower',
                    'Pandacan Warehouse Complex'
                )
            )
        );
        DELETE FROM attendance WHERE daily_log_id IN (
            SELECT id FROM daily_logs WHERE project_id IN (
                SELECT id FROM projects WHERE name IN (
                    'Sta. Mesa Mixed-Use Development',
                    'Quezon Avenue Commercial Tower',
                    'Pandacan Warehouse Complex'
                )
            )
        );
    """)
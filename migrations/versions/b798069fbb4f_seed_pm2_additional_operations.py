"""seed_pm2_additional_operations

Revision ID: b798069fbb4f
Revises: f56af50dd18c
Create Date: 2026-06-21 18:47:53.917667

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b798069fbb4f'
down_revision: Union[str, Sequence[str], None] = 'f56af50dd18c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


import random
from datetime import date
from sqlalchemy import text
TYPHOON_MONTHS = {7, 8, 9, 10}
MATERIAL_BASE_COSTS = {
    "Cement": 270.00, "Sand": 50.00, "Gravel": 60.00, "Steel Rebar": 850.00,
    "Lumber": 120.00, "Hollow Blocks": 14.00, "Paint": 350.00,
    "GI Wire": 180.00, "PVC Pipes": 220.00, "Plywood": 480.00,
}
MATERIAL_UNITS = {
    "Cement": "bag", "Sand": "cu.m", "Gravel": "cu.m", "Steel Rebar": "pc",
    "Lumber": "bd.ft", "Hollow Blocks": "pc", "Paint": "gal",
    "GI Wire": "kg", "PVC Pipes": "length", "Plywood": "sheet",
}
EQUIPMENT_NAMES = ["Concrete Mixer", "Scaffolding", "Excavator", "Dump Truck", "Welding Machine", "Compactor"]
NEW_PROJECT_NAMES = ["Davao Riverside Residences", "Makati Avenue Office Retrofit", "Marikina Riverbank Flood Control"]
def get_material_cost_multiplier(log_date: date) -> float:
    y, m = log_date.year, log_date.month
    if y == 2024 and m in {7, 8, 9}:
        return 1.0 + 0.25 + (0.15 * random.random())
    if y == 2025 and m in {4, 5, 6}:
        return 1.0 + 0.20 + (0.10 * random.random())
    return 1.0
def get_phase(log_date: date, project_name: str) -> str:
    if "Marikina" in project_name:
        if log_date < date(2024, 7, 1):
            return "Foundation"
        if log_date < date(2025, 4, 1):
            return "Structure"
        return "Finishing"
    if "Makati" in project_name:
        if log_date < date(2025, 6, 1):
            return "Foundation"
        if log_date < date(2026, 4, 1):
            return "Structure"
        return "Finishing"
    # Davao
    if log_date < date(2025, 1, 1):
        return "Foundation"
    if log_date < date(2026, 4, 1):
        return "Structure"
    return "Finishing"
def get_quantity_multiplier(phase: str) -> float:
    return {"Foundation": 0.8, "Structure": 1.4, "Finishing": 0.7}.get(phase, 1.0)
def get_equipment_condition(log_date: date, rng: random.Random) -> str:
    year = log_date.year
    weights = [0.85, 0.12, 0.03] if year == 2024 else ([0.65, 0.25, 0.10] if year == 2025 else [0.55, 0.30, 0.15])
    return rng.choices(["Good", "Needs Repair", "Broken"], weights=weights)[0]
def upgrade() -> None:
    """Upgrade schema."""
    rng = random.Random(43)
    conn = op.get_bind()
    logs = conn.execute(text("""
        SELECT dl.id, dl.log_date, dl.project_id, dl.submitted_by, p.name AS project_name
        FROM daily_logs dl
        JOIN projects p ON p.id = dl.project_id
        WHERE p.name = ANY(:names)
        ORDER BY dl.id
    """), {"names": NEW_PROJECT_NAMES}).fetchall()
    worker_map = {}
    rows = conn.execute(text("""
        SELECT wa.project_id, u.email
        FROM worker_assignments wa
        JOIN users u ON u.id = wa.user_id
        JOIN projects p ON p.id = wa.project_id
        WHERE p.name = ANY(:names)
    """), {"names": NEW_PROJECT_NAMES}).fetchall()
    for row in rows:
        worker_map.setdefault(row.project_id, []).append(row.email)
    user_rows = conn.execute(text("SELECT id, email FROM users")).fetchall()
    user_id_map = {r.email: r.id for r in user_rows}
    attendance_rows = []
    material_rows = []
    equipment_rows = []
    incident_rows = []
    for log in logs:
        log_id, log_date_, project_id, project_name, submitted_by = log.id, log.log_date, log.project_id, log.project_name, log.submitted_by
        is_typhoon = log_date_.month in TYPHOON_MONTHS
        # Incidents
        has_incident = False
        incident_severity = None
        inc_rate = 0.10
        if rng.random() < inc_rate:
            has_incident = True
            severity_roll = rng.random()
            incident_severity = "Low" if severity_roll < 0.70 else ("Medium" if severity_roll < 0.90 else "High")
            status = "Resolved" if rng.random() < 0.70 else "Open"
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
                "log_id": log_id, "reported_by": submitted_by,
                "description": rng.choice(descriptions), "severity": incident_severity, "status": status,
            })
        # Attendance
        workers = worker_map.get(project_id, [])
        if not workers:
            continue
        base_count = rng.randint(2, 3)
        if has_incident and incident_severity == "High":
            base_count = max(1, int(base_count * rng.uniform(0.50, 0.70)))
        elif is_typhoon:
            base_count = max(1, int(base_count * 0.75))
        selected_workers = rng.sample(workers, min(base_count, len(workers)))
        for email in selected_workers:
            hours = round(rng.uniform(4.0, 6.0), 2) if (is_typhoon or (has_incident and incident_severity == "High")) else round(rng.uniform(8.0, 10.0), 2)
            attendance_rows.append({"log_id": log_id, "worker_id": user_id_map[email], "hours": hours})
        # Materials
        phase = get_phase(log_date_, project_name)
        qty_mult = get_quantity_multiplier(phase)
        cost_mult = get_material_cost_multiplier(log_date_)
        material_count = rng.randint(2, 4)
        chosen_materials = rng.sample(list(MATERIAL_BASE_COSTS.keys()), material_count)
        for mat in chosen_materials:
            base_qty = rng.uniform(50.0, 130.0) * qty_mult
            unit_cost = round(MATERIAL_BASE_COSTS[mat] * cost_mult * rng.uniform(0.95, 1.05), 2)
            material_rows.append({
                "log_id": log_id, "name": mat, "quantity": round(base_qty, 2),
                "unit": MATERIAL_UNITS[mat], "unit_cost": unit_cost,
            })
        # Equipment — 60% of logs
        if rng.random() < 0.60:
            equip_count = rng.randint(1, 2)
            chosen_equip = rng.sample(EQUIPMENT_NAMES, equip_count)
            for eq in chosen_equip:
                equipment_rows.append({
                    "log_id": log_id, "name": eq, "quantity": rng.randint(1, 3),
                    "condition": get_equipment_condition(log_date_, rng),
                })
    def insert_batch(table, rows, value_fn, batch_size=100):
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i + batch_size]
            values = ", ".join([value_fn(r) for r in batch])
            op.execute(f"INSERT INTO {table} VALUES {values}")
    insert_batch(
        "attendance (daily_log_id, worker_id, hours_worked)", attendance_rows,
        lambda r: f"({r['log_id']}, {r['worker_id']}, {r['hours']})",
    )
    insert_batch(
        "materials (daily_log_id, name, quantity, unit, unit_cost)", material_rows,
        lambda r: f"({r['log_id']}, '{r['name']}', {r['quantity']}, '{r['unit']}', {r['unit_cost']})",
    )
    insert_batch(
        "equipment (daily_log_id, name, quantity, condition)", equipment_rows,
        lambda r: f"({r['log_id']}, '{r['name']}', {r['quantity']}, '{r['condition']}')",
    )
    insert_batch(
        "incidents (daily_log_id, reported_by, description, severity, status)", incident_rows,
        lambda r: f"({r['log_id']}, {r['reported_by']}, '{r['description']}', '{r['severity']}', '{r['status']}')",
    )
def downgrade() -> None:
    """Downgrade schema."""
    op.execute("""
        DELETE FROM incidents WHERE daily_log_id IN (
            SELECT dl.id FROM daily_logs dl JOIN projects p ON p.id = dl.project_id
            WHERE p.name IN ('Davao Riverside Residences', 'Makati Avenue Office Retrofit', 'Marikina Riverbank Flood Control')
        );
        DELETE FROM equipment WHERE daily_log_id IN (
            SELECT dl.id FROM daily_logs dl JOIN projects p ON p.id = dl.project_id
            WHERE p.name IN ('Davao Riverside Residences', 'Makati Avenue Office Retrofit', 'Marikina Riverbank Flood Control')
        );
        DELETE FROM materials WHERE daily_log_id IN (
            SELECT dl.id FROM daily_logs dl JOIN projects p ON p.id = dl.project_id
            WHERE p.name IN ('Davao Riverside Residences', 'Makati Avenue Office Retrofit', 'Marikina Riverbank Flood Control')
        );
        DELETE FROM attendance WHERE daily_log_id IN (
            SELECT dl.id FROM daily_logs dl JOIN projects p ON p.id = dl.project_id
            WHERE p.name IN ('Davao Riverside Residences', 'Makati Avenue Office Retrofit', 'Marikina Riverbank Flood Control')
        );
    """)

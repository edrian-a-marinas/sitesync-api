"""seed_daily_logs_2024_2026

Revision ID: 479f014141b5
Revises: 10663761f721
Create Date: 2026-06-12 13:04:30.048054

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '479f014141b5'
down_revision: Union[str, Sequence[str], None] = '10663761f721'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


import random
from datetime import date, timedelta


# ------------------------------------------------------------------ #
# Helpers                                                             #
# ------------------------------------------------------------------ #

PHILIPPINE_HOLIDAYS = {
    # 2024
    date(2024, 1, 1), date(2024, 4, 9), date(2024, 5, 1),
    date(2024, 6, 12), date(2024, 8, 26), date(2024, 11, 1),
    date(2024, 11, 30), date(2024, 12, 25), date(2024, 12, 30),
    # 2025
    date(2025, 1, 1), date(2025, 4, 9), date(2025, 5, 1),
    date(2025, 6, 12), date(2025, 8, 25), date(2025, 11, 1),
    date(2025, 11, 30), date(2025, 12, 25), date(2025, 12, 30),
    # 2026
    date(2026, 1, 1), date(2026, 4, 9), date(2026, 5, 1),
    date(2026, 6, 12), date(2026, 8, 24), date(2026, 11, 1),
    date(2026, 11, 30), date(2026, 12, 25), date(2026, 12, 30),
}

HOLY_WEEK = {
    # 2024: Mar 28–30
    date(2024, 3, 28), date(2024, 3, 29), date(2024, 3, 30),
    # 2025: Apr 17–19
    date(2025, 4, 17), date(2025, 4, 18), date(2025, 4, 19),
    # 2026: Apr 2–4
    date(2026, 4, 2), date(2026, 4, 3), date(2026, 4, 4),
}

CHRISTMAS_NEW_YEAR = {
    # 2023–2024 turn
    date(2023, 12, 26), date(2023, 12, 27), date(2023, 12, 28),
    date(2023, 12, 29), date(2023, 12, 31),
    date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4), date(2024, 1, 5),
    # 2024–2025 turn
    date(2024, 12, 26), date(2024, 12, 27), date(2024, 12, 28),
    date(2024, 12, 29), date(2024, 12, 31),
    date(2025, 1, 2), date(2025, 1, 3), date(2025, 1, 4), date(2025, 1, 5),
    # 2025–2026 turn
    date(2025, 12, 26), date(2025, 12, 27), date(2025, 12, 28),
    date(2025, 12, 29), date(2025, 12, 31),
    date(2026, 1, 2), date(2026, 1, 3), date(2026, 1, 4), date(2026, 1, 5),
}

SKIP_DAYS = PHILIPPINE_HOLIDAYS | HOLY_WEEK | CHRISTMAS_NEW_YEAR

TYPHOON_MONTHS = {7, 8, 9, 10}

WEATHER_NORMAL = ["Sunny", "Partly Cloudy", "Cloudy"]
WEATHER_TYPHOON = ["Rainy", "Stormy", "Rainy", "Rainy"]  # weighted rainy

WORK_ACCOMPLISHED = [
    "Concrete pouring and curing",
    "Steel rebar installation",
    "Formwork assembly",
    "Masonry and hollow block laying",
    "Scaffolding erection",
    "Excavation and grading",
    "Waterproofing application",
    "Electrical rough-in works",
    "Plumbing rough-in works",
    "Finishing and plastering",
    "Tile installation",
    "Painting and coating",
    "Roof framing and sheathing",
    "Structural steel erection",
    "Site cleanup and debris removal",
]


def is_workday(d: date) -> bool:
    return d.weekday() != 6 and d not in SKIP_DAYS  # no Sundays, no holidays


def should_log(d: date, is_typhoon_month: bool, rng: random.Random) -> bool:
    if is_typhoon_month:
        return rng.random() > 0.30  # 30% fewer logs
    return True


def get_weather(d: date, rng: random.Random) -> str:
    if d.month in TYPHOON_MONTHS:
        return rng.choice(WEATHER_TYPHOON)
    return rng.choice(WEATHER_NORMAL)


def build_logs(
    project_name: str,
    pm_email: str,
    start: date,
    end: date,
    rng: random.Random,
) -> list[dict]:
    logs = []
    current = start
    while current <= end:
        if is_workday(current):
            typhoon = current.month in TYPHOON_MONTHS
            if should_log(current, typhoon, rng):
                logs.append({
                    "project_name": project_name,
                    "pm_email": pm_email,
                    "log_date": current.isoformat(),
                    "weather": get_weather(current, rng),
                    "work_accomplished": rng.choice(WORK_ACCOMPLISHED),
                })
        current += timedelta(days=1)
    return logs


def upgrade() -> None:
    rng = random.Random(42)  # fixed seed for reproducibility

    projects = [
        {
            "name": "Sta. Mesa Mixed-Use Development",
            "pm_email": "seed.project_manager@sitesync.com",
            "start": date(2024, 1, 8),
            "end": date(2026, 6, 30),
        },
        {
            "name": "Quezon Avenue Commercial Tower",
            "pm_email": "seed.pm2@sitesync.com",
            "start": date(2024, 6, 3),
            "end": date(2026, 6, 30),
        },
        {
            "name": "Pandacan Warehouse Complex",
            "pm_email": "seed.project_manager@sitesync.com",
            "start": date(2024, 1, 8),
            "end": date(2025, 3, 31),
        },
    ]

    all_logs = []
    for p in projects:
        all_logs.extend(build_logs(p["name"], p["pm_email"], p["start"], p["end"], rng))

    # Insert in batches of 100
    batch_size = 100
    for i in range(0, len(all_logs), batch_size):
        batch = all_logs[i:i + batch_size]
        values = ", ".join([
            f"""(
                (SELECT id FROM projects WHERE name = '{r["project_name"]}'),
                (SELECT id FROM users WHERE email = '{r["pm_email"]}'),
                '{r["log_date"]}',
                '{r["weather"]}',
                '{r["work_accomplished"]}'
            )"""
            for r in batch
        ])
        op.execute(f"""
            INSERT INTO daily_logs (project_id, submitted_by, log_date, weather_condition, work_accomplished)
            VALUES {values}
        """)


def downgrade() -> None:
    op.execute("""
        DELETE FROM daily_logs WHERE project_id IN (
            SELECT id FROM projects WHERE name IN (
                'Sta. Mesa Mixed-Use Development',
                'Quezon Avenue Commercial Tower',
                'Pandacan Warehouse Complex'
            )
        )
    """)
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def get_budget_overrun_features(db: AsyncSession) -> list[dict]:
    """Extract features for budget overrun classifier — one row per project."""
    rows = await db.execute(
        text("""
        SELECT
            p.id                                                        AS project_id,
            p.name                                                      AS project_name,
            p.status                                                    AS status,
            p.total_budget,
            COALESCE(SUM(m.quantity * m.unit_cost), 0)                  AS total_spent,
            COALESCE(SUM(m.quantity * m.unit_cost), 0)
                / NULLIF(p.total_budget, 0)                             AS spend_rate,
            COUNT(DISTINCT i.id)                                        AS incident_count,
            COUNT(DISTINCT dl.id)                                       AS log_count,
            EXTRACT(DAY FROM NOW() - p.start_date)                      AS days_elapsed,
            COUNT(DISTINCT CASE
                WHEN EXTRACT(MONTH FROM dl.log_date) IN (7,8,9,10)
                THEN dl.id END) * 1.0
                / NULLIF(COUNT(DISTINCT dl.id), 0)                      AS typhoon_log_ratio,
            CASE WHEN COALESCE(SUM(m.quantity * m.unit_cost), 0)
                      > p.total_budget THEN 1 ELSE 0 END                AS is_over_budget
        FROM projects p
        LEFT JOIN daily_logs dl ON dl.project_id = p.id
        LEFT JOIN materials m   ON m.daily_log_id = dl.id
        LEFT JOIN incidents i   ON i.daily_log_id = dl.id
        GROUP BY p.id, p.name, p.total_budget, p.start_date
    """)
    )
    result = rows.mappings().all()
    logger.info(f"ML_FEATURES | budget_overrun | rows={len(result)}")
    return [dict(r) for r in result]


async def get_delay_risk_features(db: AsyncSession) -> list[dict]:
    """Extract features for delay risk scorer — one row per project."""
    rows = await db.execute(
        text("""
        SELECT
            p.id                                                        AS project_id,
            p.name                                                      AS project_name,
            p.status                                                    AS status,
            COUNT(DISTINCT dl.id)                                       AS log_count,
            COALESCE(AVG(a.hours_worked), 0)                            AS avg_hours,
            COUNT(DISTINCT i.id) * 1.0
                / NULLIF(COUNT(DISTINCT dl.id), 0)                      AS incident_rate,
            COUNT(DISTINCT CASE
                WHEN EXTRACT(MONTH FROM dl.log_date) IN (7,8,9,10)
                THEN dl.id END) * 1.0
                / NULLIF(COUNT(DISTINCT dl.id), 0)                      AS typhoon_log_ratio,
            EXTRACT(DAY FROM (NOW() - p.start_date::timestamp))         AS days_elapsed,
            EXTRACT(DAY FROM (p.target_end_date::timestamp - NOW()))    AS days_remaining,
            CASE WHEN p.status = 'Active' THEN 1 ELSE 0 END             AS is_active,
            -- Structure phase slipping: In Progress but >60% of project time elapsed
            CASE WHEN EXISTS (
                SELECT 1 FROM project_phases pp
                WHERE pp.project_id = p.id
                  AND pp.name = 'Structure'
                  AND pp.status = 'In Progress'
                  AND EXTRACT(DAY FROM (NOW() - p.start_date::timestamp))
                      > 0.6 * EXTRACT(DAY FROM (p.target_end_date::timestamp - p.start_date::timestamp))
            ) THEN 1 ELSE 0 END                                         AS structure_slipping
        FROM projects p
        LEFT JOIN daily_logs dl ON dl.project_id = p.id
        LEFT JOIN attendance a  ON a.daily_log_id = dl.id
        LEFT JOIN incidents i   ON i.daily_log_id = dl.id
        GROUP BY p.id, p.name, p.start_date, p.target_end_date, p.status
    """)
    )
    result = rows.mappings().all()
    logger.info(f"ML_FEATURES | delay_risk | rows={len(result)}")
    return [dict(r) for r in result]


async def get_material_forecast_features(db: AsyncSession) -> list[dict]:
    """Extract monthly material spend per project for forecasting."""
    rows = await db.execute(
        text("""
        SELECT
            p.id                                                        AS project_id,
            p.name                                                      AS project_name,
            p.status                                                    AS status,
            EXTRACT(YEAR FROM dl.log_date)                              AS year,
            EXTRACT(MONTH FROM dl.log_date)                             AS month,
            EXTRACT(QUARTER FROM dl.log_date)                           AS quarter,
            COALESCE(SUM(m.quantity * m.unit_cost), 0)                  AS monthly_cost,
            CASE WHEN EXTRACT(MONTH FROM dl.log_date) IN (7,8,9)
                 AND EXTRACT(YEAR FROM dl.log_date) = 2024
                 THEN 1 ELSE 0 END                                      AS q3_2024_spike,
            CASE WHEN EXTRACT(MONTH FROM dl.log_date) IN (4,5,6)
                 AND EXTRACT(YEAR FROM dl.log_date) = 2025
                 THEN 1 ELSE 0 END                                      AS q2_2025_spike,
            CASE WHEN EXTRACT(MONTH FROM dl.log_date) IN (7,8,9,10)
                 THEN 1 ELSE 0 END                                      AS is_typhoon_month
        FROM projects p
        LEFT JOIN daily_logs dl ON dl.project_id = p.id
        LEFT JOIN materials m   ON m.daily_log_id = dl.id
        GROUP BY p.id, p.name, year, month, quarter
        ORDER BY p.id, year, month
    """)
    )
    result = rows.mappings().all()
    logger.info(f"ML_FEATURES | material_forecast | rows={len(result)}")
    return [dict(r) for r in result]

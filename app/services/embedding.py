import logging

from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        logger.info("EMBEDDING | loading model=all-MiniLM-L6-v2")
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def generate_embedding(text: str) -> list[float]:
    model = _get_model()
    vector = model.encode(text, normalize_embeddings=True)
    return vector.tolist()


async def build_daily_log_chunk_text(db, daily_log_id: int) -> str:
    # Imports kept local to the function (not top-level) to avoid circular import risk, since embedding.py is a low-level service that other services will import.
    from sqlalchemy.future import select

    from app.models.attendance import Attendance
    from app.models.daily_log import DailyLog
    from app.models.incident import Incident
    from app.models.material import Material

    daily_log = (await db.execute(select(DailyLog).where(DailyLog.id == daily_log_id))).scalar_one_or_none()
    if not daily_log:
        raise ValueError(f"DailyLog {daily_log_id} not found")

    lines = [
        f"Date: {daily_log.log_date}",
        f"Weather: {daily_log.weather_condition or 'Not recorded'}",
        f"Work accomplished: {daily_log.work_accomplished}",
    ]
    if daily_log.notes:
        lines.append(f"Notes: {daily_log.notes}")

    materials = (await db.execute(select(Material).where(Material.daily_log_id == daily_log_id))).scalars().all()
    if materials:
        lines.append("Materials used:")
        for m in materials:
            lines.append(f"  - {m.name}: {float(m.quantity)} {m.unit} at ₱{float(m.unit_cost):,.2f} each")

    attendance = (await db.execute(select(Attendance).where(Attendance.daily_log_id == daily_log_id))).scalars().all()
    if attendance:
        total_hours = sum(float(a.hours_worked) for a in attendance)
        lines.append(f"Attendance: {len(attendance)} workers, {total_hours:.1f} total hours")

    incidents = (await db.execute(select(Incident).where(Incident.daily_log_id == daily_log_id))).scalars().all()
    if incidents:
        lines.append("Incidents:")
        for i in incidents:
            lines.append(f"  - [{i.severity}/{i.status}] {i.description}")

    return "\n".join(lines)

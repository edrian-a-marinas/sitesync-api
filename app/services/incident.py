import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.incident import Incident
from app.models.user import User
from app.schemas.incident import IncidentCreate, IncidentUpdate

logger = logging.getLogger(__name__)


async def get_incidents(log_id: int, db: AsyncSession) -> list[Incident]:
    result = await db.execute(select(Incident).where(Incident.daily_log_id == log_id))
    return result.scalars().all()


async def create_incident(log_id: int, data: IncidentCreate, current_user: User, db: AsyncSession) -> Incident:
    incident = Incident(**data.model_dump(), daily_log_id=log_id, reported_by=current_user.id)
    db.add(incident)
    await db.commit()
    await db.refresh(incident)
    logger.info(
        f"INCIDENT_CREATE | log_id={log_id} | incident_id={incident.id} | reported_by={current_user.id} | severity={data.severity} | status=success"
    )
    return incident


async def update_incident(log_id: int, incident_id: int, data: IncidentUpdate, current_user: User, db: AsyncSession) -> Incident | None:
    incident = (await db.execute(select(Incident).where(Incident.id == incident_id).where(Incident.daily_log_id == log_id))).scalar_one_or_none()
    if not incident:
        return None
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(incident, field, value)
    await db.commit()
    await db.refresh(incident)
    logger.info(f"INCIDENT_UPDATE | log_id={log_id} | incident_id={incident_id} | updated_by={current_user.id} | status=success")
    return incident

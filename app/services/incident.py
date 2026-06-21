import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.cache import delete_cache
from app.models.incident import Incident
from app.models.project import ProjectAssignment, WorkerAssignment
from app.models.role import Role
from app.models.user import User
from app.schemas.incident import IncidentCreate, IncidentUpdate

logger = logging.getLogger(__name__)


async def _check_manager_assigned(project_id: int, current_user: User, db: AsyncSession) -> bool:
    role = (await db.execute(select(Role).where(Role.id == current_user.role_id))).scalar_one_or_none()
    if role and role.name == "project_manager":
        assigned = (
            await db.execute(
                select(ProjectAssignment).where(ProjectAssignment.project_id == project_id).where(ProjectAssignment.user_id == current_user.id)
            )
        ).scalar_one_or_none()
        if not assigned:
            logger.warning(f"INCIDENT | user_id={current_user.id} | project_id={project_id} | status=failed | reason=manager not assigned to project")
            return False
    return True


async def get_incidents(project_id: int, log_id: int, current_user: User, db: AsyncSession) -> list[Incident]:
    role = (await db.execute(select(Role).where(Role.id == current_user.role_id))).scalar_one_or_none()

    if role and role.name == "site_worker":
        assigned = (
            await db.execute(
                select(WorkerAssignment).where(WorkerAssignment.project_id == project_id).where(WorkerAssignment.user_id == current_user.id)
            )
        ).scalar_one_or_none()
        if not assigned:
            logger.warning(f"INCIDENT_GET | log_id={log_id} | user_id={current_user.id} | status=failed | reason=worker not assigned to project")
            return []

    result = await db.execute(select(Incident).where(Incident.daily_log_id == log_id))
    incidents = result.scalars().all()
    logger.info(f"INCIDENT_GET | log_id={log_id} | user_id={current_user.id} | count={len(incidents)}")
    return incidents


async def create_incident(project_id: int, log_id: int, data: IncidentCreate, current_user: User, db: AsyncSession) -> Incident | None:
    if not await _check_manager_assigned(project_id, current_user, db):
        return None
    incident = Incident(**data.model_dump(), daily_log_id=log_id, reported_by=current_user.id)
    db.add(incident)
    await db.commit()
    await db.refresh(incident)
    await delete_cache(f"dashboard:manager:{project_id}")
    await delete_cache(f"dashboard:manager:aggregate:{current_user.id}")
    await delete_cache("dashboard:owner")
    logger.info(
        f"INCIDENT_CREATE | log_id={log_id} | incident_id={incident.id} | reported_by={current_user.id} | severity={data.severity} | status=success"
    )
    return incident


async def update_incident(
    project_id: int, log_id: int, incident_id: int, data: IncidentUpdate, current_user: User, db: AsyncSession
) -> Incident | None | bool:
    if not await _check_manager_assigned(project_id, current_user, db):
        return False
    incident = (await db.execute(select(Incident).where(Incident.id == incident_id).where(Incident.daily_log_id == log_id))).scalar_one_or_none()
    if not incident:
        logger.warning(
            f"INCIDENT_UPDATE | log_id={log_id} | incident_id={incident_id} | updated_by={current_user.id} | status=failed | reason=not found"
        )
        return None
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(incident, field, value)
    await db.commit()
    await db.refresh(incident)
    await delete_cache(f"dashboard:manager:{project_id}")
    await delete_cache(f"dashboard:manager:aggregate:{current_user.id}")
    await delete_cache("dashboard:owner")
    logger.info(f"INCIDENT_UPDATE | log_id={log_id} | incident_id={incident_id} | updated_by={current_user.id} | status=success")
    return incident

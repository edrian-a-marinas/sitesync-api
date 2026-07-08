import logging

from kombu.exceptions import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.cache import delete_cache, delete_pattern, get_cache, set_cache
from app.models.daily_log import DailyLog
from app.models.incident import Incident
from app.models.project import Project, ProjectAssignment, WorkerAssignment
from app.models.role import Role
from app.models.user import User
from app.schemas.incident import IncidentCreate, IncidentUpdate
from app.services.notification import notify_project_stakeholders
from app.tasks.embedding import generate_daily_log_embedding
from app.tasks.webhook import send_incident_webhook

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

    cache_key = f"incident:{project_id}:{log_id}"
    cached = await get_cache(cache_key)
    if cached is not None:
        logger.info(f"INCIDENT_GET | log_id={log_id} | user_id={current_user.id} | count={len(cached)} | source=cache")
        return [Incident(**item) for item in cached]

    result = await db.execute(select(Incident).where(Incident.daily_log_id == log_id))
    incidents = result.scalars().all()
    logger.info(f"INCIDENT_GET | log_id={log_id} | user_id={current_user.id} | count={len(incidents)} | source=db")

    serialized = [
        {
            "id": i.id,
            "daily_log_id": i.daily_log_id,
            "reported_by": i.reported_by,
            "description": i.description,
            "severity": i.severity,
            "status": i.status,
        }
        for i in incidents
    ]
    await set_cache(cache_key, serialized, ttl=3600)
    return incidents


async def create_incident(project_id: int, log_id: int, data: IncidentCreate, current_user: User, db: AsyncSession) -> Incident | None:
    if not await _check_manager_assigned(project_id, current_user, db):
        return None
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    daily_log = (await db.execute(select(DailyLog).where(DailyLog.id == log_id))).scalar_one_or_none()
    incident = Incident(**data.model_dump(), daily_log_id=log_id, reported_by=current_user.id)
    db.add(incident)
    await db.commit()
    await db.refresh(incident)
    await delete_cache(f"incident:{project_id}:{log_id}")
    await delete_cache(f"dashboard:manager:{project_id}")
    await delete_cache(f"dashboard:manager:aggregate:{current_user.id}")
    await delete_pattern("dashboard:owner:*")
    logger.info(
        f"INCIDENT_CREATE | log_id={log_id} | incident_id={incident.id} | reported_by={current_user.id} | severity={data.severity} | status=success"
    )
    try:
        generate_daily_log_embedding.delay(log_id)
    except OperationalError:
        logger.error(f"EMBEDDING | log_id={log_id} | status=failed | reason=queue unreachable")
    if incident.severity == "High":
        try:
            send_incident_webhook.delay(
                {
                    "event": "incident.logged",
                    "incident_id": incident.id,
                    "project_id": project_id,
                    "daily_log_id": log_id,
                    "severity": incident.severity,
                    "description": incident.description,
                    "reported_by": current_user.id,
                }
            )
        except OperationalError:
            logger.error(f"WEBHOOK | incident_id={incident.id} | status=failed | reason=queue unreachable")

    try:
        await notify_project_stakeholders(
            project_id=project_id,
            type="incident",
            title="Incident Logged",
            message=incident.description,
            data={
                "incident_id": incident.id,
                "daily_log_id": log_id,
                "severity": incident.severity,
                "project_name": project.name if project else None,
                "log_date": daily_log.log_date.isoformat() if daily_log else None,
            },
            db=db,
        )
    except Exception as e:
        logger.error(f"NOTIFICATION | incident_id={incident.id} | status=failed | reason={str(e)}")
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
    await delete_cache(f"incident:{project_id}:{log_id}")
    await delete_cache(f"dashboard:manager:{project_id}")
    await delete_cache(f"dashboard:manager:aggregate:{current_user.id}")
    await delete_pattern("dashboard:owner:*")
    logger.info(f"INCIDENT_UPDATE | log_id={log_id} | incident_id={incident_id} | updated_by={current_user.id} | status=success")
    try:
        generate_daily_log_embedding.delay(log_id)
    except OperationalError:
        logger.error(f"EMBEDDING | log_id={log_id} | status=failed | reason=queue unreachable")
    return incident


async def delete_incident(project_id: int, log_id: int, incident_id: int, current_user: User, db: AsyncSession) -> bool | None:
    if not await _check_manager_assigned(project_id, current_user, db):
        return False
    incident = (await db.execute(select(Incident).where(Incident.id == incident_id).where(Incident.daily_log_id == log_id))).scalar_one_or_none()
    if not incident:
        logger.warning(
            f"INCIDENT_DELETE | log_id={log_id} | incident_id={incident_id} | deleted_by={current_user.id} | status=failed | reason=not found"
        )
        return None
    await db.delete(incident)
    await db.commit()
    await delete_cache(f"incident:{project_id}:{log_id}")
    await delete_cache(f"dashboard:manager:{project_id}")
    await delete_cache(f"dashboard:manager:aggregate:{current_user.id}")
    await delete_pattern("dashboard:owner:*")
    logger.info(f"INCIDENT_DELETE | log_id={log_id} | incident_id={incident_id} | deleted_by={current_user.id} | status=success")
    try:
        generate_daily_log_embedding.delay(log_id)
    except OperationalError:
        logger.error(f"EMBEDDING | log_id={log_id} | status=failed | reason=queue unreachable")
    return True

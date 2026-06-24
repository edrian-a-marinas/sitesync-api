import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.core.cache import delete_cache, delete_pattern, get_cache, set_cache
from app.core.settings import settings
from app.models.project import (
    Project,
    ProjectAssignment,
    ProjectPhase,
    WorkerAssignment,
)
from app.models.role import Role
from app.models.user import User
from app.schemas.project import (
    AssignedUserResponse,
    AssignUserRequest,
    PhaseCreate,
    PhaseResponse,
    PhaseUpdate,
    ProjectCreate,
    ProjectDetailResponse,
    ProjectResponse,
    ProjectUpdate,
)

logger = logging.getLogger(__name__)


PROJECTS_TTL = settings.PROJECTS_TTL


async def get_projects(current_user: User, db: AsyncSession, status: str | None = None) -> list[Project]:
    cache_key = f"projects:user:{current_user.id}:{status or 'all'}"
    cached = await get_cache(cache_key)
    if cached:
        return [Project(**p) for p in cached]
    current_role = (await db.execute(select(Role).where(Role.id == current_user.role_id))).scalar_one_or_none()
    if current_role and current_role.name == "owner":
        query = select(Project)
    else:
        query = (
            select(Project).join(ProjectAssignment, ProjectAssignment.project_id == Project.id).where(ProjectAssignment.user_id == current_user.id)
        )
    if status:
        query = query.where(Project.status == status)
    result = await db.execute(query)
    projects = result.scalars().all()

    await set_cache(cache_key, [ProjectResponse.model_validate(p).model_dump(mode="json") for p in projects], PROJECTS_TTL)
    return projects


async def get_project_by_id(project_id: int, current_user: User, db: AsyncSession) -> Project | None:
    project = (
        await db.execute(
            select(Project)
            .options(
                selectinload(Project.phases),
                selectinload(Project.assignments).selectinload(ProjectAssignment.user),
                selectinload(Project.worker_assignments).selectinload(WorkerAssignment.user),
            )
            .where(Project.id == project_id)
        )
    ).scalar_one_or_none()
    if not project:
        logger.warning(f"PROJECT_GET | project_id={project_id} | user_id={current_user.id} | status=not_found")
        return None
    current_role = (await db.execute(select(Role).where(Role.id == current_user.role_id))).scalar_one_or_none()
    if current_role and current_role.name != "owner":
        assigned = (
            await db.execute(
                select(ProjectAssignment).where(ProjectAssignment.project_id == project_id).where(ProjectAssignment.user_id == current_user.id)
            )
        ).scalar_one_or_none()
        if not assigned:
            logger.warning(f"PROJECT_GET | project_id={project_id} | user_id={current_user.id} | status=access_denied")
            return None

    return ProjectDetailResponse(
        **ProjectDetailResponse.model_validate(project).model_dump(exclude={"managers", "workers", "phases"}),
        phases=[PhaseResponse.model_validate(p) for p in project.phases],
        managers=[AssignedUserResponse.model_validate(a.user) for a in project.assignments],
        workers=[AssignedUserResponse.model_validate(w.user) for w in project.worker_assignments],
    )


async def create_project(data: ProjectCreate, current_user: User, db: AsyncSession) -> Project:
    project = Project(**data.model_dump(), owner_id=current_user.id)
    db.add(project)
    await db.commit()
    await db.refresh(project)
    await delete_pattern("projects:user:*")
    logger.info(f"PROJECT_CREATE | project_id={project.id} | owner_id={current_user.id} | status=success")
    return project


async def update_project(project_id: int, data: ProjectUpdate, current_user: User, db: AsyncSession) -> Project | None:
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not project:
        logger.warning(f"PROJECT_UPDATE | project_id={project_id} | user_id={current_user.id} | status=not_found")
        return None
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(project, field, value)
    await db.commit()
    await db.refresh(project)
    await delete_pattern("projects:user:*")
    await delete_cache(f"dashboard:manager:{project_id}")
    await delete_cache("dashboard:owner")
    logger.info(f"PROJECT_UPDATE | project_id={project_id} | updated_by={current_user.id} | status=success")
    return project


async def delete_project(project_id: int, current_user: User, db: AsyncSession) -> bool:
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not project:
        logger.warning(f"PROJECT_DELETE | project_id={project_id} | user_id={current_user.id} | status=not_found")
        return False
    await db.delete(project)
    await db.commit()
    await delete_pattern("projects:user:*")
    await delete_cache("dashboard:owner")
    logger.info(f"PROJECT_DELETE | project_id={project_id} | deleted_by={current_user.id} | status=success")
    return True


async def assign_manager(project_id: int, data: AssignUserRequest, current_user: User, db: AsyncSession) -> ProjectAssignment | None:
    project = await get_project_by_id(project_id, current_user, db)
    if not project:
        return None

    # Only project managers can be assigned as managers
    manager = (await db.execute(select(User).where(User.id == data.user_id))).scalar_one_or_none()
    manager_role = (await db.execute(select(Role).where(Role.id == manager.role_id))).scalar_one_or_none() if manager else None
    if not manager or not manager_role or manager_role.name != "project_manager":
        logger.warning(
            f"ASSIGN_MANAGER | project_id={project_id} | user_id={data.user_id} | assigned_by={current_user.id} | status=failed | reason=not a project manager"
        )
        return None

    assignment = ProjectAssignment(project_id=project_id, user_id=data.user_id)
    db.add(assignment)
    await db.commit()
    await db.refresh(assignment)
    logger.info(f"ASSIGN_MANAGER | project_id={project_id} | user_id={data.user_id} | assigned_by={current_user.id} | status=success")
    return assignment


async def assign_worker(project_id: int, data: AssignUserRequest, current_user: User, db: AsyncSession) -> WorkerAssignment | None:
    project = await get_project_by_id(project_id, current_user, db)
    if not project:
        return None

    # Only site workers can be assigned as workers
    worker = (await db.execute(select(User).where(User.id == data.user_id))).scalar_one_or_none()
    worker_role = (await db.execute(select(Role).where(Role.id == worker.role_id))).scalar_one_or_none() if worker else None
    if not worker or not worker_role or worker_role.name != "site_worker":
        logger.warning(
            f"ASSIGN_WORKER | project_id={project_id} | user_id={data.user_id} | assigned_by={current_user.id} | status=failed | reason=not a site worker"
        )
        return None

    assignment = WorkerAssignment(project_id=project_id, user_id=data.user_id)
    db.add(assignment)
    await db.commit()
    await db.refresh(assignment)
    logger.info(f"ASSIGN_WORKER | project_id={project_id} | user_id={data.user_id} | assigned_by={current_user.id} | status=success")
    return assignment


async def create_phase(project_id: int, data: PhaseCreate, current_user: User, db: AsyncSession) -> ProjectPhase | None:
    project = await get_project_by_id(project_id, current_user, db)
    if not project:
        return None
    phase = ProjectPhase(**data.model_dump(), project_id=project_id)
    db.add(phase)
    await db.commit()
    await db.refresh(phase)
    logger.info(f"PHASE_CREATE | project_id={project_id} | phase_id={phase.id} | created_by={current_user.id} | status=success")
    return phase


async def update_phase(project_id: int, phase_id: int, data: PhaseUpdate, current_user: User, db: AsyncSession) -> ProjectPhase | None:
    project = await get_project_by_id(project_id, current_user, db)
    if not project:
        return None
    phase = (
        await db.execute(select(ProjectPhase).where(ProjectPhase.id == phase_id).where(ProjectPhase.project_id == project_id))
    ).scalar_one_or_none()
    if not phase:
        logger.warning(f"PHASE_UPDATE | project_id={project_id} | phase_id={phase_id} | user_id={current_user.id} | status=not_found")
        return None
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(phase, field, value)
    await db.commit()
    await db.refresh(phase)
    logger.info(f"PHASE_UPDATE | project_id={project_id} | phase_id={phase_id} | updated_by={current_user.id} | status=success")
    return phase

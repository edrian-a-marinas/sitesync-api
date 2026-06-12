import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.cache import delete_cache, delete_pattern, get_cache, set_cache
from app.models.project import (
    Project,
    ProjectAssignment,
    ProjectPhase,
    WorkerAssignment,
)
from app.models.user import User
from app.schemas.project import (
    AssignUserRequest,
    PhaseCreate,
    PhaseUpdate,
    ProjectCreate,
    ProjectUpdate,
)

logger = logging.getLogger(__name__)


PROJECTS_TTL = 120


async def get_projects(current_user: User, db: AsyncSession) -> list[Project]:
    cache_key = f"projects:user:{current_user.id}"
    cached = await get_cache(cache_key)
    if cached:
        return [Project(**p) for p in cached]

    if current_user.role_id == 1:
        result = await db.execute(select(Project))
        projects = result.scalars().all()
    else:
        # PM — only assigned projects
        result = await db.execute(
            select(Project).join(ProjectAssignment, ProjectAssignment.project_id == Project.id).where(ProjectAssignment.user_id == current_user.id)
        )
        projects = result.scalars().all()

    from app.schemas.project import ProjectResponse
    await set_cache(cache_key, [
        ProjectResponse.model_validate(p).model_dump(mode="json")
        for p in projects
    ], PROJECTS_TTL)
    return projects


async def get_project(project_id: int, current_user: User, db: AsyncSession) -> Project | None:
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not project:
        logger.warning(f"PROJECT_GET | project_id={project_id} | user_id={current_user.id} | status=not_found")
        return None
    if current_user.role_id == 1:
        return project
    # PM — check if assigned
    assigned = (
        await db.execute(
            select(ProjectAssignment).where(ProjectAssignment.project_id == project_id).where(ProjectAssignment.user_id == current_user.id)
        )
    ).scalar_one_or_none()
    if not assigned:
        logger.warning(f"PROJECT_GET | project_id={project_id} | user_id={current_user.id} | status=access_denied")
        return None
    return project


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

async def assign_manager(project_id: int, data: AssignUserRequest, current_user: User, db: AsyncSession) -> ProjectAssignment | None:
    project = await get_project(project_id, current_user, db)
    if not project:
        return None

    # Only project managers can be assigned as managers
    manager = (await db.execute(select(User).where(User.id == data.user_id))).scalar_one_or_none()
    if not manager or manager.role_id != 2:
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
    project = await get_project(project_id, current_user, db)
    if not project:
        return None

    # Only site workers can be assigned as workers
    worker = (await db.execute(select(User).where(User.id == data.user_id))).scalar_one_or_none()
    if not worker or worker.role_id != 3:
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
    project = await get_project(project_id, current_user, db)
    if not project:
        return None
    phase = ProjectPhase(**data.model_dump(), project_id=project_id)
    db.add(phase)
    await db.commit()
    await db.refresh(phase)
    logger.info(f"PHASE_CREATE | project_id={project_id} | phase_id={phase.id} | created_by={current_user.id} | status=success")
    return phase


async def update_phase(project_id: int, phase_id: int, data: PhaseUpdate, current_user: User, db: AsyncSession) -> ProjectPhase | None:
    project = await get_project(project_id, current_user, db)
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

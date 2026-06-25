import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.project import Project, ProjectAssignment, WorkerAssignment
from app.models.user import User
from app.schemas.auth import UserResponse, UserUpdateRequest

logger = logging.getLogger(__name__)


from app.models.role import Role


async def get_users(current_user: User, db: AsyncSession, scope: str | None = None) -> list[UserResponse]:
    role = (await db.execute(select(Role).where(Role.id == current_user.role_id))).scalar_one_or_none()
    if role and role.name == "owner":
        result = await db.execute(select(User))
        users = result.scalars().all()
    else:
        # PM — scope=mine returns only mutual project site workers, otherwise all site workers
        worker_role = (await db.execute(select(Role).where(Role.name == "site_worker"))).scalar_one_or_none()
        if scope == "mine":
            pm_project_ids = select(ProjectAssignment.project_id).where(ProjectAssignment.user_id == current_user.id)
            worker_ids = select(WorkerAssignment.user_id).where(WorkerAssignment.project_id.in_(pm_project_ids))
            result = await db.execute(select(User).where(User.role_id == worker_role.id).where(User.id.in_(worker_ids)).distinct())
        else:
            result = await db.execute(select(User).where(User.role_id == worker_role.id))
        users = result.scalars().all()

    # Fetch all assigned user IDs in one query
    assigned_pm_ids = set((await db.execute(select(ProjectAssignment.user_id).distinct())).scalars().all())
    assigned_worker_ids = set((await db.execute(select(WorkerAssignment.user_id).distinct())).scalars().all())
    assigned_ids = assigned_pm_ids | assigned_worker_ids

    return [
        UserResponse(
            **{c.name: getattr(u, c.name) for c in u.__table__.columns},
            has_assignments=u.id in assigned_ids,
        )
        for u in users
    ]


async def get_user_by_id(user_id: int, current_user: User, db: AsyncSession) -> User | None:
    role = (await db.execute(select(Role).where(Role.id == current_user.role_id))).scalar_one_or_none()
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        return None
    if role and role.name == "owner":
        return user

    # PM — verify worker shares a project with them
    in_project = (
        await db.execute(
            select(WorkerAssignment)
            .where(WorkerAssignment.user_id == user_id)
            .where(WorkerAssignment.project_id.in_(select(ProjectAssignment.project_id).where(ProjectAssignment.user_id == current_user.id)))
            .limit(1)
        )
    ).scalar_one_or_none()
    return user if in_project else None


async def get_user_assignments(user_id: int, current_user: User, db: AsyncSession) -> list[dict]:
    target_user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not target_user:
        return []

    target_role = (await db.execute(select(Role).where(Role.id == target_user.role_id))).scalar_one_or_none()
    if not target_role:
        return []

    results = []

    if target_role.name == "project_manager":
        rows = (
            (
                await db.execute(
                    select(Project).join(ProjectAssignment, ProjectAssignment.project_id == Project.id).where(ProjectAssignment.user_id == user_id)
                )
            )
            .scalars()
            .all()
        )
        results = [{"id": p.id, "name": p.name, "location": p.location, "status": p.status, "role": "Project Manager"} for p in rows]

    elif target_role.name == "site_worker":
        rows = (
            (
                await db.execute(
                    select(Project).join(WorkerAssignment, WorkerAssignment.project_id == Project.id).where(WorkerAssignment.user_id == user_id)
                )
            )
            .scalars()
            .all()
        )
        results = [{"id": p.id, "name": p.name, "location": p.location, "status": p.status, "role": "Site Worker"} for p in rows]

    return results


async def update_user_by_id(user_id: int, data: UserUpdateRequest, current_user: User, db: AsyncSession) -> User | None:
    user = await get_user_by_id(user_id, current_user, db)
    if not user:
        return None
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(user, field, value)
    await db.commit()
    await db.refresh(user)
    logger.info(f"USER_UPDATE | user_id={user_id} | updated_by={current_user.id} | status=success")
    return user


async def set_user_status(user_id: int, is_active: bool, current_user: User, db: AsyncSession) -> User | None:
    current_role = (await db.execute(select(Role).where(Role.id == current_user.role_id))).scalar_one_or_none()
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        return None
    if not current_role or current_role.name != "owner":
        user_role = (await db.execute(select(Role).where(Role.id == user.role_id))).scalar_one_or_none()
        if not user_role or user_role.name != "site_worker":
            logger.warning(f"USER_ACTIVE | user_id={user_id} | attempted_by={current_user.id} | status=forbidden")
            return None
        shared_project = (
            await db.execute(
                select(WorkerAssignment)
                .where(
                    WorkerAssignment.user_id == user_id,
                    WorkerAssignment.project_id.in_(select(ProjectAssignment.project_id).where(ProjectAssignment.user_id == current_user.id)),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if not shared_project:
            logger.warning(f"USER_ACTIVE | user_id={user_id} | attempted_by={current_user.id} | status=forbidden")
            return None
    user.is_active = is_active
    await db.commit()
    await db.refresh(user)
    logger.info(f"USER_ACTIVE | user_id={user_id} | is_active={is_active} | updated_by={current_user.id} | status=success")
    return user

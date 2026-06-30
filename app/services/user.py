import logging

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.cache import delete_pattern, get_cache, set_cache
from app.core.security import hash_password, verify_password
from app.models.project import Project, ProjectAssignment, WorkerAssignment
from app.models.role import Role
from app.models.user import User
from app.schemas.auth import PasswordChangeRequest, PasswordResetRequest, UserListResponse, UserResponse, UserUpdateRequest

logger = logging.getLogger(__name__)


async def get_users(
    current_user: User,
    db: AsyncSession,
    scope: str | None = None,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
) -> UserListResponse:
    role = (await db.execute(select(Role).where(Role.id == current_user.role_id))).scalar_one_or_none()
    search_term = search.strip() if search else None
    cache_key = f"users:{current_user.id}:{scope or ''}:{page}:{page_size}:{search_term or ''}"
    cached = await get_cache(cache_key)
    if cached:
        logger.info(f"USER | get_users | user_id={current_user.id} | page={page} | search={search_term} | source=cache")
        return UserListResponse(**cached)

    if role and role.name == "owner":
        base_query = select(User)
        count_query = select(func.count()).select_from(User)
    else:
        worker_role = (await db.execute(select(Role).where(Role.name == "site_worker"))).scalar_one_or_none()
        if scope == "mine":
            pm_project_ids = select(ProjectAssignment.project_id).where(ProjectAssignment.user_id == current_user.id)
            worker_ids = select(WorkerAssignment.user_id).where(WorkerAssignment.project_id.in_(pm_project_ids))
            base_query = select(User).where(User.role_id == worker_role.id).where(User.id.in_(worker_ids)).distinct()
            count_query = select(func.count()).select_from(User).where(User.role_id == worker_role.id).where(User.id.in_(worker_ids))
        else:
            base_query = select(User).where(User.role_id == worker_role.id)
            count_query = select(func.count()).select_from(User).where(User.role_id == worker_role.id)

    if search_term:
        pattern = f"%{search_term}%"
        search_filter = (
            User.first_name.ilike(pattern)
            | User.last_name.ilike(pattern)
            | User.email.ilike(pattern)
            | (User.first_name + " " + User.last_name).ilike(pattern)
        )
        base_query = base_query.where(search_filter)
        count_query = count_query.where(search_filter)

    total = (await db.execute(count_query)).scalar() or 0
    result = await db.execute(base_query.order_by(User.id.asc()).limit(page_size).offset((page - 1) * page_size))
    users = result.scalars().all()

    assigned_pm_ids = set((await db.execute(select(ProjectAssignment.user_id).distinct())).scalars().all())
    assigned_worker_ids = set((await db.execute(select(WorkerAssignment.user_id).distinct())).scalars().all())
    assigned_ids = assigned_pm_ids | assigned_worker_ids

    items = [
        UserResponse(
            **{c.name: getattr(u, c.name) for c in u.__table__.columns},
            has_assignments=u.id in assigned_ids,
        )
        for u in users
    ]
    response = UserListResponse(items=items, total=total, page=page, page_size=page_size)
    logger.info(f"USER | get_users | user_id={current_user.id} | page={page} | search={search_term} | count={len(items)} | source=db")
    await set_cache(cache_key, response.model_dump(mode="json"), ttl=120)
    return response


async def get_user_by_id(user_id: int, current_user: User, db: AsyncSession) -> User | None:
    role = (await db.execute(select(Role).where(Role.id == current_user.role_id))).scalar_one_or_none()
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        return None
    if role and role.name == "owner":
        return user
    if role and role.name == "project_manager" and user_id == current_user.id:
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
    await delete_pattern(f"users:{current_user.id}:*")
    logger.info(f"USER_UPDATE | user_id={user_id} | updated_by={current_user.id} | status=success")
    return user


async def set_user_status(user_id: int, is_active: bool, current_user: User, db: AsyncSession) -> User | None:
    current_role = (await db.execute(select(Role).where(Role.id == current_user.role_id))).scalar_one_or_none()
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        return None
    if user_id == current_user.id:
        if not current_role or current_role.name != "project_manager" or is_active is not False:
            logger.warning(
                f"USER_ACTIVE | role={current_role.name if current_role else None} | user_id={current_user.id} | attempted_by={current_user.id} | status=forbidden | reason=self status change not allowed"
            )
            return None
        user.is_active = False
        await db.commit()
        await db.refresh(user)
        await delete_pattern(f"users:{current_user.id}:*")
        logger.info(
            f"USER_ACTIVE | role={current_role.name} | user_id={current_user.id} | is_active=False | updated_by={current_user.id} | status=success"
        )
        return user
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
    await delete_pattern(f"users:{current_user.id}:*")
    logger.info(f"USER_ACTIVE | user_id={user_id} | is_active={is_active} | updated_by={current_user.id} | status=success")
    return user


async def change_password(data: PasswordChangeRequest, current_user: User, db: AsyncSession) -> bool | None:
    if not verify_password(data.current_password, current_user.password_hash):
        logger.warning(f"PASSWORD_CHANGE | user_id={current_user.id} | status=failed | reason=incorrect current password")
        return None
    if verify_password(data.new_password, current_user.password_hash):
        logger.warning(f"PASSWORD_CHANGE | user_id={current_user.id} | status=failed | reason=new password same as current")
        return False
    current_user.password_hash = hash_password(data.new_password)
    await db.commit()
    logger.info(f"PASSWORD_CHANGE | user_id={current_user.id} | status=success")
    return True


async def reset_password(user_id: int, data: PasswordResetRequest, current_user: User, db: AsyncSession) -> bool | None:
    if user_id == current_user.id:
        logger.warning(
            f"PASSWORD_RESET | user_id={current_user.id} | target_id={user_id} | status=forbidden | reason=cannot reset own password via reset endpoint"
        )
        return None
    target_user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not target_user:
        return None
    current_role = (await db.execute(select(Role).where(Role.id == current_user.role_id))).scalar_one_or_none()
    target_role = (await db.execute(select(Role).where(Role.id == target_user.role_id))).scalar_one_or_none()
    current_role_name = current_role.name if current_role else None
    target_role_name = target_role.name if target_role else None
    if current_role_name == "owner":
        allowed = target_role_name in ("owner", "project_manager", "site_worker")
    elif current_role_name == "project_manager":
        allowed = target_role_name == "site_worker"
    else:
        allowed = False
    if not allowed:
        logger.warning(f"PASSWORD_RESET | role={current_role_name} | user_id={current_user.id} | target_id={user_id} | status=forbidden")
        return None
    target_user.password_hash = hash_password(data.new_password)
    await db.commit()
    logger.info(f"PASSWORD_RESET | role={current_role_name} | user_id={current_user.id} | target_id={user_id} | status=success")
    return True

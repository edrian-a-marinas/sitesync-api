import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.project import ProjectAssignment
from app.models.user import User
from app.schemas.auth import UserUpdateRequest

logger = logging.getLogger(__name__)


from app.models.role import Role


async def get_users(current_user: User, db: AsyncSession) -> list[User]:
    role = (await db.execute(select(Role).where(Role.id == current_user.role_id))).scalar_one_or_none()
    if role and role.name == "owner":
        result = await db.execute(select(User))
        return result.scalars().all()

    # PM — only users in their assigned projects
    result = await db.execute(
        select(User)
        .join(ProjectAssignment, ProjectAssignment.user_id == User.id)
        .where(ProjectAssignment.project_id.in_(select(ProjectAssignment.project_id).where(ProjectAssignment.user_id == current_user.id)))
    )
    return result.scalars().unique().all()


async def get_user_by_id(user_id: int, current_user: User, db: AsyncSession) -> User | None:
    role = (await db.execute(select(Role).where(Role.id == current_user.role_id))).scalar_one_or_none()
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        return None
    if role and role.name == "owner":
        return user

    # PM — verify user is in their projects
    in_project = (
        await db.execute(
            select(ProjectAssignment)
            .where(ProjectAssignment.user_id == user_id)
            .where(ProjectAssignment.project_id.in_(select(ProjectAssignment.project_id).where(ProjectAssignment.user_id == current_user.id)))
            .limit(1)
        )
    ).scalar_one_or_none()
    return user if in_project else None


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
        if user.created_by != current_user.id or not user_role or user_role.name != "site_worker":
            logger.warning(f"USER_ACTIVE | user_id={user_id} | attempted_by={current_user.id} | status=forbidden")
            return None
    user.is_active = is_active
    await db.commit()
    await db.refresh(user)
    logger.info(f"USER_ACTIVE | user_id={user_id} | is_active={is_active} | updated_by={current_user.id} | status=success")
    return user

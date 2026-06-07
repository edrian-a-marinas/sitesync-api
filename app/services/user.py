import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.user import User
from app.models.project import ProjectAssignment
from app.schemas.auth import UserUpdateRequest

logger = logging.getLogger(__name__)


async def get_users(current_user: User, db: AsyncSession) -> list[User]:
    if current_user.role_id == 1:
        result = await db.execute(select(User))
        return result.scalars().all()

    # PM — only users in their assigned projects
    result = await db.execute(
        select(User)
        .join(ProjectAssignment, ProjectAssignment.user_id == User.id)
        .where(ProjectAssignment.project_id.in_(
            select(ProjectAssignment.project_id).where(ProjectAssignment.user_id == current_user.id)
        ))
    )
    return result.scalars().unique().all()


async def get_user(user_id: int, current_user: User, db: AsyncSession) -> User | None:
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        return None
    if current_user.role_id == 1:
        return user

    # PM — verify user is in their projects
    in_project = (await db.execute(
        select(ProjectAssignment)
        .where(ProjectAssignment.user_id == user_id)
        .where(ProjectAssignment.project_id.in_(
            select(ProjectAssignment.project_id).where(ProjectAssignment.user_id == current_user.id)
        ))
    )).scalar_one_or_none()
    return user if in_project else None


async def update_user(user_id: int, data: UserUpdateRequest, current_user: User, db: AsyncSession) -> User | None:
    user = await get_user(user_id, current_user, db)
    if not user:
        return None
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(user, field, value)
    await db.commit()
    await db.refresh(user)
    logger.info(f"USER_UPDATE | user_id={user_id} | updated_by={current_user.id} | status=success")
    return user


async def set_user_active(user_id: int, is_active: bool, current_user: User, db: AsyncSession) -> User | None:
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        return None
    if current_user.role_id != 1:
        if user.created_by != current_user.id or user.role_id != 3:
            logger.warning(f"USER_ACTIVE | user_id={user_id} | attempted_by={current_user.id} | status=forbidden")
            return None
    user.is_active = is_active
    await db.commit()
    await db.refresh(user)
    logger.info(f"USER_ACTIVE | user_id={user_id} | is_active={is_active} | updated_by={current_user.id} | status=success")
    return user
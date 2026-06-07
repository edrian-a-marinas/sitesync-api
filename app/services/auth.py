import logging

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.security import create_access_token, hash_password, verify_password
from app.models.role import Role
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest

logger = logging.getLogger(__name__)


async def get_role_by_name(name: str, db: AsyncSession):
    result = await db.execute(select(Role).where(Role.name == name))
    return result.scalar_one_or_none()


async def register_user(data: RegisterRequest, db: AsyncSession, request: Request, created_by: User) -> User:
    owner_role = await get_role_by_name("owner", db)

    if data.role_id == owner_role.id:
        logger.warning(
            f"REGISTER | email={data.email} | ip={request.client.host} | created_by={created_by.id} | status=failed | reason=cannot create owner"
        )
        raise ValueError("Cannot create owner account")

    project_manager_role = await get_role_by_name("project_manager", db)

    if created_by.role_id == project_manager_role.id:
        site_worker_role = await get_role_by_name("site_worker", db)
        if data.role_id != site_worker_role.id:
            logger.warning(
                f"REGISTER | email={data.email} | ip={request.client.host} | created_by={created_by.id} | status=failed | reason=manager can only create site workers"
            )
            raise ValueError("Project Managers can only register site workers")

    result = await db.execute(select(User).where(User.email == data.email))
    if result.scalar_one_or_none():
        logger.warning(
            f"REGISTER | email={data.email} | ip={request.client.host} | created_by={created_by.id} | status=failed | reason=email already exists"
        )
        raise ValueError("Email already registered")

    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        first_name=data.first_name,
        middle_name=data.middle_name,
        last_name=data.last_name,
        phone_number=data.phone_number,
        role_id=data.role_id,
        created_by=created_by.id,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    logger.info(f"REGISTER | email={user.email} | role_id={user.role_id} | ip={request.client.host} | created_by={created_by.id} | status=success")
    return user


async def login_user(data: LoginRequest, db: AsyncSession, request: Request) -> str:
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    if not user:
        logger.warning(f"LOGIN | email={data.email} | ip={request.client.host} | status=failed | reason=user not found")
        raise ValueError("Invalid credentials")

    if not verify_password(data.password, user.password_hash):
        logger.warning(f"LOGIN | email={data.email} | ip={request.client.host} | status=failed | reason=invalid password")
        raise ValueError("Invalid credentials")

    if not user.is_active:
        logger.warning(f"LOGIN | email={data.email} | ip={request.client.host} | status=failed | reason=account inactive")
        raise ValueError("Account is inactive")

    token = create_access_token({"sub": str(user.id), "role_id": user.role_id})

    logger.info(f"LOGIN | email={user.email} | role_id={user.role_id} | ip={request.client.host} | status=success")
    return token

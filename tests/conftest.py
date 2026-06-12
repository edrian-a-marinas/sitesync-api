from app.core.limiter import limiter

limiter.enabled = False
import asyncio

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.security import hash_password
from app.core.settings import settings
from app.database import Base, get_db
from app.main import app
from app.models.daily_log import DailyLog
from app.models.role import Role
from app.models.user import User

TEST_DATABASE_URL = settings.TEST_DATABASE_URL

from sqlalchemy import create_engine as create_sync_engine

SYNC_TEST_DATABASE_URL = TEST_DATABASE_URL.replace("postgresql+asyncpg", "postgresql+psycopg2")


def pytest_configure(config):
    sync_engine = create_sync_engine(SYNC_TEST_DATABASE_URL)
    Base.metadata.create_all(sync_engine)
    sync_engine.dispose()


def pytest_unconfigure(config):
    sync_engine = create_sync_engine(SYNC_TEST_DATABASE_URL)
    Base.metadata.drop_all(sync_engine)
    sync_engine.dispose()


@pytest.fixture(scope="session")
def event_loop_policy():
    return asyncio.DefaultEventLoopPolicy()


@pytest_asyncio.fixture(scope="function", loop_scope="function")
async def db():
    _engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        connect_args={"statement_cache_size": 0},
    )
    _session_factory = async_sessionmaker(bind=_engine, class_=AsyncSession, expire_on_commit=False)
    async with _session_factory() as session:
        yield session
        await session.rollback()
        async with _engine.begin() as conn:
            for table in reversed(Base.metadata.sorted_tables):
                await conn.execute(table.delete())
    await _engine.dispose()


@pytest_asyncio.fixture(scope="function", loop_scope="function")
async def client(db: AsyncSession):
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def create_role(db: AsyncSession, name: str) -> Role:
    role = Role(name=name)
    db.add(role)
    await db.commit()
    await db.refresh(role)
    return role


async def create_user(
    db: AsyncSession,
    role_id: int,
    email: str = "test@example.com",
    password: str = "password123",
    is_active: bool = True,
    created_by: int | None = None,
) -> User:
    user = User(
        email=email,
        password_hash=hash_password(password),
        first_name="Test",
        last_name="User",
        role_id=role_id,
        is_active=is_active,
        created_by=created_by,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def get_auth_token(client: AsyncClient, email: str, password: str) -> str:
    res = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return res.json().get("access_token", "")


async def create_daily_log(db: AsyncSession, project_id: int, submitted_by: int, log_date: str = "2026-01-01") -> DailyLog:
    from datetime import date

    log = DailyLog(
        project_id=project_id,
        submitted_by=submitted_by,
        log_date=date.fromisoformat(log_date),
        work_accomplished="Test work",
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)
    return log

from app.core.limiter import limiter

limiter.enabled = False

from datetime import date

import pytest_asyncio
import sqlalchemy as sa
from fastapi import FastAPI, HTTPException, status
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy.pool import NullPool
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.cache import redis_client
from app.core.dependencies import get_current_user, require_owner, require_owner_or_manager
from app.core.limiter import configure_limiter
from app.core.logging import http_exception_handler, validation_exception_handler
from app.core.security import hash_password
from app.core.settings import settings
from app.database import Base, get_db
from app.models.daily_log import DailyLog
from app.models.project import Project
from app.models.role import Role
from app.models.user import User
from app.routers import all_routers
from app.routers.health import router as health_router

TEST_DATABASE_URL = settings.TEST_DATABASE_URL


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def flush_test_cache():
    await redis_client.flushdb()


# ── Isolated app factory — one instance per role, no override bleed ───────────
def _make_test_app(overrides: dict) -> FastAPI:
    a = FastAPI(**settings.app_config)
    a.add_exception_handler(RequestValidationError, validation_exception_handler)
    a.add_exception_handler(StarletteHTTPException, http_exception_handler)
    configure_limiter(a)
    for router in all_routers:
        a.include_router(router, prefix="/api/v1")
    a.dependency_overrides = overrides
    return a


# ── Session-scoped engine ─────────────────────────────────────────────────────
@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def test_engine():
    engine = create_async_engine(
        TEST_DATABASE_URL,
        poolclass=NullPool,
        connect_args={"statement_cache_size": 0},
    )
    async with engine.begin() as conn:
        await conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


# ── Session-scoped session factory ────────────────────────────────────────────
@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def test_session_factory(test_engine):
    return async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


# ── Seed roles + users once per session ──────────────────────────────────────
@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def seed_users(test_session_factory):
    owner_role = Role(name="owner")
    manager_role = Role(name="project_manager")
    worker_role = Role(name="site_worker")
    async with test_session_factory() as session:
        async with session.begin():
            session.add_all([owner_role, manager_role, worker_role])
            await session.flush()
            owner = User(
                email="owner@test.com",
                password_hash=hash_password("password123"),
                first_name="Test",
                last_name="Owner",
                role_id=owner_role.id,
                is_active=True,
            )
            manager = User(
                email="manager@test.com",
                password_hash=hash_password("password123"),
                first_name="Test",
                last_name="Manager",
                role_id=manager_role.id,
                is_active=True,
            )
            worker = User(
                email="worker@test.com",
                password_hash=hash_password("password123"),
                first_name="Test",
                last_name="Worker",
                role_id=worker_role.id,
                is_active=True,
            )
            inactive = User(
                email="inactive@test.com",
                password_hash=hash_password("password123"),
                first_name="Test",
                last_name="Inactive",
                role_id=worker_role.id,
                is_active=False,
            )
            session.add_all([owner, manager, worker, inactive])
            await session.flush()
        await session.execute(
            select(User).where(User.email.in_(["owner@test.com", "manager@test.com", "worker@test.com"])).options(selectinload(User.role))
        )
        yield {
            "owner": owner,
            "manager": manager,
            "worker": worker,
            "inactive": inactive,
            "owner_role": owner_role,
            "manager_role": manager_role,
            "worker_role": worker_role,
        }


# ── Per-test DB session ───────────────────────────────────────────────────────
@pytest_asyncio.fixture(scope="function")
async def db(test_session_factory):
    async with test_session_factory() as session:
        yield session
        await session.rollback()


# ── get_db override ───────────────────────────────────────────────────────────
def make_get_db_override(session_factory):
    async def override():
        async with session_factory() as session:
            yield session

    return override


# ── Auth override helpers ─────────────────────────────────────────────────────
def make_owner_overrides(user: User):
    async def current_user_override():
        return user

    async def owner_override():
        return user

    return current_user_override, owner_override


def make_manager_overrides(user: User):
    async def current_user_override():
        return user

    async def owner_or_manager_override():
        return user

    async def owner_forbidden():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Owner access required")

    return current_user_override, owner_or_manager_override, owner_forbidden


def make_worker_overrides(user: User):
    async def current_user_override():
        return user

    return current_user_override


# ── Role-scoped clients ───────────────────────────────────────────────────────
@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def owner_client(seed_users, test_session_factory):
    cu, ow = make_owner_overrides(seed_users["owner"])
    a = _make_test_app(
        {
            get_current_user: cu,
            require_owner: ow,
            require_owner_or_manager: ow,
            get_db: make_get_db_override(test_session_factory),
        }
    )
    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def manager_client(seed_users, test_session_factory):
    cu, om, forbidden = make_manager_overrides(seed_users["manager"])
    a = _make_test_app(
        {
            get_current_user: cu,
            require_owner_or_manager: om,
            require_owner: forbidden,
            get_db: make_get_db_override(test_session_factory),
        }
    )
    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def worker_client(seed_users, test_session_factory):
    cu = make_worker_overrides(seed_users["worker"])
    a = _make_test_app(
        {
            get_current_user: cu,
            get_db: make_get_db_override(test_session_factory),
        }
    )
    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def unauth_client(test_session_factory):
    # No get_current_user override — real auth runs and returns 401
    a = _make_test_app(
        {
            get_db: make_get_db_override(test_session_factory),
        }
    )
    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture(scope="function")
async def client(db: AsyncSession):
    async def override_get_db():
        yield db

    a = _make_test_app({get_db: override_get_db})
    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture(scope="function")
async def health_client(db: AsyncSession):
    async def override_get_db():
        yield db

    a = _make_test_app({get_db: override_get_db})
    a.include_router(health_router)
    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as ac:
        yield ac


# ── Helper functions ──────────────────────────────────────────────────────────
async def create_role(db: AsyncSession, name: str) -> Role:
    role = Role(name=name)
    db.add(role)
    await db.flush()
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
    await db.flush()
    await db.refresh(user)
    return user


async def get_auth_token(client: AsyncClient, email: str, password: str) -> str:
    res = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return res.json().get("access_token", "")


async def create_daily_log(db: AsyncSession, project_id: int, submitted_by: int, log_date: str = "2026-01-01") -> DailyLog:
    log = DailyLog(
        project_id=project_id,
        submitted_by=submitted_by,
        log_date=date.fromisoformat(log_date),
        work_accomplished="Test work",
    )
    db.add(log)
    await db.flush()
    await db.refresh(log)
    return log


async def create_worker_assignment(db: AsyncSession, project_id: int, user_id: int):
    from app.models.project import WorkerAssignment

    assignment = WorkerAssignment(project_id=project_id, user_id=user_id)
    db.add(assignment)
    await db.flush()


async def create_project(db: AsyncSession, owner_id: int, name: str = "Test Project") -> Project:
    project = Project(
        owner_id=owner_id,
        name=name,
        location="Manila",
        total_budget=1000000.0,
        start_date=date(2026, 1, 1),
        target_end_date=date(2026, 12, 31),
        status="Active",
    )
    db.add(project)
    await db.flush()
    await db.refresh(project)
    return project

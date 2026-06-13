from app.core.limiter import limiter

limiter.enabled = False
from datetime import date

import pytest_asyncio
from fastapi import HTTPException, status
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine as create_sync_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.dependencies import get_current_user, require_owner, require_owner_or_manager
from app.core.security import hash_password
from app.core.settings import settings
from app.database import Base, get_db
from app.main import app
from app.models.daily_log import DailyLog
from app.models.project import Project
from app.models.role import Role
from app.models.user import User

TEST_DATABASE_URL = settings.TEST_DATABASE_URL
SYNC_TEST_DATABASE_URL = TEST_DATABASE_URL.replace("postgresql+asyncpg", "postgresql+psycopg2")


# ── Schema: create once, drop once ───────────────────────────────────────────
def pytest_configure(config):
    sync_engine = create_sync_engine(SYNC_TEST_DATABASE_URL)
    Base.metadata.drop_all(sync_engine)
    Base.metadata.create_all(sync_engine)
    sync_engine.dispose()


def pytest_unconfigure(config):
    sync_engine = create_sync_engine(SYNC_TEST_DATABASE_URL)
    Base.metadata.drop_all(sync_engine)
    sync_engine.dispose()


# ── Session-scoped engine ─────────────────────────────────────────────────────
@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def test_engine():
    engine = create_async_engine(
        TEST_DATABASE_URL,
        poolclass=NullPool,
        connect_args={"statement_cache_size": 0},
    )
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

    yield {
        "owner": owner,
        "manager": manager,
        "worker": worker,
        "owner_role": owner_role,
        "manager_role": manager_role,
        "worker_role": worker_role,
    }


# ── Per-test DB session with truncate ────────────────────────────────────────
_PRESERVE_TABLES = {"users", "roles", "notifications"}


@pytest_asyncio.fixture(scope="function", loop_scope="session", autouse=True)
async def _truncate_tables(test_session_factory):
    yield
    async with test_session_factory() as session:
        async with session.bind.begin() as conn:
            for table in reversed(Base.metadata.sorted_tables):
                if table.name not in _PRESERVE_TABLES:
                    await conn.execute(table.delete())


@pytest_asyncio.fixture(scope="function", loop_scope="session")
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
@pytest_asyncio.fixture(scope="function", loop_scope="session")
async def owner_client(seed_users, test_session_factory):
    user = seed_users["owner"]
    cu, ow = make_owner_overrides(user)
    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_current_user] = cu
    app.dependency_overrides[require_owner] = ow
    app.dependency_overrides[require_owner_or_manager] = ow
    app.dependency_overrides[get_db] = make_get_db_override(test_session_factory)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
    app.dependency_overrides.update(previous)


@pytest_asyncio.fixture(scope="function", loop_scope="session")
async def manager_client(seed_users, test_session_factory):
    user = seed_users["manager"]
    cu, om, forbidden = make_manager_overrides(user)
    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_current_user] = cu
    app.dependency_overrides[require_owner_or_manager] = om
    app.dependency_overrides[require_owner] = forbidden
    app.dependency_overrides[get_db] = make_get_db_override(test_session_factory)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
    app.dependency_overrides.update(previous)


@pytest_asyncio.fixture(scope="function", loop_scope="session")
async def worker_client(seed_users, test_session_factory):
    user = seed_users["worker"]
    cu = make_worker_overrides(user)
    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_current_user] = cu
    app.dependency_overrides[get_db] = make_get_db_override(test_session_factory)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
    app.dependency_overrides.update(previous)


@pytest_asyncio.fixture(scope="function", loop_scope="session")
async def unauth_client(test_session_factory):
    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = make_get_db_override(test_session_factory)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
    app.dependency_overrides.update(previous)


@pytest_asyncio.fixture(scope="function", loop_scope="session")
async def client(db: AsyncSession):
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_db, None)


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


async def create_worker_assignment(db: AsyncSession, project_id: int, user_id: int):
    from app.models.project import WorkerAssignment

    assignment = WorkerAssignment(project_id=project_id, user_id=user_id)
    db.add(assignment)
    await db.commit()


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
    await db.commit()
    await db.refresh(project)
    return project

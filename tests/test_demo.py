# DEMO FEATURE: delete this test file if demo mode is retired
import uuid

import pytest_asyncio
from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.demo import block_demo_writes
from app.core.limiter import configure_limiter
from app.core.logging import http_exception_handler, validation_exception_handler
from app.core.security import hash_password
from app.core.settings import settings
from app.database import get_db
from app.models.ai_query import AIQuery
from app.models.user import User
from app.routers import all_routers, auth_router


def _make_demo_test_app(session_factory) -> FastAPI:
    """Standalone app replicating main.py's demo-write-block wiring, isolated from conftest's _make_test_app."""
    a = FastAPI(**settings.app_config)
    a.add_exception_handler(RequestValidationError, validation_exception_handler)
    a.add_exception_handler(StarletteHTTPException, http_exception_handler)
    configure_limiter(a)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    for router in all_routers:
        if router is auth_router:
            a.include_router(router, prefix="/api/v1")
        else:
            a.include_router(router, prefix="/api/v1", dependencies=[Depends(block_demo_writes)])
    a.dependency_overrides[get_db] = override_get_db
    return a


async def get_token(client: AsyncClient, email: str, password: str) -> str:
    res = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return res.json().get("access_token", "")


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def seed_demo_users(test_session_factory, seed_users):
    """3 demo accounts (owner/manager/worker), is_demo=True — created once, cleaned up once."""
    suffix = uuid.uuid4().hex[:8]
    demo_owner = User(
        email=f"demo_owner_{suffix}@test.com",
        password_hash=hash_password("demo1234"),
        first_name="Demo",
        last_name="Owner",
        role_id=seed_users["owner_role"].id,
        is_active=True,
        is_demo=True,
    )
    demo_manager = User(
        email=f"demo_manager_{suffix}@test.com",
        password_hash=hash_password("demo1234"),
        first_name="Demo",
        last_name="Manager",
        role_id=seed_users["manager_role"].id,
        is_active=True,
        is_demo=True,
    )
    demo_worker = User(
        email=f"demo_worker_{suffix}@test.com",
        password_hash=hash_password("demo1234"),
        first_name="Demo",
        last_name="Worker",
        role_id=seed_users["worker_role"].id,
        is_active=True,
        is_demo=True,
    )
    async with test_session_factory() as session:
        async with session.begin():
            session.add_all([demo_owner, demo_manager, demo_worker])
    yield {"owner": demo_owner, "manager": demo_manager, "worker": demo_worker}
    async with test_session_factory() as session:
        async with session.begin():
            await session.execute(delete(AIQuery).where(AIQuery.user_id.in_([demo_owner.id, demo_manager.id, demo_worker.id])))
            await session.execute(delete(User).where(User.id.in_([demo_owner.id, demo_manager.id, demo_worker.id])))


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def demo_client(test_session_factory):
    a = _make_demo_test_app(test_session_factory)
    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as ac:
        yield ac


class TestDemoWriteBlocked:
    async def test_demo_owner_cannot_patch(self, demo_client: AsyncClient, seed_demo_users):
        token = await get_token(demo_client, seed_demo_users["owner"].email, "demo1234")
        res = await demo_client.patch(
            "/api/v1/users/me/password",
            json={"current_password": "demo1234", "new_password": "shouldnotwork1"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 403
        assert res.json()["detail"] == "Demo accounts are read-only. Owner demo can use AI Assistant, Analytics, and generate reports only."

    async def test_demo_manager_cannot_patch(self, demo_client: AsyncClient, seed_demo_users):
        token = await get_token(demo_client, seed_demo_users["manager"].email, "demo1234")
        res = await demo_client.patch(
            "/api/v1/users/me/password",
            json={"current_password": "demo1234", "new_password": "shouldnotwork1"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 403
        assert res.json()["detail"] == "Demo accounts are read-only. Owner demo can use AI Assistant, Analytics, and generate reports only."

    async def test_demo_worker_cannot_patch(self, demo_client: AsyncClient, seed_demo_users):
        token = await get_token(demo_client, seed_demo_users["worker"].email, "demo1234")
        res = await demo_client.patch(
            "/api/v1/users/me/password",
            json={"current_password": "demo1234", "new_password": "shouldnotwork1"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 403
        assert res.json()["detail"] == "Demo accounts are read-only. Owner demo can use AI Assistant, Analytics, and generate reports only."


class TestDemoReadAllowed:
    async def test_demo_owner_can_get(self, demo_client: AsyncClient, seed_demo_users):
        token = await get_token(demo_client, seed_demo_users["owner"].email, "demo1234")
        res = await demo_client.get(
            "/api/v1/users",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200

    async def test_demo_owner_can_login_and_read_me(self, demo_client: AsyncClient, seed_demo_users):
        token = await get_token(demo_client, seed_demo_users["owner"].email, "demo1234")
        res = await demo_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        assert res.json()["is_demo"] is True


class TestDemoAllowedWrites:
    async def test_demo_owner_can_trigger_ai_query(self, demo_client: AsyncClient, seed_demo_users):
        token = await get_token(demo_client, seed_demo_users["owner"].email, "demo1234")
        res = await demo_client.post(
            "/api/v1/ai/query",
            json={"question": "How many active projects are there?"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code != 403

    async def test_demo_owner_can_trigger_ml_retrain(self, demo_client: AsyncClient, seed_demo_users):
        token = await get_token(demo_client, seed_demo_users["owner"].email, "demo1234")
        res = await demo_client.post(
            "/api/v1/ml/retrain",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code != 403

    async def test_demo_manager_still_blocked_from_ai_query(self, demo_client: AsyncClient, seed_demo_users):
        token = await get_token(demo_client, seed_demo_users["manager"].email, "demo1234")
        res = await demo_client.post(
            "/api/v1/ai/query",
            json={"question": "How many active projects are there?"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 403

    async def test_demo_owner_can_generate_report(self, demo_client: AsyncClient, seed_demo_users):
        token = await get_token(demo_client, seed_demo_users["owner"].email, "demo1234")
        res = await demo_client.post(
            "/api/v1/reports/1/generate",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code != 403

    async def test_demo_manager_still_blocked_from_generate_report(self, demo_client: AsyncClient, seed_demo_users):
        token = await get_token(demo_client, seed_demo_users["manager"].email, "demo1234")
        res = await demo_client.post(
            "/api/v1/reports/1/generate",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 403

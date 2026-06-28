from datetime import date

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete

from app.core.security import hash_password
from app.models.project import Project, ProjectAssignment, WorkerAssignment
from app.models.user import User

# ---------------------------------------------------------------------------
# Session-scoped seeds
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def seed_user_project(test_session_factory, seed_users):
    """Shared project with manager + worker assigned — reused across list/get/update tests."""
    async with test_session_factory() as session:
        async with session.begin():
            project = Project(
                owner_id=seed_users["owner"].id,
                name="User Test Project",
                location="Manila",
                total_budget=1_000_000,
                start_date=date(2026, 1, 1),
                target_end_date=date(2026, 12, 31),
                status="Active",
            )
            session.add(project)
            await session.flush()
            session.add_all(
                [
                    ProjectAssignment(project_id=project.id, user_id=seed_users["manager"].id),
                    WorkerAssignment(project_id=project.id, user_id=seed_users["worker"].id),
                ]
            )
    yield project
    async with test_session_factory() as session:
        async with session.begin():
            await session.execute(delete(WorkerAssignment).where(WorkerAssignment.project_id == project.id))
            await session.execute(delete(ProjectAssignment).where(ProjectAssignment.project_id == project.id))
            await session.execute(delete(Project).where(Project.id == project.id))


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def seed_user_extras(test_session_factory, seed_users):
    """Extra users needed for deactivate/activate tests — created once, cleaned up once."""

    # Worker shared with manager via project
    manager_created_worker = User(
        email="created_worker@test.com",
        password_hash=hash_password("password123"),
        first_name="Created",
        last_name="Worker",
        role_id=seed_users["worker_role"].id,
        is_active=True,
    )
    # Worker NOT in any of manager's projects
    owner_created_worker = User(
        email="owner_created_worker@test.com",
        password_hash=hash_password("password123"),
        first_name="Owner",
        last_name="Created",
        role_id=seed_users["worker_role"].id,
        is_active=True,
    )
    manager2 = User(
        email="manager2_user@test.com",
        password_hash=hash_password("password123"),
        first_name="Manager",
        last_name="Two",
        role_id=seed_users["manager_role"].id,
        is_active=True,
    )
    inactive_worker = User(
        email="inactive_worker@test.com",
        password_hash=hash_password("password123"),
        first_name="Inactive",
        last_name="Worker",
        role_id=seed_users["worker_role"].id,
        is_active=False,
    )
    # Inactive worker shared with manager via project
    inactive_created_worker = User(
        email="inactive_created_worker@test.com",
        password_hash=hash_password("password123"),
        first_name="Inactive",
        last_name="Created",
        role_id=seed_users["worker_role"].id,
        is_active=False,
    )
    # Inactive worker NOT in any of manager's projects
    other_inactive_worker = User(
        email="other_inactive_worker@test.com",
        password_hash=hash_password("password123"),
        first_name="Other",
        last_name="Inactive",
        role_id=seed_users["worker_role"].id,
        is_active=False,
    )
    async with test_session_factory() as session:
        async with session.begin():
            session.add_all(
                [
                    manager_created_worker,
                    owner_created_worker,
                    manager2,
                    inactive_worker,
                    inactive_created_worker,
                    other_inactive_worker,
                ]
            )
            await session.flush()

            # Project shared between manager and manager_created_worker / inactive_created_worker
            extras_project = Project(
                owner_id=seed_users["owner"].id,
                name="Extras Test Project",
                location="Manila",
                total_budget=500_000,
                start_date=date(2026, 1, 1),
                target_end_date=date(2026, 12, 31),
                status="Active",
            )
            session.add(extras_project)
            await session.flush()

            session.add_all(
                [
                    ProjectAssignment(project_id=extras_project.id, user_id=seed_users["manager"].id),
                    WorkerAssignment(project_id=extras_project.id, user_id=manager_created_worker.id),
                    WorkerAssignment(project_id=extras_project.id, user_id=inactive_created_worker.id),
                ]
            )

    yield {
        "manager_created_worker": manager_created_worker,
        "owner_created_worker": owner_created_worker,
        "manager2": manager2,
        "inactive_worker": inactive_worker,
        "inactive_created_worker": inactive_created_worker,
        "other_inactive_worker": other_inactive_worker,
        "extras_project": extras_project,
    }
    async with test_session_factory() as session:
        async with session.begin():
            await session.execute(delete(WorkerAssignment).where(WorkerAssignment.project_id == extras_project.id))
            await session.execute(delete(ProjectAssignment).where(ProjectAssignment.project_id == extras_project.id))
            await session.execute(delete(Project).where(Project.id == extras_project.id))
        async with session.begin():
            await session.execute(
                delete(User).where(
                    User.email.in_(
                        [
                            "created_worker@test.com",
                            "owner_created_worker@test.com",
                            "manager2_user@test.com",
                            "inactive_worker@test.com",
                            "inactive_created_worker@test.com",
                            "other_inactive_worker@test.com",
                        ]
                    )
                )
            )


# ---------------------------------------------------------------------------
# GET /api/v1/users
# ---------------------------------------------------------------------------


class TestListUsers:
    async def test_owner_sees_all_users(self, owner_client: AsyncClient, seed_users):
        res = await owner_client.get("/api/v1/users")
        assert res.status_code == 200
        emails = [u["email"] for u in res.json()["items"]]
        assert "owner@test.com" in emails
        assert "manager@test.com" in emails
        assert "worker@test.com" in emails

    async def test_manager_sees_only_shared_project_users(self, manager_client: AsyncClient, seed_user_project):
        res = await manager_client.get("/api/v1/users")
        assert res.status_code == 200
        emails = [u["email"] for u in res.json()["items"]]
        assert "worker@test.com" in emails

    async def test_site_worker_forbidden(self, worker_client: AsyncClient):
        res = await worker_client.get("/api/v1/users")
        assert res.status_code == 403

    async def test_unauthenticated(self, unauth_client: AsyncClient):
        res = await unauth_client.get("/api/v1/users")
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/v1/users/{user_id}
# ---------------------------------------------------------------------------


class TestGetUser:
    async def test_owner_can_get_any_user(self, owner_client: AsyncClient, seed_users):
        res = await owner_client.get(f"/api/v1/users/{seed_users['worker'].id}")
        assert res.status_code == 200
        assert res.json()["email"] == "worker@test.com"

    async def test_manager_can_get_shared_project_user(self, manager_client: AsyncClient, seed_users, seed_user_project):
        res = await manager_client.get(f"/api/v1/users/{seed_users['worker'].id}")
        assert res.status_code == 200
        assert res.json()["email"] == "worker@test.com"

    async def test_manager_cannot_get_unrelated_user(self, manager_client: AsyncClient, seed_user_extras):
        # owner_created_worker has no shared project with manager
        res = await manager_client.get(f"/api/v1/users/{seed_user_extras['owner_created_worker'].id}")
        assert res.status_code == 404

    async def test_nonexistent_user_returns_404(self, owner_client: AsyncClient):
        res = await owner_client.get("/api/v1/users/99999")
        assert res.status_code == 404

    async def test_site_worker_forbidden(self, worker_client: AsyncClient, seed_users):
        res = await worker_client.get(f"/api/v1/users/{seed_users['owner'].id}")
        assert res.status_code == 403

    async def test_unauthenticated(self, unauth_client: AsyncClient):
        res = await unauth_client.get("/api/v1/users/1")
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /api/v1/users/{user_id}
# ---------------------------------------------------------------------------


class TestUpdateUser:
    async def test_owner_can_update_any_user(self, owner_client: AsyncClient, seed_user_extras):
        res = await owner_client.patch(
            f"/api/v1/users/{seed_user_extras['owner_created_worker'].id}",
            json={"first_name": "Updated"},
        )
        assert res.status_code == 200
        assert res.json()["first_name"] == "Updated"

    async def test_manager_can_update_shared_project_user(self, manager_client: AsyncClient, seed_users, seed_user_project):
        res = await manager_client.patch(
            f"/api/v1/users/{seed_users['worker'].id}",
            json={"last_name": "Patched"},
        )
        assert res.status_code == 200
        assert res.json()["last_name"] == "Patched"

    async def test_manager_cannot_update_unrelated_user(self, manager_client: AsyncClient, seed_user_extras):
        res = await manager_client.patch(
            f"/api/v1/users/{seed_user_extras['owner_created_worker'].id}",
            json={"first_name": "Hack"},
        )
        assert res.status_code == 404

    async def test_partial_update_only_changes_provided_fields(self, owner_client: AsyncClient, seed_user_extras):
        get_res = await owner_client.get(f"/api/v1/users/{seed_user_extras['manager_created_worker'].id}")
        original_last_name = get_res.json()["last_name"]
        res = await owner_client.patch(
            f"/api/v1/users/{seed_user_extras['manager_created_worker'].id}",
            json={"first_name": "OnlyFirst"},
        )
        assert res.status_code == 200
        assert res.json()["first_name"] == "OnlyFirst"
        assert res.json()["last_name"] == original_last_name

    async def test_update_nonexistent_user_returns_404(self, owner_client: AsyncClient):
        res = await owner_client.patch("/api/v1/users/99999", json={"first_name": "Ghost"})
        assert res.status_code == 404

    async def test_site_worker_forbidden(self, worker_client: AsyncClient, seed_users):
        res = await worker_client.patch(
            f"/api/v1/users/{seed_users['owner'].id}",
            json={"first_name": "Hack"},
        )
        assert res.status_code == 403

    async def test_unauthenticated(self, unauth_client: AsyncClient):
        res = await unauth_client.patch("/api/v1/users/1", json={"first_name": "X"})
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /api/v1/users/{user_id}/deactivate
# ---------------------------------------------------------------------------


class TestDeactivateUser:
    async def test_owner_can_deactivate_any_user(self, owner_client: AsyncClient, seed_user_extras):
        res = await owner_client.patch(f"/api/v1/users/{seed_user_extras['manager_created_worker'].id}/deactivate")
        assert res.status_code == 200
        assert res.json()["is_active"] is False

    async def test_manager_can_deactivate_shared_project_worker(self, manager_client: AsyncClient, seed_user_extras):
        res = await manager_client.patch(f"/api/v1/users/{seed_user_extras['manager_created_worker'].id}/deactivate")
        assert res.status_code == 200
        assert res.json()["is_active"] is False

    async def test_manager_cannot_deactivate_unrelated_worker(self, manager_client: AsyncClient, seed_user_extras):
        res = await manager_client.patch(f"/api/v1/users/{seed_user_extras['owner_created_worker'].id}/deactivate")
        assert res.status_code == 403

    async def test_manager_cannot_deactivate_another_manager(self, manager_client: AsyncClient, seed_user_extras):
        res = await manager_client.patch(f"/api/v1/users/{seed_user_extras['manager2'].id}/deactivate")
        assert res.status_code == 403

    async def test_deactivate_nonexistent_user(self, owner_client: AsyncClient):
        res = await owner_client.patch("/api/v1/users/99999/deactivate")
        assert res.status_code == 403

    async def test_site_worker_forbidden(self, worker_client: AsyncClient, seed_users):
        res = await worker_client.patch(f"/api/v1/users/{seed_users['owner'].id}/deactivate")
        assert res.status_code == 403

    async def test_unauthenticated(self, unauth_client: AsyncClient):
        res = await unauth_client.patch("/api/v1/users/1/deactivate")
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /api/v1/users/{user_id}/activate
# ---------------------------------------------------------------------------


class TestActivateUser:
    async def test_owner_can_activate_inactive_user(self, owner_client: AsyncClient, seed_user_extras):
        res = await owner_client.patch(f"/api/v1/users/{seed_user_extras['inactive_worker'].id}/activate")
        assert res.status_code == 200
        assert res.json()["is_active"] is True

    async def test_manager_can_activate_shared_project_worker(self, manager_client: AsyncClient, seed_user_extras):
        res = await manager_client.patch(f"/api/v1/users/{seed_user_extras['inactive_created_worker'].id}/activate")
        assert res.status_code == 200
        assert res.json()["is_active"] is True

    async def test_manager_cannot_activate_unrelated_worker(self, manager_client: AsyncClient, seed_user_extras):
        res = await manager_client.patch(f"/api/v1/users/{seed_user_extras['other_inactive_worker'].id}/activate")
        assert res.status_code == 403

    async def test_activate_nonexistent_user(self, owner_client: AsyncClient):
        res = await owner_client.patch("/api/v1/users/99999/activate")
        assert res.status_code == 403

    async def test_site_worker_forbidden(self, worker_client: AsyncClient, seed_users):
        res = await worker_client.patch(f"/api/v1/users/{seed_users['owner'].id}/activate")
        assert res.status_code == 403

    async def test_unauthenticated(self, unauth_client: AsyncClient):
        res = await unauth_client.patch("/api/v1/users/1/activate")
        assert res.status_code == 401

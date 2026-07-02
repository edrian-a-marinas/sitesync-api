from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete

from app.core.security import hash_password
from app.models.project import Project, ProjectAssignment, WorkerAssignment
from app.models.user import User
from app.schemas.auth import PasswordResetRequest
from app.services.user import reset_password

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

    async def test_manager_can_update_own_name(self, manager_client: AsyncClient, owner_client: AsyncClient, seed_users):
        res = await manager_client.patch(
            f"/api/v1/users/{seed_users['manager'].id}",
            json={"first_name": "SelfEdited"},
        )
        assert res.status_code == 200
        assert res.json()["first_name"] == "SelfEdited"
        res2 = await owner_client.patch(f"/api/v1/users/{seed_users['manager'].id}", json={"first_name": "Test"})
        assert res2.status_code == 200


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


# ---------------------------------------------------------------------------
# PATCH /api/v1/users/me/password
# ---------------------------------------------------------------------------
class TestChangePassword:
    async def test_change_password_success(self, manager_client: AsyncClient):
        res = await manager_client.patch(
            "/api/v1/users/me/password",
            json={"current_password": "password123", "new_password": "newpassword456"},
        )
        assert res.status_code == 200
        res2 = await manager_client.patch(
            "/api/v1/users/me/password",
            json={"current_password": "newpassword456", "new_password": "password123"},
        )
        assert res2.status_code == 200

    async def test_change_password_wrong_current_password(self, manager_client: AsyncClient):
        res = await manager_client.patch(
            "/api/v1/users/me/password",
            json={"current_password": "wrongpassword", "new_password": "newpassword456"},
        )
        assert res.status_code == 400

    async def test_change_password_same_as_current(self, manager_client: AsyncClient):
        res = await manager_client.patch(
            "/api/v1/users/me/password",
            json={"current_password": "password123", "new_password": "password123"},
        )
        assert res.status_code == 400

    async def test_unauthenticated(self, unauth_client: AsyncClient):
        res = await unauth_client.patch(
            "/api/v1/users/me/password",
            json={"current_password": "x", "new_password": "y12345678"},
        )
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /api/v1/users/{user_id}/password/reset
# ---------------------------------------------------------------------------
class TestResetPassword:
    async def test_current_user_with_invalid_role_is_forbidden(self, seed_users, seed_user_extras, test_session_factory):
        current_user = MagicMock(id=999999, role_id=99999)
        target_user = seed_user_extras["owner_created_worker"]
        async with test_session_factory() as session:
            result = await reset_password(target_user.id, PasswordResetRequest(new_password="whatever123"), current_user, session)
        assert result is None

    async def test_owner_can_reset_manager_password(self, owner_client: AsyncClient, seed_users):
        res = await owner_client.patch(
            f"/api/v1/users/{seed_users['manager'].id}/password/reset",
            json={"new_password": "ownerresetpw1"},
        )
        assert res.status_code == 200
        res2 = await owner_client.patch(
            f"/api/v1/users/{seed_users['manager'].id}/password/reset",
            json={"new_password": "password123"},
        )
        assert res2.status_code == 200

    async def test_owner_can_reset_worker_password(self, owner_client: AsyncClient, seed_users):
        res = await owner_client.patch(
            f"/api/v1/users/{seed_users['worker'].id}/password/reset",
            json={"new_password": "ownerresetpw2"},
        )
        assert res.status_code == 200
        res2 = await owner_client.patch(
            f"/api/v1/users/{seed_users['worker'].id}/password/reset",
            json={"new_password": "password123"},
        )
        assert res2.status_code == 200

    async def test_manager_can_reset_shared_worker_password(self, manager_client: AsyncClient, seed_user_extras):
        res = await manager_client.patch(
            f"/api/v1/users/{seed_user_extras['manager_created_worker'].id}/password/reset",
            json={"new_password": "pmresetpw1"},
        )
        assert res.status_code == 200

    async def test_manager_cannot_reset_unrelated_worker(self, manager_client: AsyncClient, seed_user_extras):
        res = await manager_client.patch(
            f"/api/v1/users/{seed_user_extras['owner_created_worker'].id}/password/reset",
            json={"new_password": "pmresetpw2"},
        )
        assert res.status_code == 403

    async def test_manager_cannot_reset_another_manager(self, manager_client: AsyncClient, seed_user_extras):
        res = await manager_client.patch(
            f"/api/v1/users/{seed_user_extras['manager2'].id}/password/reset",
            json={"new_password": "pmresetpw3"},
        )
        assert res.status_code == 403

    async def test_manager_cannot_reset_owner(self, manager_client: AsyncClient, seed_users):
        res = await manager_client.patch(
            f"/api/v1/users/{seed_users['owner'].id}/password/reset",
            json={"new_password": "pmresetpw4"},
        )
        assert res.status_code == 403

    async def test_owner_cannot_reset_own_password(self, owner_client: AsyncClient, seed_users):
        res = await owner_client.patch(
            f"/api/v1/users/{seed_users['owner'].id}/password/reset",
            json={"new_password": "selfresetpw"},
        )
        assert res.status_code == 403

    async def test_manager_cannot_reset_own_password(self, manager_client: AsyncClient, seed_users):
        res = await manager_client.patch(
            f"/api/v1/users/{seed_users['manager'].id}/password/reset",
            json={"new_password": "selfresetpw2"},
        )
        assert res.status_code == 403

    async def test_reset_nonexistent_user(self, owner_client: AsyncClient):
        res = await owner_client.patch(
            "/api/v1/users/99999/password/reset",
            json={"new_password": "ghostpassword"},
        )
        assert res.status_code == 403

    async def test_site_worker_forbidden(self, worker_client: AsyncClient, seed_users):
        res = await worker_client.patch(
            f"/api/v1/users/{seed_users['owner'].id}/password/reset",
            json={"new_password": "workerattempt"},
        )
        assert res.status_code == 403

    async def test_unauthenticated(self, unauth_client: AsyncClient):
        res = await unauth_client.patch(
            "/api/v1/users/1/password/reset",
            json={"new_password": "x12345678"},
        )
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /api/v1/users/{user_id}/deactivate — self-deactivation
# ---------------------------------------------------------------------------
class TestSelfDeactivate:
    async def test_manager_can_deactivate_self(self, manager_client: AsyncClient, owner_client: AsyncClient, seed_users):
        res = await manager_client.patch(f"/api/v1/users/{seed_users['manager'].id}/deactivate")
        assert res.status_code == 200
        assert res.json()["is_active"] is False
        # reactivate via owner so DB state doesn't bleed into other tests
        res2 = await owner_client.patch(f"/api/v1/users/{seed_users['manager'].id}/activate")
        assert res2.status_code == 200
        assert res2.json()["is_active"] is True

    async def test_owner_cannot_deactivate_self(self, owner_client: AsyncClient, seed_users):
        res = await owner_client.patch(f"/api/v1/users/{seed_users['owner'].id}/deactivate")
        assert res.status_code == 403

    async def test_manager_cannot_reactivate_self_while_active(self, manager_client: AsyncClient, seed_users):
        res = await manager_client.patch(f"/api/v1/users/{seed_users['manager'].id}/activate")
        assert res.status_code == 403

    async def test_worker_cannot_self_deactivate(self, worker_client: AsyncClient, seed_users):
        res = await worker_client.patch(f"/api/v1/users/{seed_users['worker'].id}/deactivate")
        assert res.status_code == 403


# ---------------------------------------------------------------------------
# GET /api/v1/users — search + scope=mine
# ---------------------------------------------------------------------------
class TestListUsersSearchAndScope:
    async def test_owner_search_by_name(self, owner_client: AsyncClient, seed_users):
        res = await owner_client.get("/api/v1/users", params={"search": "Owner"})
        assert res.status_code == 200
        emails = [u["email"] for u in res.json()["items"]]
        assert "owner@test.com" in emails

    async def test_owner_search_by_email(self, owner_client: AsyncClient, seed_users):
        res = await owner_client.get("/api/v1/users", params={"search": "worker@test.com"})
        assert res.status_code == 200
        emails = [u["email"] for u in res.json()["items"]]
        assert "worker@test.com" in emails

    async def test_owner_search_no_match_returns_empty(self, owner_client: AsyncClient):
        res = await owner_client.get("/api/v1/users", params={"search": "zzznomatchzzz"})
        assert res.status_code == 200
        assert res.json()["items"] == []

    async def test_manager_scope_mine_returns_shared_workers_only(self, manager_client: AsyncClient, seed_user_project, seed_user_extras):
        res = await manager_client.get("/api/v1/users", params={"scope": "mine"})
        assert res.status_code == 200
        emails = [u["email"] for u in res.json()["items"]]
        assert "worker@test.com" in emails
        assert "owner_created_worker@test.com" not in emails

    async def test_manager_scope_all_returns_every_worker(self, manager_client: AsyncClient, seed_user_extras):
        res = await manager_client.get("/api/v1/users", params={"scope": "all"})
        assert res.status_code == 200
        emails = [u["email"] for u in res.json()["items"]]
        assert "owner_created_worker@test.com" in emails

    async def test_cached_result_is_returned_on_second_call(self, owner_client: AsyncClient, seed_users):
        res1 = await owner_client.get("/api/v1/users", params={"page": 1, "page_size": 5})
        assert res1.status_code == 200
        res2 = await owner_client.get("/api/v1/users", params={"page": 1, "page_size": 5})
        assert res2.status_code == 200
        assert res1.json() == res2.json()


# ---------------------------------------------------------------------------
# GET /api/v1/users/{user_id}/assignments
# ---------------------------------------------------------------------------
class TestGetUserAssignments:
    async def test_target_user_with_invalid_role_returns_empty_list(self, seed_users, test_session_factory):
        from app.services.user import get_user_assignments

        # target_user exists but its role_id no longer resolves to a Role (simulated via mock)
        target_user = MagicMock(role_id=99999)
        mock_session = MagicMock()
        mock_execute_user = MagicMock()
        mock_execute_user.scalar_one_or_none.return_value = target_user
        mock_execute_role = MagicMock()
        mock_execute_role.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(side_effect=[mock_execute_user, mock_execute_role])
        result = await get_user_assignments(1, seed_users["owner"], mock_session)
        assert result == []

    async def test_owner_gets_manager_assignments(self, owner_client: AsyncClient, seed_users, seed_user_project):
        res = await owner_client.get(f"/api/v1/users/{seed_users['manager'].id}/assignments")
        assert res.status_code == 200
        names = [a["name"] for a in res.json()]
        assert "User Test Project" in names
        assert res.json()[0]["role"] == "Project Manager"

    async def test_owner_gets_worker_assignments(self, owner_client: AsyncClient, seed_users, seed_user_project):
        res = await owner_client.get(f"/api/v1/users/{seed_users['worker'].id}/assignments")
        assert res.status_code == 200
        names = [a["name"] for a in res.json()]
        assert "User Test Project" in names
        assert res.json()[0]["role"] == "Site Worker"

    async def test_owner_gets_empty_assignments_for_unassigned_user(self, owner_client: AsyncClient, seed_user_extras):
        res = await owner_client.get(f"/api/v1/users/{seed_user_extras['owner_created_worker'].id}/assignments")
        assert res.status_code == 200
        assert res.json() == []

    async def test_nonexistent_user_returns_empty_list(self, owner_client: AsyncClient):
        res = await owner_client.get("/api/v1/users/99999/assignments")
        assert res.status_code == 200
        assert res.json() == []

    async def test_manager_can_get_assignments(self, manager_client: AsyncClient, seed_users, seed_user_project):
        res = await manager_client.get(f"/api/v1/users/{seed_users['worker'].id}/assignments")
        assert res.status_code == 200

    async def test_site_worker_forbidden(self, worker_client: AsyncClient, seed_users):
        res = await worker_client.get(f"/api/v1/users/{seed_users['owner'].id}/assignments")
        assert res.status_code == 403

    async def test_unauthenticated(self, unauth_client: AsyncClient):
        res = await unauth_client.get("/api/v1/users/1/assignments")
        assert res.status_code == 401

from datetime import date

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project, ProjectAssignment
from tests.conftest import create_role, create_user, get_auth_token

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def create_project(db: AsyncSession, owner_id: int) -> Project:
    project = Project(
        owner_id=owner_id,
        name="Test Project",
        location="Manila",
        total_budget=1_000_000,
        start_date=date(2026, 1, 1),
        target_end_date=date(2026, 12, 31),
        status="Active",
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


async def assign_to_project(db: AsyncSession, project_id: int, user_id: int) -> None:
    assignment = ProjectAssignment(project_id=project_id, user_id=user_id)
    db.add(assignment)
    await db.commit()


# ---------------------------------------------------------------------------
# GET /api/v1/users
# ---------------------------------------------------------------------------


class TestListUsers:
    async def test_owner_sees_all_users(self, client: AsyncClient, db: AsyncSession):
        owner_role = await create_role(db, "owner")
        manager_role = await create_role(db, "project_manager")
        worker_role = await create_role(db, "site_worker")

        await create_user(db, owner_role.id, email="owner@test.com")
        await create_user(db, manager_role.id, email="manager@test.com")
        await create_user(db, worker_role.id, email="worker@test.com")

        token = await get_auth_token(client, "owner@test.com", "password123")
        res = await client.get("/api/v1/users", headers={"Authorization": f"Bearer {token}"})

        assert res.status_code == 200
        emails = [u["email"] for u in res.json()]
        assert "owner@test.com" in emails
        assert "manager@test.com" in emails
        assert "worker@test.com" in emails

    async def test_manager_sees_only_shared_project_users(self, client: AsyncClient, db: AsyncSession):
        owner_role = await create_role(db, "owner")
        manager_role = await create_role(db, "project_manager")
        worker_role = await create_role(db, "site_worker")

        owner = await create_user(db, owner_role.id, email="owner@test.com")
        manager = await create_user(db, manager_role.id, email="manager@test.com")
        worker_in = await create_user(db, worker_role.id, email="worker_in@test.com")
        await create_user(db, worker_role.id, email="worker_out@test.com")

        project = await create_project(db, owner.id)
        await assign_to_project(db, project.id, manager.id)
        await assign_to_project(db, project.id, worker_in.id)
        # worker_out is NOT assigned to this project

        token = await get_auth_token(client, "manager@test.com", "password123")
        res = await client.get("/api/v1/users", headers={"Authorization": f"Bearer {token}"})

        assert res.status_code == 200
        emails = [u["email"] for u in res.json()]
        assert "worker_in@test.com" in emails
        assert "worker_out@test.com" not in emails

    async def test_site_worker_forbidden(self, client: AsyncClient, db: AsyncSession):
        owner_role = await create_role(db, "owner")
        worker_role = await create_role(db, "site_worker")

        await create_user(db, owner_role.id, email="owner@test.com")
        await create_user(db, worker_role.id, email="worker@test.com")

        token = await get_auth_token(client, "worker@test.com", "password123")
        res = await client.get("/api/v1/users", headers={"Authorization": f"Bearer {token}"})

        assert res.status_code == 403

    async def test_unauthenticated(self, client: AsyncClient, db: AsyncSession):
        res = await client.get("/api/v1/users")
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/v1/users/{user_id}
# ---------------------------------------------------------------------------


class TestGetUser:
    async def test_owner_can_get_any_user(self, client: AsyncClient, db: AsyncSession):
        owner_role = await create_role(db, "owner")
        worker_role = await create_role(db, "site_worker")

        await create_user(db, owner_role.id, email="owner@test.com")
        worker = await create_user(db, worker_role.id, email="worker@test.com")

        token = await get_auth_token(client, "owner@test.com", "password123")
        res = await client.get(f"/api/v1/users/{worker.id}", headers={"Authorization": f"Bearer {token}"})

        assert res.status_code == 200
        assert res.json()["email"] == "worker@test.com"

    async def test_manager_can_get_shared_project_user(self, client: AsyncClient, db: AsyncSession):
        owner_role = await create_role(db, "owner")
        manager_role = await create_role(db, "project_manager")
        worker_role = await create_role(db, "site_worker")

        owner = await create_user(db, owner_role.id, email="owner@test.com")
        manager = await create_user(db, manager_role.id, email="manager@test.com")
        worker = await create_user(db, worker_role.id, email="worker@test.com")

        project = await create_project(db, owner.id)
        await assign_to_project(db, project.id, manager.id)
        await assign_to_project(db, project.id, worker.id)

        token = await get_auth_token(client, "manager@test.com", "password123")
        res = await client.get(f"/api/v1/users/{worker.id}", headers={"Authorization": f"Bearer {token}"})

        assert res.status_code == 200
        assert res.json()["email"] == "worker@test.com"

    async def test_manager_cannot_get_unrelated_user(self, client: AsyncClient, db: AsyncSession):
        owner_role = await create_role(db, "owner")
        manager_role = await create_role(db, "project_manager")
        worker_role = await create_role(db, "site_worker")

        await create_user(db, owner_role.id, email="owner@test.com")
        await create_user(db, manager_role.id, email="manager@test.com")
        worker = await create_user(db, worker_role.id, email="worker@test.com")

        # manager has no shared project with worker
        token = await get_auth_token(client, "manager@test.com", "password123")
        res = await client.get(f"/api/v1/users/{worker.id}", headers={"Authorization": f"Bearer {token}"})

        assert res.status_code == 404

    async def test_nonexistent_user_returns_404(self, client: AsyncClient, db: AsyncSession):
        owner_role = await create_role(db, "owner")
        await create_user(db, owner_role.id, email="owner@test.com")

        token = await get_auth_token(client, "owner@test.com", "password123")
        res = await client.get("/api/v1/users/99999", headers={"Authorization": f"Bearer {token}"})

        assert res.status_code == 404

    async def test_site_worker_forbidden(self, client: AsyncClient, db: AsyncSession):
        owner_role = await create_role(db, "owner")
        worker_role = await create_role(db, "site_worker")

        owner = await create_user(db, owner_role.id, email="owner@test.com")
        await create_user(db, worker_role.id, email="worker@test.com")

        token = await get_auth_token(client, "worker@test.com", "password123")
        res = await client.get(f"/api/v1/users/{owner.id}", headers={"Authorization": f"Bearer {token}"})

        assert res.status_code == 403

    async def test_unauthenticated(self, client: AsyncClient, db: AsyncSession):
        res = await client.get("/api/v1/users/1")
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /api/v1/users/{user_id}
# ---------------------------------------------------------------------------


class TestUpdateUser:
    async def test_owner_can_update_any_user(self, client: AsyncClient, db: AsyncSession):
        owner_role = await create_role(db, "owner")
        worker_role = await create_role(db, "site_worker")

        await create_user(db, owner_role.id, email="owner@test.com")
        worker = await create_user(db, worker_role.id, email="worker@test.com")

        token = await get_auth_token(client, "owner@test.com", "password123")
        res = await client.patch(
            f"/api/v1/users/{worker.id}",
            json={"first_name": "Updated"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert res.status_code == 200
        assert res.json()["first_name"] == "Updated"

    async def test_manager_can_update_shared_project_user(self, client: AsyncClient, db: AsyncSession):
        owner_role = await create_role(db, "owner")
        manager_role = await create_role(db, "project_manager")
        worker_role = await create_role(db, "site_worker")

        owner = await create_user(db, owner_role.id, email="owner@test.com")
        manager = await create_user(db, manager_role.id, email="manager@test.com")
        worker = await create_user(db, worker_role.id, email="worker@test.com")

        project = await create_project(db, owner.id)
        await assign_to_project(db, project.id, manager.id)
        await assign_to_project(db, project.id, worker.id)

        token = await get_auth_token(client, "manager@test.com", "password123")
        res = await client.patch(
            f"/api/v1/users/{worker.id}",
            json={"last_name": "Patched"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert res.status_code == 200
        assert res.json()["last_name"] == "Patched"

    async def test_manager_cannot_update_unrelated_user(self, client: AsyncClient, db: AsyncSession):
        owner_role = await create_role(db, "owner")
        manager_role = await create_role(db, "project_manager")
        worker_role = await create_role(db, "site_worker")

        await create_user(db, owner_role.id, email="owner@test.com")
        await create_user(db, manager_role.id, email="manager@test.com")
        worker = await create_user(db, worker_role.id, email="worker@test.com")

        token = await get_auth_token(client, "manager@test.com", "password123")
        res = await client.patch(
            f"/api/v1/users/{worker.id}",
            json={"first_name": "Hack"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert res.status_code == 404

    async def test_partial_update_only_changes_provided_fields(self, client: AsyncClient, db: AsyncSession):
        owner_role = await create_role(db, "owner")
        worker_role = await create_role(db, "site_worker")

        await create_user(db, owner_role.id, email="owner@test.com")
        worker = await create_user(db, worker_role.id, email="worker@test.com")

        token = await get_auth_token(client, "owner@test.com", "password123")
        res = await client.patch(
            f"/api/v1/users/{worker.id}",
            json={"first_name": "OnlyFirst"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert res.status_code == 200
        data = res.json()
        assert data["first_name"] == "OnlyFirst"
        assert data["last_name"] == "User"  # unchanged from create_user default

    async def test_update_nonexistent_user_returns_404(self, client: AsyncClient, db: AsyncSession):
        owner_role = await create_role(db, "owner")
        await create_user(db, owner_role.id, email="owner@test.com")

        token = await get_auth_token(client, "owner@test.com", "password123")
        res = await client.patch(
            "/api/v1/users/99999",
            json={"first_name": "Ghost"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert res.status_code == 404

    async def test_site_worker_forbidden(self, client: AsyncClient, db: AsyncSession):
        owner_role = await create_role(db, "owner")
        worker_role = await create_role(db, "site_worker")

        owner = await create_user(db, owner_role.id, email="owner@test.com")
        await create_user(db, worker_role.id, email="worker@test.com")

        token = await get_auth_token(client, "worker@test.com", "password123")
        res = await client.patch(
            f"/api/v1/users/{owner.id}",
            json={"first_name": "Hack"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert res.status_code == 403

    async def test_unauthenticated(self, client: AsyncClient, db: AsyncSession):
        res = await client.patch("/api/v1/users/1", json={"first_name": "X"})
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /api/v1/users/{user_id}/deactivate
# ---------------------------------------------------------------------------


class TestDeactivateUser:
    async def test_owner_can_deactivate_any_user(self, client: AsyncClient, db: AsyncSession):
        owner_role = await create_role(db, "owner")
        worker_role = await create_role(db, "site_worker")

        await create_user(db, owner_role.id, email="owner@test.com")
        worker = await create_user(db, worker_role.id, email="worker@test.com")

        token = await get_auth_token(client, "owner@test.com", "password123")
        res = await client.patch(
            f"/api/v1/users/{worker.id}/deactivate",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert res.status_code == 200
        assert res.json()["is_active"] is False

    async def test_manager_can_deactivate_own_created_worker(self, client: AsyncClient, db: AsyncSession):
        owner_role = await create_role(db, "owner")
        manager_role = await create_role(db, "project_manager")
        worker_role = await create_role(db, "site_worker")

        await create_user(db, owner_role.id, email="owner@test.com")
        manager = await create_user(db, manager_role.id, email="manager@test.com")
        worker = await create_user(
            db,
            worker_role.id,
            email="worker@test.com",
            created_by=manager.id,
        )

        token = await get_auth_token(client, "manager@test.com", "password123")
        res = await client.patch(
            f"/api/v1/users/{worker.id}/deactivate",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert res.status_code == 200
        assert res.json()["is_active"] is False

    async def test_manager_cannot_deactivate_worker_created_by_other(self, client: AsyncClient, db: AsyncSession):
        owner_role = await create_role(db, "owner")
        manager_role = await create_role(db, "project_manager")
        worker_role = await create_role(db, "site_worker")

        owner = await create_user(db, owner_role.id, email="owner@test.com")
        await create_user(db, manager_role.id, email="manager@test.com")
        # worker created by owner, not the manager
        worker = await create_user(
            db,
            worker_role.id,
            email="worker@test.com",
            created_by=owner.id,
        )

        token = await get_auth_token(client, "manager@test.com", "password123")
        res = await client.patch(
            f"/api/v1/users/{worker.id}/deactivate",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert res.status_code == 403

    async def test_manager_cannot_deactivate_another_manager(self, client: AsyncClient, db: AsyncSession):
        owner_role = await create_role(db, "owner")
        manager_role = await create_role(db, "project_manager")

        await create_user(db, owner_role.id, email="owner@test.com")
        manager = await create_user(db, manager_role.id, email="manager@test.com")
        manager2 = await create_user(db, manager_role.id, email="manager2@test.com", created_by=manager.id)

        token = await get_auth_token(client, "manager@test.com", "password123")
        res = await client.patch(
            f"/api/v1/users/{manager2.id}/deactivate",
            headers={"Authorization": f"Bearer {token}"},
        )

        # manager created manager2 but manager2 is not a site_worker — must be denied
        assert res.status_code == 403

    async def test_deactivate_nonexistent_user(self, client: AsyncClient, db: AsyncSession):
        owner_role = await create_role(db, "owner")
        await create_user(db, owner_role.id, email="owner@test.com")

        token = await get_auth_token(client, "owner@test.com", "password123")
        res = await client.patch(
            "/api/v1/users/99999/deactivate",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert res.status_code == 403  # set_user_active returns None → 403

    async def test_site_worker_forbidden(self, client: AsyncClient, db: AsyncSession):
        owner_role = await create_role(db, "owner")
        worker_role = await create_role(db, "site_worker")

        owner = await create_user(db, owner_role.id, email="owner@test.com")
        await create_user(db, worker_role.id, email="worker@test.com")

        token = await get_auth_token(client, "worker@test.com", "password123")
        res = await client.patch(
            f"/api/v1/users/{owner.id}/deactivate",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert res.status_code == 403

    async def test_unauthenticated(self, client: AsyncClient, db: AsyncSession):
        res = await client.patch("/api/v1/users/1/deactivate")
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /api/v1/users/{user_id}/activate
# ---------------------------------------------------------------------------


class TestActivateUser:
    async def test_owner_can_activate_inactive_user(self, client: AsyncClient, db: AsyncSession):
        owner_role = await create_role(db, "owner")
        worker_role = await create_role(db, "site_worker")

        await create_user(db, owner_role.id, email="owner@test.com")
        worker = await create_user(db, worker_role.id, email="worker@test.com", is_active=False)

        token = await get_auth_token(client, "owner@test.com", "password123")
        res = await client.patch(
            f"/api/v1/users/{worker.id}/activate",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert res.status_code == 200
        assert res.json()["is_active"] is True

    async def test_manager_can_activate_own_created_worker(self, client: AsyncClient, db: AsyncSession):
        owner_role = await create_role(db, "owner")
        manager_role = await create_role(db, "project_manager")
        worker_role = await create_role(db, "site_worker")

        await create_user(db, owner_role.id, email="owner@test.com")
        manager = await create_user(db, manager_role.id, email="manager@test.com")
        worker = await create_user(
            db,
            worker_role.id,
            email="worker@test.com",
            is_active=False,
            created_by=manager.id,
        )

        token = await get_auth_token(client, "manager@test.com", "password123")
        res = await client.patch(
            f"/api/v1/users/{worker.id}/activate",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert res.status_code == 200
        assert res.json()["is_active"] is True

    async def test_manager_cannot_activate_worker_created_by_other(self, client: AsyncClient, db: AsyncSession):
        owner_role = await create_role(db, "owner")
        manager_role = await create_role(db, "project_manager")
        worker_role = await create_role(db, "site_worker")

        owner = await create_user(db, owner_role.id, email="owner@test.com")
        await create_user(db, manager_role.id, email="manager@test.com")
        worker = await create_user(
            db,
            worker_role.id,
            email="worker@test.com",
            is_active=False,
            created_by=owner.id,
        )

        token = await get_auth_token(client, "manager@test.com", "password123")
        res = await client.patch(
            f"/api/v1/users/{worker.id}/activate",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert res.status_code == 403

    async def test_activate_nonexistent_user(self, client: AsyncClient, db: AsyncSession):
        owner_role = await create_role(db, "owner")
        await create_user(db, owner_role.id, email="owner@test.com")

        token = await get_auth_token(client, "owner@test.com", "password123")
        res = await client.patch(
            "/api/v1/users/99999/activate",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert res.status_code == 403

    async def test_site_worker_forbidden(self, client: AsyncClient, db: AsyncSession):
        owner_role = await create_role(db, "owner")
        worker_role = await create_role(db, "site_worker")

        owner = await create_user(db, owner_role.id, email="owner@test.com")
        await create_user(db, worker_role.id, email="worker@test.com")

        token = await get_auth_token(client, "worker@test.com", "password123")
        res = await client.patch(
            f"/api/v1/users/{owner.id}/activate",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert res.status_code == 403

    async def test_unauthenticated(self, client: AsyncClient, db: AsyncSession):
        res = await client.patch("/api/v1/users/1/activate")
        assert res.status_code == 401

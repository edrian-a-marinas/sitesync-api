from datetime import date

from httpx import AsyncClient

from app.models.project import Project, ProjectAssignment

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def create_project(session_factory, owner_id: int) -> Project:
    async with session_factory() as session:
        project = Project(
            owner_id=owner_id,
            name="Test Project",
            location="Manila",
            total_budget=1_000_000,
            start_date=date(2026, 1, 1),
            target_end_date=date(2026, 12, 31),
            status="Active",
        )
        session.add(project)
        await session.commit()
        await session.refresh(project)
        return project


async def assign_to_project(session_factory, project_id: int, user_id: int) -> None:
    async with session_factory() as session:
        assignment = ProjectAssignment(project_id=project_id, user_id=user_id)
        session.add(assignment)
        await session.commit()


# ---------------------------------------------------------------------------
# GET /api/v1/users
# ---------------------------------------------------------------------------


class TestListUsers:
    async def test_owner_sees_all_users(self, owner_client: AsyncClient, seed_users):
        res = await owner_client.get("/api/v1/users")
        assert res.status_code == 200
        emails = [u["email"] for u in res.json()]
        assert "owner@test.com" in emails
        assert "manager@test.com" in emails
        assert "worker@test.com" in emails

    async def test_manager_sees_only_shared_project_users(self, manager_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        await assign_to_project(test_session_factory, project.id, seed_users["manager"].id)
        await assign_to_project(test_session_factory, project.id, seed_users["worker"].id)

        res = await manager_client.get("/api/v1/users")
        assert res.status_code == 200
        emails = [u["email"] for u in res.json()]
        assert "worker@test.com" in emails

    async def test_site_worker_forbidden(self, worker_client: AsyncClient, seed_users):
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

    async def test_manager_can_get_shared_project_user(self, manager_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        await assign_to_project(test_session_factory, project.id, seed_users["manager"].id)
        await assign_to_project(test_session_factory, project.id, seed_users["worker"].id)

        res = await manager_client.get(f"/api/v1/users/{seed_users['worker'].id}")
        assert res.status_code == 200
        assert res.json()["email"] == "worker@test.com"

    async def test_manager_cannot_get_unrelated_user(self, manager_client: AsyncClient, seed_users):
        # No shared project between manager and worker
        res = await manager_client.get(f"/api/v1/users/{seed_users['worker'].id}")
        assert res.status_code == 404

    async def test_nonexistent_user_returns_404(self, owner_client: AsyncClient, seed_users):
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
    async def test_owner_can_update_any_user(self, owner_client: AsyncClient, seed_users):
        res = await owner_client.patch(
            f"/api/v1/users/{seed_users['worker'].id}",
            json={"first_name": "Updated"},
        )
        assert res.status_code == 200
        assert res.json()["first_name"] == "Updated"

    async def test_manager_can_update_shared_project_user(self, manager_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        await assign_to_project(test_session_factory, project.id, seed_users["manager"].id)
        await assign_to_project(test_session_factory, project.id, seed_users["worker"].id)

        res = await manager_client.patch(
            f"/api/v1/users/{seed_users['worker'].id}",
            json={"last_name": "Patched"},
        )
        assert res.status_code == 200
        assert res.json()["last_name"] == "Patched"

    async def test_manager_cannot_update_unrelated_user(self, manager_client: AsyncClient, seed_users):
        res = await manager_client.patch(
            f"/api/v1/users/{seed_users['worker'].id}",
            json={"first_name": "Hack"},
        )
        assert res.status_code == 404

    async def test_partial_update_only_changes_provided_fields(self, owner_client: AsyncClient, seed_users):
        # First get current last_name to avoid depending on mutation order
        get_res = await owner_client.get(f"/api/v1/users/{seed_users['worker'].id}")
        original_last_name = get_res.json()["last_name"]

        res = await owner_client.patch(
            f"/api/v1/users/{seed_users['worker'].id}",
            json={"first_name": "OnlyFirst"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["first_name"] == "OnlyFirst"
        assert data["last_name"] == original_last_name

    async def test_update_nonexistent_user_returns_404(self, owner_client: AsyncClient, seed_users):
        res = await owner_client.patch(
            "/api/v1/users/99999",
            json={"first_name": "Ghost"},
        )
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
    async def test_owner_can_deactivate_any_user(self, owner_client: AsyncClient, seed_users):
        res = await owner_client.patch(f"/api/v1/users/{seed_users['worker'].id}/deactivate")
        assert res.status_code == 200
        assert res.json()["is_active"] is False

    async def test_manager_can_deactivate_own_created_worker(self, manager_client: AsyncClient, seed_users, test_session_factory):
        # Create a worker created_by the manager
        from app.core.security import hash_password
        from app.models.user import User

        async with test_session_factory() as session:
            worker = User(
                email="created_worker@test.com",
                password_hash=hash_password("password123"),
                first_name="Created",
                last_name="Worker",
                role_id=seed_users["worker_role"].id,
                is_active=True,
                created_by=seed_users["manager"].id,
            )
            session.add(worker)
            await session.commit()
            await session.refresh(worker)

        res = await manager_client.patch(f"/api/v1/users/{worker.id}/deactivate")
        assert res.status_code == 200
        assert res.json()["is_active"] is False

    async def test_manager_cannot_deactivate_worker_created_by_other(self, manager_client: AsyncClient, seed_users, test_session_factory):
        # Worker created by owner, not manager
        from app.core.security import hash_password
        from app.models.user import User

        async with test_session_factory() as session:
            worker = User(
                email="owner_created_worker@test.com",
                password_hash=hash_password("password123"),
                first_name="Owner",
                last_name="Created",
                role_id=seed_users["worker_role"].id,
                is_active=True,
                created_by=seed_users["owner"].id,
            )
            session.add(worker)
            await session.commit()
            await session.refresh(worker)

        res = await manager_client.patch(f"/api/v1/users/{worker.id}/deactivate")
        assert res.status_code == 403

    async def test_manager_cannot_deactivate_another_manager(self, manager_client: AsyncClient, seed_users, test_session_factory):
        from app.core.security import hash_password
        from app.models.user import User

        async with test_session_factory() as session:
            manager2 = User(
                email="manager2@test.com",
                password_hash=hash_password("password123"),
                first_name="Manager",
                last_name="Two",
                role_id=seed_users["manager_role"].id,
                is_active=True,
                created_by=seed_users["manager"].id,
            )
            session.add(manager2)
            await session.commit()
            await session.refresh(manager2)

        res = await manager_client.patch(f"/api/v1/users/{manager2.id}/deactivate")
        assert res.status_code == 403

    async def test_deactivate_nonexistent_user(self, owner_client: AsyncClient, seed_users):
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
    async def test_owner_can_activate_inactive_user(self, owner_client: AsyncClient, seed_users, test_session_factory):
        from app.core.security import hash_password
        from app.models.user import User

        async with test_session_factory() as session:
            worker = User(
                email="inactive_worker@test.com",
                password_hash=hash_password("password123"),
                first_name="Inactive",
                last_name="Worker",
                role_id=seed_users["worker_role"].id,
                is_active=False,
            )
            session.add(worker)
            await session.commit()
            await session.refresh(worker)

        res = await owner_client.patch(f"/api/v1/users/{worker.id}/activate")
        assert res.status_code == 200
        assert res.json()["is_active"] is True

    async def test_manager_can_activate_own_created_worker(self, manager_client: AsyncClient, seed_users, test_session_factory):
        from app.core.security import hash_password
        from app.models.user import User

        async with test_session_factory() as session:
            worker = User(
                email="inactive_created_worker@test.com",
                password_hash=hash_password("password123"),
                first_name="Inactive",
                last_name="Created",
                role_id=seed_users["worker_role"].id,
                is_active=False,
                created_by=seed_users["manager"].id,
            )
            session.add(worker)
            await session.commit()
            await session.refresh(worker)

        res = await manager_client.patch(f"/api/v1/users/{worker.id}/activate")
        assert res.status_code == 200
        assert res.json()["is_active"] is True

    async def test_manager_cannot_activate_worker_created_by_other(self, manager_client: AsyncClient, seed_users, test_session_factory):
        from app.core.security import hash_password
        from app.models.user import User

        async with test_session_factory() as session:
            worker = User(
                email="other_inactive_worker@test.com",
                password_hash=hash_password("password123"),
                first_name="Other",
                last_name="Inactive",
                role_id=seed_users["worker_role"].id,
                is_active=False,
                created_by=seed_users["owner"].id,
            )
            session.add(worker)
            await session.commit()
            await session.refresh(worker)

        res = await manager_client.patch(f"/api/v1/users/{worker.id}/activate")
        assert res.status_code == 403

    async def test_activate_nonexistent_user(self, owner_client: AsyncClient, seed_users):
        res = await owner_client.patch("/api/v1/users/99999/activate")
        assert res.status_code == 403

    async def test_site_worker_forbidden(self, worker_client: AsyncClient, seed_users):
        res = await worker_client.patch(f"/api/v1/users/{seed_users['owner'].id}/activate")
        assert res.status_code == 403

    async def test_unauthenticated(self, unauth_client: AsyncClient):
        res = await unauth_client.patch("/api/v1/users/1/activate")
        assert res.status_code == 401

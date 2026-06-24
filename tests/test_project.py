from datetime import date

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete

from app.models.project import Project, ProjectAssignment, ProjectPhase, WorkerAssignment

PROJECT_PAYLOAD = {
    "name": "Test Project",
    "location": "Manila",
    "total_budget": 1000000.0,
    "start_date": "2026-01-01",
    "target_end_date": "2026-12-31",
    "status": "Active",
}

# ---------------------------------------------------------------------------
# Session-scoped seeds
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def seed_project_data(test_session_factory, seed_users):
    """One owner project, one assigned to manager — reused across all project tests."""
    async with test_session_factory() as session:
        async with session.begin():
            owner_project = Project(
                owner_id=seed_users["owner"].id,
                name="Owner Project",
                location="Manila",
                total_budget=1_000_000,
                start_date=date(2026, 1, 1),
                target_end_date=date(2026, 12, 31),
                status="Active",
            )
            unassigned_project = Project(
                owner_id=seed_users["owner"].id,
                name="Unassigned Project",
                location="Manila",
                total_budget=500_000,
                start_date=date(2026, 1, 1),
                target_end_date=date(2026, 12, 31),
                status="Active",
            )
            session.add_all([owner_project, unassigned_project])
            await session.flush()
            session.add(
                ProjectAssignment(
                    project_id=owner_project.id,
                    user_id=seed_users["manager"].id,
                )
            )
    yield {
        "owner_project": owner_project,
        "unassigned_project": unassigned_project,
    }
    async with test_session_factory() as session:
        async with session.begin():
            await session.execute(delete(ProjectPhase).where(ProjectPhase.project_id.in_([owner_project.id, unassigned_project.id])))
            await session.execute(delete(ProjectAssignment).where(ProjectAssignment.project_id.in_([owner_project.id, unassigned_project.id])))
            await session.execute(delete(WorkerAssignment).where(WorkerAssignment.project_id.in_([owner_project.id, unassigned_project.id])))
            await session.execute(delete(Project).where(Project.id.in_([owner_project.id, unassigned_project.id])))


# ---------------------------------------------------------------------------
# POST /api/v1/projects
# ---------------------------------------------------------------------------


class TestProjectCreate:
    async def test_owner_can_create(self, owner_client: AsyncClient):
        res = await owner_client.post("/api/v1/projects", json=PROJECT_PAYLOAD)
        assert res.status_code == 201
        assert res.json()["name"] == "Test Project"

    async def test_manager_cannot_create(self, manager_client: AsyncClient):
        res = await manager_client.post("/api/v1/projects", json=PROJECT_PAYLOAD)
        assert res.status_code == 403

    async def test_unauthenticated(self, unauth_client: AsyncClient):
        res = await unauth_client.post("/api/v1/projects", json=PROJECT_PAYLOAD)
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/v1/projects
# ---------------------------------------------------------------------------


class TestProjectList:
    async def test_owner_sees_all(self, owner_client: AsyncClient, seed_project_data):
        res = await owner_client.get("/api/v1/projects")
        assert res.status_code == 200
        ids = [p["id"] for p in res.json()]
        assert seed_project_data["owner_project"].id in ids
        assert seed_project_data["unassigned_project"].id in ids

    async def test_manager_sees_only_assigned(self, manager_client: AsyncClient, seed_project_data):
        res = await manager_client.get("/api/v1/projects")
        assert res.status_code == 200
        ids = [p["id"] for p in res.json()]
        assert seed_project_data["owner_project"].id in ids
        assert seed_project_data["unassigned_project"].id not in ids

    async def test_unauthenticated(self, unauth_client: AsyncClient):
        res = await unauth_client.get("/api/v1/projects")
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/v1/projects/{project_id}
# ---------------------------------------------------------------------------


class TestProjectGet:
    async def test_owner_can_get(self, owner_client: AsyncClient, seed_project_data):
        pid = seed_project_data["owner_project"].id
        res = await owner_client.get(f"/api/v1/projects/{pid}")
        assert res.status_code == 200
        assert res.json()["id"] == pid

    async def test_not_found(self, owner_client: AsyncClient):
        res = await owner_client.get("/api/v1/projects/99999")
        assert res.status_code == 404

    async def test_manager_access_denied_unassigned(self, manager_client: AsyncClient, seed_project_data):
        pid = seed_project_data["unassigned_project"].id
        res = await manager_client.get(f"/api/v1/projects/{pid}")
        assert res.status_code == 404

    async def test_manager_can_get_assigned(self, manager_client: AsyncClient, seed_project_data):
        pid = seed_project_data["owner_project"].id
        res = await manager_client.get(f"/api/v1/projects/{pid}")
        assert res.status_code == 200

    async def test_unauthenticated(self, unauth_client: AsyncClient, seed_project_data):
        pid = seed_project_data["owner_project"].id
        res = await unauth_client.get(f"/api/v1/projects/{pid}")
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /api/v1/projects/{project_id}
# ---------------------------------------------------------------------------


class TestProjectUpdate:
    async def test_owner_can_update(self, owner_client: AsyncClient, seed_project_data):
        pid = seed_project_data["owner_project"].id
        res = await owner_client.patch(f"/api/v1/projects/{pid}", json={"status": "On Hold"})
        assert res.status_code == 200
        assert res.json()["status"] == "On Hold"
        # restore
        await owner_client.patch(f"/api/v1/projects/{pid}", json={"status": "Active"})

    async def test_manager_cannot_update(self, manager_client: AsyncClient, seed_project_data):
        pid = seed_project_data["owner_project"].id
        res = await manager_client.patch(f"/api/v1/projects/{pid}", json={"status": "Completed"})
        assert res.status_code == 403

    async def test_not_found(self, owner_client: AsyncClient):
        res = await owner_client.patch("/api/v1/projects/99999", json={"status": "Completed"})
        assert res.status_code == 404

    async def test_unauthenticated(self, unauth_client: AsyncClient, seed_project_data):
        pid = seed_project_data["owner_project"].id
        res = await unauth_client.patch(f"/api/v1/projects/{pid}", json={"status": "Completed"})
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/v1/projects/{project_id}/assign-manager
# ---------------------------------------------------------------------------


class TestAssignManager:
    async def test_assign_valid_manager(self, owner_client: AsyncClient, seed_project_data, seed_users):
        pid = seed_project_data["unassigned_project"].id
        res = await owner_client.post(
            f"/api/v1/projects/{pid}/assign-manager",
            json={"user_id": seed_users["manager"].id},
        )
        assert res.status_code == 200
        assert res.json()["message"] == "Manager assigned successfully"

    async def test_assign_non_manager_fails(self, owner_client: AsyncClient, seed_project_data, seed_users):
        pid = seed_project_data["owner_project"].id
        res = await owner_client.post(
            f"/api/v1/projects/{pid}/assign-manager",
            json={"user_id": seed_users["worker"].id},
        )
        assert res.status_code == 400

    async def test_unauthenticated(self, unauth_client: AsyncClient, seed_project_data, seed_users):
        pid = seed_project_data["owner_project"].id
        res = await unauth_client.post(
            f"/api/v1/projects/{pid}/assign-manager",
            json={"user_id": seed_users["manager"].id},
        )
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/v1/projects/{project_id}/phases
# PATCH /api/v1/projects/{project_id}/phases/{phase_id}
# ---------------------------------------------------------------------------


class TestPhases:
    async def test_create_phase(self, owner_client: AsyncClient, seed_project_data):
        pid = seed_project_data["owner_project"].id
        res = await owner_client.post(
            f"/api/v1/projects/{pid}/phases",
            json={"name": "Foundation", "allocated_budget": 500000.0, "status": "Not Started"},
        )
        assert res.status_code == 201
        assert res.json()["name"] == "Foundation"

    async def test_update_phase(self, owner_client: AsyncClient, seed_project_data):
        pid = seed_project_data["owner_project"].id
        create_res = await owner_client.post(
            f"/api/v1/projects/{pid}/phases",
            json={"name": "Structure", "allocated_budget": 300000.0, "status": "Not Started"},
        )
        phase_id = create_res.json()["id"]
        res = await owner_client.patch(
            f"/api/v1/projects/{pid}/phases/{phase_id}",
            json={"status": "In Progress"},
        )
        assert res.status_code == 200
        assert res.json()["status"] == "In Progress"

    async def test_manager_cannot_create_phase(self, manager_client: AsyncClient, seed_project_data):
        pid = seed_project_data["owner_project"].id
        res = await manager_client.post(
            f"/api/v1/projects/{pid}/phases",
            json={"name": "Finishing", "allocated_budget": 200000.0, "status": "Not Started"},
        )
        assert res.status_code == 403

    async def test_unauthenticated_cannot_create_phase(self, unauth_client: AsyncClient, seed_project_data):
        pid = seed_project_data["owner_project"].id
        res = await unauth_client.post(
            f"/api/v1/projects/{pid}/phases",
            json={"name": "Finishing", "allocated_budget": 200000.0, "status": "Not Started"},
        )
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /api/v1/projects/{project_id}
# ---------------------------------------------------------------------------
class TestProjectDelete:
    async def test_owner_can_delete(self, owner_client: AsyncClient, seed_users):
        # Create a fresh project to delete
        res = await owner_client.post("/api/v1/projects", json=PROJECT_PAYLOAD)
        assert res.status_code == 201
        pid = res.json()["id"]

        delete_res = await owner_client.delete(f"/api/v1/projects/{pid}")
        assert delete_res.status_code == 204

    async def test_manager_cannot_delete(self, manager_client: AsyncClient, seed_project_data):
        pid = seed_project_data["owner_project"].id
        res = await manager_client.delete(f"/api/v1/projects/{pid}")
        assert res.status_code == 403

    async def test_not_found(self, owner_client: AsyncClient):
        res = await owner_client.delete("/api/v1/projects/99999")
        assert res.status_code == 404

    async def test_unauthenticated(self, unauth_client: AsyncClient, seed_project_data):
        pid = seed_project_data["owner_project"].id
        res = await unauth_client.delete(f"/api/v1/projects/{pid}")
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /api/v1/projects/{project_id}/unassign
# ---------------------------------------------------------------------------
class TestUnassignUser:
    async def test_owner_can_unassign_manager(self, owner_client: AsyncClient, seed_users):
        # create a fresh project
        create_res = await owner_client.post("/api/v1/projects", json=PROJECT_PAYLOAD)
        assert create_res.status_code == 201
        pid = create_res.json()["id"]

        await owner_client.post(
            f"/api/v1/projects/{pid}/assign-manager",
            json={"user_id": seed_users["manager"].id},
        )
        res = await owner_client.delete(
            f"/api/v1/projects/{pid}/unassign",
            params={"user_id": seed_users["manager"].id, "type": "manager"},
        )
        assert res.status_code == 204

        # cleanup
        await owner_client.delete(f"/api/v1/projects/{pid}")

    async def test_owner_can_unassign_worker(self, owner_client: AsyncClient, seed_project_data, seed_users):
        pid = seed_project_data["owner_project"].id
        # first assign
        await owner_client.post(
            f"/api/v1/projects/{pid}/assign-worker",
            json={"user_id": seed_users["worker"].id},
        )
        res = await owner_client.delete(
            f"/api/v1/projects/{pid}/unassign",
            params={"user_id": seed_users["worker"].id, "type": "worker"},
        )
        assert res.status_code == 204

    async def test_not_found(self, owner_client: AsyncClient, seed_project_data):
        pid = seed_project_data["owner_project"].id
        res = await owner_client.delete(
            f"/api/v1/projects/{pid}/unassign",
            params={"user_id": 99999, "type": "manager"},
        )
        assert res.status_code == 404

    async def test_manager_cannot_unassign(self, manager_client: AsyncClient, seed_project_data, seed_users):
        pid = seed_project_data["owner_project"].id
        res = await manager_client.delete(
            f"/api/v1/projects/{pid}/unassign",
            params={"user_id": seed_users["worker"].id, "type": "worker"},
        )
        assert res.status_code == 403

    async def test_unauthenticated(self, unauth_client: AsyncClient, seed_project_data, seed_users):
        pid = seed_project_data["owner_project"].id
        res = await unauth_client.delete(
            f"/api/v1/projects/{pid}/unassign",
            params={"user_id": seed_users["manager"].id, "type": "manager"},
        )
        assert res.status_code == 401

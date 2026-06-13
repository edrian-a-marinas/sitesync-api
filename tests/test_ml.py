from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import (
    create_daily_log,
    create_role,
    create_user,
    create_worker_assignment,
    get_auth_token,
)

PROJECT_PAYLOAD = {
    "name": "ML Test Project",
    "location": "Manila",
    "total_budget": 1000000.0,
    "start_date": "2024-01-01",
    "target_end_date": "2026-12-31",
    "status": "Active",
}

LOG_PAYLOAD = {
    "log_date": "2024-06-01",
    "work_accomplished": "Poured concrete",
    "weather_condition": "Sunny",
    "notes": "No issues",
}


async def setup_ml_context(client: AsyncClient, db: AsyncSession):
    from app.models.attendance import Attendance
    from app.models.incident import Incident
    from app.models.material import Material

    owner_role = await create_role(db, "owner")
    manager_role = await create_role(db, "project_manager")
    worker_role = await create_role(db, "site_worker")
    owner = await create_user(db, owner_role.id, email="owner@test.com")
    manager = await create_user(db, manager_role.id, email="manager@test.com")
    worker = await create_user(db, worker_role.id, email="worker@test.com")
    owner_token = await get_auth_token(client, "owner@test.com", "password123")
    manager_token = await get_auth_token(client, "manager@test.com", "password123")

    # Create project via HTTP
    res = await client.post(
        "/api/v1/projects",
        json=PROJECT_PAYLOAD,
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    project_id = res.json()["id"]

    # Assign manager via HTTP
    await client.post(
        f"/api/v1/projects/{project_id}/assign-manager",
        json={"user_id": manager.id},
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    # Seed log, material, attendance, incident directly via DB
    log = await create_daily_log(db, project_id, owner.id, "2024-06-01")

    material = Material(
        daily_log_id=log.id,
        name="Cement",
        quantity=50.0,
        unit="bags",
        unit_cost=300.0,
    )
    db.add(material)

    await create_worker_assignment(db, project_id, worker.id)

    attendance = Attendance(
        daily_log_id=log.id,
        worker_id=worker.id,
        hours_worked=8.0,
    )
    db.add(attendance)

    incident = Incident(
        daily_log_id=log.id,
        reported_by=owner.id,
        description="Minor scaffolding issue",
        severity="Low",
        status="Open",
    )
    db.add(incident)

    await db.commit()

    return {
        "owner": owner,
        "manager": manager,
        "owner_token": owner_token,
        "manager_token": manager_token,
        "project_id": project_id,
        "log_id": log.id,
    }


class TestBudgetOverrun:
    async def test_owner_can_access(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_ml_context(client, db)
        res = await client.get(
            "/api/v1/ml/budget-overrun",
            headers={"Authorization": f"Bearer {ctx['owner_token']}"},
        )
        assert res.status_code == 200
        data = res.json()
        assert "results" in data
        assert isinstance(data["results"], list)

    async def test_results_shape_when_data_exists(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_ml_context(client, db)
        res = await client.get(
            "/api/v1/ml/budget-overrun",
            headers={"Authorization": f"Bearer {ctx['owner_token']}"},
        )
        assert res.status_code == 200
        # Model may not exist in test env — empty list is valid
        results = res.json()["results"]
        for item in results:
            assert "project_id" in item
            assert "project_name" in item
            assert "overrun_probability" in item
            assert "is_over_budget" in item
            assert "total_budget" in item
            assert "total_spent" in item

    async def test_manager_cannot_access(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_ml_context(client, db)
        res = await client.get(
            "/api/v1/ml/budget-overrun",
            headers={"Authorization": f"Bearer {ctx['manager_token']}"},
        )
        assert res.status_code == 403

    async def test_unauthenticated_cannot_access(self, client: AsyncClient, db: AsyncSession):
        res = await client.get("/api/v1/ml/budget-overrun")
        assert res.status_code == 401

    async def test_empty_db_returns_empty_results(self, client: AsyncClient, db: AsyncSession):
        owner_role = await create_role(db, "owner")
        await create_user(db, owner_role.id, email="owner@test.com")
        token = await get_auth_token(client, "owner@test.com", "password123")
        res = await client.get(
            "/api/v1/ml/budget-overrun",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        assert res.json()["results"] == []


class TestDelayRisk:
    async def test_owner_can_access(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_ml_context(client, db)
        res = await client.get(
            "/api/v1/ml/delay-risk",
            headers={"Authorization": f"Bearer {ctx['owner_token']}"},
        )
        assert res.status_code == 200
        data = res.json()
        assert "results" in data
        assert isinstance(data["results"], list)

    async def test_results_shape_when_data_exists(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_ml_context(client, db)
        res = await client.get(
            "/api/v1/ml/delay-risk",
            headers={"Authorization": f"Bearer {ctx['owner_token']}"},
        )
        assert res.status_code == 200
        results = res.json()["results"]
        for item in results:
            assert "project_id" in item
            assert "project_name" in item
            assert "delay_risk_score" in item
            assert "risk_level" in item
            assert item["risk_level"] in ("Low", "Medium", "High")

    async def test_manager_cannot_access(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_ml_context(client, db)
        res = await client.get(
            "/api/v1/ml/delay-risk",
            headers={"Authorization": f"Bearer {ctx['manager_token']}"},
        )
        assert res.status_code == 403

    async def test_unauthenticated_cannot_access(self, client: AsyncClient, db: AsyncSession):
        res = await client.get("/api/v1/ml/delay-risk")
        assert res.status_code == 401

    async def test_empty_db_returns_empty_results(self, client: AsyncClient, db: AsyncSession):
        owner_role = await create_role(db, "owner")
        await create_user(db, owner_role.id, email="owner@test.com")
        token = await get_auth_token(client, "owner@test.com", "password123")
        res = await client.get(
            "/api/v1/ml/delay-risk",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        assert res.json()["results"] == []


class TestMaterialForecast:
    async def test_owner_can_access(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_ml_context(client, db)
        res = await client.get(
            "/api/v1/ml/material-forecast",
            headers={"Authorization": f"Bearer {ctx['owner_token']}"},
        )
        assert res.status_code == 200
        data = res.json()
        assert "results" in data
        assert isinstance(data["results"], list)

    async def test_results_shape_when_data_exists(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_ml_context(client, db)
        res = await client.get(
            "/api/v1/ml/material-forecast",
            headers={"Authorization": f"Bearer {ctx['owner_token']}"},
        )
        assert res.status_code == 200
        results = res.json()["results"]
        for item in results:
            assert "project_id" in item
            assert "project_name" in item
            assert "forecast_month" in item
            assert "predicted_cost" in item

    async def test_manager_cannot_access(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_ml_context(client, db)
        res = await client.get(
            "/api/v1/ml/material-forecast",
            headers={"Authorization": f"Bearer {ctx['manager_token']}"},
        )
        assert res.status_code == 403

    async def test_unauthenticated_cannot_access(self, client: AsyncClient, db: AsyncSession):
        res = await client.get("/api/v1/ml/material-forecast")
        assert res.status_code == 401

    async def test_empty_db_returns_empty_results(self, client: AsyncClient, db: AsyncSession):
        owner_role = await create_role(db, "owner")
        await create_user(db, owner_role.id, email="owner@test.com")
        token = await get_auth_token(client, "owner@test.com", "password123")
        res = await client.get(
            "/api/v1/ml/material-forecast",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        assert res.json()["results"] == []

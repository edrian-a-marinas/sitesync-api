from unittest.mock import patch

from httpx import AsyncClient


class TestBudgetOverrun:
    async def test_owner_can_access(self, owner_client: AsyncClient, seed_users):
        with patch("app.services.ml.predict_budget_overrun", return_value=[]):
            res = await owner_client.get("/api/v1/ml/budget-overrun")
        assert res.status_code == 200
        assert "results" in res.json()

    async def test_manager_cannot_access(self, manager_client: AsyncClient, seed_users):
        res = await manager_client.get("/api/v1/ml/budget-overrun")
        assert res.status_code == 403

    async def test_unauthenticated_cannot_access(self, unauth_client: AsyncClient, seed_users):
        res = await unauth_client.get("/api/v1/ml/budget-overrun")
        assert res.status_code == 401

    async def test_returns_correct_schema(self, owner_client: AsyncClient, seed_users):
        mock_result = [
            {
                "project_id": 1,
                "project_name": "Test Project",
                "overrun_probability": 0.85,
                "is_over_budget": True,
                "total_budget": 1000000.0,
                "total_spent": 1200000.0,
            }
        ]
        with patch("app.services.ml.predict_budget_overrun", return_value=mock_result), patch("app.services.ml.get_cache", return_value=None):
            res = await owner_client.get("/api/v1/ml/budget-overrun")
        assert res.status_code == 200
        result = res.json()["results"][0]
        assert "project_id" in result
        assert "overrun_probability" in result
        assert "is_over_budget" in result


class TestDelayRisk:
    async def test_owner_can_access(self, owner_client: AsyncClient, seed_users):
        with patch("app.services.ml.predict_delay_risk", return_value=[]):
            res = await owner_client.get("/api/v1/ml/delay-risk")
        assert res.status_code == 200
        assert "results" in res.json()

    async def test_manager_cannot_access(self, manager_client: AsyncClient, seed_users):
        res = await manager_client.get("/api/v1/ml/delay-risk")
        assert res.status_code == 403

    async def test_unauthenticated_cannot_access(self, unauth_client: AsyncClient, seed_users):
        res = await unauth_client.get("/api/v1/ml/delay-risk")
        assert res.status_code == 401

    async def test_returns_correct_schema(self, owner_client: AsyncClient, seed_users):
        mock_result = [
            {
                "project_id": 1,
                "project_name": "Test Project",
                "delay_risk_score": 0.72,
                "risk_level": "High",
            }
        ]
        with patch("app.services.ml.predict_delay_risk", return_value=mock_result), patch("app.services.ml.get_cache", return_value=None):
            res = await owner_client.get("/api/v1/ml/delay-risk")
        assert res.status_code == 200
        result = res.json()["results"][0]
        assert "delay_risk_score" in result
        assert "risk_level" in result
        assert result["risk_level"] in ["Low", "Medium", "High"]


class TestMaterialForecast:
    async def test_owner_can_access(self, owner_client: AsyncClient, seed_users):
        with patch("app.services.ml.predict_material_forecast", return_value=[]):
            res = await owner_client.get("/api/v1/ml/material-forecast")
        assert res.status_code == 200
        assert "results" in res.json()

    async def test_manager_cannot_access(self, manager_client: AsyncClient, seed_users):
        res = await manager_client.get("/api/v1/ml/material-forecast")
        assert res.status_code == 403

    async def test_unauthenticated_cannot_access(self, unauth_client: AsyncClient, seed_users):
        res = await unauth_client.get("/api/v1/ml/material-forecast")
        assert res.status_code == 401

    async def test_returns_correct_schema(self, owner_client: AsyncClient, seed_users):
        mock_result = [
            {
                "project_id": 1,
                "project_name": "Test Project",
                "forecast_month": 7,
                "predicted_cost": 250000.0,
            }
        ]
        with patch("app.services.ml.predict_material_forecast", return_value=mock_result), patch("app.services.ml.get_cache", return_value=None):
            res = await owner_client.get("/api/v1/ml/material-forecast")
        assert res.status_code == 200
        result = res.json()["results"][0]
        assert "forecast_month" in result
        assert "predicted_cost" in result

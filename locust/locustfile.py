"""
SiteSync Load Test
==================
Simulates realistic Owner and Project Manager traffic against the SiteSync API.

Usage:
    locust -f locust/locustfile.py --host=http://localhost:8000

Web UI:
    Open http://localhost:8089 after starting Locust.
    Set users=500, spawn rate=10, then start.

Headless (CI / scripted):
    locust -f locust/locustfile.py --host=http://localhost:8000 \
           --headless -u 500 -r 10 --run-time 60s \
           --csv=locust/results/run

Credentials used are from the seeded dataset (alembic seed migrations).
"""

import random

from locust import HttpUser, between, task

# ---------------------------------------------------------------------------
# Owner user — full cross-project access, dashboard, AI queries
# ---------------------------------------------------------------------------


class OwnerUser(HttpUser):
    """
    Simulates the construction company owner.
    High read volume on dashboard and project overview.
    Occasional AI query submission.
    """

    wait_time = between(1, 3)
    weight = 1  # 1 owner per simulation

    def on_start(self):
        """Authenticate once at session start and store the JWT."""
        res = self.client.post(
            "/api/v1/auth/login",
            json={"email": "seed.owner@gmail.com", "password": "test1234"},
        )
        if res.status_code == 200:
            token = res.json().get("access_token", "")
            self.headers = {"Authorization": f"Bearer {token}"}
            self.project_ids = []
            self._load_projects()
        else:
            self.headers = {}
            self.project_ids = []

    def _load_projects(self):
        """Fetch project IDs once so task methods can use real IDs."""
        res = self.client.get("/api/v1/projects", headers=self.headers)
        if res.status_code == 200:
            self.project_ids = [p["id"] for p in res.json()]

    @task(5)
    def get_owner_dashboard(self):
        self.client.get(
            "/api/v1/dashboard/owner",
            headers=self.headers,
            name="/api/v1/dashboard/owner",
        )

    @task(4)
    def list_projects(self):
        self.client.get(
            "/api/v1/projects",
            headers=self.headers,
            name="/api/v1/projects",
        )

    @task(3)
    def get_project_detail(self):
        if not self.project_ids:
            return
        project_id = random.choice(self.project_ids)
        self.client.get(
            f"/api/v1/projects/{project_id}",
            headers=self.headers,
            name="/api/v1/projects/[id]",
        )

    @task(3)
    def list_daily_logs(self):
        if not self.project_ids:
            return
        project_id = random.choice(self.project_ids)
        self.client.get(
            f"/api/v1/projects/{project_id}/daily-logs",
            headers=self.headers,
            name="/api/v1/projects/[id]/daily-logs",
        )

    @task(2)
    def list_reports(self):
        if not self.project_ids:
            return
        project_id = random.choice(self.project_ids)
        self.client.get(
            f"/api/v1/reports/{project_id}",
            headers=self.headers,
            name="/api/v1/reports/[id]",
        )

    @task(2)
    def list_users(self):
        self.client.get(
            "/api/v1/users",
            headers=self.headers,
            name="/api/v1/users",
        )

    @task(1)
    def submit_ai_query(self):
        questions = [
            "Which project consumed the most cement this month?",
            "Which site had the most incidents this quarter?",
            "Which phase is currently most over budget?",
            "What is the total material cost across all projects?",
            "Which project has the lowest workforce attendance rate?",
        ]
        self.client.post(
            "/api/v1/ai/query",
            json={"question": random.choice(questions), "project_id": None},
            headers=self.headers,
            name="/api/v1/ai/query",
        )

    @task(1)
    def get_ml_predictions(self):
        if not self.project_ids:
            return
        project_id = random.choice(self.project_ids)
        self.client.get(
            f"/api/v1/ml/predict/{project_id}",
            headers=self.headers,
            name="/api/v1/ml/predict/[id]",
        )


# ---------------------------------------------------------------------------
# Project Manager user — assigned project access, daily log management
# ---------------------------------------------------------------------------


class ManagerUser(HttpUser):
    """
    Simulates a Project Manager on an assigned site.
    Primarily reads logs and dashboard, occasionally submits attendance/materials.
    """

    wait_time = between(2, 5)
    weight = 3  # 3 managers per 1 owner in simulation

    def on_start(self):
        res = self.client.post(
            "/api/v1/auth/login",
            json={"email": "seed.project_manager@gmail.com", "password": "test1234"},
        )
        if res.status_code == 200:
            token = res.json().get("access_token", "")
            self.headers = {"Authorization": f"Bearer {token}"}
            self.project_ids = []
            self.log_ids: dict[int, list[int]] = {}
            self._load_projects()
        else:
            self.headers = {}
            self.project_ids = []
            self.log_ids = {}

    def _load_projects(self):
        res = self.client.get("/api/v1/projects", headers=self.headers)
        if res.status_code == 200:
            self.project_ids = [p["id"] for p in res.json()]
            for pid in self.project_ids:
                self._load_logs(pid)

    def _load_logs(self, project_id: int):
        res = self.client.get(
            f"/api/v1/projects/{project_id}/daily-logs",
            headers=self.headers,
        )
        if res.status_code == 200:
            self.log_ids[project_id] = [log["id"] for log in res.json()]

    @task(5)
    def list_daily_logs(self):
        if not self.project_ids:
            return
        project_id = random.choice(self.project_ids)
        self.client.get(
            f"/api/v1/projects/{project_id}/daily-logs",
            headers=self.headers,
            name="/api/v1/projects/[id]/daily-logs",
        )

    @task(4)
    def get_manager_dashboard(self):
        if not self.project_ids:
            return
        project_id = random.choice(self.project_ids)
        self.client.get(
            f"/api/v1/dashboard/manager/{project_id}",
            headers=self.headers,
            name="/api/v1/dashboard/manager/[id]",
        )

    @task(3)
    def list_projects(self):
        self.client.get(
            "/api/v1/projects",
            headers=self.headers,
            name="/api/v1/projects",
        )

    @task(3)
    def list_materials(self):
        if not self.project_ids:
            return
        project_id = random.choice(self.project_ids)
        logs = self.log_ids.get(project_id, [])
        if not logs:
            return
        log_id = random.choice(logs)
        self.client.get(
            f"/api/v1/projects/{project_id}/daily-logs/{log_id}/materials",
            headers=self.headers,
            name="/api/v1/projects/[id]/daily-logs/[id]/materials",
        )

    @task(2)
    def list_attendance(self):
        if not self.project_ids:
            return
        project_id = random.choice(self.project_ids)
        logs = self.log_ids.get(project_id, [])
        if not logs:
            return
        log_id = random.choice(logs)
        self.client.get(
            f"/api/v1/projects/{project_id}/daily-logs/{log_id}/attendance",
            headers=self.headers,
            name="/api/v1/projects/[id]/daily-logs/[id]/attendance",
        )

    @task(2)
    def list_incidents(self):
        if not self.project_ids:
            return
        project_id = random.choice(self.project_ids)
        logs = self.log_ids.get(project_id, [])
        if not logs:
            return
        log_id = random.choice(logs)
        self.client.get(
            f"/api/v1/projects/{project_id}/daily-logs/{log_id}/incidents",
            headers=self.headers,
            name="/api/v1/projects/[id]/daily-logs/[id]/incidents",
        )

    @task(1)
    def list_reports(self):
        if not self.project_ids:
            return
        project_id = random.choice(self.project_ids)
        self.client.get(
            f"/api/v1/reports/{project_id}",
            headers=self.headers,
            name="/api/v1/reports/[id]",
        )

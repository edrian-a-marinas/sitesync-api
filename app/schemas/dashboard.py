from pydantic import BaseModel


class ProjectBudgetSummary(BaseModel):
    project_id: int
    project_name: str
    total_budget: float
    actual_spending: float
    is_over_budget: bool

    class Config:
        from_attributes = True


class OwnerDashboard(BaseModel):
    total_active_projects: int
    total_budget: float
    total_spending: float
    over_budget_projects: list[ProjectBudgetSummary]
    total_workers_active: int
    total_material_cost: float


class PhaseBudgetSummary(BaseModel):
    phase_id: int
    phase_name: str
    allocated_budget: float
    actual_spending: float
    is_over_budget: bool

    class Config:
        from_attributes = True


class ProjectManagerDashboard(BaseModel):
    project_id: int
    project_name: str
    logs_submitted: int
    attendance_rate: float
    total_material_cost: float
    total_incidents: int
    open_incidents: int
    phases: list[PhaseBudgetSummary]


class WorkerDashboard(BaseModel):
    worker_id: int
    worker_name: str
    assigned_project: str | None
    total_logs: int
    total_hours_worked: float

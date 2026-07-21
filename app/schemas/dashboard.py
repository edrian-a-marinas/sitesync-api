from typing import Literal

from pydantic import BaseModel


class ProjectBudgetSummary(BaseModel):
    project_id: int
    project_name: str
    status: Literal["Active", "Completed"]
    total_budget: float
    actual_spending: float
    is_over_budget: bool
    total_incidents: int = 0
    total_workers: int = 0

    class Config:
        from_attributes = True


class MaterialWeeklyTrend(BaseModel):
    week: str | None = None
    material_name: str
    total_cost: float
    project_id: int | None = None


class OwnerDashboard(BaseModel):
    total_active_projects: int
    total_budget: float
    total_spending: float
    over_budget_projects: list[ProjectBudgetSummary]
    all_projects_budget: list[ProjectBudgetSummary]
    material_trends: list[MaterialWeeklyTrend]
    total_workers_active: int
    total_material_cost: float
    incidents_this_week: int
    total_incidents: int
    total_spending_delta_percent: float | None = None
    total_workers_active_delta: int | None = None
    incidents_this_week_delta: int | None = None


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
    status: Literal["Active", "Completed"]
    logs_submitted: int
    attendance_rate: float
    total_material_cost: float
    total_incidents: int
    incidents_this_week: int
    open_incidents: int
    phases: list[PhaseBudgetSummary]
    material_trends: list[MaterialWeeklyTrend]
    logs_submitted_delta: int | None = None
    attendance_rate_delta: float | None = None
    total_spending_delta_percent: float | None = None
    incidents_this_week_delta: int | None = None


class ProjectManagerAggregateDashboard(BaseModel):
    total_logs_submitted: int
    total_budget: float
    total_spending: float
    average_attendance_rate: float
    incidents_this_week: int
    over_budget_projects: list[ProjectBudgetSummary]
    all_projects_budget: list[ProjectBudgetSummary]
    material_trends: list[MaterialWeeklyTrend]
    total_logs_submitted_delta: int | None = None
    total_spending_delta_percent: float | None = None
    average_attendance_rate_delta: float | None = None
    incidents_this_week_delta: int | None = None


class CurrentShiftLog(BaseModel):
    log_id: int
    log_date: str
    work_accomplished: str
    weather_condition: str | None

    class Config:
        from_attributes = True


class WorkerDashboard(BaseModel):
    worker_id: int
    worker_name: str
    assigned_project: str | None
    total_logs: int
    total_hours_worked: float
    current_shift_log: CurrentShiftLog | None

from pydantic import BaseModel


class BudgetOverrunResult(BaseModel):
    project_id: int
    project_name: str
    overrun_probability: float
    is_over_budget: bool
    total_budget: float
    total_spent: float


class DelayRiskResult(BaseModel):
    project_id: int
    project_name: str
    delay_risk_score: float
    risk_level: str


class MaterialForecastResult(BaseModel):
    project_id: int
    project_name: str
    forecast_month: int
    predicted_cost: float


class BudgetOverrunResponse(BaseModel):
    results: list[BudgetOverrunResult]


class DelayRiskResponse(BaseModel):
    results: list[DelayRiskResult]


class MaterialForecastResponse(BaseModel):
    results: list[MaterialForecastResult]

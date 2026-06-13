from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_owner
from app.core.limiter import limiter
from app.database import get_db
from app.models.user import User
from app.schemas.ml import BudgetOverrunResponse, DelayRiskResponse, MaterialForecastResponse
from app.services.ml import (
    get_budget_overrun_predictions as _get_budget_overrun_predictions,
)
from app.services.ml import (
    get_delay_risk_predictions as _get_delay_risk_predictions,
)
from app.services.ml import (
    get_material_forecast_predictions as _get_material_forecast_predictions,
)

router = APIRouter(prefix="/ml", tags=["ML Analytics"])


@router.get("/budget-overrun", response_model=BudgetOverrunResponse)
@limiter.limit("20/minute")
async def get_budget_overrun_predictions(
    request: Request,
    current_user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    return await _get_budget_overrun_predictions(db)


@router.get("/delay-risk", response_model=DelayRiskResponse)
@limiter.limit("20/minute")
async def get_delay_risk_predictions(
    request: Request,
    current_user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    return await _get_delay_risk_predictions(db)


@router.get("/material-forecast", response_model=MaterialForecastResponse)
@limiter.limit("20/minute")
async def get_material_forecast_predictions(
    request: Request,
    current_user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    return await _get_material_forecast_predictions(db)

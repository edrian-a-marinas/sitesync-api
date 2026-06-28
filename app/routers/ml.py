import os

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_owner
from app.core.limiter import limiter
from app.core.settings import settings
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
from app.tasks.ml import retrain_ml_models

router = APIRouter(prefix="/ml", tags=["ML Analytics"])

MODELS_DIR = settings.ML_MODELS_DIR  # app/ml/models


def _model_status(filename: str) -> dict:
    path = os.path.join(MODELS_DIR, filename)
    exists = os.path.exists(path)
    last_trained = None
    if exists:
        import datetime

        last_trained = datetime.datetime.fromtimestamp(os.path.getmtime(path), tz=datetime.timezone.utc).isoformat()
    return {"ready": exists, "last_trained": last_trained}


@router.get("/status")
@limiter.limit("30/minute")
async def get_ml_status(
    request: Request,
    current_user: User = Depends(require_owner),
):
    return {
        "budget_overrun": _model_status("budget_overrun.joblib"),
        "delay_risk": _model_status("delay_risk.joblib"),
        "material_forecast": _model_status("material_forecast.joblib"),
    }


@router.post("/retrain")
@limiter.limit("3/minute")
async def trigger_retrain(
    request: Request,
    current_user: User = Depends(require_owner),
):
    retrain_ml_models.delay()
    return {"status": "queued", "detail": "ML models retraining started"}


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

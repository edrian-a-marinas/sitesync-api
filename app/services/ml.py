import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.ml.features import (
    get_budget_overrun_features,
    get_delay_risk_features,
    get_material_forecast_features,
)
from app.ml.predict import (
    predict_budget_overrun,
    predict_delay_risk,
    predict_material_forecast,
)
from app.schemas.ml import (
    BudgetOverrunResponse,
    DelayRiskResponse,
    MaterialForecastResponse,
)

logger = logging.getLogger(__name__)


async def get_budget_overrun_predictions(db: AsyncSession) -> BudgetOverrunResponse:
    records = await get_budget_overrun_features(db)
    results = predict_budget_overrun(records)
    logger.info(f"ML_SERVICE | budget_overrun | projects={len(results)}")
    return BudgetOverrunResponse(results=results)


async def get_delay_risk_predictions(db: AsyncSession) -> DelayRiskResponse:
    records = await get_delay_risk_features(db)
    results = predict_delay_risk(records)
    logger.info(f"ML_SERVICE | delay_risk | projects={len(results)}")
    return DelayRiskResponse(results=results)


async def get_material_forecast_predictions(db: AsyncSession) -> MaterialForecastResponse:
    records = await get_material_forecast_features(db)
    results = predict_material_forecast(records)
    logger.info(f"ML_SERVICE | material_forecast | projects={len(results)}")
    return MaterialForecastResponse(results=results)

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import delete_pattern, get_cache, set_cache
from app.core.settings import settings
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

DEFAULT_CACHE_TTL = settings.DEFAULT_CACHE_TTL  # 1 hour — matches retrain schedule


async def get_budget_overrun_predictions(db: AsyncSession) -> BudgetOverrunResponse:
    cache_key = "ml:budget_overrun"
    cached = await get_cache(cache_key)
    if cached:
        logger.info("ML_SERVICE | budget_overrun | source=cache")
        return BudgetOverrunResponse(**cached)
    records = await get_budget_overrun_features(db)
    results = predict_budget_overrun(records)
    logger.info(f"ML_SERVICE | budget_overrun | projects={len(results)} | source=db")
    response = BudgetOverrunResponse(results=results)
    await set_cache(cache_key, response.model_dump(), ttl=DEFAULT_CACHE_TTL)
    return response


async def get_delay_risk_predictions(db: AsyncSession) -> DelayRiskResponse:
    cache_key = "ml:delay_risk"
    cached = await get_cache(cache_key)
    if cached:
        logger.info("ML_SERVICE | delay_risk | source=cache")
        return DelayRiskResponse(**cached)
    records = await get_delay_risk_features(db)
    results = predict_delay_risk(records)
    logger.info(f"ML_SERVICE | delay_risk | projects={len(results)} | source=db")
    response = DelayRiskResponse(results=results)
    await set_cache(cache_key, response.model_dump(), ttl=DEFAULT_CACHE_TTL)
    return response


async def get_material_forecast_predictions(db: AsyncSession) -> MaterialForecastResponse:
    cache_key = "ml:material_forecast"
    cached = await get_cache(cache_key)
    if cached:
        logger.info("ML_SERVICE | material_forecast | source=cache")
        return MaterialForecastResponse(**cached)
    records = await get_material_forecast_features(db)
    results = predict_material_forecast(records)
    logger.info(f"ML_SERVICE | material_forecast | projects={len(results)} | source=db")
    response = MaterialForecastResponse(results=results)
    await set_cache(cache_key, response.model_dump(), ttl=DEFAULT_CACHE_TTL)
    return response


async def invalidate_ml_cache() -> None:
    await delete_pattern("ml:*")
    logger.info("ML_SERVICE | cache invalidated")


def log_queue_failure(task_name: str, current_user) -> None:
    logger.error(
        f"ML_SERVICE | task={task_name} | user_id={current_user.id} | role_id={current_user.role_id} | status=failed | reason=queue unreachable"
    )

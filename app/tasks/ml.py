import asyncio
import logging

from app.core.celery import celery_app
from app.database import AsyncSessionLocal
from app.ml.features import (
    get_budget_overrun_features,
    get_delay_risk_features,
    get_material_forecast_features,
)
from app.ml.train import train_budget_overrun, train_delay_risk, train_material_forecast

logger = logging.getLogger(__name__)


@celery_app.task(name="retrain_ml_models")
def retrain_ml_models():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_retrain())
    finally:
        loop.close()


async def _retrain():
    async with AsyncSessionLocal() as db:
        try:
            budget_records = await get_budget_overrun_features(db)
            train_budget_overrun(budget_records)

            delay_records = await get_delay_risk_features(db)
            train_delay_risk(delay_records)

            forecast_records = await get_material_forecast_features(db)
            train_material_forecast(forecast_records)

            logger.info("ML_RETRAIN | all models retrained successfully")
        except Exception as e:
            logger.error(f"ML_RETRAIN | failed | reason={str(e)}")

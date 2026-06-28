import asyncio
import logging

import redis

from app.core.celery import celery_app
from app.core.celery_db import make_celery_session
from app.core.settings import settings
from app.ml.features import (
    get_budget_overrun_features,
    get_delay_risk_features,
    get_material_forecast_features,
)
from app.ml.train import train_budget_overrun, train_delay_risk, train_material_forecast

logger = logging.getLogger(__name__)


@celery_app.task(name="retrain_ml_models")
def retrain_ml_models():
    logger.info("ML_RETRAIN | task=started")
    asyncio.run(_retrain())


async def _retrain():
    async with make_celery_session()() as db:
        try:
            budget_records = await get_budget_overrun_features(db)
            train_budget_overrun(budget_records)
            logger.info("ML_RETRAIN | model=budget_overrun | status=done")

            delay_records = await get_delay_risk_features(db)
            train_delay_risk(delay_records)
            logger.info("ML_RETRAIN | model=delay_risk | status=done")

            forecast_records = await get_material_forecast_features(db)
            train_material_forecast(forecast_records)
            logger.info("ML_RETRAIN | model=material_forecast | status=done")

            logger.info("ML_RETRAIN | all models retrained | status=done")
            r = redis.from_url(settings.REDIS_CACHE_URL, decode_responses=True)
            for key in r.scan_iter("ml:*"):
                r.delete(key)
            logger.info("ML_RETRAIN | cache invalidated")
        except Exception as e:
            logger.error(f"ML_RETRAIN | status=failed | reason={str(e)}")

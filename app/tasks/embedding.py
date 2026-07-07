import asyncio
import logging

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.future import select

from app.core.celery import celery_app
from app.core.celery_db import make_celery_session
from app.models.daily_log import DailyLog
from app.models.embedding import DailyLogEmbedding
from app.services.embedding import build_daily_log_chunk_text, generate_embedding

logger = logging.getLogger(__name__)


@celery_app.task(name="generate_daily_log_embedding")
def generate_daily_log_embedding(daily_log_id: int):
    asyncio.run(_generate_daily_log_embedding(daily_log_id))


@celery_app.task(name="backfill_daily_log_embeddings")
def backfill_daily_log_embeddings():
    logger.info("EMBEDDING_BACKFILL | task=started")
    asyncio.run(_backfill_embeddings_async())


async def _backfill_embeddings_async():
    async with make_celery_session()() as db:
        daily_log_ids = (await db.execute(select(DailyLog.id))).scalars().all()
        count = len(daily_log_ids)
        for daily_log_id in daily_log_ids:
            generate_daily_log_embedding.delay(daily_log_id)
        logger.info(f"EMBEDDING_BACKFILL | total_queued={count} | status=done")


async def _generate_daily_log_embedding(daily_log_id: int):
    async with make_celery_session()() as db:
        try:
            daily_log = (await db.execute(select(DailyLog).where(DailyLog.id == daily_log_id))).scalar_one_or_none()
            if not daily_log:
                logger.error(f"EMBEDDING | daily_log_id={daily_log_id} | status=failed | reason=not_found")
                return

            content_text = await build_daily_log_chunk_text(db, daily_log_id)
            vector = generate_embedding(content_text)

            stmt = pg_insert(DailyLogEmbedding).values(
                daily_log_id=daily_log_id,
                project_id=daily_log.project_id,
                content_text=content_text,
                embedding=vector,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["daily_log_id"],
                set_={"content_text": content_text, "embedding": vector},
            )
            await db.execute(stmt)
            await db.commit()
            logger.info(f"EMBEDDING | daily_log_id={daily_log_id} | status=done")
        except Exception as e:
            await db.rollback()
            logger.error(f"EMBEDDING | daily_log_id={daily_log_id} | status=failed | reason={str(e)}")

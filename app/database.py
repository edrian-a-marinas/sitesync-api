import logging

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.settings import settings

logger = logging.getLogger(__name__)

DATABASE_URL = settings.DATABASE_URL

POOL_SIZE = settings.POOL_SIZE  # int = 20
MAX_OVERFLOW = settings.MAX_OVERFLOW  # int  = 10
POOL_TIMEOUT = settings.POOL_TIMEOUT  # int  = 30
POOL_RECYCLE = settings.POOL_RECYCLE  # int  = 300

engine = create_async_engine(
    DATABASE_URL,
    pool_size=POOL_SIZE,
    max_overflow=MAX_OVERFLOW,
    pool_timeout=POOL_TIMEOUT,
    pool_recycle=POOL_RECYCLE,
    pool_pre_ping=True,
    echo=False,
    connect_args={"statement_cache_size": 0},
)

logger.info(f"DB_ENGINE | pool_size={POOL_SIZE} | max_overflow={MAX_OVERFLOW} | total_capacity={POOL_SIZE + MAX_OVERFLOW}")

TOTAL_CAPACITY = POOL_SIZE + MAX_OVERFLOW


@event.listens_for(engine.sync_engine, "checkout")
def _on_checkout(dbapi_conn, connection_record, connection_proxy):
    checked_out = engine.pool.checkedout()
    if checked_out >= TOTAL_CAPACITY:
        logger.warning(f"DB_POOL | EXHAUSTED | checked_out={checked_out}/{TOTAL_CAPACITY}")
    elif checked_out >= int(TOTAL_CAPACITY * 0.8):
        logger.warning(f"DB_POOL | NEAR_CAPACITY | checked_out={checked_out}/{TOTAL_CAPACITY}")


@event.listens_for(engine.sync_engine, "checkin")
def _on_checkin(dbapi_conn, connection_record):
    checked_out = engine.pool.checkedout()
    if checked_out == 0:
        logger.debug(f"DB_POOL | IDLE | checked_out=0/{TOTAL_CAPACITY}")


AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            logger.exception("DB_SESSION | rolling_back")
            await session.rollback()
            raise
        finally:
            await session.close()

import logging

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.settings import settings

logger = logging.getLogger(__name__)


def make_celery_session() -> async_sessionmaker:
    engine = create_async_engine(
        settings.DATABASE_URL,
        pool_size=1,
        max_overflow=0,
        pool_pre_ping=True,
        connect_args={"statement_cache_size": 0},
    )
    return async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


def make_celery_sync_session() -> sessionmaker:
    engine = create_engine(
        settings.SYNC_DATABASE_URL,
        pool_size=1,
        max_overflow=0,
        pool_pre_ping=True,
    )
    return sessionmaker(bind=engine, class_=Session, expire_on_commit=False)

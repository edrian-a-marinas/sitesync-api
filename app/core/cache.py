import json
import logging
from typing import Any

import redis.asyncio as aioredis

from app.core.settings import settings

logger = logging.getLogger(__name__)

redis_client = aioredis.from_url(settings.REDIS_CACHE_URL, decode_responses=True)


async def get_cache(key: str) -> Any | None:
    try:
        value = await redis_client.get(key)
        if value:
            logger.info(f"CACHE_HIT | key={key}")
            return json.loads(value)
        logger.info(f"CACHE_MISS | key={key}")
        return None
    except Exception as e:
        logger.error(f"CACHE_GET | key={key} | error={str(e)}")
        return None


async def set_cache(key: str, value: Any, ttl: int) -> None:
    try:
        await redis_client.setex(key, ttl, json.dumps(value))
        logger.info(f"CACHE_SET | key={key} | ttl={ttl}")
    except Exception as e:
        logger.error(f"CACHE_SET | key={key} | error={str(e)}")


async def delete_cache(key: str) -> None:
    try:
        await redis_client.delete(key)
        logger.info(f"CACHE_DELETE | key={key}")
    except Exception as e:
        logger.error(f"CACHE_DELETE | key={key} | error={str(e)}")


async def delete_pattern(pattern: str) -> None:
    try:
        keys = await redis_client.keys(pattern)
        if keys:
            await redis_client.delete(*keys)
            logger.info(f"CACHE_DELETE_PATTERN | pattern={pattern} | count={len(keys)}")
    except Exception as e:
        logger.error(f"CACHE_DELETE_PATTERN | pattern={pattern} | error={str(e)}")

import logging
from functools import lru_cache

from motor.motor_asyncio import AsyncIOMotorClient

from app.core.settings import settings

logger = logging.getLogger(__name__)


@lru_cache
def get_mongo_client() -> AsyncIOMotorClient:
    return AsyncIOMotorClient(settings.MONGO_URL)


def get_notifications_collection():
    return get_mongo_client().get_database("sitesync").get_collection("notifications")


class _NotificationsCollectionProxy:
    def __getattr__(self, name):
        return getattr(get_notifications_collection(), name)


notifications_collection = _NotificationsCollectionProxy()

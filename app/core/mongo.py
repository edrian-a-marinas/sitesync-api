import logging

from motor.motor_asyncio import AsyncIOMotorClient

from app.core.settings import settings

logger = logging.getLogger(__name__)

mongo_client = AsyncIOMotorClient(settings.MONGO_URL)
mongo_db = mongo_client.get_database("sitesync")
notifications_collection = mongo_db.get_collection("notifications")

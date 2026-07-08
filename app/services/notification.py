import logging
from datetime import datetime, timezone

from bson import ObjectId

from app.core.mongo import notifications_collection

logger = logging.getLogger(__name__)


async def create_notification(user_id: int, type: str, title: str, message: str, data: dict | None = None) -> dict:
    doc = {
        "user_id": user_id,
        "type": type,
        "title": title,
        "message": message,
        "data": data or {},
        "is_read": False,
        "created_at": datetime.now(timezone.utc),
    }
    result = await notifications_collection.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    logger.info(f"NOTIFICATION_CREATE | user_id={user_id} | type={type} | notification_id={doc['_id']} | status=success")
    return doc


async def get_notifications(user_id: int, page: int = 1, page_size: int = 20) -> list[dict]:
    skip = (page - 1) * page_size
    cursor = notifications_collection.find({"user_id": user_id}).sort("created_at", -1).skip(skip).limit(page_size)
    results = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        results.append(doc)
    logger.info(f"NOTIFICATION_LIST | user_id={user_id} | page={page} | count={len(results)} | status=success")
    return results


async def mark_as_read(notification_id: str, user_id: int) -> bool:
    result = await notifications_collection.update_one(
        {"_id": ObjectId(notification_id), "user_id": user_id},
        {"$set": {"is_read": True}},
    )
    if result.modified_count == 0:
        logger.warning(f"NOTIFICATION_READ | user_id={user_id} | notification_id={notification_id} | status=failed | reason=not found")
        return False
    logger.info(f"NOTIFICATION_READ | user_id={user_id} | notification_id={notification_id} | status=success")
    return True


async def get_unread_count(user_id: int) -> int:
    count = await notifications_collection.count_documents({"user_id": user_id, "is_read": False})
    logger.info(f"NOTIFICATION_UNREAD_COUNT | user_id={user_id} | count={count}")
    return count

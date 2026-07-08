import asyncio
import logging
from datetime import datetime, timezone

from bson import ObjectId
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.mongo import notifications_collection
from app.core.ws_manager import manager
from app.models.project import Project, ProjectAssignment

logger = logging.getLogger(__name__)


# ==================== Cross-service dispatch (reusable) ====================
async def notify_project_stakeholders(project_id: int, type: str, title: str, message: str, data: dict, db: AsyncSession) -> None:
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not project:
        logger.warning(f"NOTIFICATION_DISPATCH | project_id={project_id} | status=failed | reason=project not found")
        return
    recipient_ids = {project.owner_id}
    assignments = (await db.execute(select(ProjectAssignment.user_id).where(ProjectAssignment.project_id == project_id))).scalars().all()
    recipient_ids.update(assignments)
    for user_id in recipient_ids:
        try:
            notification = await create_notification(user_id=user_id, type=type, title=title, message=message, data=data)
            await manager.send_to_user(user_id, notification)
        except Exception as e:
            logger.error(f"NOTIFICATION_DISPATCH | project_id={project_id} | user_id={user_id} | status=failed | reason={str(e)}")
    logger.info(f"NOTIFICATION_DISPATCH | project_id={project_id} | type={type} | recipients={len(recipient_ids)} | status=success")


def notify_project_stakeholders_sync(project_id: int, type: str, title: str, message: str, data: dict, db) -> None:
    """Sync wrapper for Celery tasks (sync DB session) — resolves recipients synchronously,
    then bridges to async for Mongo insert + WebSocket push."""
    project = db.execute(select(Project).where(Project.id == project_id)).scalar_one_or_none()
    if not project:
        logger.warning(f"NOTIFICATION_DISPATCH | project_id={project_id} | status=failed | reason=project not found")
        return
    recipient_ids = {project.owner_id}
    assignments = db.execute(select(ProjectAssignment.user_id).where(ProjectAssignment.project_id == project_id)).scalars().all()
    recipient_ids.update(assignments)

    async def _dispatch():
        for user_id in recipient_ids:
            try:
                notification = await create_notification(user_id=user_id, type=type, title=title, message=message, data=data)
                await manager.send_to_user(user_id, notification)
            except Exception as e:
                logger.error(f"NOTIFICATION_DISPATCH | project_id={project_id} | user_id={user_id} | status=failed | reason={str(e)}")

    asyncio.run(_dispatch())
    logger.info(f"NOTIFICATION_DISPATCH | project_id={project_id} | type={type} | recipients={len(recipient_ids)} | status=success")


# ==================== Used by routers ====================
async def create_notification(user_id: int, type: str, title: str, message: str, data: dict | None = None) -> dict:
    now = datetime.now(timezone.utc)
    doc = {
        "user_id": user_id,
        "type": type,
        "title": title,
        "message": message,
        "data": data or {},
        "is_read": False,
        "created_at": now,
    }
    result = await notifications_collection.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    doc["created_at"] = now.isoformat()
    logger.info(f"NOTIFICATION_CREATE | user_id={user_id} | type={type} | notification_id={doc['_id']} | status=success")
    return doc


async def get_notifications(user_id: int, page: int = 1, page_size: int = 20) -> list[dict]:
    skip = (page - 1) * page_size
    cursor = notifications_collection.find({"user_id": user_id}).sort("created_at", -1).skip(skip).limit(page_size)
    results = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        if isinstance(doc.get("created_at"), datetime) and doc["created_at"].tzinfo is None:
            doc["created_at"] = doc["created_at"].replace(tzinfo=timezone.utc)
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


async def mark_all_as_read(user_id: int) -> int:
    result = await notifications_collection.update_many(
        {"user_id": user_id, "is_read": False},
        {"$set": {"is_read": True}},
    )
    logger.info(f"NOTIFICATION_READ_ALL | user_id={user_id} | modified_count={result.modified_count} | status=success")
    return result.modified_count


async def get_unread_count(user_id: int) -> int:
    count = await notifications_collection.count_documents({"user_id": user_id, "is_read": False})
    logger.info(f"NOTIFICATION_UNREAD_COUNT | user_id={user_id} | count={count}")
    return count


async def delete_notification(notification_id: str, user_id: int) -> bool:
    result = await notifications_collection.delete_one(
        {"_id": ObjectId(notification_id), "user_id": user_id},
    )
    if result.deleted_count == 0:
        logger.warning(f"NOTIFICATION_DELETE | user_id={user_id} | notification_id={notification_id} | status=failed | reason=not found")
        return False
    logger.info(f"NOTIFICATION_DELETE | user_id={user_id} | notification_id={notification_id} | status=success")
    return True

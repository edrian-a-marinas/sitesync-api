import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.equipment import Equipment
from app.models.user import User
from app.schemas.equipment import EquipmentCreate, EquipmentUpdate

logger = logging.getLogger(__name__)


async def get_equipment(log_id: int, db: AsyncSession) -> list[Equipment]:
    result = await db.execute(select(Equipment).where(Equipment.daily_log_id == log_id))
    return result.scalars().all()


async def create_equipment(log_id: int, data: EquipmentCreate, current_user: User, db: AsyncSession) -> Equipment:
    equipment = Equipment(**data.model_dump(), daily_log_id=log_id)
    db.add(equipment)
    await db.commit()
    await db.refresh(equipment)
    logger.info(f"EQUIPMENT_CREATE | log_id={log_id} | equipment_id={equipment.id} | submitted_by={current_user.id} | status=success")
    return equipment


async def update_equipment(log_id: int, equipment_id: int, data: EquipmentUpdate, current_user: User, db: AsyncSession) -> Equipment | None:
    equipment = (await db.execute(select(Equipment).where(Equipment.id == equipment_id).where(Equipment.daily_log_id == log_id))).scalar_one_or_none()
    if not equipment:
        return None
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(equipment, field, value)
    await db.commit()
    await db.refresh(equipment)
    logger.info(f"EQUIPMENT_UPDATE | log_id={log_id} | equipment_id={equipment_id} | updated_by={current_user.id} | status=success")
    return equipment

import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.material import Material
from app.models.user import User
from app.schemas.material import MaterialCreate, MaterialUpdate

logger = logging.getLogger(__name__)


async def get_materials(log_id: int, db: AsyncSession) -> list[Material]:
    result = await db.execute(select(Material).where(Material.daily_log_id == log_id))
    return result.scalars().all()


async def create_material(log_id: int, data: MaterialCreate, current_user: User, db: AsyncSession) -> Material:
    material = Material(**data.model_dump(), daily_log_id=log_id)
    db.add(material)
    await db.commit()
    await db.refresh(material)
    logger.info(f"MATERIAL_CREATE | log_id={log_id} | material_id={material.id} | submitted_by={current_user.id} | status=success")
    return material


async def update_material(log_id: int, material_id: int, data: MaterialUpdate, current_user: User, db: AsyncSession) -> Material | None:
    material = (await db.execute(select(Material).where(Material.id == material_id).where(Material.daily_log_id == log_id))).scalar_one_or_none()
    if not material:
        return None
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(material, field, value)
    await db.commit()
    await db.refresh(material)
    logger.info(f"MATERIAL_UPDATE | log_id={log_id} | material_id={material_id} | updated_by={current_user.id} | status=success")
    return material

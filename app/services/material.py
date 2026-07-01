import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.cache import delete_cache, delete_pattern, get_cache, set_cache
from app.models.material import Material
from app.models.project import ProjectAssignment
from app.models.role import Role
from app.models.user import User
from app.schemas.material import MaterialCreate, MaterialUpdate

logger = logging.getLogger(__name__)


async def get_materials(project_id: int, log_id: int, current_user: User, db: AsyncSession) -> list[Material] | list[dict]:
    role = (await db.execute(select(Role).where(Role.id == current_user.role_id))).scalar_one_or_none()

    if role and role.name == "site_worker":
        from app.models.project import WorkerAssignment

        assigned = (
            await db.execute(
                select(WorkerAssignment).where(WorkerAssignment.project_id == project_id).where(WorkerAssignment.user_id == current_user.id)
            )
        ).scalar_one_or_none()
        if not assigned:
            logger.warning(f"MATERIAL_GET | log_id={log_id} | user_id={current_user.id} | status=failed | reason=worker not assigned to project")
            return []

    cache_key = f"material:{project_id}:{log_id}"
    cached = await get_cache(cache_key)
    if cached is not None:
        logger.info(f"MATERIAL_GET | log_id={log_id} | user_id={current_user.id} | count={len(cached)} | source=cache")
        return cached

    result = await db.execute(select(Material).where(Material.daily_log_id == log_id))
    materials = result.scalars().all()
    logger.info(f"MATERIAL_GET | log_id={log_id} | user_id={current_user.id} | count={len(materials)} | source=db")

    serialized = [
        {
            "id": m.id,
            "daily_log_id": m.daily_log_id,
            "name": m.name,
            "quantity": float(m.quantity),
            "unit": m.unit,
            "unit_cost": float(m.unit_cost),
            "total_cost": float(m.total_cost),
        }
        for m in materials
    ]
    await set_cache(cache_key, serialized, ttl=3600)
    return materials


async def _check_manager_assigned(project_id: int, current_user: User, db: AsyncSession) -> bool:
    role = (await db.execute(select(Role).where(Role.id == current_user.role_id))).scalar_one_or_none()
    if role and role.name == "project_manager":
        assigned = (
            await db.execute(
                select(ProjectAssignment).where(ProjectAssignment.project_id == project_id).where(ProjectAssignment.user_id == current_user.id)
            )
        ).scalar_one_or_none()
        if not assigned:
            logger.warning(f"MATERIAL | user_id={current_user.id} | project_id={project_id} | status=failed | reason=manager not assigned to project")
            return False
    return True


async def create_material(project_id: int, log_id: int, data: MaterialCreate, current_user: User, db: AsyncSession) -> Material | None:
    if not await _check_manager_assigned(project_id, current_user, db):
        return None
    material = Material(**data.model_dump(), daily_log_id=log_id)
    db.add(material)
    await db.commit()
    await db.refresh(material)
    await delete_cache(f"dashboard:manager:{project_id}")
    await delete_cache(f"dashboard:manager:aggregate:{current_user.id}")
    await delete_pattern("dashboard:owner:*")
    await delete_pattern("ml:*")
    logger.info(f"MATERIAL_CREATE | log_id={log_id} | material_id={material.id} | submitted_by={current_user.id} | status=success")
    return material


async def update_material(
    project_id: int, log_id: int, material_id: int, data: MaterialUpdate, current_user: User, db: AsyncSession
) -> Material | None | bool:
    if not await _check_manager_assigned(project_id, current_user, db):
        return False
    material = (await db.execute(select(Material).where(Material.id == material_id).where(Material.daily_log_id == log_id))).scalar_one_or_none()
    if not material:
        logger.warning(
            f"MATERIAL_UPDATE | log_id={log_id} | material_id={material_id} | updated_by={current_user.id} | status=failed | reason=not found"
        )
        return None
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(material, field, value)
    await db.commit()
    await db.refresh(material)
    await delete_cache(f"dashboard:manager:{project_id}")
    await delete_cache(f"dashboard:manager:aggregate:{current_user.id}")
    await delete_pattern("dashboard:owner:*")
    await delete_pattern("ml:*")
    logger.info(f"MATERIAL_UPDATE | log_id={log_id} | material_id={material_id} | updated_by={current_user.id} | status=success")
    return material


async def delete_material(project_id: int, log_id: int, material_id: int, current_user: User, db: AsyncSession) -> bool | None:
    if not await _check_manager_assigned(project_id, current_user, db):
        return False
    material = (await db.execute(select(Material).where(Material.id == material_id).where(Material.daily_log_id == log_id))).scalar_one_or_none()
    if not material:
        logger.warning(
            f"MATERIAL_DELETE | log_id={log_id} | material_id={material_id} | deleted_by={current_user.id} | status=failed | reason=not found"
        )
        return None
    await db.delete(material)
    await db.commit()
    await delete_cache(f"dashboard:manager:{project_id}")
    await delete_cache(f"dashboard:manager:aggregate:{current_user.id}")
    await delete_pattern("dashboard:owner:*")
    await delete_pattern("ml:*")
    logger.info(f"MATERIAL_DELETE | log_id={log_id} | material_id={material_id} | deleted_by={current_user.id} | status=success")
    return True

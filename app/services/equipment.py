import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.equipment import Equipment
from app.models.project import ProjectAssignment, WorkerAssignment
from app.models.role import Role
from app.models.user import User
from app.schemas.equipment import EquipmentCreate, EquipmentUpdate

logger = logging.getLogger(__name__)


async def _check_manager_assigned(project_id: int, current_user: User, db: AsyncSession) -> bool:
    role = (await db.execute(select(Role).where(Role.id == current_user.role_id))).scalar_one_or_none()
    if role and role.name == "project_manager":
        assigned = (
            await db.execute(
                select(ProjectAssignment).where(ProjectAssignment.project_id == project_id).where(ProjectAssignment.user_id == current_user.id)
            )
        ).scalar_one_or_none()
        if not assigned:
            logger.warning(
                f"EQUIPMENT | user_id={current_user.id} | project_id={project_id} | status=failed | reason=manager not assigned to project"
            )
            return False
    return True


async def get_equipment(project_id: int, log_id: int, current_user: User, db: AsyncSession) -> list[Equipment]:
    role = (await db.execute(select(Role).where(Role.id == current_user.role_id))).scalar_one_or_none()

    if role and role.name == "site_worker":
        assigned = (
            await db.execute(
                select(WorkerAssignment).where(WorkerAssignment.project_id == project_id).where(WorkerAssignment.user_id == current_user.id)
            )
        ).scalar_one_or_none()
        if not assigned:
            logger.warning(f"EQUIPMENT_GET | log_id={log_id} | user_id={current_user.id} | status=failed | reason=worker not assigned to project")
            return []

    result = await db.execute(select(Equipment).where(Equipment.daily_log_id == log_id))
    equipment = result.scalars().all()
    logger.info(f"EQUIPMENT_GET | log_id={log_id} | user_id={current_user.id} | count={len(equipment)}")
    return equipment


async def create_equipment(project_id: int, log_id: int, data: EquipmentCreate, current_user: User, db: AsyncSession) -> Equipment | None:
    if not await _check_manager_assigned(project_id, current_user, db):
        return None
    equipment = Equipment(**data.model_dump(), daily_log_id=log_id)
    db.add(equipment)
    await db.commit()
    await db.refresh(equipment)
    logger.info(f"EQUIPMENT_CREATE | log_id={log_id} | equipment_id={equipment.id} | submitted_by={current_user.id} | status=success")
    return equipment


async def update_equipment(
    project_id: int, log_id: int, equipment_id: int, data: EquipmentUpdate, current_user: User, db: AsyncSession
) -> Equipment | None | bool:
    if not await _check_manager_assigned(project_id, current_user, db):
        return False
    equipment = (await db.execute(select(Equipment).where(Equipment.id == equipment_id).where(Equipment.daily_log_id == log_id))).scalar_one_or_none()
    if not equipment:
        logger.warning(
            f"EQUIPMENT_UPDATE | log_id={log_id} | equipment_id={equipment_id} | updated_by={current_user.id} | status=failed | reason=not found"
        )
        return None
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(equipment, field, value)
    await db.commit()
    await db.refresh(equipment)
    logger.info(f"EQUIPMENT_UPDATE | log_id={log_id} | equipment_id={equipment_id} | updated_by={current_user.id} | status=success")
    return equipment

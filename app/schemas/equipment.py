from pydantic import BaseModel


class EquipmentCreate(BaseModel):
    name: str
    quantity: int
    condition: str | None = None


class EquipmentUpdate(BaseModel):
    name: str | None = None
    quantity: int | None = None
    condition: str | None = None


class EquipmentResponse(EquipmentCreate):
    id: int
    daily_log_id: int

    class Config:
        from_attributes = True

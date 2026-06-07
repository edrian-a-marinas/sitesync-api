from pydantic import BaseModel


class MaterialCreate(BaseModel):
    name: str
    quantity: float
    unit: str
    unit_cost: float


class MaterialUpdate(BaseModel):
    name: str | None = None
    quantity: float | None = None
    unit: str | None = None
    unit_cost: float | None = None


class MaterialResponse(MaterialCreate):
    id: int
    daily_log_id: int
    total_cost: float

    class Config:
        from_attributes = True

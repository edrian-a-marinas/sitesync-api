from pydantic import BaseModel


class IncidentCreate(BaseModel):
    description: str
    severity: str
    status: str = "Open"


class IncidentUpdate(BaseModel):
    description: str | None = None
    severity: str | None = None
    status: str | None = None


class IncidentResponse(IncidentCreate):
    id: int
    daily_log_id: int
    reported_by: int

    class Config:
        from_attributes = True

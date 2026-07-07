from typing import Literal

from pydantic import BaseModel

IncidentSeverity = Literal["Low", "Medium", "High"]
IncidentStatus = Literal["Open", "Resolved"]


class IncidentCreate(BaseModel):
    description: str
    severity: IncidentSeverity
    status: IncidentStatus = "Open"


class IncidentUpdate(BaseModel):
    description: str | None = None
    severity: IncidentSeverity | None = None
    status: IncidentStatus | None = None


class IncidentResponse(IncidentCreate):
    id: int
    daily_log_id: int
    reported_by: int

    class Config:
        from_attributes = True

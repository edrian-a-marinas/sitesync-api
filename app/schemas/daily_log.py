from datetime import date

from pydantic import BaseModel


class DailyLogCreate(BaseModel):
    log_date: date
    weather_condition: str | None = None
    work_accomplished: str
    notes: str | None = None


class DailyLogUpdate(BaseModel):
    weather_condition: str | None = None
    work_accomplished: str | None = None
    notes: str | None = None


class DailyLogResponse(BaseModel):
    id: int
    project_id: int
    submitted_by: int
    log_date: date
    weather_condition: str | None
    work_accomplished: str
    notes: str | None

    class Config:
        from_attributes = True

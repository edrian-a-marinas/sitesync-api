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


class DailyLogResponse(DailyLogCreate):
    id: int
    project_id: int
    submitted_by: int
    submitted_by_name: str

    class Config:
        from_attributes = True

from pydantic import BaseModel


class AttendanceCreate(BaseModel):
    worker_id: int
    hours_worked: float


class AttendanceResponse(AttendanceCreate):
    id: int
    daily_log_id: int

    class Config:
        from_attributes = True

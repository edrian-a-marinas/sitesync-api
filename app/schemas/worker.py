from datetime import date

from pydantic import BaseModel


class WorkerProjectResponse(BaseModel):
    id: int
    name: str
    location: str
    status: str
    start_date: date
    target_end_date: date
    total_budget: float

    class Config:
        from_attributes = True

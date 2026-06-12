from datetime import date, datetime

from pydantic import BaseModel


class ReportResponse(BaseModel):
    id: int
    project_id: int
    generated_by: int
    week_start: date
    week_end: date
    s3_key: str
    created_at: datetime

    model_config = {"from_attributes": True}

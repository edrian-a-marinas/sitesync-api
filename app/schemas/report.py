from datetime import date, datetime

from pydantic import BaseModel


class ReportResponse(BaseModel):
    id: int
    project_id: int
    generated_by: int
    generated_by_name: str | None = None
    week_start: date
    week_end: date
    s3_key: str
    source: str
    file_url: str | None = None
    total_hours: float
    total_material_cost: float
    log_count: int
    incident_count: int
    open_incident_count: int
    created_at: datetime
    model_config = {"from_attributes": True}

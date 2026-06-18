from datetime import datetime

from pydantic import BaseModel


class SitePhotoResponse(BaseModel):
    id: int
    daily_log_id: int
    uploaded_by: int
    filename: str
    content_type: str
    s3_key: str
    uploaded_at: datetime
    file_url: str

    model_config = {"from_attributes": True}

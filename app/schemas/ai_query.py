from pydantic import BaseModel


class AIQueryRequest(BaseModel):
    question: str
    project_id: int | None = None


class AIQueryResponse(BaseModel):
    id: int
    user_id: int
    project_id: int | None
    question: str
    answer: str | None
    status: str

    class Config:
        from_attributes = True

from datetime import date
from typing import Annotated

from pydantic import BaseModel, StringConstraints

NameStr = Annotated[str, StringConstraints(min_length=1, max_length=100)]


class ProjectCreate(BaseModel):
    name: NameStr
    location: str
    total_budget: float
    start_date: date
    target_end_date: date
    status: str = "Active"


class ProjectUpdate(BaseModel):
    name: NameStr | None = None
    location: str | None = None
    total_budget: float | None = None
    start_date: date | None = None
    target_end_date: date | None = None
    status: str | None = None


class ProjectResponse(BaseModel):
    id: int
    owner_id: int
    name: str
    location: str
    total_budget: float
    start_date: date
    target_end_date: date
    status: str

    class Config:
        from_attributes = True


class PhaseCreate(BaseModel):
    name: NameStr
    allocated_budget: float
    status: str = "Not Started"


class PhaseUpdate(BaseModel):
    name: NameStr | None = None
    allocated_budget: float | None = None
    status: str | None = None


class PhaseResponse(BaseModel):
    id: int
    project_id: int
    name: str
    allocated_budget: float
    status: str

    class Config:
        from_attributes = True


class AssignManagerRequest(BaseModel):
    user_id: int


class AssignWorkerRequest(BaseModel):
    user_id: int
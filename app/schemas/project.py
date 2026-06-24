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


class ProjectResponse(ProjectCreate):
    id: int
    owner_id: int

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


class PhaseResponse(PhaseCreate):
    id: int
    project_id: int

    class Config:
        from_attributes = True


class ProjectDetailResponse(ProjectResponse):
    phases: list[PhaseResponse] = []

    class Config:
        from_attributes = True


class AssignUserRequest(BaseModel):
    user_id: int

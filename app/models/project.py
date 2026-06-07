from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    location: Mapped[str] = mapped_column(String, nullable=False)
    total_budget: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    start_date: Mapped[Date] = mapped_column(Date, nullable=False)
    target_end_date: Mapped[Date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="Active")  # Active, On Hold, Completed
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    owner: Mapped["User"] = relationship("User", back_populates="projects_owned")
    phases: Mapped[list["ProjectPhase"]] = relationship("ProjectPhase", back_populates="project")
    assignments: Mapped[list["ProjectAssignment"]] = relationship("ProjectAssignment", back_populates="project")
    worker_assignments: Mapped[list["WorkerAssignment"]] = relationship("WorkerAssignment", back_populates="project")
    daily_logs: Mapped[list["DailyLog"]] = relationship("DailyLog", back_populates="project")
    reports: Mapped[list["Report"]] = relationship("Report", back_populates="project")
    ai_queries: Mapped[list["AIQuery"]] = relationship("AIQuery", back_populates="project")


class ProjectPhase(Base):
    __tablename__ = "project_phases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)  # Foundation, Structure, Finishing
    allocated_budget: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="Not Started")  # Not Started, In Progress, Completed
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped["Project"] = relationship("Project", back_populates="phases")


class ProjectAssignment(Base):
    __tablename__ = "project_assignments"
    __table_args__ = (UniqueConstraint("project_id", "user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    assigned_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped["Project"] = relationship("Project", back_populates="assignments")
    user: Mapped["User"] = relationship("User", back_populates="project_assignments")


class WorkerAssignment(Base):
    __tablename__ = "worker_assignments"
    __table_args__ = (UniqueConstraint("project_id", "user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    assigned_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped["Project"] = relationship("Project", back_populates="worker_assignments")
    user: Mapped["User"] = relationship("User", back_populates="worker_assignments")

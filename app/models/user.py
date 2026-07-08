from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role_id: Mapped[int] = mapped_column(Integer, ForeignKey("roles.id"), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    first_name: Mapped[str] = mapped_column(String, nullable=False)
    middle_name: Mapped[str | None] = mapped_column(String, nullable=True)
    last_name: Mapped[str] = mapped_column(String, nullable=False)
    phone_number: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_demo: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default="false"
    )  # DEMO FEATURE: remove this line if demo mode is retired
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)

    role: Mapped["Role"] = relationship("Role", back_populates="users")
    projects_owned: Mapped[list["Project"]] = relationship("Project", back_populates="owner")
    project_assignments: Mapped[list["ProjectAssignment"]] = relationship("ProjectAssignment", back_populates="user")
    worker_assignments: Mapped[list["WorkerAssignment"]] = relationship("WorkerAssignment", back_populates="user")
    daily_logs: Mapped[list["DailyLog"]] = relationship("DailyLog", back_populates="submitted_by_user")
    attendance: Mapped[list["Attendance"]] = relationship("Attendance", back_populates="worker")
    incidents_reported: Mapped[list["Incident"]] = relationship("Incident", back_populates="reported_by_user")
    site_photos: Mapped[list["SitePhoto"]] = relationship("SitePhoto", back_populates="uploaded_by_user")
    reports: Mapped[list["Report"]] = relationship("Report", back_populates="generated_by_user")
    ai_queries: Mapped[list["AIQuery"]] = relationship("AIQuery", back_populates="user")

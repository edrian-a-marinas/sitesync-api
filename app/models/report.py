from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id"), nullable=False)
    generated_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    week_start: Mapped[Date] = mapped_column(Date, nullable=False)
    week_end: Mapped[Date] = mapped_column(Date, nullable=False)
    s3_key: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'manual'"))
    total_hours: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0.0)
    total_material_cost: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False, default=0.0)
    log_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    incident_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    open_incident_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped["Project"] = relationship("Project", back_populates="reports")
    generated_by_user: Mapped["User"] = relationship("User", back_populates="reports")

    __table_args__ = (UniqueConstraint("project_id", "week_start", name="uq_report_project_week"),)

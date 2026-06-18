from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


class DailyLog(Base):
    __tablename__ = "daily_logs"
    __table_args__ = (UniqueConstraint("project_id", "log_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    submitted_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    log_date: Mapped[Date] = mapped_column(Date, nullable=False)
    weather_condition: Mapped[str | None] = mapped_column(String, nullable=True)
    work_accomplished: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped["Project"] = relationship("Project", back_populates="daily_logs")
    submitted_by_user: Mapped["User"] = relationship("User", back_populates="daily_logs")
    attendance: Mapped[list["Attendance"]] = relationship("Attendance", back_populates="daily_log")
    materials: Mapped[list["Material"]] = relationship("Material", back_populates="daily_log")
    equipment: Mapped[list["Equipment"]] = relationship("Equipment", back_populates="daily_log")
    incidents: Mapped[list["Incident"]] = relationship("Incident", back_populates="daily_log")
    site_photos: Mapped[list["SitePhoto"]] = relationship("SitePhoto", back_populates="daily_log")

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    daily_log_id: Mapped[int] = mapped_column(Integer, ForeignKey("daily_logs.id"), nullable=False, index=True)
    reported_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String, nullable=False)  # Low, Medium, High
    status: Mapped[str] = mapped_column(String, nullable=False, default="Open")  # Open, Resolved
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    daily_log: Mapped["DailyLog"] = relationship("DailyLog", back_populates="incidents")
    reported_by_user: Mapped["User"] = relationship("User", back_populates="incidents_reported")

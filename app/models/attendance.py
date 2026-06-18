from sqlalchemy import ForeignKey, Integer, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Attendance(Base):
    __tablename__ = "attendance"
    __table_args__ = (UniqueConstraint("daily_log_id", "worker_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    daily_log_id: Mapped[int] = mapped_column(Integer, ForeignKey("daily_logs.id"), nullable=False, index=True)
    worker_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    hours_worked: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)

    daily_log: Mapped["DailyLog"] = relationship("DailyLog", back_populates="attendance")
    worker: Mapped["User"] = relationship("User", back_populates="attendance")

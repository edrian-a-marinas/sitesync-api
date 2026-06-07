from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Equipment(Base):
    __tablename__ = "equipment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    daily_log_id: Mapped[int] = mapped_column(Integer, ForeignKey("daily_logs.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    condition: Mapped[str | None] = mapped_column(String, nullable=True)  # Good, Needs Repair, Broken

    daily_log: Mapped["DailyLog"] = relationship("DailyLog", back_populates="equipment")
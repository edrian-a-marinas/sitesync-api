from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


class AIQuery(Base):
    __tablename__ = "ai_queries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    project_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("projects.id"), nullable=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="Pending")
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    user: Mapped["User"] = relationship("User", back_populates="ai_queries")
    project: Mapped["Project"] = relationship("Project", back_populates="ai_queries")

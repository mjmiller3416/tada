from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Reminder(Base):
    """Polled by the Railway cron service every minute (SPEC §2). Phase 0
    scope only: `task_id` is deliberately omitted here since the Task table
    doesn't exist until Phase 1 — the Phase 1 migration adds it additively,
    per SPEC §3 / §8."""

    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")

    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recurrence_rule: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Reminder(Base):
    """Polled by the Railway cron service every minute (SPEC §2). Two kinds
    exist in Phase 1:

    - The daily nudge: one per user, `recurrence_rule="daily"`, `task_id`
      NULL. Its body is composed at send time from the current priority
      ranking, and the cron advances `scheduled_for` after sending.
    - Snooze reminders: one-shot rows with `task_id` set, created when a
      task is snoozed ("defer the reminder", SPEC §6). Deactivated after
      sending, or silently dropped if the task got done in the meantime.

    Phase 4 adds a third kind: list countdowns (`list_id` set — packing
    countdowns before Phase 6 generalized lists), whose body — "Trip in
    3 days, 6 items still to pack" — is composed at send time from the
    live list, then advanced daily until the event date.
    """

    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True
    )
    list_id: Mapped[int | None] = mapped_column(
        ForeignKey("lists.id", ondelete="CASCADE"), nullable=True
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

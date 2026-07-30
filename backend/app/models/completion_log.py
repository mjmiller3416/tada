from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CompletionLog(Base):
    """One row per completion (SPEC §3/§4) — the permanent history that
    feeds streaks, badges, and kid-completion notifications in later
    phases. Written by the scheduling service on every completion."""

    __tablename__ = "completion_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    completed_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    # "focus_session" | "direct" | "guest_mode" | "zone" | "campaign"
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="direct")
    # The task's last_done_at as it stood when this completion overwrote
    # it (Phase 9): the exact value undo restores. NULL = a first-ever
    # completion (undo returns the task to never-done) — or a row from
    # before the 0010 migration, an accepted one-day edge.
    previous_last_done_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Read-side convenience for the Done Today view (Phase 5).
    task: Mapped["Task"] = relationship("Task")  # noqa: F821

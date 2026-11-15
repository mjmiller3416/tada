from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
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
    # "focus_session" | "direct" | "guest_mode" | "zone" | "campaign" |
    # "hearth" (the Hearth wall — docs/hearth-integration.md) | "orbit"
    # (Link's planner app — routers/orbit.py). String(20) already fits
    # every value, so new sources need no migration.
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="direct")
    # The task's last_done_at as it stood when this completion overwrote
    # it (Phase 9): the exact value undo restores. NULL = a first-ever
    # completion (undo returns the task to never-done) — or a row from
    # before the 0010 migration, an accepted one-day edge.
    previous_last_done_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Parent check (migration 0014). NULL = an ordinary completion. For a
    # task that needs a parent check, a kid's Done writes "ready"; a
    # parent then marks it "checked" (physically inspected and approved)
    # or "sent_back" (not up to standard: the decay reset is reversed and
    # the chore is due again). services/parent_check.py owns the moves.
    check_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Who checked or sent it back, and when; the note rides with a send-back.
    checked_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    check_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Read-side convenience for the Done Today view (Phase 5).
    task: Mapped["Task"] = relationship("Task")  # noqa: F821

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Task(Base):
    """The central entity (SPEC §3). A task has no due date — it decays:
    `cadence_days` is the decay rate and `last_done_at` anchors the curve.
    All prioritization derives from those two fields via
    services/scheduling.py.

    `snoozed_until` powers the decay-aware snooze (SPEC §6): while set and
    in the future, the task is hidden from daily focus and sessions, but
    `last_done_at` is untouched so the task keeps aging quietly.
    """

    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    room_id: Mapped[int | None] = mapped_column(
        ForeignKey("rooms.id", ondelete="SET NULL"), nullable=True
    )

    category: Mapped[str] = mapped_column(
        String(20), nullable=False, default="cleaning"
    )  # "cleaning" | "maintenance" (maintenance UI is Phase 2)
    cadence_days: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    effort: Mapped[str] = mapped_column(String(10), nullable=False, default="quick")  # "quick" | "deep"
    guest_facing: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    last_done_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    snoozed_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    assignee_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    room: Mapped["Room | None"] = relationship(back_populates="tasks")  # noqa: F821

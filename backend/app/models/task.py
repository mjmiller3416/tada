from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, SmallInteger, String, Text
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

    Assignment (Phase 2): `assignee_id` pins a task to one member;
    `claimable` marks an unassigned task as "up for grabs" so kids can
    claim it. A task assigned to someone else stays out of your own
    doing-surfaces (it's delegated), but planning views show everything.

    `preferred_day` (Phase 8) is a ranking BOOST, never a schedule:
    Python weekday() convention (Monday = 0 ... Sunday = 6), null = no
    preference. The task still decays normally — missing the day carries
    no penalty and creates no overdue state.

    `task_type` (Phase 10/11, SPEC §4 lanes) says WHICH CLOCK schedules
    the task: routine / weekly_blessing / maintenance decay as always;
    zone tasks are eligible only during their zone's week (decay ranks
    within the pool); project is manual-only and never enters automatic
    selection. Phase 11's composer reads it behind zone_lane_enabled,
    and the review UI (task form + planning rows) edits it.
    """

    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    room_id: Mapped[int | None] = mapped_column(
        ForeignKey("rooms.id", ondelete="SET NULL"), nullable=True
    )

    # DEPRECATED (Phase 10): superseded by task_type. Kept only for
    # rollback safety — no code reads it anymore; drop the column in a
    # later cleanup phase once task_type has survived a full rotation.
    category: Mapped[str] = mapped_column(
        String(20), nullable=False, default="cleaning"
    )
    task_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="routine", server_default="routine"
    )  # "routine" | "weekly_blessing" | "zone" | "maintenance" | "project"
    cadence_days: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    effort: Mapped[str] = mapped_column(String(10), nullable=False, default="quick")  # "quick" | "deep"
    guest_facing: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    preferred_day: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True, default=None
    )  # Monday = 0 ... Sunday = 6; null = no preference (Phase 8)

    last_done_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    snoozed_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    assignee_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    claimable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    room: Mapped["Room | None"] = relationship(back_populates="tasks")  # noqa: F821
    # selectin so every surface that serializes tasks (focus, sessions,
    # chores, planning lists) gets these without per-call-site loader
    # options — no N+1s, and the inline supply flag is always available.
    assignee: Mapped["User | None"] = relationship(lazy="selectin")  # noqa: F821
    supplies: Mapped[list["Supply"]] = relationship(  # noqa: F821
        secondary="task_supplies", back_populates="tasks", lazy="selectin"
    )

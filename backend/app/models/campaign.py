from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Campaign(Base):
    """A seasonal campaign (SPEC §6, Phase 3): an episodic, opt-in bundle
    of tasks with a date window — "Spring Cleaning" — distinct from the
    everyday decay loop. Activating it surfaces its task set spread over
    the window's days and tracks % complete; it never replaces the decay
    engine, it sits on top of it."""

    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    #: A free label ("Spring", "Holiday prep") — display only.
    season: Mapped[str | None] = mapped_column(String(50), nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    # Ordered by the association table's natural order; deleting a
    # campaign takes its checklist with it, never the tasks themselves.
    task_links: Mapped[list["CampaignTask"]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan", lazy="selectin"
    )


class CampaignTask(Base):
    """One task's spot on a campaign's checklist (SPEC §3). `done` is the
    campaign's own progress flag — separate from the task's decay state,
    because "did it this spring" outlives the next regular clean."""

    __tablename__ = "campaign_tasks"

    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), primary_key=True
    )
    task_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    campaign: Mapped[Campaign] = relationship(back_populates="task_links")
    task: Mapped["Task"] = relationship(lazy="selectin")  # noqa: F821

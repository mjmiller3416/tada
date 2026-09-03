from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

#: Many-to-many Task <-> Supply (SPEC §3 TaskSupply). A plain association
#: table — the link carries no data of its own.
task_supplies = Table(
    "task_supplies",
    Base.metadata,
    Column("task_id", Integer, ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True),
    Column("supply_id", Integer, ForeignKey("supplies.id", ondelete="CASCADE"), primary_key=True),
)


class Supply(Base):
    """A cleaning supply (SPEC §6, Phase 2). Status is MANUAL only — one
    tap in the UI, never auto-decremented (auto-decrement is guesswork
    that drifts).

    Tada has no shopping list of its own: when status goes low/out the
    supply is pushed into Enchanted Spoon's list (services/mealgenie.py), and
    `last_pushed_at` dedupes so one low-run is pushed exactly once.
    Restocking clears it, so the next low-run pushes again."""

    __tablename__ = "supplies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(
        String(10), nullable=False, default="in_stock"
    )  # "in_stock" | "low" | "out"
    last_pushed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    tasks: Mapped[list["Task"]] = relationship(  # noqa: F821
        secondary=task_supplies, back_populates="supplies"
    )

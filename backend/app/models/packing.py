from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

#: The ten list categories (Phase 4 spec). Stored as plain strings; the
#: API schema validates against this set.
PACKING_CATEGORIES: tuple[str, ...] = (
    "moving",
    "travel",
    "events",
    "work",
    "outdoor",
    "family_kids",
    "emergency",
    "shipping_storage",
    "everyday",
    "custom",
)


class PackingList(Base):
    """A packing checklist (Phase 4) — a deliberately separate world from
    cleaning tasks. One-off and event-driven: no cadence, no dirtiness,
    no last_done_at, and it never touches the scheduling engine.

    Templates are just template-flagged lists (`is_template = True`), so
    one set of tables covers both — "create from template" clones a
    template's sections + items into a fresh active list, and reusing an
    archived list is the very same clone."""

    __tablename__ = "packing_lists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    is_template: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: Move/trip date — drives the optional countdown reminder.
    event_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    #: "active" | "archived". Finished lists archive (never delete) so
    #: they can be referenced or cloned again later.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    sections: Mapped[list["PackingSection"]] = relationship(
        back_populates="packing_list",
        cascade="all, delete-orphan",
        order_by="PackingSection.sort_order",
        lazy="selectin",
    )


class PackingSection(Base):
    """A group within a list ("Clothes", "Documents", ...). Sections keep
    the full checklist scannable — the whole point of packing is seeing
    everything at once, grouped."""

    __tablename__ = "packing_sections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    list_id: Mapped[int] = mapped_column(
        ForeignKey("packing_lists.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Named packing_list (not `list`) — a relationship called `list`
    # shadows the builtin inside this class's lazily-evaluated Mapped[]
    # annotations and breaks mapper configuration.
    packing_list: Mapped[PackingList] = relationship(back_populates="sections")
    items: Mapped[list["PackingItem"]] = relationship(
        back_populates="section",
        cascade="all, delete-orphan",
        order_by="PackingItem.sort_order",
        lazy="selectin",
    )


class PackingItem(Base):
    """One checkbox on the list. `packed` is the whole state machine —
    no decay, no completion log, no reset curve."""

    __tablename__ = "packing_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    section_id: Mapped[int] = mapped_column(
        ForeignKey("packing_sections.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    #: Free text ("2", "1 per person") — quantities are notes, not math.
    quantity: Mapped[str | None] = mapped_column(String(50), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    packed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    section: Mapped[PackingSection] = relationship(back_populates="items")

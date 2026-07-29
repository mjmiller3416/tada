from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

#: What a list is *for* (Phase 6). Kind drives small presentation
#: differences only — packing leans on sections, shopping makes quantity
#: and price prominent, tasks reads flat, custom has no opinion. Stored
#: as plain strings; the API schema validates against this set.
LIST_KINDS: tuple[str, ...] = (
    "packing",
    "shopping",
    "tasks",
    "custom",
)


class List(Base):
    """A general-purpose checklist (Phase 6, grown out of Phase 4's
    packing module) — a deliberately separate world from cleaning tasks.
    One-off: no cadence, no dirtiness, no last_done_at, and it never
    touches the scheduling engine. List items must never surface on the
    daily focus home screen or in a focus session.

    Templates are just template-flagged lists (`is_template = True`), so
    one set of tables covers both — "create from template" clones a
    template's sections + items into a fresh active list, and reusing an
    archived list is the very same clone."""

    __tablename__ = "lists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    is_template: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: Trip/move/holiday date — drives the optional countdown reminder.
    event_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    #: Where the list is headed ("Orlando", "Grandma's") — packing color.
    destination: Mapped[str | None] = mapped_column(String(120), nullable=True)
    #: How long, as free text ("5 days", "a long weekend") — a note,
    #: not math, same philosophy as item quantities.
    duration: Mapped[str | None] = mapped_column(String(60), nullable=True)
    #: "active" | "archived". Finished lists archive (never delete) so
    #: they can be referenced or cloned again later.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    sections: Mapped[list["ListSection"]] = relationship(
        back_populates="parent_list",
        cascade="all, delete-orphan",
        order_by="ListSection.sort_order",
        lazy="selectin",
    )


class ListSection(Base):
    """A group within a list ("Clothes", "Documents", ...). Sections keep
    a big checklist scannable; a list with a single section renders as a
    plain flat list (the header hides client-side)."""

    __tablename__ = "list_sections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    list_id: Mapped[int] = mapped_column(
        ForeignKey("lists.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Named parent_list (not `list`) — a relationship called `list`
    # shadows the builtin inside this class's lazily-evaluated Mapped[]
    # annotations and breaks mapper configuration.
    parent_list: Mapped[List] = relationship(back_populates="sections")
    items: Mapped[list["ListItem"]] = relationship(
        back_populates="section",
        cascade="all, delete-orphan",
        order_by="ListItem.sort_order",
        lazy="selectin",
    )


class ListItem(Base):
    """One checkbox on the list. `packed` is the whole state machine —
    no decay, no completion log, no reset curve."""

    __tablename__ = "list_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    section_id: Mapped[int] = mapped_column(
        ForeignKey("list_sections.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    #: Free text ("2", "1 per person") — quantities are notes, not math.
    quantity: Mapped[str | None] = mapped_column(String(50), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    packed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: Optional price (Phase 6) — Numeric, never a float for money.
    #: Totals are computed in the read model, never stored.
    price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    section: Mapped[ListSection] = relationship(back_populates="items")

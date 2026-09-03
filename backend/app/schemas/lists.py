from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.models.lists import LIST_KINDS, List, ListSection
from app.services import lists as list_service


def _money(value: Decimal | None) -> str | None:
    """Decimal -> "12.50" (or None). Money travels as a string so no
    JSON float ever touches it; the frontend only formats it."""
    return None if value is None else f"{value:.2f}"


class ListItemRead(BaseModel):
    id: int
    name: str
    quantity: str | None
    notes: str | None
    packed: bool
    price: str | None
    sort_order: int


class ListSectionRead(BaseModel):
    id: int
    name: str
    sort_order: int
    packed_count: int
    total_count: int
    items: list[ListItemRead]


class ListRead(BaseModel):
    """A list summary with its progress rollup — what the index shows.
    Price totals are computed here, never stored, and stay None until at
    least one item is priced (no pointless $0.00 on a packing list)."""

    id: int
    name: str
    kind: str
    is_template: bool
    event_date: date | None
    destination: str | None
    duration: str | None
    status: str
    packed_count: int
    total_count: int
    percent: int
    #: Sum over priced items; "checked" reads as spend-to-date on a
    #: shopping list ("$340 of $500"). None when nothing is priced.
    checked_price: str | None
    total_price: str | None
    created_at: datetime


class ListDetail(ListRead):
    """The full grouped checklist, plus whether the countdown nudge is on."""

    reminder_enabled: bool
    sections: list[ListSectionRead]


class ListCreate(BaseModel):
    """Clone a source list — a starter template or a finished archived
    list, same move — into a fresh active list."""

    source_list_id: int
    #: Defaults to the source's name when omitted.
    name: str | None = Field(default=None, min_length=1, max_length=120)
    event_date: date | None = None
    destination: str | None = Field(default=None, max_length=120)
    #: Free text ("5 days", "a long weekend") — a note, not math.
    duration: str | None = Field(default=None, max_length=60)


class ListUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    event_date: date | None = None
    clear_event_date: bool = False
    destination: str | None = Field(default=None, max_length=120)
    clear_destination: bool = False
    duration: str | None = Field(default=None, max_length=60)
    clear_duration: bool = False
    status: str | None = None
    #: Turn the countdown nudge on/off (needs an event_date to turn on).
    reminder_enabled: bool | None = None
    #: None = not provided — the sync keeps the lead already persisted on
    #: the reminder (issue #19: a rename must never snap a 14-day lead
    #: back to the default 3).
    reminder_days_before: int | None = Field(default=None, ge=0, le=30)

    @field_validator("status")
    @classmethod
    def check_status(cls, value: str | None) -> str | None:
        if value is not None and value not in ("active", "archived"):
            raise ValueError("status must be 'active' or 'archived'")
        return value


class ListSectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ListSectionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    #: Target position within the list (0-based); the service reindexes.
    sort_order: int | None = Field(default=None, ge=0)


class ListItemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    quantity: str | None = Field(default=None, max_length=50)
    notes: str | None = None
    #: Decimal in, Decimal stored — never a float for money.
    price: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)


class ListItemUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    quantity: str | None = Field(default=None, max_length=50)
    clear_quantity: bool = False
    notes: str | None = None
    clear_notes: bool = False
    packed: bool | None = None
    price: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    clear_price: bool = False
    #: Target position within the section (0-based); the service reindexes.
    sort_order: int | None = Field(default=None, ge=0)


def section_to_read(section: ListSection) -> ListSectionRead:
    packed, total = list_service.section_progress(section)
    return ListSectionRead(
        id=section.id,
        name=section.name,
        sort_order=section.sort_order,
        packed_count=packed,
        total_count=total,
        items=[
            ListItemRead(
                id=item.id,
                name=item.name,
                quantity=item.quantity,
                notes=item.notes,
                packed=item.packed,
                price=_money(item.price),
                sort_order=item.sort_order,
            )
            for item in section.items
        ],
    )


def list_to_read(parent_list: List) -> ListRead:
    packed, total = list_service.progress(parent_list)
    totals = list_service.price_totals(parent_list)
    return ListRead(
        id=parent_list.id,
        name=parent_list.name,
        kind=parent_list.kind if parent_list.kind in LIST_KINDS else "custom",
        is_template=parent_list.is_template,
        event_date=parent_list.event_date,
        destination=parent_list.destination,
        duration=parent_list.duration,
        status=parent_list.status,
        packed_count=packed,
        total_count=total,
        percent=round(100 * packed / total) if total else 0,
        checked_price=_money(totals[0]) if totals else None,
        total_price=_money(totals[1]) if totals else None,
        created_at=parent_list.created_at,
    )


def list_to_detail(parent_list: List, reminder_enabled: bool) -> ListDetail:
    base = list_to_read(parent_list)
    return ListDetail(
        **base.model_dump(),
        reminder_enabled=reminder_enabled,
        sections=[section_to_read(section) for section in parent_list.sections],
    )

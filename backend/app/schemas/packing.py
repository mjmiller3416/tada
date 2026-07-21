from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

from app.models.packing import PACKING_CATEGORIES, PackingList, PackingSection
from app.services import packing as packing_service


class PackingItemRead(BaseModel):
    id: int
    name: str
    quantity: str | None
    notes: str | None
    packed: bool
    sort_order: int


class PackingSectionRead(BaseModel):
    id: int
    name: str
    sort_order: int
    packed_count: int
    total_count: int
    items: list[PackingItemRead]


class PackingListRead(BaseModel):
    """A list summary with its progress rollup — what the index shows."""

    id: int
    name: str
    category: str
    is_template: bool
    event_date: date | None
    destination: str | None
    duration: str | None
    status: str
    packed_count: int
    total_count: int
    percent: int
    created_at: datetime


class PackingListDetail(PackingListRead):
    """The full grouped checklist, plus whether the countdown nudge is on."""

    reminder_enabled: bool
    sections: list[PackingSectionRead]


class PackingListCreate(BaseModel):
    """Clone a source list — a starter template or a finished archived
    list, same move — into a fresh active list."""

    source_list_id: int
    #: Defaults to the source's name when omitted.
    name: str | None = Field(default=None, min_length=1, max_length=120)
    event_date: date | None = None
    destination: str | None = Field(default=None, max_length=120)
    #: Free text ("5 days", "a long weekend") — a note, not math.
    duration: str | None = Field(default=None, max_length=60)


class PackingListUpdate(BaseModel):
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
    reminder_days_before: int = Field(
        default=packing_service.DEFAULT_REMINDER_DAYS_BEFORE, ge=0, le=30
    )

    @field_validator("status")
    @classmethod
    def check_status(cls, value: str | None) -> str | None:
        if value is not None and value not in ("active", "archived"):
            raise ValueError("status must be 'active' or 'archived'")
        return value


class PackingSectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class PackingSectionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    #: Target position within the list (0-based); the service reindexes.
    sort_order: int | None = Field(default=None, ge=0)


class PackingItemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    quantity: str | None = Field(default=None, max_length=50)
    notes: str | None = None


class PackingItemUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    quantity: str | None = Field(default=None, max_length=50)
    clear_quantity: bool = False
    notes: str | None = None
    clear_notes: bool = False
    packed: bool | None = None
    #: Target position within the section (0-based); the service reindexes.
    sort_order: int | None = Field(default=None, ge=0)


def section_to_read(section: PackingSection) -> PackingSectionRead:
    packed, total = packing_service.section_progress(section)
    return PackingSectionRead(
        id=section.id,
        name=section.name,
        sort_order=section.sort_order,
        packed_count=packed,
        total_count=total,
        items=[
            PackingItemRead(
                id=item.id,
                name=item.name,
                quantity=item.quantity,
                notes=item.notes,
                packed=item.packed,
                sort_order=item.sort_order,
            )
            for item in section.items
        ],
    )


def list_to_read(packing_list: PackingList) -> PackingListRead:
    packed, total = packing_service.progress(packing_list)
    return PackingListRead(
        id=packing_list.id,
        name=packing_list.name,
        category=packing_list.category
        if packing_list.category in PACKING_CATEGORIES
        else "custom",
        is_template=packing_list.is_template,
        event_date=packing_list.event_date,
        destination=packing_list.destination,
        duration=packing_list.duration,
        status=packing_list.status,
        packed_count=packed,
        total_count=total,
        percent=round(100 * packed / total) if total else 0,
        created_at=packing_list.created_at,
    )


def list_to_detail(
    packing_list: PackingList, reminder_enabled: bool
) -> PackingListDetail:
    base = list_to_read(packing_list)
    return PackingListDetail(
        **base.model_dump(),
        reminder_enabled=reminder_enabled,
        sections=[section_to_read(section) for section in packing_list.sections],
    )

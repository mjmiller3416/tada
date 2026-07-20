from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.task import Task
from app.services import scheduling

Effort = Literal["quick", "deep"]
Category = Literal["cleaning", "maintenance"]


class SupplyBrief(BaseModel):
    """A linked supply as it rides along on a task — just enough for the
    inline "heads up, you're low on X" flag (SPEC §6 Supplies)."""

    id: int
    name: str
    status: str


class TaskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    room_id: int | None = None
    category: Category = "cleaning"
    cadence_days: int = Field(ge=1, le=730)
    estimated_minutes: int = Field(ge=1, le=480)
    effort: Effort = "quick"
    guest_facing: bool = False
    assignee_id: int | None = None
    claimable: bool = False
    supply_ids: list[int] | None = None
    notes: str | None = None


class TaskUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    room_id: int | None = None
    clear_room: bool = False  # room_id=None is also "not provided", so clearing is explicit
    category: Category | None = None
    cadence_days: int | None = Field(default=None, ge=1, le=730)
    estimated_minutes: int | None = Field(default=None, ge=1, le=480)
    effort: Effort | None = None
    guest_facing: bool | None = None
    assignee_id: int | None = None
    clear_assignee: bool = False  # same pattern as clear_room
    claimable: bool | None = None
    supply_ids: list[int] | None = None
    notes: str | None = None
    is_active: bool | None = None


class TaskRead(BaseModel):
    """A task plus its computed decay state — every surface renders from
    the same `ratio`/`band` the scheduling service produced."""

    id: int
    name: str
    room_id: int | None
    room_name: str | None
    category: str
    cadence_days: int
    estimated_minutes: int
    effort: str
    guest_facing: bool
    last_done_at: datetime | None
    snoozed_until: datetime | None
    is_snoozed: bool
    is_active: bool
    assignee_id: int | None
    assignee_name: str | None
    claimable: bool
    supplies: list[SupplyBrief]
    notes: str | None
    ratio: float
    band: str


def task_to_read(task: Task, now: datetime | None = None) -> TaskRead:
    ratio = scheduling.dirtiness_ratio(task, now)
    return TaskRead(
        id=task.id,
        name=task.name,
        room_id=task.room_id,
        room_name=task.room.name if task.room else None,
        category=task.category,
        cadence_days=task.cadence_days,
        estimated_minutes=task.estimated_minutes,
        effort=task.effort,
        guest_facing=task.guest_facing,
        last_done_at=task.last_done_at,
        snoozed_until=task.snoozed_until,
        is_snoozed=scheduling.is_snoozed(task, now),
        is_active=task.is_active,
        assignee_id=task.assignee_id,
        assignee_name=task.assignee.name if task.assignee else None,
        claimable=task.claimable,
        supplies=[
            SupplyBrief(id=s.id, name=s.name, status=s.status) for s in task.supplies
        ],
        notes=task.notes,
        ratio=round(ratio, 3),
        band=scheduling.band_for_ratio(ratio),
    )


class CompleteRequest(BaseModel):
    source: Literal["focus_session", "direct"] = "direct"


class SnoozeRequest(BaseModel):
    option: Literal["later_today", "tomorrow", "few_days", "wake"]

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.models.task import Task
from app.services import scheduling

Effort = Literal["quick", "deep"]
# The form's two-way toggle (kept through Phase 10; the five-type review
# UI arrives in Phase 11). It now maps onto task_type — the Task.category
# column is deprecated and no longer read or meaningfully written.
Category = Literal["cleaning", "maintenance"]
TaskType = Literal["routine", "weekly_blessing", "zone", "maintenance", "project"]
# Where a completion came from — recorded on the CompletionLog so history
# can tell a focus session from a zone week from a campaign (SPEC §3).
# "hearth" is the Hearth wall (docs/hearth-integration.md gap #2); the
# String(20) column already fits it, so adding it needs no migration.
Source = Literal[
    "focus_session", "direct", "guest_mode", "zone", "campaign", "hearth"
]


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
    # The Phase 11 five-type picker. When omitted, the legacy category
    # toggle decides (maintenance -> maintenance, otherwise routine).
    task_type: TaskType | None = None
    cadence_days: int = Field(ge=1, le=730)
    estimated_minutes: int = Field(ge=1, le=480)
    effort: Effort = "quick"
    guest_facing: bool = False
    assignee_id: int | None = None
    claimable: bool = False
    supply_ids: list[int] | None = None
    notes: str | None = None
    # "Usually a Saturday job" (Phase 8): Monday = 0 ... Sunday = 6.
    # A ranking preference, never a deadline; None = no preference.
    preferred_day: int | None = Field(default=None, ge=0, le=6)


class TaskUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    room_id: int | None = None
    clear_room: bool = False  # room_id=None is also "not provided", so clearing is explicit
    category: Category | None = None
    # The Phase 11 reclassification review: the five-type editor. Takes
    # precedence over the legacy two-way category toggle when both arrive.
    task_type: TaskType | None = None
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
    # "When was this last done?" (Phase 4.6): a correction to history —
    # the decay engine reads last_done_at as its only anchor, so editing
    # it is exposing an existing field, never a new scheduling concept.
    last_done_at: datetime | None = None
    clear_last_done: bool = False  # back to "never done"; same pattern as clear_room
    # Preferred day (Phase 8): a preference, never a deadline.
    preferred_day: int | None = Field(default=None, ge=0, le=6)
    clear_preferred_day: bool = False  # back to "no set day"; same pattern as clear_room

    @field_validator("last_done_at")
    @classmethod
    def validate_last_done_at(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return value
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        if value > datetime.now(timezone.utc):
            raise ValueError("can't be in the future — it's when it was last done")
        return value


class TaskRead(BaseModel):
    """A task plus its computed decay state — every surface renders from
    the same `ratio`/`band` the scheduling service produced.

    With the Phase 11 lanes active, an out-of-window zone mission's
    `band` reads "waiting" instead of a color band — the no-debt rule's
    display half — and `zone_name` names the zone its week belongs to
    (the home card's mission label, and the "waits for Kitchen week"
    copy). `ratio` stays honest either way."""

    id: int
    name: str
    room_id: int | None
    room_name: str | None
    # Editable via the Phase 11 review UI (task form + planning rows).
    task_type: TaskType
    # Derived compatibility view of task_type — kept so the API shape
    # doesn't change under a client mid-deploy. Nothing reads the
    # deprecated Task.category column itself.
    category: str
    cadence_days: int
    estimated_minutes: int
    effort: str
    guest_facing: bool
    preferred_day: int | None
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
    band: str  # a SPEC §4 color band, or "waiting" (Phase 11, see above)
    zone_name: str | None = None


def task_to_read(
    task: Task,
    now: datetime | None = None,
    ctx: "scheduling.ZoneWindowContext | None" = None,
) -> TaskRead:
    """`ctx` (from scheduling.presentation_context) is None whenever the
    lanes are off, so every legacy surface serializes exactly as before —
    only lanes-active reads present the waiting state."""
    ratio = scheduling.dirtiness_ratio(task, now)
    band = scheduling.band_for_ratio(ratio)
    if not scheduling.in_zone_window(task, ctx):
        band = "waiting"
    return TaskRead(
        id=task.id,
        name=task.name,
        room_id=task.room_id,
        room_name=task.room.name if task.room else None,
        task_type=task.task_type,
        category="maintenance" if task.task_type == "maintenance" else "cleaning",
        cadence_days=task.cadence_days,
        estimated_minutes=task.estimated_minutes,
        effort=task.effort,
        guest_facing=task.guest_facing,
        preferred_day=task.preferred_day,
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
        band=band,
        zone_name=scheduling.window_zone_name(task, ctx),
    )


class CompleteRequest(BaseModel):
    # The Phase 3 lenses log their own source so history can tell a
    # chaos clean from a zone week from a campaign (SPEC §3).
    source: Source = "direct"


class CompleteResponse(TaskRead):
    """The completed task, plus the id of the CompletionLog row just
    written — the handle the undo toast needs (Phase 9)."""

    completion_id: int


class SnoozeRequest(BaseModel):
    option: Literal["later_today", "tomorrow", "few_days", "wake"]

"""Request/response shapes for the Orbit integration (routers/orbit.py).

Orbit is Link's personal planner — a separate app that reads his chores
from Tada and checks them off. These shapes are the contract Orbit is
built against, so field names are fixed: snake_case, every id a STRING on
the wire (Tada's integer ids serialized with str()), datetimes ISO 8601
with the household's offset, dates as YYYY-MM-DD in the household's
timezone. Request ids are accepted as strings or bare numbers.
"""

from datetime import date as Date
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class OrbitMember(BaseModel):
    id: str
    name: str
    role: str  # "owner" | "kid"


class OrbitMembersResponse(BaseModel):
    members: list[OrbitMember]


class OrbitMemberRef(BaseModel):
    id: str
    name: str


class OrbitChore(BaseModel):
    """One chore as Orbit shows it. `due_on` is when Tada's own decay /
    Monday-reset logic next puts the chore in front of the member (never a
    deadline Tada enforces); `done` / `completion_id` / `completed_at` /
    `can_undo` describe today's completion by this member, if any."""

    id: str
    name: str
    room: str | None
    instructions: str | None  # Task.notes
    estimated_minutes: int | None
    effort: str | int | None
    cadence_days: int | None
    cadence_label: str | None
    preferred_day: int | None  # Monday = 0
    due_on: Date | None
    done: bool
    completion_id: str | None
    completed_at: datetime | None
    can_undo: bool
    claimable: bool
    assigned_to_member: bool


class OrbitStats(BaseModel):
    current_streak: int
    longest_streak: int
    completed_today: int
    completed_this_week: int


class OrbitChoresResponse(BaseModel):
    member: OrbitMemberRef
    date: Date
    timezone: str
    today: list[OrbitChore]
    upcoming: list[OrbitChore]
    recurring: list[OrbitChore]
    stats: OrbitStats


class OrbitCompletion(BaseModel):
    completion_id: str
    task_id: str
    task_name: str
    room: str | None
    completed_at: datetime
    source: str


class OrbitCompletionsResponse(BaseModel):
    completions: list[OrbitCompletion]


class OrbitCompleteRequest(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True)

    task_id: str
    member_id: str


class OrbitCompleteResponse(BaseModel):
    completion_id: str
    completed_at: datetime


class OrbitUndoRequest(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True)

    completion_id: str
    member_id: str

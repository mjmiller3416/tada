from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.badges import BadgeRead
from app.schemas.tasks import Effort, TaskRead


class FocusResponse(BaseModel):
    """The daily focus home screen payload. `total_active_tasks` lets the
    frontend tell "all caught up" apart from "not set up yet"."""

    tasks: list[TaskRead]
    total_active_tasks: int


class SessionBuildRequest(BaseModel):
    """One request shape for every session trigger (SPEC §5/§6): a time
    budget, a room, and — Phase 3 — a zone, a campaign, or guest/Chaos
    mode. The lenses stack except `campaign_id`, which builds from the
    campaign's own checklist instead."""

    minutes: int | None = Field(default=None, ge=5, le=240)
    room_id: int | None = None
    effort: Effort | None = None
    zone_id: int | None = None
    campaign_id: int | None = None
    guest: bool = False
    # Phase 11: a mission-only zone session ("this week's zone", or the
    # planning path with an explicit zone_id). Ignored while the lanes
    # are off — the request gracefully degrades to the legacy zone-scoped
    # session, so an updated client never breaks against the flag.
    zone_missions: bool = False
    # Phase 5: a timer-extend top-up excludes what's already queued so
    # the added minutes bring genuinely new tasks.
    exclude_task_ids: list[int] = Field(default_factory=list)


class SessionBuildResponse(BaseModel):
    tasks: list[TaskRead]
    total_minutes: int


class SessionCompleteRequest(BaseModel):
    """Sent when a session ends (SPEC §5: session-complete celebration +
    badge check). `started_at` lets the response include badges earned
    mid-session too, so nothing gets celebrated late — or twice."""

    tasks_done: int = Field(ge=0)
    started_at: datetime | None = None


class SessionCompleteResponse(BaseModel):
    new_badges: list[BadgeRead]


class SessionTimerRequest(BaseModel):
    """Start (or extend by) this many minutes. Matches the session
    budget's own bounds."""

    minutes: int = Field(ge=5, le=240)


class SessionTimerRead(BaseModel):
    id: int
    fires_at: datetime

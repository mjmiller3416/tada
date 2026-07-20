from pydantic import BaseModel, Field

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


class SessionBuildResponse(BaseModel):
    tasks: list[TaskRead]
    total_minutes: int

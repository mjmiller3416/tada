from pydantic import BaseModel, Field

from app.schemas.tasks import Effort, TaskRead


class FocusResponse(BaseModel):
    """The daily focus home screen payload. `total_active_tasks` lets the
    frontend tell "all caught up" apart from "not set up yet"."""

    tasks: list[TaskRead]
    total_active_tasks: int


class SessionBuildRequest(BaseModel):
    minutes: int | None = Field(default=None, ge=5, le=240)
    room_id: int | None = None
    effort: Effort | None = None


class SessionBuildResponse(BaseModel):
    tasks: list[TaskRead]
    total_minutes: int

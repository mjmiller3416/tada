"""Request/response shapes for the Hearth wall (docs/hearth-integration.md).

These match Hearth's client (src/lib/tada/client.ts) exactly. Every id is
a STRING on the wire — Tada's integer User/Room/Task/CompletionLog ids
serialized with str(); Hearth treats room ids as opaque round-trip values
and resolves memberId through its own TADA_MEMBERS map. The `room` field
inside a task/completion is the room NAME (display text), not the filter
id — the same split the doc's examples show.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class HearthRoom(BaseModel):
    id: str
    name: str


class HearthRoomsResponse(BaseModel):
    rooms: list[HearthRoom]


class HearthTask(BaseModel):
    """A single task for the Clean view — id/name/room only. The decay
    score is deliberately absent (SPEC D4: the wall shows one task, never
    a priority number)."""

    id: str
    name: str
    room: str | None


class HearthNextResponse(BaseModel):
    task: HearthTask | None


class HearthCompletion(BaseModel):
    completionId: str
    taskName: str
    room: str | None
    completedAt: datetime  # in the member's timezone, so the ISO offset is local


class HearthDoneTodayResponse(BaseModel):
    completions: list[HearthCompletion]


class HearthKidChore(BaseModel):
    id: str
    name: str
    done: bool
    completionId: str | None = None  # the undo handle, present only when done


class HearthKid(BaseModel):
    memberId: str
    chores: list[HearthKidChore]


class HearthKidsResponse(BaseModel):
    kids: list[HearthKid]


class HearthCompleteRequest(BaseModel):
    taskId: str
    memberId: str
    source: Literal["hearth"] = "hearth"


class HearthCompleteResponse(BaseModel):
    completionId: str


class HearthUndoRequest(BaseModel):
    completionId: str
    memberId: str

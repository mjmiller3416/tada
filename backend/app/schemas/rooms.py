from pydantic import BaseModel, Field


class RoomCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class RoomUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    sort_order: int | None = None


class RoomRead(BaseModel):
    """A room plus its aggregate dirtiness (SPEC §4) for the Room view.
    `ratio`/`band` are None when the room has no active tasks."""

    id: int
    name: str
    sort_order: int
    ratio: float | None
    band: str | None
    task_count: int
    due_count: int

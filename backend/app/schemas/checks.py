"""Shapes for the parent check (services/parent_check.py)."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.completion_log import CompletionLog
from app.models.user import User
from app.services.parent_check import NOTE_MAX_LENGTH


class CheckItem(BaseModel):
    """One completion as the parent check sees it: what was done, by whom
    and when, and where its check stands. `status` is "ready" (waiting for
    a parent to look), "checked" (a parent physically inspected and
    approved it) or "sent_back" (due again; `note` says why)."""

    completion_id: int
    task_id: int
    task_name: str
    room_id: int | None
    room_name: str | None
    done_by_id: int
    done_by_name: str
    done_at: datetime
    status: str
    checked_by_id: int | None = None
    checked_by_name: str | None = None
    checked_at: datetime | None = None
    note: str | None = None


class CheckListResponse(BaseModel):
    """The parents' "To check" list, longest-waiting first. Small by
    nature: only chores whose task asks for a parent check land here."""

    waiting: list[CheckItem]


class SendBackRequest(BaseModel):
    # Optional: "the mirror still has streaks" — shown to the kid.
    note: str | None = Field(default=None, max_length=NOTE_MAX_LENGTH)


def _first_name(members: dict[int, User], member_id: int | None) -> str | None:
    if member_id is None:
        return None
    member = members.get(member_id)
    return member.name.split()[0] if member else "Someone"


def check_to_item(log: CompletionLog, members: dict[int, User]) -> CheckItem:
    """Project a completion row (task + room loaded) for the check views.
    `members` maps user id -> User, for the first names."""
    return CheckItem(
        completion_id=log.id,
        task_id=log.task_id,
        task_name=log.task.name,
        room_id=log.task.room_id,
        room_name=log.task.room.name if log.task.room else None,
        done_by_id=log.completed_by,
        done_by_name=_first_name(members, log.completed_by) or "Someone",
        done_at=log.completed_at,
        status=log.check_status or "done",
        checked_by_id=log.checked_by,
        checked_by_name=_first_name(members, log.checked_by),
        checked_at=log.checked_at,
        note=log.check_note,
    )

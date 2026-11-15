"""The parent check's routes (services/parent_check.py has the rules).

A kid asks for a check with a plain Done on a task that needs one (or
POST /api/tasks/{id}/ready-for-check). Everything here is the parent's
side: the "To check" list, "checked", "send back" and undoing either.
All of it is adults only (require_owner), and the service checks again.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models.completion_log import CompletionLog
from app.models.task import Task
from app.models.user import User
from app.routers.auth import require_owner
from app.schemas.checks import (
    CheckItem,
    CheckListResponse,
    SendBackRequest,
    check_to_item,
)
from app.services import completion, parent_check, settings_service

router = APIRouter(prefix="/api/checks", tags=["checks"])


def _members(db: Session) -> dict[int, User]:
    return {u.id: u for u in db.scalars(select(User)).all()}


def _get_log(db: Session, completion_id: int) -> CompletionLog:
    log = db.scalar(
        select(CompletionLog)
        .options(joinedload(CompletionLog.task).joinedload(Task.room))
        .where(CompletionLog.id == completion_id)
    )
    if log is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Completion not found")
    return log


def _apply(db: Session, log: CompletionLog, move) -> CheckItem:
    """Run one parent-check move, mapping its refusals to HTTP, then
    commit and project the row."""
    try:
        move()
    except parent_check.NotAParent as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc))
    except parent_check.CheckRefused as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    db.commit()
    db.refresh(log)
    return check_to_item(log, _members(db))


@router.get("", response_model=CheckListResponse)
def list_waiting(
    _: User = Depends(require_owner), db: Session = Depends(get_db)
) -> CheckListResponse:
    """What's waiting for a parent to look at, longest-waiting first."""
    members = _members(db)
    return CheckListResponse(
        waiting=[check_to_item(log, members) for log in parent_check.waiting_for_check(db)]
    )


@router.post("/{completion_id}/checked", response_model=CheckItem)
def mark_checked(
    completion_id: int,
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> CheckItem:
    """A parent physically inspected it and it's good. Records who and
    when; the schedule doesn't move (it reset when the chore was done)."""
    log = _get_log(db, completion_id)
    return _apply(db, log, lambda: parent_check.mark_checked(db, log, current_user))


@router.post("/{completion_id}/send-back", response_model=CheckItem)
def send_back(
    completion_id: int,
    payload: SendBackRequest,
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> CheckItem:
    """Not up to standard: the chore is due again, with an optional note
    for whoever did it (who also gets a gentle push)."""
    log = _get_log(db, completion_id)
    tz = settings_service.user_timezone(db, current_user.id)
    item = _apply(
        db,
        log,
        lambda: parent_check.send_back(db, log, current_user, payload.note, tz=tz),
    )
    completion.notify_sent_back(db, log, log.task, current_user)
    return item


@router.post("/{completion_id}/undo", response_model=CheckItem)
def undo_check(
    completion_id: int,
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> CheckItem:
    """Take back "checked" or "sent back": the completion is waiting for a
    check again (undoing a send-back also puts the chore's decay reset
    back)."""
    log = _get_log(db, completion_id)
    tz = settings_service.user_timezone(db, current_user.id)
    return _apply(db, log, lambda: parent_check.undo_check(db, log, current_user, tz=tz))

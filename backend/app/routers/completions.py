"""Undo a completion (Phase 9).

The whole premise of Tada is that mistakes are fine — this applies that
to the app's own primary interaction. Undo reverses the decay state
only: streaks and badges are untouched (services/scheduling.py has the
reasoning). Scoped to today's completions; older history is the Phase
4.6 last-done editor's job.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.completion_log import CompletionLog
from app.models.user import User
from app.routers.auth import get_current_user
from app.schemas.tasks import TaskRead, task_to_read
from app.services import scheduling, settings_service

router = APIRouter(prefix="/api/completions", tags=["completions"])


@router.post("/{completion_id}/undo", response_model=TaskRead)
def undo_completion(
    completion_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TaskRead:
    """Reverse one of today's completions. An owner can undo any of
    them; a kid only their own. A correction, not a dispute — nothing
    more elaborate than that."""
    log = db.get(CompletionLog, completion_id)
    if log is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Completion not found")
    if current_user.role != "owner" and log.completed_by != current_user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "That one isn't yours to undo")

    try:
        task = scheduling.undo_completion(
            db, log, tz=settings_service.user_timezone(db, current_user.id)
        )
    except scheduling.UndoWindowClosed as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))

    db.commit()
    db.refresh(task)
    return task_to_read(
        task, ctx=scheduling.presentation_context(db, current_user.id)
    )

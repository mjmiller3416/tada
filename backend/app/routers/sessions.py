from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.task import Task
from app.models.user import User
from app.routers.auth import get_current_user
from app.schemas.sessions import FocusResponse, SessionBuildRequest, SessionBuildResponse
from app.schemas.tasks import task_to_read
from app.services import scheduling, settings_service

router = APIRouter(prefix="/api", tags=["sessions"])


@router.get("/focus", response_model=FocusResponse)
def daily_focus(
    effort: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FocusResponse:
    """The calm home screen (SPEC §6): top 1–3 tasks by priority. The
    count comes from the daily_focus_count setting."""
    limit = int(settings_service.get_setting(db, current_user.id, "daily_focus_count"))
    effort = effort if effort in ("quick", "deep") else None
    tasks = scheduling.daily_focus(db, limit=limit, effort=effort)
    total = db.scalar(select(func.count(Task.id)).where(Task.is_active.is_(True))) or 0
    return FocusResponse(
        tasks=[task_to_read(t) for t in tasks],
        total_active_tasks=total,
    )


@router.post("/sessions/build", response_model=SessionBuildResponse)
def build_session(
    payload: SessionBuildRequest,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SessionBuildResponse:
    """Build a focus session (SPEC §5): "I have X minutes" greedy fill
    and/or a room-scoped session. The frontend presents the result one
    task at a time — never as a list."""
    tasks = scheduling.build_session(
        db,
        minutes=payload.minutes,
        room_id=payload.room_id,
        effort=payload.effort,
    )
    return SessionBuildResponse(
        tasks=[task_to_read(t) for t in tasks],
        total_minutes=sum(t.estimated_minutes for t in tasks),
    )

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.campaign import Campaign
from app.models.task import Task
from app.models.user import User
from app.routers.auth import require_owner
from app.schemas.sessions import FocusResponse, SessionBuildRequest, SessionBuildResponse
from app.schemas.tasks import task_to_read
from app.services import campaigns as campaign_service
from app.services import scheduling, settings_service
from app.services import zones as zone_service

router = APIRouter(prefix="/api", tags=["sessions"])


@router.get("/focus", response_model=FocusResponse)
def daily_focus(
    effort: str | None = None,
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> FocusResponse:
    """The calm home screen (SPEC §6): top 1–3 tasks by priority. The
    count comes from the daily_focus_count setting."""
    limit = int(settings_service.get_setting(db, current_user.id, "daily_focus_count"))
    effort = effort if effort in ("quick", "deep") else None
    tasks = scheduling.daily_focus(
        db, limit=limit, for_user_id=current_user.id, effort=effort
    )
    total = db.scalar(select(func.count(Task.id)).where(Task.is_active.is_(True))) or 0
    return FocusResponse(
        tasks=[task_to_read(t) for t in tasks],
        total_active_tasks=total,
    )


@router.post("/sessions/build", response_model=SessionBuildResponse)
def build_session(
    payload: SessionBuildRequest,
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> SessionBuildResponse:
    """Build a focus session (SPEC §5): "I have X minutes" greedy fill,
    a room, and — Phase 3 — guest/Chaos mode, "this week's zone", or a
    campaign's daily slice. The frontend presents the result one task at
    a time — never as a list."""
    if payload.campaign_id is not None:
        campaign = db.get(Campaign, payload.campaign_id)
        if campaign is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Campaign not found")
        today = zone_service.local_today(db, current_user.id)
        tasks = campaign_service.today_slice(db, campaign, today)
    else:
        tasks = scheduling.build_session(
            db,
            minutes=payload.minutes,
            for_user_id=current_user.id,
            room_id=payload.room_id,
            effort=payload.effort,
            zone_id=payload.zone_id,
            guest_only=payload.guest,
        )
    return SessionBuildResponse(
        tasks=[task_to_read(t) for t in tasks],
        total_minutes=sum(t.estimated_minutes for t in tasks),
    )

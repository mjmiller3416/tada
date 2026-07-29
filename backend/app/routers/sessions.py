from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.badge import Badge, UserBadge
from app.models.campaign import Campaign
from app.models.reminder import Reminder
from app.models.task import Task
from app.models.user import User
from app.routers.auth import require_owner
from app.schemas.badges import badge_to_read
from app.schemas.sessions import (
    FocusResponse,
    SessionBuildRequest,
    SessionBuildResponse,
    SessionCompleteRequest,
    SessionCompleteResponse,
    SessionTimerRead,
    SessionTimerRequest,
)
from app.schemas.tasks import task_to_read
from app.services import badges as badge_service
from app.services import campaigns as campaign_service
from app.services import reminder_service, scheduling, settings_service
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
            exclude_ids=set(payload.exclude_task_ids) or None,
        )
    return SessionBuildResponse(
        tasks=[task_to_read(t) for t in tasks],
        total_minutes=sum(t.estimated_minutes for t in tasks),
    )


@router.post("/sessions/complete", response_model=SessionCompleteResponse)
def complete_session(
    payload: SessionCompleteRequest,
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> SessionCompleteResponse:
    """The session-complete badge check (SPEC §5: "session-complete
    celebration + badge check"). Returns everything newly earned since
    the session started — including badges picked up mid-session on
    individual completions — so the celebration can show them."""
    badge_service.evaluate_session_complete(db, current_user, payload.tasks_done)
    db.commit()

    query = (
        select(UserBadge)
        .join(Badge)
        .where(UserBadge.user_id == current_user.id)
        .order_by(Badge.sort_order)
    )
    if payload.started_at is not None:
        query = query.where(UserBadge.earned_at >= payload.started_at)
    else:
        # No session start supplied — only what this very call awarded
        # would be new, and we can't tell that apart afterwards; return
        # nothing rather than re-celebrating old badges.
        return SessionCompleteResponse(new_badges=[])

    earned = db.scalars(query).all()
    return SessionCompleteResponse(
        new_badges=[badge_to_read(ub.badge, ub.earned_at) for ub in earned]
    )


def _get_timer(db: Session, timer_id: int, user: User) -> Reminder:
    reminder = db.get(Reminder, timer_id)
    if (
        reminder is None
        or reminder.user_id != user.id
        or not reminder_service.is_session_timer(reminder)
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Timer not found")
    return reminder


@router.post("/sessions/timer", response_model=SessionTimerRead)
def start_timer(
    payload: SessionTimerRequest,
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> SessionTimerRead:
    """Opt-in session timer (Phase 5), routed through the Reminder + cron
    plumbing so the alert survives a sleeping screen and a pocketed
    phone. It notifies; it never auto-ends the session."""
    reminder = reminder_service.start_session_timer(db, current_user, payload.minutes)
    db.commit()
    return SessionTimerRead(id=reminder.id, fires_at=reminder.scheduled_for)


@router.post("/sessions/timer/{timer_id}/extend", response_model=SessionTimerRead)
def extend_timer(
    timer_id: int,
    payload: SessionTimerRequest,
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> SessionTimerRead:
    """Add minutes to a running (or just-fired) timer. The frontend pairs
    this with a /sessions/build top-up so added time always comes with
    something to do."""
    reminder = _get_timer(db, timer_id, current_user)
    reminder_service.extend_session_timer(db, reminder, payload.minutes)
    db.commit()
    return SessionTimerRead(id=reminder.id, fires_at=reminder.scheduled_for)


@router.delete("/sessions/timer/{timer_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_timer(
    timer_id: int,
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> None:
    """Ending a session early quietly takes the pending alert with it."""
    reminder = _get_timer(db, timer_id, current_user)
    reminder.active = False
    db.commit()
